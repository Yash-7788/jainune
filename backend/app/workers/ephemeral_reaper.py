"""
Ephemeral reaper — scheduled cleanup worker.

Tasks (all beat-triggered — see celery_app.py):

  reap_ephemeral_media()              every 5 min
    → delete quarantine-bucket objects for media that failed moderation
      and whose DB record is > 1 hour old

  downgrade_expired_subscriptions()   every 15 min
    → set subscription_tier='free' where subscription_valid_until < NOW()

  reap_stale_matches()                every hour
    → expire matches where no message was sent in > 7 days (configurable)
    → dispatch expiry-warning notifications for matches expiring in ~25h

  purge_deleted_users()               daily at 03:00
    → hard-delete users where account_status='deleted' AND deleted_at < 30 days ago
    → cascade deletes media, prompts, interactions, reports via FK ON DELETE CASCADE
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.celery_app import celery_app
from app.core.config import settings
from app.workers.worker_pool import get_worker_conn, run_worker_task

log = logging.getLogger(__name__)

MATCH_EXPIRY_DAYS = 7          # matches auto-expire after 7 days of silence
EXPIRY_WARN_HOURS = 25         # warn users 25h before expiry (catches the 24h window)
DELETED_USER_RETENTION_DAYS = 30


async def _get_conn() -> asyncpg.Connection:
    return await get_worker_conn()


def _s3_client():
    if not boto3 or not settings.aws_access_key_id or settings.aws_access_key_id.startswith("mock"):
        return None
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


# ---------------------------------------------------------------------------
# Task: reap quarantine media
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.ephemeral_reaper.reap_ephemeral_media")
def reap_ephemeral_media() -> None:
    """
    Find media records in 'rejected' or 'pending' state older than 1 hour.
    Delete the S3 object from quarantine and mark the DB record purged.
    """

    async def _run():
        conn = await _get_conn()
        try:
            s3 = _s3_client()
            if not s3:
                log.info("reap_ephemeral_media: AWS S3 client unavailable/mock, skipping S3 purge")
                return
            # Mark stranded processing media as rejected after 30-minute timeout (NEW-020)
            await conn.execute(
                """
                UPDATE user_media
                SET status = 'rejected', rejection_reason = 'PROCESSING_TIMEOUT'
                WHERE status = 'processing'
                  AND created_at < NOW() - INTERVAL '30 minutes'
                """
            )

            rows = await conn.fetch(
                """
                SELECT id, s3_key
                FROM user_media
                WHERE status IN ('rejected', 'pending')
                  AND created_at < NOW() - INTERVAL '1 hour'
                  AND s3_purged = FALSE
                LIMIT 200
                """
            )
            if not rows:
                return

            objects_to_delete = [{"Key": r["s3_key"]} for r in rows if r.get("s3_key")]
            if objects_to_delete:
                try:
                    await asyncio.to_thread(
                        s3.delete_objects,
                        Bucket=settings.aws_s3_quarantine_bucket,
                        Delete={"Objects": objects_to_delete, "Quiet": True},
                    )
                except (BotoCoreError, ClientError) as exc:
                    log.warning("Batch S3 delete failed in reap_ephemeral_media: %s", exc)

            row_ids = [r["id"] for r in rows]
            await conn.execute(
                "UPDATE user_media SET s3_purged = TRUE WHERE id = ANY($1::uuid[])",
                row_ids,
            )
            log.info("reap_ephemeral_media: purged %d media rows", len(rows))
        finally:
            await conn.close()

    run_worker_task(_run())


# ---------------------------------------------------------------------------
# Task: downgrade expired subscriptions
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.ephemeral_reaper.downgrade_expired_subscriptions")
def downgrade_expired_subscriptions() -> None:
    """
    Sweep users whose subscription_valid_until has passed.
    Reset to free tier + clear valid_until.
    """

    async def _run():
        conn = await _get_conn()
        try:
            result = await conn.execute(
                """
                WITH to_downgrade AS (
                    SELECT id FROM users
                    WHERE subscription_tier != 'free'
                      AND subscription_valid_until IS NOT NULL
                      AND subscription_valid_until < NOW()
                    LIMIT 500
                )
                UPDATE users
                   SET subscription_tier        = 'free',
                       subscription_valid_until  = NULL,
                       super_connect_credits     = 0,
                       updated_at                = NOW()
                 WHERE id IN (SELECT id FROM to_downgrade)
                """
            )
            # asyncpg returns 'UPDATE N'
            count = int(result.split()[-1])
            if count:
                log.info("downgrade_expired_subscriptions: downgraded %d users", count)
        finally:
            await conn.close()

    run_worker_task(_run())


# ---------------------------------------------------------------------------
# Task: reap stale matches
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.ephemeral_reaper.reap_stale_matches")
def reap_stale_matches() -> None:
    """
    1. Expire matches that have been silent for MATCH_EXPIRY_DAYS.
    2. Find matches expiring in ~EXPIRY_WARN_HOURS and dispatch warning pushes.
    """

    async def _run():
        conn = await _get_conn()
        try:
            # --- Step 1: expire silent matches ---
            tx = conn.transaction() if hasattr(conn, "transaction") and callable(conn.transaction) else None
            if asyncio.iscoroutine(tx):
                tx.close()
                tx = None
            if tx is not None and hasattr(tx, "__aenter__") and not asyncio.iscoroutine(tx):
                async with tx:
                    expired_ids = await conn.fetch(
                        f"""
                        UPDATE matches
                           SET status     = 'expired',
                               expired_at = NOW()
                         WHERE status IN ('active', 'matched')
                           AND COALESCE(last_message_at, created_at) < NOW() - INTERVAL '{MATCH_EXPIRY_DAYS} days'
                        RETURNING id
                        """  # nosec B608
                    )
                    if expired_ids:
                        exp_list = [r["id"] for r in expired_ids]
                        await conn.execute(
                            "UPDATE chats SET is_unmatched = TRUE, updated_at = NOW() WHERE match_id = ANY($1::uuid[])",
                            exp_list,
                        )
            else:
                expired_ids = await conn.fetch(
                    f"""
                    UPDATE matches
                       SET status     = 'expired',
                           expired_at = NOW()
                     WHERE status IN ('active', 'matched')
                       AND COALESCE(last_message_at, created_at) < NOW() - INTERVAL '{MATCH_EXPIRY_DAYS} days'
                    RETURNING id
                    """  # nosec B608
                )
                if expired_ids:
                    exp_list = [r["id"] for r in expired_ids]
                    await conn.execute(
                        "UPDATE chats SET is_unmatched = TRUE, updated_at = NOW() WHERE match_id = ANY($1::uuid[])",
                        exp_list,
                    )
            if expired_ids:
                log.info("reap_stale_matches: expired %d matches and closed chats", len(expired_ids))
                try:
                    from app.core.redis import get_redis
                    r = get_redis()
                    if r and hasattr(r, "scan_iter"):
                        for mid in exp_list:
                            pattern = f"chat:safety:single_chars:{mid}:*"
                            async for k in r.scan_iter(pattern):
                                await r.delete(k)
                except Exception:
                    pass

            # --- Step 2: warn matches expiring within EXPIRY_WARN_HOURS ---
            warn_ids = await conn.fetch(
                f"""
                SELECT id FROM matches
                WHERE status IN ('active', 'matched')
                  AND expiry_warned = FALSE
                  AND COALESCE(last_message_at, created_at) < NOW() - INTERVAL '{MATCH_EXPIRY_DAYS} days'
                                                + INTERVAL '{EXPIRY_WARN_HOURS} hours'
                LIMIT 500
                """  # nosec B608
            )

            if warn_ids:
                from app.workers.notification_worker import notify_match_expiring

                for row in warn_ids:
                    notify_match_expiring.delay(str(row["id"]))

                # Mark as warned to prevent duplicate notifications
                ids = [row["id"] for row in warn_ids]
                await conn.execute(
                    "UPDATE matches SET expiry_warned = TRUE WHERE id = ANY($1::uuid[])",
                    ids,
                )
                log.info("reap_stale_matches: queued %d expiry warnings", len(warn_ids))
        finally:
            await conn.close()

    run_worker_task(_run())


# ---------------------------------------------------------------------------
# Task: purge deleted users
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.ephemeral_reaper.purge_deleted_users")
def purge_deleted_users() -> None:
    """
    Hard-delete users soft-deleted > DELETED_USER_RETENTION_DAYS days ago per DPDP Act & UI terms.
    Excludes users with active paid subscriptions to retain billing and audit integrity.
    Archives all payment and transaction records to financial_audit_logs (7-year RBI retention).
    """

    async def _run():
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                f"""
                SELECT id FROM users
                WHERE account_status = 'deleted'
                  AND deleted_at < NOW() - INTERVAL '{DELETED_USER_RETENTION_DAYS} days'
                  AND (subscription_tier = 'free' OR subscription_valid_until IS NULL OR subscription_valid_until < NOW())
                LIMIT 100
                """  # nosec B608
            )
            if not rows:
                return

            ids = [r["id"] for r in rows]

            # Archive financial records for 7-year regulatory retention (RBI / DPDP Act)
            for uid in ids:
                try:
                    await conn.execute(
                        """
                        INSERT INTO financial_audit_logs (
                            original_user_id, transaction_type, reference_id,
                            razorpay_order_id, razorpay_payment_id, plan_id,
                            amount_inr, currency, status, captured_at, archived_at, retention_until
                        )
                        SELECT
                            user_id, 'subscription_intent', COALESCE(razorpay_payment_id, razorpay_order_id, id::text),
                            razorpay_order_id, razorpay_payment_id, plan_id,
                            (amount / 100.0)::numeric(10,2), currency, status, captured_at, NOW(), NOW() + INTERVAL '7 years'
                        FROM payment_intents
                        WHERE user_id = $1
                        ON CONFLICT (reference_id) DO NOTHING
                        """,
                        uid,
                    )
                    await conn.execute(
                        """
                        INSERT INTO financial_audit_logs (
                            original_user_id, transaction_type, reference_id,
                            razorpay_order_id, razorpay_payment_id, plan_id,
                            amount_inr, currency, status, captured_at, archived_at, retention_until
                        )
                        SELECT
                            user_id, 'arcade_transaction', COALESCE(razorpay_payment_id, razorpay_order_id, id::text),
                            razorpay_order_id, razorpay_payment_id, action_type,
                            amount_inr, 'INR', status, created_at, NOW(), NOW() + INTERVAL '7 years'
                        FROM arcade_transactions
                        WHERE user_id = $1 AND amount_inr > 0
                        ON CONFLICT (reference_id) DO NOTHING
                        """,
                        uid,
                    )
                except Exception as exc:
                    log.warning(f"Financial record archive error for user {uid}: {exc}")

            # Delete S3 objects first (no cascade for external storage)
            media_keys = await conn.fetch(
                "SELECT s3_key FROM user_media WHERE user_id = ANY($1::uuid[])",
                ids,
            )
            from app.services.account_service import _delete_s3_keys_sync
            await asyncio.to_thread(
                _delete_s3_keys_sync,
                [mk["s3_key"] for mk in media_keys if mk.get("s3_key")],
            )

            # Hard delete — cascades non-financial data
            result = await conn.execute(
                "DELETE FROM users WHERE id = ANY($1::uuid[])",
                ids,
            )
            count = int(result.split()[-1])
            log.info("purge_deleted_users: hard-deleted %d users after 72h retention", count)
        finally:
            await conn.close()

    run_worker_task(_run())


# ---------------------------------------------------------------------------
# Task: reap stale payment intents (>24h uncaptured)
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.ephemeral_reaper.reap_stale_payment_intents")
def reap_stale_payment_intents() -> None:
    """Marks abandoned/uncaptured payment intents older than 24 hours as expired."""

    async def _run():
        conn = await _get_conn()
        try:
            result = await conn.execute(
                """
                UPDATE payment_intents
                   SET status = 'expired',
                       updated_at = NOW()
                 WHERE status = 'created'
                   AND created_at < NOW() - INTERVAL '24 hours'
                """
            )
            count = int(result.split()[-1])
            if count > 0:
                log.info("reap_stale_payment_intents: expired %d stale payment intents", count)
        finally:
            await conn.close()

    run_worker_task(_run())
