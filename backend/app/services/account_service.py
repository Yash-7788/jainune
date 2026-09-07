"""
Account Lifecycle & Data Purge Service:
- Immediate physical deletion of user data to free database disk and memory.
- Amazon S3 media asset removal (both production and quarantine buckets).
- Invalidation and purging of Redis memory caches, quotas, and session keys.
- Token revocation and session cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

import asyncpg
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

import redis.asyncio as aioredis

from app.core.config import settings

log = logging.getLogger(__name__)


def _delete_s3_keys_sync(s3_keys: list[str]) -> None:
    """Synchronously delete objects from both quarantine and production S3 buckets."""
    if not s3_keys:
        return

    try:
        s3 = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    except Exception as exc:
        log.warning(f"Failed to initialize S3 client for media purge: {exc}")
        return

    for key in s3_keys:
        if not key:
            continue
        # Try prod bucket
        try:
            s3.delete_object(Bucket=settings.aws_s3_production_bucket, Key=key)
        except ClientError as ce:
            log.debug(f"Could not delete {key} from prod bucket: {ce}")
        except Exception:
            pass

        # Try quarantine bucket (and also variant upload prefix if applicable)
        try:
            quarantine_key = key.replace("media/", "uploads/")
            s3.delete_object(Bucket=settings.aws_s3_quarantine_bucket, Key=quarantine_key)
        except ClientError as ce:
            log.debug(f"Could not delete {quarantine_key} from quarantine bucket: {ce}")
        except Exception:
            pass


async def purge_user_account(
    user_id: uuid.UUID,
    conn: asyncpg.Connection,
    redis: aioredis.Redis,
) -> dict:
    """
    Permanently purges all user data:
    1. Fetches all media files and deletes them from S3 storage.
    2. Nullifies administrative reviewer/resolver references.
    3. Physically deletes user rows from PostgreSQL database tables.
    4. Clears all Redis cache, quota, feed, and rate limit keys.
    Returns summary of deleted resources.
    """
    user_row = await conn.fetchrow(
        "SELECT phone_number, email, subscription_tier, subscription_valid_until FROM users WHERE id = $1",
        user_id,
    )
    phone = user_row["phone_number"] if user_row else None
    email = user_row["email"] if user_row else None

    # AUDIT-2: Block hard-delete while subscription is active — force soft-delete instead
    if user_row and isinstance(user_row, dict) and user_row.get("subscription_tier") and user_row["subscription_tier"] != "free":
        from datetime import datetime, timezone
        valid_until = user_row.get("subscription_valid_until")
        now = datetime.now(timezone.utc)
        if isinstance(valid_until, datetime):
            vu = valid_until if valid_until.tzinfo else valid_until.replace(tzinfo=timezone.utc)
            if vu > now:
                log.warning(
                    f"User {user_id} has active {user_row['subscription_tier']} subscription until {valid_until}. "
                    "Blocking hard-purge and falling back to soft-delete to preserve billing records."
                )
                return await soft_delete_user_account(user_id, conn, redis)

    # AUDIT-1: Retain financial transaction logs for 7 years per RBI regulations
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
            user_id,
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
            user_id,
        )
    except Exception as exc:
        log.warning(f"Financial audit log archiving for {user_id}: {exc}")

    # 1. Fetch all media s3 keys
    media_rows = await conn.fetch(
        "SELECT s3_key FROM user_media WHERE user_id = $1",
        user_id,
    )
    s3_keys = [r["s3_key"] for r in media_rows if r.get("s3_key")]

    # Delete from S3 asynchronously
    if s3_keys:
        try:
            await asyncio.to_thread(_delete_s3_keys_sync, s3_keys)
        except Exception as exc:
            log.error(f"S3 deletion failed during account purge for {user_id}: {exc}")

    # 2. Database cleanup within transaction
    async with conn.transaction():
        # Try nullifying user_id on financial records to prevent orphan cascades if schema allows
        try:
            await conn.execute("UPDATE payment_intents SET user_id = NULL WHERE user_id = $1", user_id)
        except Exception:
            pass
        try:
            await conn.execute("UPDATE arcade_transactions SET user_id = NULL WHERE user_id = $1 AND amount_inr > 0", user_id)
        except Exception:
            pass

        # Clear non-cascading FK references first
        await conn.execute("UPDATE user_media SET reviewed_by = NULL WHERE reviewed_by = $1", user_id)
        await conn.execute("UPDATE reports SET resolved_by = NULL WHERE resolved_by = $1", user_id)
        await conn.execute("UPDATE admin_users SET created_by = NULL WHERE created_by = $1", user_id)

        # Delete from user_blocks
        await conn.execute(
            "DELETE FROM user_blocks WHERE blocker_id = $1 OR blocked_id = $1",
            user_id,
        )

        # Delete from reports
        await conn.execute(
            "DELETE FROM reports WHERE reporter_id = $1 OR reported_id = $1",
            user_id,
        )

        # Delete refresh tokens
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)

        # Delete user media, prompts, behavior vectors, badges
        await conn.execute("DELETE FROM user_media WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM user_prompts WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM user_behavior_vectors WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM dignity_badges WHERE from_user_id = $1 OR to_user_id = $1", user_id)

        # Delete wallet & transactions
        await conn.execute("DELETE FROM arcade_transactions WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM user_arcade_wallet WHERE user_id = $1", user_id)

        # Cascade / explicit delete on interactions, matches, chats, messages
        # Note: messages & chats cascade from users, but clean explicitly to ensure zero orphaned memory
        await conn.execute("DELETE FROM messages WHERE sender_id = $1", user_id)
        await conn.execute(
            "DELETE FROM chats WHERE participant_a = $1 OR participant_b = $1 OR participant_1_id = $1 OR participant_2_id = $1",
            user_id,
        )
        await conn.execute(
            """
            DELETE FROM matches
            WHERE user_a = $1 OR user_b = $1
               OR user_id_1 = $1 OR user_id_2 = $1
               OR user_a_id = $1 OR user_b_id = $1
            """,
            user_id,
        )
        await conn.execute("DELETE FROM interactions WHERE actor_id = $1 OR target_id = $1", user_id)

        # Finally, delete user record itself
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    # 3. Redis memory cleanup
    try:
        keys_to_delete = [
            f"feed:cache:{user_id}",
            f"user:session:{user_id}",
            f"user:active:{user_id}",
            f"daily_likes:{user_id}",
            f"daily_super_connects:{user_id}",
            f"quota:{user_id}",
        ]
        if phone:
            keys_to_delete.extend([
                f"auth:otp:{phone}",
                f"auth:otp_rate:{phone}",
            ])
        if email:
            keys_to_delete.extend([
                f"auth:email_otp:{email}",
                f"auth:email_otp_rate:{email}",
            ])

        # Delete direct keys
        if keys_to_delete:
            await redis.delete(*keys_to_delete)

        # Scan for wildcard keys (daily_likes:{user_id}:*, etc.)
        for pattern in [f"daily_likes:{user_id}:*", f"daily_super_connects:{user_id}:*", f"ratelimit:*:{user_id}*"]:
            cursor = 0
            while True:
                cursor, matched_keys = await redis.scan(cursor=cursor, match=pattern, count=100)
                if matched_keys:
                    await redis.delete(*matched_keys)
                if cursor == 0:
                    break
    except Exception as exc:
        log.warning(f"Redis memory cleanup error for {user_id}: {exc}")

    return {
        "status": "purged",
        "user_id": str(user_id),
        "media_files_deleted": len(s3_keys),
    }


async def soft_delete_user_account(
    user_id: uuid.UUID,
    conn: asyncpg.Connection,
    redis: aioredis.Redis,
) -> dict:
    """Soft delete: scrubs PII, sets account_status='deleted', revokes active sessions."""
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE users
               SET account_status   = 'deleted',
                   first_name       = 'Deleted User',
                   phone_number     = 'DELETED_' || id::text,
                   email            = NULL,
                   google_id        = NULL,
                   apple_id         = NULL,
                   bio              = NULL,
                   job_title        = NULL,
                   company          = NULL,
                   education        = NULL,
                   deleted_at       = NOW(),
                   updated_at       = NOW()
             WHERE id = $1
            """,
            user_id,
        )
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)

        # Terminate active matches and chats for soft-deleted user
        await conn.execute(
            """
            UPDATE matches
            SET status = 'unmatched', updated_at = NOW()
            WHERE (user_a = $1 OR user_b = $1 OR user_id_1 = $1 OR user_id_2 = $1 OR user_a_id = $1 OR user_b_id = $1)
              AND status = 'active'
            """,
            user_id,
        )
        await conn.execute(
            """
            UPDATE chats
            SET is_unmatched = TRUE, updated_at = NOW()
            WHERE (participant_1_id = $1 OR participant_2_id = $1 OR participant_a = $1 OR participant_b = $1)
              AND is_unmatched = FALSE
            """,
            user_id,
        )

    # Invalidate feed & sessions in Redis
    try:
        await redis.delete(f"feed:cache:{user_id}", f"user:session:{user_id}")
    except Exception:
        pass

    return {
        "status": "soft_deleted",
        "user_id": str(user_id),
    }
