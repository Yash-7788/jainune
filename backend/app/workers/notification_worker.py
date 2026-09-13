"""
Notification worker — Celery tasks for push notification dispatch.

Tasks:
  notify_new_match(match_id)         → push to both users
  notify_new_message(chat_id, sender_id, preview)  → push to recipient
  notify_new_like(liked_user_id, liker_name, liker_id)  → paid-tier users (gold/platinum/jainune_plus/jainune_gold)
  notify_match_expiring(match_id)    → 24h warning before auto-expiry
  send_daily_digest()                → broadcast "N liked your profile today"

All tasks use asyncio.run() since Celery workers are synchronous by default.
DB connections are created per-task (no shared pool — workers are separate processes).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import asyncpg

from app.celery_app import celery_app
from app.core.config import settings
from app.services.push_notifications import get_user_device_tokens, send_push, send_push_multicast
from app.workers.worker_pool import get_worker_conn, run_worker_task

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helper — worker process pooled connection
# ---------------------------------------------------------------------------


async def _get_conn() -> asyncpg.Connection:
    return await get_worker_conn()


async def _check_and_lock_dedup(key: str, in_flight_ttl: int = 60) -> tuple[bool, str]:
    """Acquires an in-flight reservation token. Returns (is_duplicate: bool, token: str)."""
    try:
        from app.core.redis import get_redis
        r = get_redis()
        if await r.exists(f"notify:dedup:{key}"):
            return True, ""
        token = uuid.uuid4().hex
        acquired = await r.set(f"notify:inflight:{key}", token, nx=True, ex=in_flight_ttl)
        return not acquired, token
    except Exception:
        return False, ""


async def _commit_dedup(key: str, token: str, ttl: int = 120) -> None:
    """Commit durable deduplication after successful push delivery and clean in-flight key."""
    try:
        from app.core.redis import get_redis
        r = get_redis()
        pipe = r.pipeline()
        pipe.set(f"notify:dedup:{key}", "1", ex=ttl)
        pipe.delete(f"notify:inflight:{key}")
        await pipe.execute()
    except Exception:
        pass


async def _rollback_dedup(key: str, token: str) -> None:
    """Release in-flight reservation on delivery failure so retries succeed."""
    try:
        from app.core.redis import get_redis
        r = get_redis()
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await r.eval(lua, 1, f"notify:inflight:{key}", token)
    except Exception:
        pass


async def _is_dedup(key: str, ttl: int = 120) -> bool:
    """Backward-compatible deduplication check."""
    is_dup, _ = await _check_and_lock_dedup(key, in_flight_ttl=ttl)
    return is_dup


# ---------------------------------------------------------------------------
# Task: new match
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_new_match", bind=True, max_retries=3)
def notify_new_match(self, match_id: str) -> None:
    """Push to both users when a mutual match is created."""

    async def _run():
        dedup_key = f"match:{match_id}"
        is_dup, token = await _check_and_lock_dedup(dedup_key, in_flight_ttl=60)
        if is_dup:
            log.info("notify_new_match: duplicate notification for match %s skipped", match_id)
            return
        conn = await _get_conn()
        delivered = False
        try:
            m_uuid = uuid.UUID(str(match_id))
            row = await conn.fetchrow(
                """
                SELECT
                    u_a.id AS id_a, u_a.first_name AS name_a, u_a.fcm_token AS token_a,
                    u_b.id AS id_b, u_b.first_name AS name_b, u_b.fcm_token AS token_b
                FROM matches m
                JOIN users u_a ON u_a.id = COALESCE(m.user_a, m.user_a_id, m.user_id_1)
                JOIN users u_b ON u_b.id = COALESCE(m.user_b, m.user_b_id, m.user_id_2)
                WHERE m.id = $1
                """,
                m_uuid,
            )
            if row is None:
                log.warning("notify_new_match: match %s not found", match_id)
                await _commit_dedup(dedup_key, token, ttl=300)
                return

            tokens_a = (await get_user_device_tokens(row["id_a"], conn) if row.get("id_a") else []) or ([row["token_a"]] if row.get("token_a") else [])
            tokens_b = (await get_user_device_tokens(row["id_b"], conn) if row.get("id_b") else []) or ([row["token_b"]] if row.get("token_b") else [])

            tasks = []
            for t in set(tokens_a):
                tasks.append(send_push(
                    t,
                    "New Match! 🎉",
                    f"You matched with {row['name_b']}! Say hello 👋",
                    {"type": "new_match", "match_id": match_id},
                    db_conn=conn,
                ))
            for t in set(tokens_b):
                tasks.append(send_push(
                    t,
                    "New Match! 🎉",
                    f"You matched with {row['name_a']}! Say hello 👋",
                    {"type": "new_match", "match_id": match_id},
                    db_conn=conn,
                ))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                delivered = any(isinstance(r, bool) and r for r in results)
            else:
                delivered = True

            if delivered:
                await _commit_dedup(dedup_key, token, ttl=300)
            else:
                await _rollback_dedup(dedup_key, token)
                raise RuntimeError(f"Failed to deliver push notifications for match {match_id}")
        except Exception:
            await _rollback_dedup(dedup_key, token)
            raise
        finally:
            await conn.close()

    try:
        run_worker_task(_run())
    except Exception as exc:
        log.error("notify_new_match failed: %s", exc)
        if hasattr(self, "retry"):
            try:
                self.retry(exc=exc, countdown=60)
            except Exception:
                raise



# ---------------------------------------------------------------------------
# Task: new message
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_new_message", bind=True, max_retries=3)
def notify_new_message(self, chat_id: str, sender_id: str, preview: str) -> None:
    """Push to the recipient of a new chat message."""

    async def _run():
        conn = await _get_conn()
        try:
            c_uuid = uuid.UUID(str(chat_id))
            s_uuid = uuid.UUID(str(sender_id))
            # Find the other participant in this chat thread
            row = await conn.fetchrow(
                """
                SELECT
                    sender.first_name AS sender_name,
                    recipient.id AS recipient_id,
                    recipient.fcm_token AS recipient_token
                FROM chats c
                JOIN users sender    ON sender.id = $2
                JOIN users recipient ON recipient.id = CASE
                    WHEN c.participant_1_id = $2 THEN c.participant_2_id
                    ELSE c.participant_1_id
                END
                WHERE c.id = $1
                """,
                c_uuid,
                s_uuid,
            )
            if row is None:
                return

            tokens = await get_user_device_tokens(row["recipient_id"], conn) or ([row["recipient_token"]] if row.get("recipient_token") else [])
            if not tokens:
                return

            body = preview[:80] + "…" if len(preview) > 80 else preview
            for t in set(tokens):
                await send_push(
                    t,
                    row["sender_name"],
                    body,
                    {"type": "new_message", "chat_id": chat_id, "sender_id": sender_id},
                    db_conn=conn,
                )
        finally:
            await conn.close()

    try:
        run_worker_task(_run())
    except Exception as exc:
        log.error("notify_new_message failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)


# ---------------------------------------------------------------------------
# Task: new like (gold/platinum only)
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.notification_worker.notify_new_like", bind=True, max_retries=2)
def notify_new_like(self, liked_user_id: str, liker_name: str, liker_id: str = "") -> None:
    """Notify a paid-tier user that someone liked their profile."""

    async def _run():
        dedup_actor = liker_id if liker_id else liker_name
        dedup_key = f"like:{liked_user_id}:{dedup_actor}"
        is_dup, token = await _check_and_lock_dedup(dedup_key, in_flight_ttl=60)
        if is_dup:
            log.info("notify_new_like: duplicate like notification for %s skipped", liked_user_id)
            return
        conn = await _get_conn()
        try:
            u_uuid = uuid.UUID(str(liked_user_id))
            row = await conn.fetchrow(
                """
                SELECT id, fcm_token, subscription_tier
                FROM users
                WHERE id = $1 AND account_status = 'active'
                """,
                u_uuid,
            )
            if row is None:
                await _commit_dedup(dedup_key, token, ttl=120)
                return
            if row["subscription_tier"] not in ("gold", "platinum", "jainune_plus", "jainune_gold"):
                await _commit_dedup(dedup_key, token, ttl=120)
                return  # free users don't get like notifications

            tokens = await get_user_device_tokens(row["id"], conn) or ([row["fcm_token"]] if row.get("fcm_token") else [])
            if not tokens:
                await _commit_dedup(dedup_key, token, ttl=120)
                return

            results = []
            for t in set(tokens):
                r = await send_push(
                    t,
                    "Someone likes you! ❤️",
                    f"{liker_name} liked your profile",
                    {"type": "new_like"},
                    db_conn=conn,
                )
                results.append(r)

            if any(results):
                await _commit_dedup(dedup_key, token, ttl=120)
            else:
                await _rollback_dedup(dedup_key, token)
                raise RuntimeError(f"Failed to deliver like push notification to {liked_user_id}")
        except Exception:
            await _rollback_dedup(dedup_key, token)
            raise
        finally:
            await conn.close()

    try:
        run_worker_task(_run())
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
        dedup_key = f"expiring:{match_id}"
        is_dup, token = await _check_and_lock_dedup(dedup_key, in_flight_ttl=60)
        if is_dup:
            log.info("notify_match_expiring: duplicate expiring notification for %s skipped", match_id)
            return
        conn = await _get_conn()
        try:
            m_uuid = uuid.UUID(str(match_id))
            row = await conn.fetchrow(
                """
                SELECT
                    u_a.id AS id_a, u_a.first_name AS name_a, u_a.fcm_token AS token_a,
                    u_b.id AS id_b, u_b.first_name AS name_b, u_b.fcm_token AS token_b
                FROM matches m
                JOIN users u_a ON u_a.id = COALESCE(m.user_a, m.user_a_id, m.user_id_1)
                JOIN users u_b ON u_b.id = COALESCE(m.user_b, m.user_b_id, m.user_id_2)
                WHERE m.id = $1 AND m.status IN ('active', 'matched')
                """,
                m_uuid,
            )
            if row is None:
                await _commit_dedup(dedup_key, token, ttl=86400)
                return

            tokens_a = await get_user_device_tokens(row["id_a"], conn) or ([row["token_a"]] if row.get("token_a") else [])
            tokens_b = await get_user_device_tokens(row["id_b"], conn) or ([row["token_b"]] if row.get("token_b") else [])

            tasks = []
            for t in set(tokens_a):
                tasks.append(send_push(
                    t,
                    "Match expiring soon ⏰",
                    f"Your match with {row['name_b']} expires in 24 hours! Send a message.",
                    {"type": "match_expiring", "match_id": match_id},
                    db_conn=conn,
                ))
            for t in set(tokens_b):
                tasks.append(send_push(
                    t,
                    "Match expiring soon ⏰",
                    f"Your match with {row['name_a']} expires in 24 hours! Send a message.",
                    {"type": "match_expiring", "match_id": match_id},
                    db_conn=conn,
                ))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                delivered = any(isinstance(r, bool) and r for r in results)
            else:
                delivered = True

            if delivered:
                await _commit_dedup(dedup_key, token, ttl=86400)
            else:
                await _rollback_dedup(dedup_key, token)
                raise RuntimeError(f"Failed to deliver expiring match notification for {match_id}")
        except Exception:
            await _rollback_dedup(dedup_key, token)
            raise
        finally:
            await conn.close()

    try:
        run_worker_task(_run())
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
                JOIN interactions i ON i.target_id = u.id
                    AND (i.action_type = 'like' OR i.interaction_type = 'like')
                    AND i.created_at > NOW() - INTERVAL '24 hours'
                WHERE u.account_status = 'active'
                  AND u.subscription_tier IN ('gold', 'platinum', 'jainune_plus')
                  AND u.fcm_token IS NOT NULL
                  AND u.fcm_token != ''
                GROUP BY u.fcm_token
                HAVING COUNT(i.id) > 0
                """
            )

            if not rows:
                log.info("send_daily_digest: no eligible users")
                return

            # Group eligible users by like_count for multicast batching
            from collections import defaultdict
            count_groups: dict[int, list[str]] = defaultdict(list)
            for r in rows:
                count_groups[r["like_count"]].append(r["fcm_token"])

            BATCH_SIZE = 500
            total_sent = 0
            total_failed = 0
            for count, group_tokens in count_groups.items():
                title = "People are interested in you! 💛"
                body = f"{count} {'person' if count == 1 else 'people'} liked your profile today."
                data = {"type": "daily_digest"}
                for i in range(0, len(group_tokens), BATCH_SIZE):
                    batch = group_tokens[i : i + BATCH_SIZE]
                    res = await send_push_multicast(batch, title, body, data, db_conn=conn)
                    total_sent += res.get("success", 0)
                    total_failed += res.get("failure", 0)

            log.info("send_daily_digest: sent=%d failed=%d total=%d", total_sent, total_failed, len(rows))
        finally:
            await conn.close()

    run_worker_task(_run())
