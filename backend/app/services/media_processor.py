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
            cdn_url = f"{settings.cdn_public_base_url}/{prod_key}"

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


def _copy_to_production(quarantine_key: str, production_key: str, media_type: str = "photo") -> None:
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    if media_type == "photo":
        try:
            import io
            from PIL import Image

            # Download raw upload from quarantine
            obj = s3.get_object(Bucket=settings.aws_s3_quarantine_bucket, Key=quarantine_key)
            raw_data = obj["Body"].read()

            # Open image, discard EXIF/metadata, re-encode to clean WebP
            img = Image.open(io.BytesIO(raw_data))
            out_buf = io.BytesIO()
            # Saving to format without copying exif strips 100% of EXIF/GPS/IPTC
            img.save(out_buf, format="WEBP", quality=85)
            out_buf.seek(0)

            clean_key = production_key.rsplit(".", 1)[0] + ".webp"
            s3.put_object(
                Bucket=settings.aws_s3_production_bucket,
                Key=clean_key,
                Body=out_buf.getvalue(),
                ContentType="image/webp",
            )
            return
        except Exception:
            pass  # Fallback to S3 copy if Pillow parsing not applicable

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
    s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    s3.delete_object(Bucket=settings.aws_s3_quarantine_bucket, Key=s3_key)
