"""
Content Moderation Service — Google Gemini Vision Gate with Failover & Deduplication.

Enforces:
1. Multi-key pool rotation (supports 3 free-tier or paid accounts via GEMINI_API_KEYS).
2. Per-key rate limiting (15 RPM compliance).
3. Single-flight async deduplication (exactly 1 API call per photo_id under concurrency).
4. Safety refusal capture (finish_reason="SAFETY" treated as explicit violation).
5. Safe failover: exhausted quota or API errors leave photo in status='pending' for admin review.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Single-flight deduplication locks keyed by photo_id
_photo_locks: dict[str, asyncio.Lock] = {}
_photo_locks_guard = asyncio.Lock()


@dataclass
class ModerationResult:
    is_safe: Optional[bool]  # True=approved, False=rejected, None=undetermined (needs manual review)
    reason: str
    confidence: float


class GeminiModerationClient:
    """Manages Gemini Vision API calls with multi-key pool, rate limiting, and failover."""

    def __init__(self) -> None:
        self._keys: list[str] = [
            k.strip() for k in settings.gemini_api_keys.split(",") if k.strip()
        ]
        self._current_key_idx = 0
        self._key_timestamps: dict[str, list[float]] = {k: [] for k in self._keys}
        self._key_cooldowns: dict[str, float] = {k: 0.0 for k in self._keys}
        self._lock = asyncio.Lock()

    def set_keys(self, keys: list[str]) -> None:
        """Update key pool dynamically (e.g. for testing)."""
        self._keys = [k.strip() for k in keys if k.strip()]
        self._current_key_idx = 0
        self._key_timestamps = {k: [] for k in self._keys}
        self._key_cooldowns = {k: 0.0 for k in self._keys}

    async def _get_available_key(self) -> Optional[str]:
        """Selects next available key respecting 15 RPM rate limits and cooldowns."""
        async with self._lock:
            if not self._keys:
                return None

            now = time.monotonic()
            n_keys = len(self._keys)

            for i in range(n_keys):
                idx = (self._current_key_idx + i) % n_keys
                key = self._keys[idx]

                # Check cooldown (e.g., after 429)
                if self._key_cooldowns.get(key, 0.0) > now:
                    continue

                # Prune request timestamps older than 60 seconds
                stamps = [t for t in self._key_timestamps.get(key, []) if now - t < 60.0]
                self._key_timestamps[key] = stamps

                # Free tier rate limit: 15 RPM
                if len(stamps) < 15:
                    stamps.append(now)
                    self._current_key_idx = (idx + 1) % n_keys
                    return key

            return None

    def _mark_key_rate_limited(self, key: str, cooldown_seconds: float = 60.0) -> None:
        """Puts a key in cooldown on HTTP 429."""
        self._key_cooldowns[key] = time.monotonic() + cooldown_seconds
        logger.warning("Gemini API key %s rate-limited (429). Cooldown: %ss", key[:6] + "...", cooldown_seconds)

    async def moderate_image_bytes(
        self,
        image_bytes: bytes,
        mime_type: str = "image/webp",
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> ModerationResult:
        """Evaluates image bytes against dating app moderation guidelines."""
        if not settings.gemini_moderation_enabled:
            return ModerationResult(is_safe=None, reason="Moderation disabled in config", confidence=0.0)

        if not self._keys:
            logger.info("No Gemini API keys configured. Routing photo to manual admin queue.")
            return ModerationResult(is_safe=None, reason="Gemini API unconfigured; queued for admin", confidence=0.0)

        b64_data = base64.b64encode(image_bytes).decode("ascii")

        system_instruction = (
            "You are an automated photo moderator for a modern dating app. Analyze the uploaded image.\n"
            "Guidelines:\n"
            "- ALLOW: cleavage, swimwear, shirtless men, stylish revealing outfits, gym wear, ethnic clothing, normal social photos.\n"
            "- REJECT: exposed genitalia, exposed nipples/areola, explicit sex acts, pornographic content, "
            "child exploitation/CSAM, firearms/weapons, graphic violence/gore, hate symbols.\n"
            "Respond ONLY with valid JSON in this schema:\n"
            '{"is_safe": boolean, "reason": "clean" | "nudity" | "violence" | "csam" | "other", "confidence": float}'
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
            ],
        }

        attempts = len(self._keys)
        close_client = False
        client = http_client
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            close_client = True

        try:
            for _ in range(attempts):
                api_key = await self._get_available_key()
                if not api_key:
                    logger.warning("All Gemini API keys are busy or cooling down. Queuing for admin.")
                    return ModerationResult(is_safe=None, reason="Rate limit reached across all keys; queued for admin", confidence=0.0)

                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{settings.gemini_moderation_model}:generateContent?key={api_key}"
                )

                try:
                    resp = await client.post(url, json=payload)
                except httpx.RequestError as exc:
                    logger.warning("Gemini network error with key %s: %s", api_key[:6] + "...", exc)
                    continue

                if resp.status_code == 429:
                    self._mark_key_rate_limited(api_key, cooldown_seconds=60.0)
                    continue

                if resp.status_code != 200:
                    logger.warning("Gemini returned HTTP %s: %s", resp.status_code, resp.text)
                    continue

                data = resp.json()

                # 1. Check prompt feedback block
                prompt_feedback = data.get("promptFeedback", {})
                if prompt_feedback.get("blockReason"):
                    logger.warning("Gemini blocked prompt: %s", prompt_feedback)
                    return ModerationResult(is_safe=False, reason=f"Safety block: {prompt_feedback.get('blockReason')}", confidence=1.0)

                candidates = data.get("candidates", [])
                if not candidates:
                    return ModerationResult(is_safe=None, reason="No candidates returned", confidence=0.0)

                candidate = candidates[0]
                finish_reason = candidate.get("finish_reason") or candidate.get("finishReason")

                # 2. Check safety filter refusal
                if finish_reason == "SAFETY":
                    logger.warning("Gemini refused image due to safety filters (finish_reason=SAFETY)")
                    return ModerationResult(is_safe=False, reason="Refused by safety filters (nudity/explicit)", confidence=1.0)

                # 3. Parse JSON response
                parts = candidate.get("content", {}).get("parts", [])
                if not parts:
                    return ModerationResult(is_safe=None, reason="Empty response parts", confidence=0.0)

                raw_text = parts[0].get("text", "{}")
                try:
                    parsed = json.loads(raw_text)
                    is_safe = bool(parsed.get("is_safe", False))
                    reason = str(parsed.get("reason", "clean" if is_safe else "unspecified"))
                    confidence = float(parsed.get("confidence", 0.9))
                    return ModerationResult(is_safe=is_safe, reason=reason, confidence=confidence)
                except Exception as exc:
                    logger.error("Failed to parse Gemini moderation JSON: %s (raw: %s)", exc, raw_text)
                    return ModerationResult(is_safe=None, reason="Invalid JSON from model; queued for admin", confidence=0.0)

            # All attempts failed or exhausted
            return ModerationResult(is_safe=None, reason="All moderation keys exhausted; queued for admin", confidence=0.0)

        finally:
            if close_client:
                await client.aclose()


# Global client instance
gemini_moderator = GeminiModerationClient()


async def get_photo_lock(photo_id: str) -> asyncio.Lock:
    """Single-flight lock ensuring 1 concurrent moderation task per photo."""
    async with _photo_locks_guard:
        if photo_id not in _photo_locks:
            _photo_locks[photo_id] = asyncio.Lock()
        return _photo_locks[photo_id]


async def run_photo_moderation(
    photo_id: uuid.UUID,
    user_id: uuid.UUID,
    pool=None,
    moderator: Optional[GeminiModerationClient] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> ModerationResult:
    """
    Background worker task:
    1. Single-flight locks on photo_id.
    2. Checks DB to avoid re-checking already approved/rejected photo.
    3. Fetches image bytes.
    4. Moderates via Gemini client with multi-key failover.
    5. Updates user_photos status and synchronizes users.avatar_url if safe.
    """
    from app.core.database import get_pool
    from app.services.media_processor import avatar_public_url

    photo_id_str = str(photo_id)
    lock = await get_photo_lock(photo_id_str)

    if moderator is None:
        moderator = gemini_moderator

    async with lock:
        if pool is None:
            pool = get_pool()
            if pool is None:
                logger.error("run_photo_moderation: DB pool not initialized")
                return ModerationResult(is_safe=None, reason="DB pool uninitialized", confidence=0.0)

        cdn_url = avatar_public_url(user_id)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, user_id, status, cdn_url FROM user_photos WHERE id = $1 AND user_id = $2",
                photo_id,
                user_id,
            )
            if not row:
                logger.warning("run_photo_moderation: Photo %s not found in DB", photo_id)
                return ModerationResult(is_safe=None, reason="Photo not found", confidence=0.0)

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

        try:
            resp = await img_client.get(cdn_url)
            if resp.status_code != 200:
                logger.error("Failed to download avatar image from %s: HTTP %s", cdn_url, resp.status_code)
                return ModerationResult(is_safe=None, reason="Image download failed", confidence=0.0)
            image_bytes = resp.content
        finally:
            if close_img_client:
                await img_client.aclose()

        # Run moderation
        result = await moderator.moderate_image_bytes(
            image_bytes=image_bytes,
            mime_type="image/webp",
            http_client=http_client,
        )

        async with pool.acquire() as conn:
            async with conn.transaction():
                if result.is_safe is True:
                    # Auto-approve and publish to users table
                    await conn.execute(
                        """
                        UPDATE user_photos
                           SET status = 'approved', cdn_url = $1, updated_at = NOW()
                         WHERE id = $2 AND user_id = $3
                        """,
                        cdn_url,
                        photo_id,
                        user_id,
                    )
                    await conn.execute(
                        "UPDATE users SET avatar_url = $1, updated_at = NOW() WHERE id = $2",
                        cdn_url,
                        user_id,
                    )
                    logger.info("Photo %s auto-approved for user %s", photo_id, user_id)

                elif result.is_safe is False:
                    # Reject and ensure avatar_url is not published
                    await conn.execute(
                        """
                        UPDATE user_photos
                           SET status = 'rejected', rejection_reason = $1, updated_at = NOW()
                         WHERE id = $2 AND user_id = $3
                        """,
                        result.reason,
                        photo_id,
                        user_id,
                    )
                    await conn.execute(
                        "UPDATE users SET avatar_url = NULL, updated_at = NOW() WHERE id = $1 AND avatar_url = $2",
                        user_id,
                        cdn_url,
                    )
                    logger.warning("Photo %s rejected for user %s: %s", photo_id, user_id, result.reason)

                else:
                    # Undetermined / Quota exhausted -> stays 'pending' for admin review
                    logger.info("Photo %s marked pending for manual admin review: %s", photo_id, result.reason)

        return result
