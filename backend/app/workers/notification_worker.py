"""
Notification worker — Celery tasks for push notification dispatch.

Tasks:
  notify_new_match(match_id)         → push to both users
  notify_new_message(chat_id, sender_id, preview)  → push to recipient
  notify_new_like(liked_user_id, liker_name)        → gold/platinum only
  notify_match_expiring(match_id)    → 24h warning before auto-expiry
  send_daily_digest()                → broadcast "N liked your profile today"

All tasks use asyncio.run() since Celery workers are synchronous by default.
DB connections are created per-task (no shared pool — workers are separate processes).
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from app.celery_app import celery_app
from app.core.config import settings
from app.services.push_notifications import send_push, send_push_multicast

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helper — ephemeral connection per task
# ---------------------------------------------------------------------------


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(settings.database_url)


# ---------------------------------------------------------------------------
# Task: new match
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_new_match", bind=True, max_retries=3)
def notify_new_match(self, match_id: str) -> None:
    """Push to both users when a mutual match is created."""

    async def _run():
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT
                    u_a.first_name AS name_a, u_a.fcm_token AS token_a,
                    u_b.first_name AS name_b, u_b.fcm_token AS token_b
                FROM matches m
                JOIN users u_a ON u_a.id = m.user_a_id
                JOIN users u_b ON u_b.id = m.user_b_id
                WHERE m.id = $1
                """,
                match_id,
            )
            if row is None:
                log.warning("notify_new_match: match %s not found", match_id)
                return

            await asyncio.gather(
                send_push(
                    row["token_a"],
                    "New Match! 🎉",
                    f"You matched with {row['name_b']}! Say hello 👋",
                    {"type": "new_match", "match_id": match_id},
                ),
                send_push(
                    row["token_b"],
                    "New Match! 🎉",
                    f"You matched with {row['name_a']}! Say hello 👋",
                    {"type": "new_match", "match_id": match_id},
                ),
            )
        finally:
            await conn.close()

    try:
        asyncio.run(_run())
    except Exception as exc:
        log.error("notify_new_match failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Task: new message
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_new_message", bind=True, max_retries=3)
def notify_new_message(self, chat_id: str, sender_id: str, preview: str) -> None:
    """Push to the recipient of a new chat message."""

    async def _run():
        conn = await _get_conn()
        try:
            # Find the other participant in this chat thread
            row = await conn.fetchrow(
                """
                SELECT
                    sender.first_name AS sender_name,
                    recipient.fcm_token AS recipient_token
                FROM chat_threads ct
                JOIN users sender    ON sender.id = $2
                JOIN users recipient ON recipient.id = CASE
                    WHEN ct.user_a_id = $2 THEN ct.user_b_id
                    ELSE ct.user_a_id
                END
                WHERE ct.id = $1
                """,
                chat_id,
                sender_id,
            )
            if row is None or not row["recipient_token"]:
                return

            body = preview[:80] + "…" if len(preview) > 80 else preview
            await send_push(
                row["recipient_token"],
                row["sender_name"],
                body,
                {"type": "new_message", "chat_id": chat_id, "sender_id": sender_id},
            )
        finally:
            await conn.close()

    try:
        asyncio.run(_run())
    except Exception as exc:
        log.error("notify_new_message failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)


# ---------------------------------------------------------------------------
# Task: new like (gold/platinum only)
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_new_like", bind=True, max_retries=2)
def notify_new_like(self, liked_user_id: str, liker_name: str) -> None:
    """Notify a gold/platinum user that someone liked their profile."""

    async def _run():
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT fcm_token, subscription_tier
                FROM users
                WHERE id = $1 AND account_status = 'active'
                """,
                liked_user_id,
            )
            if row is None or not row["fcm_token"]:
                return
            if row["subscription_tier"] not in ("gold", "platinum"):
                return  # free users don't get like notifications

            await send_push(
                row["fcm_token"],
                "Someone likes you! ❤️",
                f"{liker_name} liked your profile",
                {"type": "new_like"},
            )
        finally:
            await conn.close()

    try:
        asyncio.run(_run())
    except Exception as exc:
        log.error("notify_new_like failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Task: match expiring warning
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_match_expiring", bind=True, max_retries=2)
def notify_match_expiring(self, match_id: str) -> None:
    """
    Warn both users 24h before their match auto-expires.
    Triggered by ephemeral_reaper scanning matches expiring in ~25h.
    """

    async def _run():
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT
                    u_a.first_name AS name_a, u_a.fcm_token AS token_a,
                    u_b.first_name AS name_b, u_b.fcm_token AS token_b
                FROM matches m
                JOIN users u_a ON u_a.id = m.user_a_id
                JOIN users u_b ON u_b.id = m.user_b_id
                WHERE m.id = $1 AND m.status = 'matched'
                """,
                match_id,
            )
            if row is None:
                return

            await asyncio.gather(
                send_push(
                    row["token_a"],
                    "Match expiring soon ⏰",
                    f"Your match with {row['name_b']} expires in 24 hours! Send a message.",
                    {"type": "match_expiring", "match_id": match_id},
                ),
                send_push(
                    row["token_b"],
                    "Match expiring soon ⏰",
                    f"Your match with {row['name_a']} expires in 24 hours! Send a message.",
                    {"type": "match_expiring", "match_id": match_id},
                ),
            )
        finally:
            await conn.close()

    try:
        asyncio.run(_run())
    except Exception as exc:
        log.error("notify_match_expiring failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ---------------------------------------------------------------------------
# Task: daily digest (beat-triggered at 08:00 IST)
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.send_daily_digest")
def send_daily_digest() -> None:
    """
    For each active user with ≥1 new like in last 24h,
    push a "X people liked your profile today" notification.
    Batch-fetches all eligible users to avoid N+1 DB calls.
    """

    async def _run():
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT
                    u.fcm_token,
                    COUNT(i.id) AS like_count
                FROM users u
                JOIN interactions i ON i.target_user_id = u.id
                    AND i.action = 'like'
                    AND i.created_at > NOW() - INTERVAL '24h'
                WHERE u.account_status = 'active'
                  AND u.fcm_token IS NOT NULL
                  AND u.fcm_token != ''
                GROUP BY u.fcm_token
                HAVING COUNT(i.id) > 0
                """
            )

            if not rows:
                log.info("send_daily_digest: no eligible users")
                return

            tokens = [r["fcm_token"] for r in rows]
            # Per-user count matters, so we send individually
            results = await asyncio.gather(
                *[
                    send_push(
                        r["fcm_token"],
                        "People are interested in you! 💛",
                        f"{r['like_count']} {'person' if r['like_count'] == 1 else 'people'} liked your profile today.",
                        {"type": "daily_digest"},
                    )
                    for r in rows
                ],
                return_exceptions=True,
            )
            success = sum(1 for r in results if r is True)
            log.info("send_daily_digest: sent=%d total=%d", success, len(tokens))
        finally:
            await conn.close()

    asyncio.run(_run())
