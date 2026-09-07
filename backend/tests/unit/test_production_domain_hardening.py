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


if __name__ == "__main__":
    unittest.main()


