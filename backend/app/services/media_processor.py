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
from urllib.parse import quote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_AVATAR_BYTES = 2 * 1024 * 1024


class AvatarTooLargeError(ValueError):
    """Raised when stored avatar bytes exceed the application upload limit."""

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


def avatar_public_url(user_id: str | uuid.UUID, version: Optional[str] = None) -> str:
    base = (settings.supabase_url or "https://supabase.local").rstrip("/")
    bucket = getattr(settings, "supabase_storage_bucket", "avatars")
    url = f"{base}/storage/v1/object/public/{bucket}/{avatar_storage_path(user_id)}"
    if version:
        url = f"{url}?v={version}"
    return url


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
    """Verify existence and size using uncached authenticated Storage metadata."""
    # Do not use public CDN HEAD as the authoritative size: its cached Content-Length can
    # describe an earlier object at this overwrite-in-place avatar path.
    try:
        client = _get_supabase()
        items = await asyncio.to_thread(client.storage.from_(settings.supabase_storage_bucket).list, str(user_id))
        for item in items:
            if item.get("name") == "avatar.webp":
                metadata = item.get("metadata") or {}
                raw_size = next(
                    (value for value in (
                        metadata.get("size"),
                        metadata.get("contentLength"),
                        metadata.get("content_length"),
                        item.get("size"),
                        item.get("contentLength"),
                    ) if value is not None),
                    None,
                )
                try:
                    size = int(raw_size) if raw_size is not None else None
                except (TypeError, ValueError):
                    size = None
                if size is None:
                    logger.warning("Avatar size metadata unavailable for %s; rejecting unverified upload", user_id)
                    return False
                if size > MAX_AVATAR_BYTES:
                    raise AvatarTooLargeError("Avatar exceeds the 2 MB upload limit")
                return size > 0
    except AvatarTooLargeError:
        raise
    except Exception as exc:
        logger.warning("Avatar SDK check failed for %s: %s", user_id, exc)

    return False


async def _read_bounded_image_response(
    http: httpx.AsyncClient,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
) -> Optional[bytes]:
    """Stream an image response and retain no more than the avatar byte limit."""
    request_headers = {"Accept-Encoding": "identity"}
    if headers:
        request_headers.update(headers)
    async with http.stream("GET", url, headers=request_headers) as response:
        if response.status_code != 200:
            return None
        if response.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
            raise ValueError("Encoded avatar response is not accepted")

        raw_size = response.headers.get("content-length")
        try:
            declared_size = int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError):
            declared_size = None
        if declared_size is not None and declared_size > MAX_AVATAR_BYTES:
            raise AvatarTooLargeError("Avatar exceeds the 2 MB upload limit")

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
            total += len(chunk)
            if total > MAX_AVATAR_BYTES:
                raise AvatarTooLargeError("Avatar exceeds the 2 MB upload limit")
            chunks.append(chunk)
        return b"".join(chunks)


async def download_avatar_bytes(
    user_id: str | uuid.UUID,
    http: httpx.AsyncClient,
    *,
    cdn_url: Optional[str] = None,
) -> Optional[bytes]:
    """Download an avatar through public CDN or authenticated Storage, with a hard byte cap."""
    public_url = cdn_url or avatar_public_url(user_id)
    try:
        image = await _read_bounded_image_response(http, public_url)
        if image:
            return image
    except AvatarTooLargeError:
        raise
    except Exception as exc:
        logger.warning("Avatar CDN download failed for %s: %s", public_url, exc)

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None

    bucket = quote(settings.supabase_storage_bucket, safe="")
    path = quote(avatar_storage_path(user_id), safe="/")
    storage_url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{path}"
    service_key = settings.supabase_service_role_key
    try:
        return await _read_bounded_image_response(
            http,
            storage_url,
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        )
    except AvatarTooLargeError:
        raise
    except Exception as exc:
        logger.error("Authenticated Supabase download failed for %s: %s", user_id, exc)
        return None


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
_MAX_BYTES   = 2 * 1024 * 1024  # 2 MB hard cap


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
