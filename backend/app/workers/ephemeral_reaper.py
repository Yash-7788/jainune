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

log = logging.getLogger(__name__)

MATCH_EXPIRY_DAYS = 7          # matches auto-expire after 7 days of silence
EXPIRY_WARN_HOURS = 25         # warn users 25h before expiry (catches the 24h window)
DELETED_USER_RETENTION_DAYS = 30


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(settings.database_url)


def _s3_client():
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
        s3 = _s3_client()
        try:
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

            purged = 0
            for row in rows:
                try:
                    s3.delete_object(
                        Bucket=settings.aws_s3_quarantine_bucket,
                        Key=row["s3_key"],
                    )
                    await conn.execute(
                        "UPDATE user_media SET s3_purged = TRUE WHERE id = $1",
                        row["id"],
                    )
                    purged += 1
                except (BotoCoreError, ClientError) as exc:
                    log.warning("S3 delete failed for media %s: %s", row["id"], exc)

            log.info("reap_ephemeral_media: purged %d/%d", purged, len(rows))
        finally:
            await conn.close()

    asyncio.run(_run())


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
                UPDATE users
                   SET subscription_tier       = 'free',
                       subscription_valid_until = NULL,
                       updated_at               = NOW()
                 WHERE subscription_tier != 'free'
                   AND subscription_valid_until IS NOT NULL
                   AND subscription_valid_until < NOW()
                """
            )
            # asyncpg returns 'UPDATE N'
            count = int(result.split()[-1])
            if count:
                log.info("downgrade_expired_subscriptions: downgraded %d users", count)
        finally:
            await conn.close()

    asyncio.run(_run())


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
            expired_ids = await conn.fetch(
                f"""
                UPDATE matches
                   SET status     = 'expired',
                       expired_at = NOW()
                 WHERE status IN ('active', 'matched')
                   AND last_message_at < NOW() - INTERVAL '{MATCH_EXPIRY_DAYS} days'
                RETURNING id
                """
            )
            if expired_ids:
                log.info("reap_stale_matches: expired %d matches", len(expired_ids))

            # --- Step 2: warn matches expiring within EXPIRY_WARN_HOURS ---
            warn_ids = await conn.fetch(
                f"""
                SELECT id FROM matches
                WHERE status IN ('active', 'matched')
                  AND expiry_warned = FALSE
                  AND last_message_at < NOW() - INTERVAL '{MATCH_EXPIRY_DAYS} days'
                                                + INTERVAL '{EXPIRY_WARN_HOURS} hours'
                LIMIT 500
                """
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

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Task: purge deleted users
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.ephemeral_reaper.purge_deleted_users")
def purge_deleted_users() -> None:
    """
    Hard-delete users soft-deleted > DELETED_USER_RETENTION_DAYS ago.
    FK ON DELETE CASCADE handles: media, prompts, interactions, reports, matches,
    dilemma_votes, dignity_badges, payment_intents, admin_audit_log entries.
    """

    async def _run():
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                f"""
                SELECT id FROM users
                WHERE account_status = 'deleted'
                  AND deleted_at < NOW() - INTERVAL '{DELETED_USER_RETENTION_DAYS} days'
                LIMIT 100
                """
            )
            if not rows:
                return

            ids = [r["id"] for r in rows]
            # Delete S3 objects first (no cascade for external storage)
            s3 = _s3_client()
            media_keys = await conn.fetch(
                "SELECT s3_key FROM user_media WHERE user_id = ANY($1::uuid[])",
                ids,
            )
            for mk in media_keys:
                try:
                    s3.delete_object(Bucket=settings.aws_s3_quarantine_bucket, Key=mk["s3_key"])
                except Exception as exc:
                    log.warning("S3 purge error for key %s: %s", mk["s3_key"], exc)

            # Hard delete — cascades via FK
            result = await conn.execute(
                "DELETE FROM users WHERE id = ANY($1::uuid[])",
                ids,
            )
            count = int(result.split()[-1])
            log.info("purge_deleted_users: hard-deleted %d users", count)
        finally:
            await conn.close()

    asyncio.run(_run())
