"""
Unit tests for Production Domain Hardening:
- Account lifecycle security: soft-deletion, temporary suspension, permanent bans.
- User blocking, mutual match/chat termination, and feed cache invalidation.
- CorePeopleFinder worker ranking adapter.
- Admin role authorization via admin_users.
"""

from __future__ import annotations

import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()
if "redis.asyncio" not in sys.modules:
    sys.modules["redis.asyncio"] = MagicMock()

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.dependencies import get_current_user
from app.routers.admin import require_admin
from app.routers.arcade import create_dilemma, CreateDilemmaBody
from app.routers.chats import get_messages
from app.routers.users import block_user, unblock_user
from app.services.core_people_finder import CorePeopleFinder, _get_cached_feed


def _make_mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    tx_mock = MagicMock()
    tx_mock.__aenter__ = AsyncMock(return_value=None)
    tx_mock.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_mock)

    return pool, conn


class TestProductionDomainHardening(unittest.IsolatedAsyncioTestCase):

    async def test_get_current_user_rejects_deleted_account(self):
        """Users with deleted_at or account_status='deleted' must receive 401."""
        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()

        conn.fetchrow.return_value = {
            "id": user_id,
            "account_status": "deleted",
            "deleted_at": datetime.now(timezone.utc),
            "suspend_until": None,
        }

        with patch("app.dependencies.validate_access_token", AsyncMock(return_value={"sub": str(user_id)})):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            with self.assertRaises(HTTPException) as ctx:
                await get_current_user(credentials=creds, db=pool, redis=MagicMock())
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("deleted", ctx.exception.detail)

    async def test_get_current_user_rejects_suspended_account(self):
        """Users with suspend_until in the future must receive 403."""
        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()

        conn.fetchrow.return_value = {
            "id": user_id,
            "account_status": "active",
            "deleted_at": None,
            "suspend_until": datetime.now(timezone.utc) + timedelta(days=3),
        }

        with patch("app.dependencies.validate_access_token", AsyncMock(return_value={"sub": str(user_id)})):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            with self.assertRaises(HTTPException) as ctx:
                await get_current_user(credentials=creds, db=pool, redis=MagicMock())
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("suspended", ctx.exception.detail)

    async def test_get_current_user_rejects_banned_account(self):
        """Users with account_status='banned' must receive 403."""
        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()

        conn.fetchrow.return_value = {
            "id": user_id,
            "account_status": "banned",
            "deleted_at": None,
            "suspend_until": None,
        }

        with patch("app.dependencies.validate_access_token", AsyncMock(return_value={"sub": str(user_id)})):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
            with self.assertRaises(HTTPException) as ctx:
                await get_current_user(credentials=creds, db=pool, redis=MagicMock())
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("banned", ctx.exception.detail)

    async def test_block_user_terminates_matches_and_clears_cache(self):
        """Blocking a user records user_blocks, unmatches match/chat, and purges Redis feed caches."""
        pool, conn = _make_mock_pool()
        blocker_id = uuid.uuid4()
        blocked_id = uuid.uuid4()

        fake_redis = AsyncMock()
        with patch("app.core.redis.get_redis", return_value=fake_redis):
            res = await block_user(
                user_id=blocked_id,
                body=None,
                current_user={"user_id": blocker_id},
                pool=pool,
            )

        self.assertTrue(res["success"])
        sql_calls = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("INSERT INTO user_blocks" in s for s in sql_calls))
        self.assertTrue(any("UPDATE matches" in s and "status = 'unmatched'" in s for s in sql_calls))
        self.assertTrue(any("UPDATE chats" in s and "is_unmatched = TRUE" in s for s in sql_calls))

        fake_redis.delete.assert_any_call(f"feed:cache:{blocker_id}")
        fake_redis.delete.assert_any_call(f"feed:cache:{blocked_id}")

    async def test_unblock_user(self):
        """Unblocking a user deletes from user_blocks."""
        pool, conn = _make_mock_pool()
        blocker_id = uuid.uuid4()
        blocked_id = uuid.uuid4()

        res = await unblock_user(
            user_id=blocked_id,
            current_user={"user_id": blocker_id},
            pool=pool,
        )
        self.assertTrue(res["success"])
        conn.execute.assert_called_once()
        self.assertIn("DELETE FROM user_blocks", conn.execute.call_args[0][0])

    async def test_core_people_finder_adapter_rank_candidates(self):
        """CorePeopleFinder.rank_candidates correctly filters gender and ranks by cultural compatibility."""
        finder = CorePeopleFinder()
        req_id = uuid.uuid4()
        requester = {
            "id": req_id,
            "gender": "man",
            "show_me": "women",
            "dietary_strictness": "pure_jain",
            "community_sect": "shwetambar_deravasi",
            "eats_onion_garlic": False,
        }

        c1 = {
            "id": uuid.uuid4(),
            "gender": "woman",
            "dietary_strictness": "pure_jain",
            "community_sect": "shwetambar_deravasi",
            "eats_onion_garlic": False,
        }
        c2 = {
            "id": uuid.uuid4(),
            "gender": "woman",
            "dietary_strictness": "vegan",
            "community_sect": "digambar",
            "eats_onion_garlic": True,
        }
        c3_man = {
            "id": uuid.uuid4(),
            "gender": "man",  # wrong gender
            "dietary_strictness": "pure_jain",
            "community_sect": "shwetambar_deravasi",
            "eats_onion_garlic": False,
        }

        ranked = await finder.rank_candidates(requester, [c1, c2, c3_man])
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["id"], c1["id"])  # higher score
        self.assertEqual(ranked[1]["id"], c2["id"])

    async def test_require_admin_valid(self):
        """User with superadmin role in admin_users passes require_admin."""
        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()
        conn.fetchval.return_value = "superadmin"

        admin = await require_admin(current_user={"user_id": user_id}, pool=pool)
        self.assertEqual(admin["admin_role"], "superadmin")

    async def test_require_admin_forbidden_for_regular_user(self):
        """Regular user without admin role receives 403 Forbidden."""
        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()
        conn.fetchval.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await require_admin(current_user={"user_id": user_id}, pool=pool)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_cached_feed_redis_error_logs_and_returns_none(self):
        """O6: Redis decode failure in _get_cached_feed must log warning and return None without NameError."""
        redis = AsyncMock()
        redis.get.return_value = "invalid-json-{"
        res = await _get_cached_feed(uuid.uuid4(), redis)
        self.assertIsNone(res)

    async def test_chat_cursor_lookup_scoped_to_chat_id(self):
        """O8: Message cursor lookup must strictly verify AND chat_id = $2 to prevent oracle cross-chat timestamp leak."""
        pool, conn = _make_mock_pool()
        current_user = {"id": str(uuid.uuid4())}
        chat_id = uuid.uuid4()
        cursor_id = uuid.uuid4()

        # Mock participant check
        conn.fetchrow.side_effect = [
            {"id": chat_id, "user_a_id": uuid.UUID(current_user["id"]), "user_b_id": uuid.uuid4()}, # chat row
            None, # cursor lookup row
        ]

        await get_messages(
            chat_id=chat_id,
            limit=20,
            cursor=str(cursor_id),
            before=None,
            current_user=current_user,
            db=pool,
        )

        # Check cursor query call args
        cursor_query_calls = [
            call for call in conn.fetchrow.call_args_list
            if "SELECT created_at, id FROM messages" in call[0][0]
        ]
        self.assertTrue(len(cursor_query_calls) > 0)
        self.assertIn("AND chat_id = $2", cursor_query_calls[0][0][0])
        self.assertEqual(cursor_query_calls[0][0][2], chat_id)

    async def test_create_dilemma_with_admin_dependency(self):
        """O9: create_dilemma consumes require_admin dependency properly."""
        pool, conn = _make_mock_pool()
        admin_id = uuid.uuid4()
        admin_user = {"user_id": admin_id, "admin_role": "moderator"}
        conn.fetchval.return_value = uuid.uuid4()

        body = CreateDilemmaBody(
            question_text="Would you prefer early morning samayik or late evening pratikraman?",
            option_a="Morning samayik",
            option_b="Evening pratikraman",
            tags=["rituals", "daily_life"],
        )

        res = await create_dilemma(body, admin=admin_user, pool=pool)
        self.assertTrue(res["created"])
        self.assertIn("INSERT INTO dilemmas", conn.fetchval.call_args[0][0])

    async def test_endpoint_rate_limiters_enforced(self):
        """Verify rate limiters trigger 429 when threshold exceeded across matrix endpoints."""
        from app.routers.websockets import create_ws_ticket
        from app.routers.auth import logout_endpoint
        from app.routers.telemetry import ingest_interaction_event, InteractionEventPayload
        from app.routers.media import presign_upload_get

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 999, True])
        mock_redis.pipeline.return_value = mock_pipe
        user_id = uuid.uuid4()
        user_dict = {"id": str(user_id), "user_id": str(user_id)}

        # WS ticket rate limit
        with self.assertRaises(HTTPException) as ctx:
            await create_ws_ticket(current_user=user_dict, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Logout rate limit
        pool, _ = _make_mock_pool()
        with self.assertRaises(HTTPException) as ctx:
            await logout_endpoint(current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Telemetry interaction event rate limit
        event = InteractionEventPayload(target_user_id=uuid.uuid4(), action="like", total_dwell_ms=1200)
        with self.assertRaises(HTTPException) as ctx:
            await ingest_interaction_event(event=event, current_user=user_dict, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Media presign upload rate limit
        with self.assertRaises(HTTPException) as ctx:
            await presign_upload_get(current_user=user_dict, db=pool, redis=mock_redis, type="photo")
        self.assertEqual(ctx.exception.status_code, 429)

        # Media delete rate limit
        from app.routers.media import delete_media, reorder_media
        from app.models.schemas.user import ReorderMediaBody, MediaPositionItem
        with self.assertRaises(HTTPException) as ctx:
            await delete_media(media_id=uuid.uuid4(), current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Media reorder rate limit
        reorder_payload = ReorderMediaBody(positions=[MediaPositionItem(media_id=uuid.uuid4(), position=1)])
        with self.assertRaises(HTTPException) as ctx:
            await reorder_media(body=reorder_payload, current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Feed daily-compatible rate limit
        from app.routers.feed import get_daily_compatible
        with self.assertRaises(HTTPException) as ctx:
            await get_daily_compatible(current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Chats mark_read rate limit
        from app.routers.chats import mark_read, unmatch_chat
        chat_id = uuid.uuid4()
        with self.assertRaises(HTTPException) as ctx:
            await mark_read(chat_id=chat_id, current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Chats unmatch rate limit
        with self.assertRaises(HTTPException) as ctx:
            await unmatch_chat(chat_id=chat_id, current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        # Interactions matches and liked_me rate limits
        from app.routers.interactions import get_my_matches, get_users_who_liked_me
        with self.assertRaises(HTTPException) as ctx:
            await get_my_matches(current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

        with self.assertRaises(HTTPException) as ctx:
            await get_users_who_liked_me(current_user=user_dict, db=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_o1_chat_moderation_nfkd_diacritics_and_original_masking(self):
        """O-1: NFKD combining diacritics normalized correctly and original string characters masked."""
        from app.services.chat_safety_filter import filter_chat_content
        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Combining accent mark sequence: 'i' + '\u0301' and 'a' + '\u0300'
        content_decomposed = "call me on i\u0301nsta\u0300 now"
        res = await filter_chat_content(content_decomposed, chat_id, user_id, None)
        self.assertTrue(res.is_moderated)
        self.assertEqual(res.content, "call me on ####### now")

        # Precomposed unicode characters: 'í' and 'à'
        content_precomposed = "call me on \u00ednst\u00e0 now"
        res2 = await filter_chat_content(content_precomposed, chat_id, user_id, None)
        self.assertTrue(res2.is_moderated)
        self.assertEqual(res2.content, "call me on ##### now")

    async def test_o2_media_processor_rejects_oversized_upload(self):
        """O-2: Media processor checks actual S3 ContentLength and rejects oversized upload."""
        from app.services.media_processor import _run_moderation
        pool, conn = _make_mock_pool()
        media_id = uuid.uuid4()

        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {"ContentLength": 15 * 1024 * 1024}

        with patch("boto3.client", return_value=mock_s3), \
             patch("app.services.media_processor.get_pool", return_value=pool), \
             patch("app.services.media_processor._delete_from_quarantine") as mock_del:
            await _run_moderation(media_id, "uploads/user/photo/test.jpg", "photo", uuid.uuid4())

            update_sql = conn.execute.call_args[0][0]
            self.assertIn("UPDATE user_media", update_sql)
            self.assertIn("SET status = 'rejected'", update_sql)
            self.assertIn("exceeds maximum allowed limit", conn.execute.call_args[0][1])
            mock_del.assert_called_once_with("uploads/user/photo/test.jpg")

    def test_o3_copy_to_production_refuses_unstripped_photo_fallback(self):
        """O-3: _copy_to_production registers pillow-heif and raises ValueError if photo sanitization fails."""
        from app.services.media_processor import _copy_to_production
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"corrupt_photo_bytes"))}

        with patch("boto3.client", return_value=mock_s3):
            with self.assertRaises(ValueError) as ctx:
                _copy_to_production("quarantine/pic.heic", "prod/pic.webp", "photo")
            self.assertIn("Failed to strip EXIF/GPS metadata from photo", str(ctx.exception))
            mock_s3.copy_object.assert_not_called()

    async def test_o4_payment_amount_reverification(self):
        """O-4: process_payment_captured and verify_payment re-verify amounts against plan catalogue price."""
        from app.services.payment_service import process_payment_captured
        from app.routers.subscriptions import verify_payment
        from app.models.schemas.payment import VerifyPaymentBody
        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()

        # 1. process_payment_captured rejects mismatched intent amount
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "gold_monthly",
            "status": "created",
            "amount": 100,
        }
        with self.assertRaises(ValueError) as ctx:
            await process_payment_captured(
                event={"payload": {"payment": {"entity": {"order_id": "order_123", "id": "pay_123", "amount": 29900}}}},
                pool=pool,
            )
        self.assertIn("does not match plan price", str(ctx.exception))

        # 2. process_payment_captured rejects mismatched captured amount
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "gold_monthly",
            "status": "created",
            "amount": 29900,
        }
        with self.assertRaises(ValueError) as ctx:
            await process_payment_captured(
                event={"payload": {"payment": {"entity": {"order_id": "order_123", "id": "pay_123", "amount": 100}}}},
                pool=pool,
            )
        self.assertIn("does not match expected plan price", str(ctx.exception))

        # 3. verify_payment rejects intent amount mismatch
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "gold_monthly",
            "status": "created",
            "amount": 999,
        }
        body = VerifyPaymentBody(razorpay_order_id="order_123", razorpay_payment_id="pay_123", razorpay_signature="sig_123")
        with self.assertRaises(HTTPException) as ctx:
            await verify_payment(body=body, current_user={"user_id": user_id}, pool=pool)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("mismatch with plan price", ctx.exception.detail)

    async def test_o5_refresh_token_concurrency_grace_and_theft(self):
        """O-5: Refresh token race returns cached token during grace window; theft detected post-lock."""
        from app.routers.auth import refresh_token_endpoint
        from app.models.schemas.auth import TokenRefreshBody
        import json, hashlib

        pool, conn = _make_mock_pool()
        user_id = uuid.uuid4()
        token = "test_refresh_token_123"
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.set = AsyncMock()

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Case 1: Within 15s grace window, return cached payload without error
        grace_data = {"access_token": "acc_grace", "refresh_token": "ref_grace", "expires_in": 900}
        mock_redis.get = AsyncMock(side_effect=lambda k: json.dumps(grace_data).encode() if f"auth:grace_rt:{token_hash}" in k else None)

        res = await refresh_token_endpoint(TokenRefreshBody(refresh_token=token), mock_request, pool, mock_redis)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["access_token"], "acc_grace")

        # Case 2: Past grace window, revoked token triggers all-session revocation and 401
        mock_redis.get = AsyncMock(side_effect=lambda k: str(user_id).encode() if f"auth:revoked_rt:{token_hash}" in k else None)
        with self.assertRaises(HTTPException) as ctx:
            await refresh_token_endpoint(TokenRefreshBody(refresh_token=token), mock_request, pool, mock_redis)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Refresh token reuse detected", ctx.exception.detail)
        conn.execute.assert_any_call("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)

    async def test_o6_interaction_action_blocked_user_forbidden(self):
        """O-6: record_interaction_action rejects like/pass/super_connect with blocked user (403)."""
        from app.routers.interactions import record_interaction_action
        from app.models.schemas.interaction import InteractionActionRequest
        pool, conn = _make_mock_pool()
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()

        # user_blocks check returns 1 (blocked exists)
        conn.fetchval.return_value = 1

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
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cannot interact with a blocked user", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()


