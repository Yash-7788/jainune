"""
Media processor service — AWS Rekognition moderation pipeline.

Called after a user confirms a direct-to-S3 upload.

Pipeline:
  1. Copy from quarantine bucket → temp processing path
  2. Submit to AWS Rekognition DetectModerationLabels
  3. If PASS → copy to production bucket, set CDN URL, mark approved
  4. If FAIL → mark rejected, store reason, delete from quarantine
  5. For voice: run Comprehend + Transcribe toxicity check instead

The `enqueue_moderation` function is the async entry point.
For production, this should be replaced with an SQS task dispatch;
for MVP, it runs inline as a fire-and-forget asyncio task.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Literal

try:
    import boto3
except ImportError:
    boto3 = None

from app.core.config import settings
from app.core.database import get_pool


# Rekognition confidence threshold — labels above this trigger rejection
_MODERATION_CONFIDENCE_THRESHOLD = 75.0

# Labels that result in immediate rejection
_BLOCKED_LABELS = {
    "Explicit Nudity",
    "Nudity",
    "Graphic Male Nudity",
    "Graphic Female Nudity",
    "Sexual Activity",
    "Illustrated Explicit Nudity",
    "Adult Toys",
    "Drugs",
    "Drug Products",
    "Drug Use",
    "Violence",
    "Graphic Violence Or Gore",
    "Hate Symbols",
    "Nazi Party",
    "White Supremacy",
    "Extremist",
}


_MAX_PHOTO_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_VOICE_BYTES = 5 * 1024 * 1024    # 5 MB


def _check_s3_size(s3_key: str, media_type: str) -> tuple[bool, str | None]:
    """Verify actual uploaded object size in S3 quarantine bucket."""
    if not boto3 or not settings.aws_access_key_id or settings.aws_access_key_id.startswith("mock"):
        return True, None
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    try:
        head = s3.head_object(Bucket=settings.aws_s3_quarantine_bucket, Key=s3_key)
        actual_size = head.get("ContentLength", 0)
        max_bytes = _MAX_PHOTO_BYTES if media_type == "photo" else _MAX_VOICE_BYTES
        if actual_size <= 0:
            return False, "Upload file is empty"
        if actual_size > max_bytes:
            return False, f"Upload size {actual_size} bytes exceeds maximum allowed limit of {max_bytes} bytes"
        return True, None
    except Exception as e:
        return False, f"Failed to verify upload object size: {e}"


async def enqueue_moderation(
    media_id: uuid.UUID,
    s3_key: str,
    media_type: Literal["photo", "voice"],
    user_id: uuid.UUID,
) -> None:
    """Fire-and-forget: runs moderation in a background asyncio task."""
    asyncio.create_task(
        _run_moderation(media_id, s3_key, media_type, user_id),
        name=f"moderate:{media_id}",
    )


async def _run_moderation(
    media_id: uuid.UUID,
    s3_key: str,
    media_type: Literal["photo", "voice"],
    user_id: uuid.UUID,
) -> None:
    """Executes the full moderation pipeline in a background task."""
    db = get_pool()
    try:
        # Check actual S3 object size against maximum limits (O-2)
        size_ok, size_reason = await asyncio.to_thread(_check_s3_size, s3_key, media_type)
        if not size_ok:
            async with db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE user_media
                    SET status = 'rejected',
                        rejection_reason = $1
                    WHERE id = $2
                    """,
                    size_reason, media_id,
                )
            await asyncio.to_thread(_delete_from_quarantine, s3_key)
            return

        if media_type == "photo":
            approved, reason = await asyncio.to_thread(
                _rekognition_check, s3_key
            )
        else:
            # Voice: basic pass for MVP — production should add Transcribe + Comprehend
            approved, reason = True, None

        if approved:
            # Copy quarantine → production
            prod_key = s3_key.replace("uploads/", "media/")
            if media_type == "photo":
                prod_key = prod_key.rsplit(".", 1)[0] + ".webp"
            base_cdn = settings.cdn_public_base_url.rstrip("/")
            cdn_url = f"{base_cdn}/{prod_key}"

            await asyncio.to_thread(_copy_to_production, s3_key, prod_key, media_type)

            async with db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE user_media
                    SET status = 'approved',
                        is_processed = TRUE,
                        cdn_url = $1,
                        s3_key = $2
                    WHERE id = $3
                    """,
                    cdn_url, prod_key, media_id,
                )
                # Activate user if onboarding completed and was waiting for media approval (BUG-038)
                if user_id:
                    await conn.execute(
                        """
                        UPDATE users
                        SET account_status = 'active', updated_at = NOW()
                        WHERE id = $1 AND onboarding_step = 22 AND account_status = 'pending_media'
                        """,
                        user_id,
                    )
            # Delete raw upload from quarantine bucket
            await asyncio.to_thread(_delete_from_quarantine, s3_key)
        else:
            async with db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE user_media
                    SET status = 'rejected',
                        rejection_reason = $1
                    WHERE id = $2
                    """,
                    reason, media_id,
                )
                # If no valid photos remain, downgrade user from active to pending_media (BUG-038)
                if user_id and media_type == "photo":
                    remaining = await conn.fetchval(
                        "SELECT COUNT(*) FROM user_media WHERE user_id = $1 AND media_type = 'photo' AND status IN ('approved', 'pending')",
                        user_id,
                    )
                    if not remaining:
                        await conn.execute(
                            "UPDATE users SET account_status = 'pending_media', updated_at = NOW() WHERE id = $1 AND account_status = 'active'",
                            user_id,
                        )
            # Delete from quarantine
            await asyncio.to_thread(_delete_from_quarantine, s3_key)

    except Exception as exc:
        # Mark as rejected on any unhandled error
        try:
            async with db.acquire() as conn:
                await conn.execute(
                    "UPDATE user_media SET status = 'rejected', rejection_reason = $1 WHERE id = $2",
                    f"Processing error: {exc}", media_id,
                )
        except Exception:
            pass


def _rekognition_check(s3_key: str) -> tuple[bool, str | None]:
    """
    Synchronous Rekognition call (run via asyncio.to_thread).
    Returns (approved: bool, rejection_reason: str | None).
    """
    if not boto3 or not settings.aws_access_key_id or settings.aws_access_key_id.startswith("mock"):
        return True, None
    client = boto3.client(
        "rekognition",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    response = client.detect_moderation_labels(
        Image={
            "S3Object": {
                "Bucket": settings.aws_s3_quarantine_bucket,
                "Name": s3_key,
            }
        },
        MinConfidence=_MODERATION_CONFIDENCE_THRESHOLD,
    )

    labels = response.get("ModerationLabels", [])
    for label in labels:
        name = label.get("Name", "")
        parent = label.get("ParentName", "")
        if name in _BLOCKED_LABELS or parent in _BLOCKED_LABELS:
            return False, f"Content policy violation: {name}"

    return True, None


def _validate_image_magic_bytes(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"mif1", b"msf1"):
            return True
    return False


def process_and_sanitize_image(raw_data: bytes) -> bytes:
    """
    Sanitizes raw photo upload before moving to production:
    1. Validates magic bytes (blocks masqueraded executables, HTML, ZIP bombs).
    2. Limits maximum decompression dimensions to prevent memory exhaustion (25 MP).
    3. Verifies file integrity against corrupt headers/streams.
    4. Strips 100% of EXIF, GPS coordinates, and device metadata.
    5. Re-encodes cleanly to standardized WebP.
    """
    import io
    from PIL import Image

    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass

    if not _validate_image_magic_bytes(raw_data):
        raise ValueError("Corrupted image header or unsupported file format.")

    # Guard against decompression bombs (max 25 million pixels)
    Image.MAX_IMAGE_PIXELS = 25_000_000

    try:
        # Pass 1: verify file integrity
        with Image.open(io.BytesIO(raw_data)) as img:
            img.verify()

        # Pass 2: decode, strip metadata, and re-encode to WebP
        with Image.open(io.BytesIO(raw_data)) as img:
            out_buf = io.BytesIO()
            rgb_img = img.convert("RGB")
            # Saving to WebP without exif keyword strips all EXIF/GPS tags
            rgb_img.save(out_buf, format="WEBP", quality=85)
            return out_buf.getvalue()
    except Image.DecompressionBombError as exc:
        raise ValueError(f"Decompression bomb detected: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Failed to process and sanitize image: {exc}") from exc


def _copy_to_production(quarantine_key: str, production_key: str, media_type: str = "photo") -> None:
    if not boto3 or not settings.aws_access_key_id or settings.aws_access_key_id.startswith("mock"):
        return
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    if media_type == "photo":
        try:
            # Download raw upload from quarantine
            obj = s3.get_object(Bucket=settings.aws_s3_quarantine_bucket, Key=quarantine_key)
            raw_data = obj["Body"].read()

            clean_bytes = process_and_sanitize_image(raw_data)

            clean_key = production_key.rsplit(".", 1)[0] + ".webp"
            s3.put_object(
                Bucket=settings.aws_s3_production_bucket,
                Key=clean_key,
                Body=clean_bytes,
                ContentType="image/webp",
            )
            return
        except Exception as exc:
            # Never fall back to copying raw unstripped photos with EXIF to production
            raise ValueError(f"Failed to strip EXIF/GPS metadata from photo: {exc}")

    s3.copy_object(
        CopySource={
            "Bucket": settings.aws_s3_quarantine_bucket,
            "Key": quarantine_key,
        },
        Bucket=settings.aws_s3_production_bucket,
        Key=production_key,
        MetadataDirective="REPLACE",  # Strip S3 user metadata
    )



def _delete_from_quarantine(s3_key: str) -> None:
    if not boto3 or not settings.aws_access_key_id or settings.aws_access_key_id.startswith("mock"):
        return
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    s3.delete_object(Bucket=settings.aws_s3_quarantine_bucket, Key=s3_key)
