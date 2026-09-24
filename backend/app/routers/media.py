"""
Media router — single WebP avatar upload via Supabase Storage signed URLs.

POST /v1/media/upload/request   → get signed Supabase upload URL (60s)
POST /v1/media/upload/confirm   → verify upload landed, store cdn_url in DB
GET  /v1/media/status/{media_id} → poll processing status

Single-image policy: each user has exactly one avatar at
    {user_id}/avatar.webp in the 'avatars' Supabase bucket.
Voice notes: REMOVED from product scope.
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.services.media_processor import (
    generate_supabase_upload_signed_url,
    verify_avatar_uploaded,
    avatar_public_url,
)

router = APIRouter(prefix="/v1/media", tags=["media"])

# Only photos accepted — voice deprecated
_ALLOWED_PHOTO_CT = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB (client compresses to ~10KB WebP before upload)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UploadRequestBody(BaseModel):
    media_type: Literal["photo"] = "photo"
    content_type: str = Field(..., max_length=64)
    file_size_bytes: int = Field(..., ge=1, le=_MAX_PHOTO_BYTES)


class UploadRequestResponse(BaseModel):
    media_id: uuid.UUID
    signed_url: str
    path: str
    cdn_url: str
    expires_in_seconds: int = 300


class ConfirmUploadBody(BaseModel):
    media_id: uuid.UUID


class MediaStatusResponse(BaseModel):
    media_id: uuid.UUID
    status: str  # "pending" | "approved"
    cdn_url: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /v1/media/upload/request
# ---------------------------------------------------------------------------

@router.post(
    "/upload/request",
    response_model=UploadRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a signed Supabase Storage upload URL for avatar WebP",
)
async def request_upload(
    body: UploadRequestBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> UploadRequestResponse:
    """
    Returns a Supabase signed upload URL for the user's single avatar slot.
    Client resizes/compresses to WebP (480×600, ≤15KB) before uploading.
    Uploading overwrites any existing avatar (single-image policy).
    """
    await sliding_window_rate_limit(
        f"ratelimit:media:upload:{current_user['user_id']}", 10, 60, redis
    )

    if body.content_type not in _ALLOWED_PHOTO_CT:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {body.content_type}")

    user_id = current_user["user_id"]

    # Create DB record for the upload intent
    media_id = uuid.uuid4()
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_media (id, user_id, media_type, status, s3_key, position)
            VALUES ($1, $2, 'photo', 'pending', $3, 1)
            ON CONFLICT (user_id, media_type, position) DO UPDATE
                SET id = $1, status = 'pending', s3_key = $3, cdn_url = NULL, is_processed = FALSE, created_at = NOW()
            """,
            media_id,
            uuid.UUID(str(user_id)),
            f"{user_id}/avatar.webp",
        )

    # Generate Supabase signed upload URL
    res = await generate_supabase_upload_signed_url(user_id)
    version_token = str(media_id).replace("-", "")[:8]
    versioned_cdn_url = avatar_public_url(user_id, version=version_token)

    return UploadRequestResponse(
        media_id=media_id,
        signed_url=res["signed_url"],
        path=res["path"],
        cdn_url=versioned_cdn_url,
        expires_in_seconds=300,
    )


# ---------------------------------------------------------------------------
# POST /v1/media/upload/confirm
# ---------------------------------------------------------------------------

@router.post(
    "/upload/confirm",
    status_code=status.HTTP_200_OK,
    summary="Confirm client upload completed; verify object in Supabase Storage",
)
async def confirm_upload(
    body: ConfirmUploadBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
):
    await sliding_window_rate_limit(
        f"ratelimit:media:confirm:{current_user['user_id']}", 10, 60, redis
    )

    user_id = current_user["user_id"]

    # Verify the object actually landed in Supabase
    uploaded = await verify_avatar_uploaded(user_id)
    if not uploaded:
        raise HTTPException(
            status_code=422,
            detail="Avatar not found in storage. Ensure upload completed before calling confirm.",
        )

    version_token = str(body.media_id).replace("-", "")[:8]
    cdn_url = avatar_public_url(user_id, version=version_token)

    # Store CDN URL and retain status='pending' until moderation completes
    async with db.acquire() as conn:
        res = await conn.execute(
            """
            UPDATE user_media
               SET status = 'pending', cdn_url = $1, is_processed = TRUE
             WHERE id = $2 AND user_id = $3
            """,
            cdn_url,
            body.media_id,
            uuid.UUID(str(user_id)),
        )
        if res == "UPDATE 0":
            raise HTTPException(
                status_code=404,
                detail="Upload intent not found or expired. Request a new upload URL.",
            )

    # Invalidate cached profile and feed
    try:
        if redis and hasattr(redis, "delete"):
            await redis.delete(f"profile:{user_id}", f"feed:cache:{user_id}")
    except Exception:
        pass

    # Dispatch automated vision moderation in background supervisor
    from app.core.background_tasks import enqueue_task
    from app.services.moderation import run_photo_moderation

    enqueue_task(
        run_photo_moderation(body.media_id, uuid.UUID(str(user_id)), pool=db),
        name=f"moderate_photo_{body.media_id}",
    )

    return {"success": True, "status": "pending", "media_id": body.media_id, "cdn_url": cdn_url}


# ---------------------------------------------------------------------------
# GET /v1/media/status/{media_id}
# ---------------------------------------------------------------------------

@router.get(
    "/status/{media_id}",
    response_model=MediaStatusResponse,
    summary="Poll avatar upload status",
)
async def get_media_status(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
):
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, cdn_url FROM user_media WHERE id = $1 AND user_id = $2",
            media_id,
            uuid.UUID(str(current_user["user_id"])),
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Media record not found")

    return MediaStatusResponse(
        media_id=row["id"],
        status=row["status"],
        cdn_url=row["cdn_url"],
    )


# ---------------------------------------------------------------------------
# DELETE /v1/media/{media_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{media_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a photo",
)
async def delete_media(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    user_id = current_user["user_id"]
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, s3_key FROM user_media WHERE id = $1 AND user_id = $2",
            media_id,
            uuid.UUID(str(user_id)),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

        from app.services.media_processor import delete_user_avatar
        await delete_user_avatar(user_id)

        await conn.execute(
            "DELETE FROM user_media WHERE id = $1 AND user_id = $2",
            media_id,
            uuid.UUID(str(user_id)),
        )
        await conn.execute(
            "UPDATE users SET avatar_url = NULL, updated_at = NOW() WHERE id = $1",
            uuid.UUID(str(user_id)),
        )
    return {"success": True}


# ---------------------------------------------------------------------------
# PATCH /v1/media/reorder
# ---------------------------------------------------------------------------

from app.models.schemas.user import ReorderMediaBody, MediaPositionItem

ReorderMediaItem = MediaPositionItem


@router.patch(
    "/reorder",
    status_code=status.HTTP_200_OK,
    summary="Reorder photos",
)
async def reorder_media(
    body: ReorderMediaBody,
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    user_id = current_user["user_id"]
    async with db.acquire() as conn:
        for item in body.positions:
            await conn.execute(
                "UPDATE user_media SET position = $1 WHERE id = $2 AND user_id = $3 AND media_type = 'photo'",
                item.position,
                item.media_id,
                uuid.UUID(str(user_id)),
            )
    return {"success": True}
