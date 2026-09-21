"""
Content Moderation Service — Cloudflare Workers AI Vision Gate with Deduplication.

Enforces:
1. Single Cloudflare API token (no key rotation; no rolling accounts).
2. 15 RPM safe pacing (asyncio.Semaphore(1) + 4.0s inter-request delay).
3. Single-flight async deduplication (exactly 1 API call per photo_id under concurrency).
4. In-memory perceptual hash cache (_banned_hashes_cache) for instant 0ms duplicate rejection.
5. Perpetual prompt prefix caching via x-session-affinity header.
6. Safe fallback: daily neuron cap reached or API errors leave photo in status='pending'.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Single-flight deduplication locks keyed by photo_id
_photo_locks: dict[str, asyncio.Lock] = {}
_photo_locks_guard = asyncio.Lock()

# In-memory perceptual hash cache — O(1) pre-check, avoids DB reads on re-uploads
_banned_hashes_cache: set[str] = set()
_banned_hashes_loaded: bool = False

# Inter-request pacing state
_last_cf_request_time: float = 0.0
_cf_rpm_lock = asyncio.Lock()

# Daily Neuron tracker
_daily_neurons_used: float = 0.0
_daily_neurons_reset_ts: float = 0.0

# Hybrid single-token prompt (perpetually cacheable — static, never changes)
_CF_MODERATION_PROMPT = (
    "You are an automated photo moderator for a Jain community dating app. "
    "ALLOW: ethnic wear, sarees, waist, short dresses, cleavage, swimwear, shirtless men, "
    "gym wear, normal social photos, hobbies (ps5, trees, etc). "
    "REJECT: genitalia, nipples, explicit sex, CSAM, weapons, gore, phone numbers/contact overlay, "
    "ads, promotional, celebrity photos (any country, TV, movies, OTT, YouTubers, TikTok), "
    "AI generated/morphed photos. "
    "Reply PASS if safe. If unsafe, reply with single word: "
    "nudity / csam / weapon / gore / contact / ad / celebrity / morph"
)


@dataclass
class ModerationResult:
    is_safe: Optional[bool]  # True=approved, False=rejected, None=undetermined (needs manual review)
    reason: str
    confidence: float


class CloudflareVisionModerationClient:
    """Cloudflare Workers AI vision moderation with 15 RPM pacing and daily Neuron cap."""

    # Neurons per photo: 256 img tokens (cached) = 1.129 N + 1 output token = 0.061 N → 1.221 N/photo
    _NEURONS_PER_PHOTO: float = 1.221

    async def _pace_request(self) -> None:
        """Enforce 15 RPM: 4.0s minimum gap between requests."""
        global _last_cf_request_time
        async with _cf_rpm_lock:
            now = time.monotonic()
            gap = now - _last_cf_request_time
            if gap < 4.0:
                await asyncio.sleep(4.0 - gap)
            _last_cf_request_time = time.monotonic()

    def _check_daily_cap(self) -> bool:
        """Returns True if daily Neuron cap has NOT been exceeded."""
        global _daily_neurons_used, _daily_neurons_reset_ts
        now = time.time()
        # Reset counter daily at midnight UTC
        if now - _daily_neurons_reset_ts >= 86400:
            _daily_neurons_used = 0.0
            _daily_neurons_reset_ts = now
        return _daily_neurons_used < settings.cf_ai_daily_neuron_cap

    def _record_neurons(self) -> None:
        global _daily_neurons_used
        _daily_neurons_used += self._NEURONS_PER_PHOTO

    async def moderate_image_bytes(
        self,
        image_bytes: bytes,
        mime_type: str = "image/webp",
        dhash: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> ModerationResult:
        """
        Evaluate image bytes via Cloudflare Workers AI Llama 3.2 Vision.
        1. dHash pre-check against in-memory banned set (0ms, 0 Neurons).
        2. Daily Neuron cap check.
        3. 15 RPM pacing.
        4. POST to Cloudflare Workers AI endpoint.
        5. Parse hybrid single-token output (PASS or reject reason).
        """
        # 1. In-memory dHash pre-check (0ms, 0 Neurons)
        if dhash and dhash in _banned_hashes_cache:
            logger.info("dHash cache hit — instant reject: %s", dhash)
            return ModerationResult(is_safe=False, reason="duplicate", confidence=1.0)

        if not settings.cf_ai_moderation_enabled:
            return ModerationResult(is_safe=None, reason="Moderation disabled in config", confidence=0.0)

        if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
            logger.info("Cloudflare Workers AI not configured. Routing photo to manual review.")
            return ModerationResult(is_safe=None, reason="Photo under review", confidence=0.0)

        # 2. Daily Neuron cap
        if not self._check_daily_cap():
            logger.warning("Daily Neuron cap reached. Routing photo to manual review.")
            return ModerationResult(is_safe=None, reason="Photo under review", confidence=0.0)

        # 3. 15 RPM pacing
        await self._pace_request()

        b64_data = base64.b64encode(image_bytes).decode("ascii")

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                        },
                        {"type": "text", "text": _CF_MODERATION_PROMPT},
                    ],
                }
            ],
            "max_tokens": 3,
        }

        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{settings.cloudflare_account_id}/ai/run/{settings.cf_ai_vision_model}"
        )
        headers = {
            "Authorization": f"Bearer {settings.cloudflare_api_token}",
            "x-session-affinity": "dating-moderation-pool",
        }

        close_client = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient(timeout=20.0)
            close_client = True

        try:
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except httpx.RequestError as exc:
                logger.warning("Cloudflare Workers AI network error: %s", exc)
                return ModerationResult(is_safe=None, reason="Photo under review", confidence=0.0)

            if resp.status_code == 429:
                logger.warning("Cloudflare Workers AI 429 rate limit hit unexpectedly.")
                return ModerationResult(is_safe=None, reason="Photo under review", confidence=0.0)

            if resp.status_code != 200:
                logger.warning("Cloudflare Workers AI returned HTTP %s: %s", resp.status_code, resp.text[:200])
                return ModerationResult(is_safe=None, reason="Photo under review", confidence=0.0)

            data = resp.json()
            raw_text = (data.get("result", {}).get("response") or "").strip().upper()

            self._record_neurons()

            if raw_text == "PASS":
                return ModerationResult(is_safe=True, reason="clean", confidence=0.95)

            # Single-word reject reason
            _VALID_REJECT_TAGS = {"NUDITY", "CSAM", "WEAPON", "GORE", "CONTACT", "AD", "CELEBRITY", "MORPH"}
            reason_word = raw_text.lower() if raw_text in _VALID_REJECT_TAGS else "other"
            return ModerationResult(is_safe=False, reason=reason_word, confidence=0.95)

        except Exception as exc:
            logger.error("Unexpected error in Cloudflare moderation: %s", exc)
            return ModerationResult(is_safe=None, reason="Photo under review", confidence=0.0)
        finally:
            if close_client:
                await client.aclose()


# Global client singleton
cf_moderator = CloudflareVisionModerationClient()


async def get_photo_lock(photo_id: str) -> asyncio.Lock:
    """Single-flight lock ensuring 1 concurrent moderation task per photo."""
    async with _photo_locks_guard:
        if photo_id not in _photo_locks:
            _photo_locks[photo_id] = asyncio.Lock()
        return _photo_locks[photo_id]


async def load_banned_hashes(pool) -> None:
    """Load all banned hashes from DB into in-memory set on startup."""
    global _banned_hashes_cache, _banned_hashes_loaded
    if _banned_hashes_loaded:
        return
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT dhash FROM banned_image_hashes")
            _banned_hashes_cache = {r["dhash"] for r in rows}
            _banned_hashes_loaded = True
            logger.info("Loaded %d banned hashes into memory", len(_banned_hashes_cache))
    except Exception as exc:
        logger.error("Failed to load banned hashes: %s", exc)


async def record_banned_hash(pool, dhash: str, reason: str, confidence: float) -> None:
    """Insert new banned hash into DB and in-memory set atomically."""
    _banned_hashes_cache.add(dhash)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO banned_image_hashes (dhash, reason, confidence)
                VALUES ($1, $2, $3)
                ON CONFLICT (dhash) DO NOTHING
                """,
                dhash,
                reason,
                confidence,
            )
    except Exception as exc:
        logger.error("Failed to persist banned hash %s: %s", dhash, exc)


async def run_photo_moderation(
    photo_id: uuid.UUID,
    user_id: uuid.UUID,
    pool=None,
    moderator: Optional[CloudflareVisionModerationClient] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    dhash: Optional[str] = None,
) -> ModerationResult:
    """
    Background worker task:
    1. Single-flight locks on photo_id.
    2. Checks DB to avoid re-checking already approved/rejected photo.
    3. dHash fast-fail against in-memory banned set.
    4. Fetches image bytes.
    5. Moderates via Cloudflare Workers AI with 15 RPM pacing.
    6. Updates user_media status and synchronizes users.avatar_url if safe.
    7. Records banned hash on rejection.
    8. Cleans up in-memory lock on completion to prevent memory leaks.
    """
    from app.core.database import get_pool
    from app.services.media_processor import avatar_public_url

    photo_id_str = str(photo_id)
    lock = await get_photo_lock(photo_id_str)

    if moderator is None:
        moderator = cf_moderator

    try:
        async with lock:
            if pool is None:
                pool = get_pool()
                if pool is None:
                    logger.error("run_photo_moderation: DB pool not initialized")
                    return ModerationResult(is_safe=None, reason="DB pool uninitialized", confidence=0.0)

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, user_id, status, cdn_url FROM user_media WHERE id = $1 AND user_id = $2",
                    photo_id,
                    user_id,
                )
                if not row:
                    logger.warning("run_photo_moderation: Photo %s not found in DB", photo_id)
                    return ModerationResult(is_safe=None, reason="Photo not found", confidence=0.0)

                # Preserve versioned cdn_url stored during confirm_upload or generate with version token
                if row.get("cdn_url"):
                    cdn_url = row["cdn_url"]
                else:
                    cdn_url = avatar_public_url(user_id, version=str(photo_id).replace("-", "")[:8])

                # Idempotency guard: already resolved
                if row["status"] in ("approved", "rejected"):
                    logger.info("Photo %s already resolved with status %s", photo_id, row["status"])
                    return ModerationResult(
                        is_safe=(row["status"] == "approved"),
                        reason=f"Already {row['status']}",
                        confidence=1.0,
                    )

            # Download image bytes from public CDN / storage
            img_client = http_client
            close_img_client = False
            if img_client is None:
                img_client = httpx.AsyncClient(timeout=10.0)
                close_img_client = True

            image_bytes = None
            try:
                resp = await img_client.get(cdn_url)
                if resp.status_code == 200:
                    image_bytes = resp.content
            except Exception as exc:
                logger.warning("Avatar HTTP GET failed for %s: %s", cdn_url, exc)
            finally:
                if close_img_client:
                    await img_client.aclose()

            # Fallback to authenticated Supabase storage download if public GET failed
            if not image_bytes:
                try:
                    from app.services.media_processor import _get_supabase, avatar_storage_path
                    supabase = _get_supabase()
                    path = avatar_storage_path(user_id)
                    image_bytes = await asyncio.to_thread(
                        supabase.storage.from_(settings.supabase_storage_bucket).download,
                        path,
                    )
                except Exception as exc:
                    logger.error("Authenticated Supabase download failed for %s: %s", user_id, exc)
                    return ModerationResult(is_safe=None, reason="Image download failed", confidence=0.0)

            # Run moderation via Cloudflare Workers AI
            result = await moderator.moderate_image_bytes(
                image_bytes=image_bytes,
                mime_type="image/webp",
                dhash=dhash,
                http_client=http_client,
            )

            async with pool.acquire() as conn:
                async with conn.transaction():
                    if result.is_safe is True:
                        # Auto-approve and publish to users table
                        await conn.execute(
                            """
                            UPDATE user_media
                               SET status = 'approved', cdn_url = $1, is_processed = TRUE
                             WHERE id = $2 AND user_id = $3
                            """,
                            cdn_url,
                            photo_id,
                            user_id,
                        )
                        # TOCTOU guard: Only update users.avatar_url if this photo is STILL the user's active avatar
                        await conn.execute(
                            """
                            UPDATE users
                               SET avatar_url = $1, updated_at = NOW()
                             WHERE id = $2
                               AND EXISTS (
                                   SELECT 1 FROM user_media
                                    WHERE id = $3 AND user_id = $2 AND position = 1 AND media_type = 'photo'
                               )
                            """,
                            cdn_url,
                            user_id,
                            photo_id,
                        )
                        logger.info("Photo %s auto-approved for user %s", photo_id, user_id)

                    elif result.is_safe is False:
                        # Reject photo record
                        await conn.execute(
                            """
                            UPDATE user_media
                               SET status = 'rejected', rejection_reason = $1, is_processed = TRUE
                             WHERE id = $2 AND user_id = $3
                            """,
                            result.reason,
                            photo_id,
                            user_id,
                        )
                        # Record banned hash for instant future rejection
                        if dhash:
                            await record_banned_hash(pool, dhash, result.reason, result.confidence)

                        # TOCTOU guard: Only clear users.avatar_url and storage if this photo is STILL the user's active avatar
                        is_active = await conn.fetchval(
                            "SELECT EXISTS (SELECT 1 FROM user_media WHERE id = $1 AND user_id = $2 AND position = 1 AND media_type = 'photo')",
                            photo_id,
                            user_id,
                        )
                        if is_active:
                            await conn.execute(
                                "UPDATE users SET avatar_url = NULL, updated_at = NOW() WHERE id = $1",
                                user_id,
                            )
                            # Quota optimization: purge rejected image from Supabase Storage to protect 1GB free tier
                            from app.services.media_processor import delete_user_avatar
                            await delete_user_avatar(user_id)
                            logger.warning("Photo %s rejected for user %s: %s (purged from storage)", photo_id, user_id, result.reason)
                        else:
                            logger.warning("Photo %s rejected for user %s: %s (skipped storage purge, superseded by newer photo)", photo_id, user_id, result.reason)

                    else:
                        # Undetermined / cap reached -> stays 'pending' for internal review
                        logger.info("Photo %s marked pending for manual review: %s", photo_id, result.reason)

            # Invalidate Redis profile and feed cache if redis is available
            try:
                from app.core.redis import get_redis
                r = get_redis()
                if r:
                    await r.delete(f"profile:{user_id}", f"feed:cache:{user_id}")
            except Exception:
                pass

            return result
    finally:
        async with _photo_locks_guard:
            _photo_locks.pop(photo_id_str, None)
