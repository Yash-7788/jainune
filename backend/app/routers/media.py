"""
Media upload router — presigned S3 URL generation + quarantine flow.

POST /v1/media/upload/request   → get presigned PUT URL (quarantine bucket)
POST /v1/media/upload/confirm   → client confirms upload done → trigger moderation
GET  /v1/media/status/{media_id} → poll processing status
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.dependencies import CurrentUser, DBDep
from app.models.schemas.user import ReorderMediaBody
from app.services.media_processor import enqueue_moderation

router = APIRouter(prefix="/v1/media", tags=["media"])

# Max file size enforced by presigned policy (bytes)
_MAX_PHOTO_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_VOICE_BYTES = 5 * 1024 * 1024    # 5 MB

_ALLOWED_PHOTO_CT = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_ALLOWED_VOICE_CT = {"audio/mp4", "audio/mpeg", "audio/ogg", "audio/webm"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UploadRequestBody(BaseModel):
    media_type: Literal["photo", "voice"]
    content_type: str
    file_size_bytes: int
    position: int = 1  # photo ordering slot (1–6)


class UploadRequestResponse(BaseModel):
    media_id: uuid.UUID
    presigned_url: str
    s3_key: str
    expires_in_seconds: int = 60


class ConfirmUploadBody(BaseModel):
    media_id: uuid.UUID


class MediaStatusResponse(BaseModel):
    media_id: uuid.UUID
    status: str        # "pending" | "processing" | "approved" | "rejected"
    cdn_url: Optional[str] = None
    rejection_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/upload/request",
    response_model=UploadRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a presigned S3 upload URL",
)
async def request_upload(
    body: UploadRequestBody,
    current_user: CurrentUser,
    db: DBDep,
) -> UploadRequestResponse:
    """
    Returns a presigned S3 PUT URL for the quarantine bucket.

    The client uploads the file directly to S3 (no proxy through API server).
    After upload, the client calls `/upload/confirm` to trigger moderation.

    Content-type and size constraints are enforced via S3 presigned policy conditions.
    """
    user_id = uuid.UUID(str(current_user["id"]))

    # Validate content type
    if body.media_type == "photo":
        if body.content_type not in _ALLOWED_PHOTO_CT:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported photo content type. Allowed: {_ALLOWED_PHOTO_CT}",
            )
        if body.file_size_bytes > _MAX_PHOTO_BYTES:
            raise HTTPException(status_code=400, detail="Photo must be under 10 MB.")
    else:
        if body.content_type not in _ALLOWED_VOICE_CT:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported voice content type. Allowed: {_ALLOWED_VOICE_CT}",
            )
        if body.file_size_bytes > _MAX_VOICE_BYTES:
            raise HTTPException(status_code=400, detail="Voice clip must be under 5 MB.")

    # Limit: 6 photos, 1 voice per user
    async with db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_media WHERE user_id = $1 AND media_type = $2 AND status != 'rejected'",
            user_id, body.media_type,
        )
    limit = 6 if body.media_type == "photo" else 1
    if count >= limit:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {limit} {body.media_type}(s) allowed.",
        )

    # Generate S3 key
    media_id = uuid.uuid4()
    ext_map = {
        "image/jpeg": "jpg", "image/png": "png",
        "image/webp": "webp", "image/heic": "heic",
        "audio/mp4": "m4a", "audio/mpeg": "mp3",
        "audio/ogg": "ogg", "audio/webm": "webm",
    }
    ext = ext_map.get(body.content_type, "bin")
    s3_key = f"uploads/{user_id}/{body.media_type}/{media_id}.{ext}"

    # Generate presigned PUT URL
    try:
        import boto3
        from botocore.config import Config
        s3 = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        presigned_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.aws_s3_quarantine_bucket,
                "Key": s3_key,
                "ContentType": body.content_type,
                "ContentLength": body.file_size_bytes,
            },
            ExpiresIn=60,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate upload URL: {e}",
        )

    # Create pending DB record
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_media
                (id, user_id, media_type, s3_key, position, status, is_processed)
            VALUES ($1, $2, $3, $4, $5, 'pending', FALSE)
            """,
            media_id, user_id, body.media_type, s3_key, body.position,
        )

    return UploadRequestResponse(
        media_id=media_id,
        presigned_url=presigned_url,
        s3_key=s3_key,
    )


@router.post(
    "/upload/confirm",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Confirm upload completed — triggers moderation",
)
async def confirm_upload(
    body: ConfirmUploadBody,
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    """
    Client calls this after the direct-to-S3 PUT succeeds.
    Sets media status to 'processing' and enqueues AWS Rekognition moderation.
    CDN URL is populated once moderation passes.
    """
    user_id = uuid.UUID(str(current_user["id"]))

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, s3_key, media_type, status FROM user_media WHERE id = $1 AND user_id = $2",
            body.media_id, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Media record not found.")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Media already in state: {row['status']}")

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE user_media SET status = 'processing' WHERE id = $1",
            body.media_id,
        )

    # Enqueue moderation job (non-blocking)
    await enqueue_moderation(
        media_id=body.media_id,
        s3_key=row["s3_key"],
        media_type=row["media_type"],
        user_id=user_id,
    )

    return {"media_id": str(body.media_id), "status": "processing"}


@router.get(
    "/status/{media_id}",
    response_model=MediaStatusResponse,
    summary="Poll media processing status",
)
async def get_media_status(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
) -> MediaStatusResponse:
    user_id = uuid.UUID(str(current_user["id"]))

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, cdn_url, rejection_reason FROM user_media WHERE id = $1 AND user_id = $2",
            media_id, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Media not found.")

    return MediaStatusResponse(
        media_id=row["id"],
        status=row["status"],
        cdn_url=row["cdn_url"],
        rejection_reason=row["rejection_reason"],
    )


@router.delete(
    "/{media_id}",
    summary="Delete a single photo or voice note",
)
async def delete_media(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    from app.services.account_service import _delete_s3_keys_sync
    import asyncio

    user_id = uuid.UUID(str(current_user["user_id"]))
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, s3_key, status FROM user_media WHERE id = $1 AND user_id = $2",
            media_id, user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Media item not found.")

        s3_key = row["s3_key"]
        if s3_key:
            try:
                await asyncio.to_thread(_delete_s3_keys_sync, [s3_key])
            except Exception:
                pass

        await conn.execute("DELETE FROM user_media WHERE id = $1 AND user_id = $2", media_id, user_id)

    return {"success": True, "message": "Media item deleted successfully."}


@router.patch(
    "/reorder",
    summary="Reorder user profile photos",
)
async def reorder_media(
    body: ReorderMediaBody,
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    user_id = uuid.UUID(str(current_user["user_id"]))
    async with db.acquire() as conn:
        async with conn.transaction():
            for item in body.positions:
                await conn.execute(
                    "UPDATE user_media SET position = $1 WHERE id = $2 AND user_id = $3",
                    item.position, item.media_id, user_id,
                )
    return {"success": True, "message": "Photos reordered successfully."}
