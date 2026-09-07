"""
Unit tests for Round 5 deep audit hardening:
1. verify_otp rejects banned user (403)
2. verify_otp rejects deleted user (401)
3. verify_otp rejects suspended user (403)
4. refresh_token_endpoint rejects banned user and purges refresh tokens (403)
5. update_my_profile invalidates feed:cache in Redis
6. unblock_user rejects self-unblock (400) and invalidates feed cache for both participants
7. record_interaction_action rejects non-existent or deleted target (404)
8. verify_location invalidates feed:cache in Redis on coordinates update
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone, timedelta

for mod in ["asyncpg", "redis", "redis.asyncio", "boto3", "botocore", "botocore.exceptions", "celery", "celery.schedules"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import app.celery_app
app.celery_app.celery_app.task = lambda *args, **kwargs: (lambda fn: fn)

from fastapi import HTTPException
from app.routers.auth import verify_otp_endpoint, refresh_token_endpoint
from app.routers.users import update_my_profile, unblock_user, UpdateProfileBody
from app.routers.interactions import record_interaction_action
from app.routers.location import verify_location, VerifyLocationRequest
from app.models.schemas.auth import OTPVerifyBody, TokenRefreshBody
from app.models.schemas.interaction import InteractionActionRequest


def _mock_async_pool_and_conn():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    tx_mock = MagicMock()
    tx_mock.__aenter__ = AsyncMock(return_value=None)
    tx_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_mock)
    return pool, conn


class TestDeepAuditRound5Hardening(unittest.IsolatedAsyncioTestCase):

    async def test_01_verify_otp_rejects_banned_user_403(self):
        """Banned users verifying valid OTP must be rejected with 403 Forbidden."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        conn.fetchrow.return_value = {
            "id": uid,
            "onboarding_completed": True,
            "account_status": "banned",
            "deleted_at": None,
            "suspend_until": None,
        }
        mock_redis = MagicMock()

        body = OTPVerifyBody(phone_number="+919876543210", otp="123456")
        with patch("app.routers.auth.verify_otp", new_callable=AsyncMock):
            with self.assertRaises(HTTPException) as ctx:
                await verify_otp_endpoint(body=body, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("permanently banned", ctx.exception.detail)

    async def test_02_verify_otp_rejects_deleted_user_401(self):
        """Deleted users verifying valid OTP must be rejected with 401 Unauthorized."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        conn.fetchrow.return_value = {
            "id": uid,
            "onboarding_completed": True,
            "account_status": "deleted",
            "deleted_at": datetime.now(timezone.utc),
            "suspend_until": None,
        }
        mock_redis = MagicMock()

        body = OTPVerifyBody(phone_number="+919876543210", otp="123456")
        with patch("app.routers.auth.verify_otp", new_callable=AsyncMock):
            with self.assertRaises(HTTPException) as ctx:
                await verify_otp_endpoint(body=body, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("has been deleted", ctx.exception.detail)

    async def test_03_verify_otp_rejects_suspended_user_403(self):
        """Suspended users verifying OTP must receive 403 with suspension deadline."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        until = datetime.now(timezone.utc) + timedelta(days=3)
        conn.fetchrow.return_value = {
            "id": uid,
            "onboarding_completed": True,
            "account_status": "suspended",
            "deleted_at": None,
            "suspend_until": until,
        }
        mock_redis = MagicMock()

        body = OTPVerifyBody(phone_number="+919876543210", otp="123456")
        with patch("app.routers.auth.verify_otp", new_callable=AsyncMock):
            with self.assertRaises(HTTPException) as ctx:
                await verify_otp_endpoint(body=body, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("temporarily suspended", ctx.exception.detail)

    async def test_04_token_refresh_rejects_banned_user_and_purges_tokens(self):
        """Token refresh for banned user raises 403 and immediately deletes refresh tokens from DB."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        conn.fetchrow.return_value = {
            "user_id": uid,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "u_id": uid,
            "account_status": "banned",
            "deleted_at": None,
            "suspend_until": None,
        }
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.get = AsyncMock(return_value=None)
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        body = TokenRefreshBody(refresh_token="rt_sample_banned_token")
        with self.assertRaises(HTTPException) as ctx:
            await refresh_token_endpoint(body=body, request=mock_request, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 403)
        # Verify refresh token deletion was executed
        conn.execute.assert_called_with("DELETE FROM refresh_tokens WHERE user_id = $1", uid)

    async def test_05_profile_update_invalidates_feed_cache(self):
        """Profile updates must invalidate user's feed:cache key in Redis."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        conn.execute.return_value = "UPDATE 1"
        fake_profile = {
            "id": uid,
            "phone_number": "+919876543210",
            "first_name": "Naman",
            "bio": "Updated Jain Bio",
            "city": "Ahmedabad",
            "state": "Gujarat",
            "dietary_strictness": "pure_jain",
            "community_sect": "shwetambar_deravasi",
            "onboarding_completed": True,
            "account_status": "active",
            "photos": [],
            "prompts": [],
        }

        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=1)

        body = UpdateProfileBody(bio="Updated Jain Bio")
        with patch("app.routers.users._get_user_row", new_callable=AsyncMock, return_value=fake_profile):
            with patch("app.routers.users.get_redis", return_value=mock_redis):
                res = await update_my_profile(body=body, current_user={"user_id": uid}, pool=pool)
        self.assertEqual(res["bio"], "Updated Jain Bio")
        mock_redis.delete.assert_called_with(f"feed:cache:{uid}")

    async def test_06_unblock_user_rejects_self_unblock_and_purges_caches(self):
        """Self-unblock raises 400; unblocking other user purges feed cache for both users."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        target_id = uuid.uuid4()

        # 1. Self unblock attempt -> 400
        with self.assertRaises(HTTPException) as ctx:
            await unblock_user(user_id=uid, current_user={"user_id": uid}, pool=pool)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot unblock yourself", ctx.exception.detail)

        # 2. Valid unblock -> deletes user_blocks and purges both feed caches
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=1)
        with patch("app.routers.users.get_redis", return_value=mock_redis):
            res = await unblock_user(user_id=target_id, current_user={"user_id": uid}, pool=pool)
        self.assertTrue(res["success"])
        mock_redis.delete.assert_any_call(f"feed:cache:{uid}")
        mock_redis.delete.assert_any_call(f"feed:cache:{target_id}")

    async def test_07_interaction_rejects_nonexistent_or_deleted_target_404(self):
        """Interactions on nonexistent or deleted users must raise 404 before credit deduction."""
        pool, conn = _mock_async_pool_and_conn()
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()

        # blocked check returns 0 (not blocked)
        conn.fetchval.return_value = None
        # target user does not exist
        conn.fetchrow.return_value = None

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        mock_redis.pipeline.return_value = mock_pipe

        body = InteractionActionRequest(target_id=target_id, action="like")
        with self.assertRaises(HTTPException) as ctx:
            await record_interaction_action(
                body=body,
                current_user={"id": str(actor_id)},
                db=pool,
                redis=mock_redis,
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Target profile not found", ctx.exception.detail)

    async def test_08_verify_location_invalidates_feed_cache(self):
        """verify_location in active zone must invalidate user's feed:cache in Redis."""
        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock(return_value=1)
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        mock_redis.pipeline.return_value = mock_pipe

        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers = {}

        body = VerifyLocationRequest(
            latitude=19.0760,
            longitude=72.8777,
            is_mocked=False,
        )

        with patch("app.routers.location.verify_location_anti_spoofing", return_value=(True, None)):
            with patch("app.routers.location.verify_location_zone", return_value=(True, {"id": "mum_mmr", "name": "Mumbai MMR", "state": "Maharashtra", "distance_to_center_km": 5.0})):
                res = await verify_location(
                    body=body,
                    request=mock_req,
                    redis=mock_redis,
                    current_user={"id": uid, "user_id": uid},
                    pool=pool,
                )
        self.assertTrue(res["data"]["allowed"])
        mock_redis.delete.assert_called_with(f"feed:cache:{uid}")

    async def test_09_verify_email_otp_rejects_banned_user_403(self):
        """Banned users verifying email OTP must be rejected with 403 Forbidden."""
        from app.routers.auth import verify_email_otp
        from app.models.schemas.auth import EmailOTPVerifyBody
        from app.core.security import hash_otp

        pool, conn = _mock_async_pool_and_conn()
        uid = uuid.uuid4()
        conn.fetchrow.return_value = {
            "id": uid,
            "onboarding_completed": True,
            "account_status": "banned",
            "deleted_at": None,
            "suspend_until": None,
        }
        email = "test.banned@jainune.com"
        otp = "123456"
        stored_hash = hash_otp(email, otp)

        mock_redis = MagicMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=stored_hash.encode())
        mock_redis.delete = AsyncMock(return_value=1)

        body = EmailOTPVerifyBody(email=email, otp=otp)
        with self.assertRaises(HTTPException) as ctx:
            await verify_email_otp(body=body, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("permanently banned", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
