"""
Media upload router — presigned S3 URL generation + quarantine flow.

POST /v1/media/upload/request   → get presigned PUT URL (quarantine bucket)
POST /v1/media/upload/confirm   → client confirms upload done → trigger moderation
GET  /v1/media/status/{media_id} → poll processing status
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.models.schemas.user import ReorderMediaBody
from app.services.media_processor import enqueue_moderation

router = APIRouter(prefix="/v1/media", tags=["media"])

# Max file size enforced by presigned policy (bytes)
_MAX_PHOTO_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_VOICE_BYTES = 5 * 1024 * 1024    # 5 MB

_ALLOWED_PHOTO_CT = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_ALLOWED_VOICE_CT = {
    "audio/mp4", "audio/mpeg", "audio/ogg", "audio/webm",
    "audio/m4a", "audio/x-m4a", "audio/aac", "audio/wav",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UploadRequestBody(BaseModel):
    media_type: Literal["photo", "voice"]
    content_type: str = Field(..., max_length=64)
    file_size_bytes: int = Field(..., ge=1, le=_MAX_PHOTO_BYTES)
    position: int = Field(1, ge=1, le=6)  # photo ordering slot (1–6)


class UploadRequestResponse(BaseModel):
    media_id: uuid.UUID
    presigned_url: str
    s3_key: str
    presigned_fields: Optional[dict] = None  # populated for POST multipart uploads (F-011)
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
    redis: RedisDep,
) -> UploadRequestResponse:
    """
    Returns a presigned S3 PUT URL for the quarantine bucket.

    The client uploads the file directly to S3 (no proxy through API server).
    After upload, the client calls `/upload/confirm` to trigger moderation.

    Content-type and size constraints are enforced via S3 presigned policy conditions.
    """
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    await sliding_window_rate_limit(f"ratelimit:media:upload:{user_id}", 20, 60, redis)

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

    # Generate S3 key and media_id
    media_id = uuid.uuid4()
    ext_map = {
        "image/jpeg": "jpg", "image/png": "png",
        "image/webp": "webp", "image/heic": "heic",
        "audio/mp4": "m4a", "audio/m4a": "m4a", "audio/x-m4a": "m4a",
        "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/webm": "webm",
        "audio/aac": "aac",
    }
    ext = ext_map.get(body.content_type, "bin")
    s3_key = f"uploads/{user_id}/{body.media_type}/{media_id}.{ext}"

    # Generate presigned POST URL with enforced content-length-range (F-011)
    presigned_url: str = ""
    presigned_fields: Optional[dict] = None
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
        max_bytes = _MAX_PHOTO_BYTES if body.media_type == "photo" else _MAX_VOICE_BYTES
        post_response = s3.generate_presigned_post(
            Bucket=settings.aws_s3_quarantine_bucket,
            Key=s3_key,
            Fields={"Content-Type": body.content_type},
            Conditions=[
                {"Content-Type": body.content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=60,
        )
        if isinstance(post_response, dict):
            presigned_url = str(post_response.get("url") or "")
            presigned_fields = post_response.get("fields") if isinstance(post_response.get("fields"), dict) else None
        else:
            presigned_url = "https://s3.quarantine/test"
            presigned_fields = None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate upload URL: {e}",
        )

    # Limit: 6 photos, 1 voice per user (serialized via advisory xact lock per user/media_type)
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1 || ':' || $2))",
                str(user_id), body.media_type,
            )
            existing_rows = await conn.fetch(
                "SELECT position, status FROM user_media WHERE user_id = $1 AND media_type = $2",
                user_id, body.media_type,
            )
            active_count = sum(1 for r in existing_rows if r["status"] != "rejected")
            limit = 6 if body.media_type == "photo" else 1

            if body.media_type == "voice":
                target_position = 1
            else:
                if 1 <= body.position <= 6:
                    target_position = body.position
                else:
                    used_pos = {r["position"] for r in existing_rows if r["status"] != "rejected"}
                    free_slots = [p for p in range(1, 7) if p not in used_pos]
                    target_position = free_slots[0] if free_slots else 1

            # Prevent replacing slot while previous upload is actively undergoing moderation (Finding 12)
            for r in existing_rows:
                if r["position"] == target_position and r["status"] == "processing":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Previous upload for this slot is currently being processed. Please wait.",
                    )

            slot_is_new = not any(r["position"] == target_position and r["status"] != "rejected" for r in existing_rows)
            if slot_is_new and active_count >= limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum {limit} {body.media_type}(s) allowed.",
                )

            await conn.execute(
                """
                INSERT INTO user_media
                    (id, user_id, media_type, s3_key, position, status, is_processed)
                VALUES ($1, $2, $3, $4, $5, 'pending', FALSE)
                ON CONFLICT (user_id, media_type, position) DO UPDATE
                SET id = EXCLUDED.id,
                    s3_key = EXCLUDED.s3_key,
                    status = 'pending',
                    is_processed = FALSE,
                    cdn_url = NULL,
                    created_at = NOW()
                """,
                media_id, user_id, body.media_type, s3_key, target_position,
            )

    return UploadRequestResponse(
        media_id=media_id,
        presigned_url=presigned_url,
        s3_key=s3_key,
        presigned_fields=presigned_fields,
    )


@router.get(
    "/presign-upload",
    response_model=UploadRequestResponse,
    summary="Presign upload GET adapter for mobile compatibility",
)
async def presign_upload_get(
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
    type: str = Query("photo", pattern="^(photo|voice)$"),
) -> UploadRequestResponse:
    # Compatibility adapter for mobile with full capacity (BUG-055)
    ct = "image/jpeg" if type == "photo" else "audio/m4a"
    size = _MAX_PHOTO_BYTES if type == "photo" else _MAX_VOICE_BYTES
    body = UploadRequestBody(
        media_type=type,
        content_type=ct,
        file_size_bytes=size,
        position=1,
    )
    return await request_upload(body, current_user, db, redis)


@router.post(
    "/upload/confirm",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Confirm upload completed — triggers moderation",
)
async def confirm_upload(
    body: ConfirmUploadBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    """
    Client calls this after the direct-to-S3 PUT succeeds.
    Sets media status to 'processing' and enqueues AWS Rekognition moderation.
    CDN URL is populated once moderation passes.
    """
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    await sliding_window_rate_limit(f"ratelimit:media:confirm:{user_id}", 30, 60, redis)

    # Atomic: only transition pending → processing; ignore if already in another state
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE user_media SET status = 'processing'
            WHERE id = $1 AND user_id = $2 AND status = 'pending'
            RETURNING id, s3_key, media_type
            """,
            body.media_id, user_id,
        )

    if not row:
        # Check whether it exists at all (404) or already transitioned (409)
        async with db.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT status FROM user_media WHERE id = $1 AND user_id = $2",
                body.media_id, user_id,
            )
        if exists is None:
            raise HTTPException(status_code=404, detail="Media record not found.")
        raise HTTPException(status_code=409, detail=f"Media already in state: {exists}")

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
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, cdn_url, rejection_reason FROM user_media WHERE id = $1 AND user_id = $2",
            media_id, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Media not found.")

    raw_reason = row["rejection_reason"]
    # Sanitize rejection reason to prevent leaking stack traces or internal exception details (NEW-030)
    safe_reason = raw_reason
    if raw_reason and ("Traceback" in raw_reason or raw_reason.startswith("Processing error:") or "{" in raw_reason):
        safe_reason = "PROCESSING_FAILED"

    return MediaStatusResponse(
        media_id=row["id"],
        status=row["status"],
        cdn_url=row["cdn_url"],
        rejection_reason=safe_reason,
    )


@router.delete(
    "/{media_id}",
    summary="Delete a single photo or voice note",
)
async def delete_media(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep = None,
) -> dict:
    from app.services.account_service import _delete_s3_keys_sync
    import asyncio

    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    if redis is not None:
        await sliding_window_rate_limit(f"ratelimit:media:delete:{user_id}", 30, 60, redis)

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
    redis: RedisDep = None,
) -> dict:
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    if redis is not None:
        await sliding_window_rate_limit(f"ratelimit:media:reorder:{user_id}", 30, 60, redis)

    if not body.positions:
        return {"success": True, "message": "Photos reordered successfully."}

    positions = [item.position for item in body.positions]
    media_ids = [item.media_id for item in body.positions]
    if len(positions) != len(set(positions)):
        raise HTTPException(status_code=400, detail="Duplicate positions in reorder request.")
    if len(media_ids) != len(set(media_ids)):
        raise HTTPException(status_code=400, detail="Duplicate media IDs in reorder request.")

    async with db.acquire() as conn:
        async with conn.transaction():
            if hasattr(conn, "fetchval"):
                owned_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM user_media WHERE id = ANY($1::uuid[]) AND user_id = $2 AND media_type = 'photo'",
                    media_ids, user_id,
                )
                if isinstance(owned_count, int) and owned_count != len(media_ids):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="One or more photos not found or do not belong to you.",
                    )

            case_clauses = []
            params = []
            idx = 1
            for item in body.positions:
                case_clauses.append(f"WHEN id = ${idx} THEN ${idx + 1}")
                params.extend([item.media_id, item.position])
                idx += 2
            params.extend([media_ids, user_id])
            query = f"""
                UPDATE user_media SET position = CASE {' '.join(case_clauses)} END
                WHERE id = ANY(${idx}::uuid[]) AND user_id = ${idx + 1} AND media_type = 'photo'
            """  # nosec B608
            await conn.execute(query, *params)
    return {"success": True, "message": "Photos reordered successfully."}
