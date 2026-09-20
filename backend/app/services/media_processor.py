"""
Media processor service — Supabase Storage single-avatar pipeline.

Policy: ONE avatar per user. Path always: {user_id}/avatar.webp
Pipeline:
  1. Generate signed upload URL (300s expiry) → client uploads directly
  2. After client confirms: verify object exists via HEAD request
  3. CDN URL stored in user_media.cdn_url; s3_key repurposed for storage path

Voice notes: DEPRECATED per product scope.
boto3/AWS: REMOVED. Uses supabase-py + httpx.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase Storage client (lazy singleton)
# ---------------------------------------------------------------------------

_supabase_client = None


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Supabase configuration missing: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required.")
        from supabase import create_client
        _supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_client


get_supabase_client = _get_supabase


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def avatar_storage_path(user_id: str | uuid.UUID) -> str:
    """Canonical storage path. Single-image policy: always same path → overwrites on re-upload."""
    return f"{user_id}/avatar.webp"


def avatar_public_url(user_id: str | uuid.UUID) -> str:
    base = (settings.supabase_url or "https://supabase.local").rstrip("/")
    bucket = getattr(settings, "supabase_storage_bucket", "avatars")
    return f"{base}/storage/v1/object/public/{bucket}/{avatar_storage_path(user_id)}"


# ---------------------------------------------------------------------------
# Signed upload URL (replaces S3 presigned PUT)
# ---------------------------------------------------------------------------

async def generate_supabase_upload_signed_url(user_id: str | uuid.UUID) -> dict:
    """
    Returns a signed upload URL valid 300 seconds.
    Client uploads WebP directly; no proxy through API server.
    """
    bucket = settings.supabase_storage_bucket
    path = avatar_storage_path(user_id)
    client = _get_supabase()
    res = await asyncio.to_thread(client.storage.from_(bucket).create_signed_upload_url, path)
    return {
        "signed_url": res["signedURL"],
        "token": res.get("token", ""),
        "path": path,
        "cdn_url": avatar_public_url(user_id),
    }


# ---------------------------------------------------------------------------
# Verify upload exists (called after client confirms upload)
# ---------------------------------------------------------------------------

async def verify_avatar_uploaded(user_id: str | uuid.UUID) -> bool:
    """HEAD request to confirm object landed in Supabase Storage with authenticated SDK fallback."""
    url = avatar_public_url(user_id)
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.head(url)
        if r.status_code == 200:
            return True
    except Exception as exc:
        logger.warning("Avatar HEAD check failed for %s: %s", user_id, exc)

    # Authenticated Supabase SDK fallback (e.g. if bucket has RLS or CDN has propagation delay)
    try:
        client = _get_supabase()
        items = await asyncio.to_thread(client.storage.from_(settings.supabase_storage_bucket).list, str(user_id))
        for item in items:
            if item.get("name") == "avatar.webp":
                return True
    except Exception as exc:
        logger.warning("Avatar SDK check failed for %s: %s", user_id, exc)

    return False


# ---------------------------------------------------------------------------
# Delete avatar (account deletion / admin purge)
# ---------------------------------------------------------------------------

async def delete_user_avatar(user_id: str | uuid.UUID) -> bool:
    """Remove avatar from Supabase Storage avatars bucket."""
    try:
        client = _get_supabase()
        await asyncio.to_thread(
            client.storage.from_(settings.supabase_storage_bucket).remove,
            [avatar_storage_path(user_id)],
        )
        return True
    except Exception as exc:
        logger.error("Failed to delete avatar for user %s: %s", user_id, exc)
        return False


# ---------------------------------------------------------------------------
# Enqueue moderation (no-op — Supabase RLS + client-side WebP compression
# replaces Rekognition pipeline. Retained as stub for future integration.)
# ---------------------------------------------------------------------------

async def enqueue_moderation(media_id: uuid.UUID, *_args, **_kwargs) -> None:
    """Stub: moderation handled by Supabase Storage RLS policies."""
    logger.debug("enqueue_moderation called for media_id=%s (no-op in Supabase mode)", media_id)


# ---------------------------------------------------------------------------
# Image payload validator (no server-side resize/transcode — client sends WebP)
# ---------------------------------------------------------------------------

import struct

# Recognised magic bytes: RIFF....WEBP, JPEG (FF D8 FF), PNG (89 50 4E 47)
_MAGIC_WEBP = (b"RIFF", b"WEBP")
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_PNG  = b"\x89PNG"
_MAX_BYTES   = 10 * 1024 * 1024  # 10 MB hard cap


def process_and_sanitize_image(data: bytes, max_dimension: int = 1920) -> bytes:
    """
    Lightweight server-side guard: validates magic bytes and enforces size cap.
    No heavy image decode or resize — that happens client-side (WebP/480px) to protect 512MB RAM.
    Raises ValueError for invalid or oversized payloads.
    Returns the original bytes unchanged.
    """
    if not data:
        raise ValueError("Corrupted image header: empty payload")
    if len(data) > _MAX_BYTES:
        raise ValueError(f"Image exceeds {_MAX_BYTES // (1024*1024)} MB limit")
    # Validate magic bytes — accept WebP, JPEG, PNG
    if data[:4] == b"RIFF":
        if len(data) < 12 or data[8:12] != b"WEBP":
            raise ValueError("Corrupted image header: Invalid WebP header")
        expected_size = struct.unpack("<I", data[4:8])[0] + 8
        if len(data) < expected_size:
            raise ValueError("Corrupted image header: Truncated WebP payload")
        return data

    if data[:3] == _MAGIC_JPEG or data[:4] == _MAGIC_PNG:
        return data

    raise ValueError("Corrupted image header: Unsupported image format (must be WebP, JPEG, or PNG)")
