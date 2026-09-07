"""
Unit tests for Round 3 deep audit hardening fixes:
1. WebSocket authorization checks (banned/suspended/deleted users).
2. Notification worker match joins with user_a / user_b COALESCE.
3. Media reorder atomic CASE statement & duplicate validation.
4. Admin ban/suspend/reinstate 404 checks & session token revocation.
5. Chat safety single-char sequence reset on multi-character messages.
6. Chat message rejection for banned recipients.
7. User prompt update duplicate validation.
8. Location verification coordinate persistence.
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
if "boto3" not in sys.modules:
    sys.modules["boto3"] = MagicMock()
if "botocore" not in sys.modules:
    sys.modules["botocore"] = MagicMock()
if "botocore.config" not in sys.modules:
    sys.modules["botocore.config"] = MagicMock()
if "botocore.exceptions" not in sys.modules:
    sys.modules["botocore.exceptions"] = MagicMock()
if "celery" not in sys.modules:
    mock_celery = MagicMock()
    mock_celery_app = MagicMock()
    mock_celery_app.task = lambda *args, **kwargs: (lambda fn: fn)
    mock_celery.Celery.return_value = mock_celery_app
    sys.modules["celery"] = mock_celery
if "celery.schedules" not in sys.modules:
    sys.modules["celery.schedules"] = MagicMock()

import app.celery_app
app.celery_app.celery_app.task = lambda *args, **kwargs: (lambda fn: fn)

import app.workers.notification_worker
import app.routers.websockets
import app.routers.media
import app.routers.admin
import app.routers.chats
import app.routers.location

from fastapi import HTTPException


def _mock_async_conn():
    conn = AsyncMock()
    tx_mock = MagicMock()
    tx_mock.__aenter__ = AsyncMock(return_value=None)
    tx_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_mock)
    return conn


class TestRound3DeepAuditHardening(unittest.IsolatedAsyncioTestCase):

    # -------------------------------------------------------------------------
    # 1. WebSocket Authorization & Account Status
    # -------------------------------------------------------------------------
    @patch("app.routers.websockets.get_redis")
    @patch("app.routers.websockets.get_pool")
    async def test_websocket_rejects_banned_caller(self, mock_pool, mock_get_redis):
        from app.routers.websockets import websocket_chat

        user_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        mock_ws = AsyncMock()
        mock_ws.headers = {}

        mock_redis = AsyncMock()
        mock_redis.get.return_value = str(user_id).encode()
        mock_get_redis.return_value = mock_redis

        mock_db = MagicMock()
        mock_conn = _mock_async_conn()
        mock_conn.fetchrow.side_effect = [
            {"account_status": "banned", "suspend_until": None, "deleted_at": None},
        ]
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.return_value = mock_db

        await websocket_chat(websocket=mock_ws, chat_id=chat_id, ticket="valid_ticket")

        mock_ws.close.assert_called_with(code=4003, reason="Account is banned or deleted.")

    @patch("app.routers.websockets.get_redis")
    @patch("app.routers.websockets.get_pool")
    async def test_websocket_rejects_suspended_caller(self, mock_pool, mock_get_redis):
        from app.routers.websockets import websocket_chat

        user_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        mock_ws = AsyncMock()
        mock_ws.headers = {}

        mock_redis = AsyncMock()
        mock_redis.get.return_value = str(user_id).encode()
        mock_get_redis.return_value = mock_redis

        mock_db = MagicMock()
        mock_conn = _mock_async_conn()
        suspend_until = datetime.now(timezone.utc) + timedelta(days=5)
        mock_conn.fetchrow.side_effect = [
            {"account_status": "active", "suspend_until": suspend_until, "deleted_at": None},
        ]
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.return_value = mock_db

        await websocket_chat(websocket=mock_ws, chat_id=chat_id, ticket="valid_ticket")

        mock_ws.close.assert_called_with(code=4003, reason="Account is suspended.")

    # -------------------------------------------------------------------------
    # 2. Notification Worker COALESCE Query
    # -------------------------------------------------------------------------
    @patch("app.workers.notification_worker._get_conn")
    @patch("app.workers.notification_worker.send_push", new_callable=AsyncMock)
    def test_notify_new_match_coalesces_user_a_and_b(self, mock_send_push, mock_get_conn):
        from app.workers.notification_worker import notify_new_match

        mock_conn = _mock_async_conn()
        mock_conn.fetchrow.return_value = {
            "name_a": "Aarav",
            "token_a": "token_aarav",
            "name_b": "Priya",
            "token_b": "token_priya",
        }
        mock_get_conn.return_value = mock_conn

        match_id = str(uuid.uuid4())
        notify_new_match(MagicMock(), match_id)

        call_args = mock_conn.fetchrow.call_args[0]
        query = call_args[0]
        self.assertIn("COALESCE(m.user_a, m.user_a_id, m.user_id_1)", query)
        self.assertIn("COALESCE(m.user_b, m.user_b_id, m.user_id_2)", query)
        self.assertEqual(mock_send_push.call_count, 2)

    # -------------------------------------------------------------------------
    # 3. Media Reorder Atomic Update & Duplicate Check
    # -------------------------------------------------------------------------
    async def test_reorder_media_rejects_duplicate_positions(self):
        from app.routers.media import reorder_media
        from app.models.schemas.user import ReorderMediaBody, MediaPositionItem

        m1, m2 = uuid.uuid4(), uuid.uuid4()
        body = ReorderMediaBody(positions=[
            MediaPositionItem(media_id=m1, position=1),
            MediaPositionItem(media_id=m2, position=1),  # duplicate pos 1
        ])
        current_user = {"id": uuid.uuid4()}
        mock_db = MagicMock()

        with self.assertRaises(HTTPException) as ctx:
            await reorder_media(body, current_user, mock_db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Duplicate positions", ctx.exception.detail)

    async def test_reorder_media_executes_atomic_case_update(self):
        from app.routers.media import reorder_media
        from app.models.schemas.user import ReorderMediaBody, MediaPositionItem

        m1, m2 = uuid.uuid4(), uuid.uuid4()
        body = ReorderMediaBody(positions=[
            MediaPositionItem(media_id=m1, position=2),
            MediaPositionItem(media_id=m2, position=1),
        ])
        user_id = uuid.uuid4()
        current_user = {"id": user_id}
        mock_db = MagicMock()
        mock_conn = _mock_async_conn()
        mock_db.acquire.return_value.__aenter__.return_value = mock_conn

        result = await reorder_media(body, current_user, mock_db)
        self.assertTrue(result["success"])
        executed_query = mock_conn.execute.call_args[0][0]
        self.assertIn("UPDATE user_media", executed_query)
        self.assertIn("SET position = CASE", executed_query)
        self.assertIn("AND media_type = 'photo'", executed_query)

    # -------------------------------------------------------------------------
    # 4. Admin Ban 404 Check & Session Revocation
    # -------------------------------------------------------------------------
    @patch("app.routers.admin.get_redis")
    async def test_admin_ban_raises_404_on_missing_user(self, mock_get_redis):
        from app.routers.admin import ban_user, BanBody

        user_id = uuid.uuid4()
        admin = {"user_id": uuid.uuid4()}
        body = BanBody(reason="Violated community safety policies")
        mock_pool = MagicMock()
        mock_conn = _mock_async_conn()
        mock_conn.execute.return_value = "UPDATE 0"
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        with self.assertRaises(HTTPException) as ctx:
            await ban_user(user_id, body, admin, mock_pool)
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("app.routers.admin.get_redis")
    async def test_admin_ban_revokes_refresh_tokens_and_cache(self, mock_get_redis):
        from app.routers.admin import ban_user, BanBody

        user_id = uuid.uuid4()
        admin = {"user_id": uuid.uuid4()}
        body = BanBody(reason="Violated community safety policies")
        mock_pool = MagicMock()
        mock_conn = _mock_async_conn()
        mock_conn.execute.return_value = "UPDATE 1"
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        result = await ban_user(user_id, body, admin, mock_pool)
        self.assertTrue(result["banned"])

        delete_token_calls = [c for c in mock_conn.execute.call_args_list if "DELETE FROM refresh_tokens" in c[0][0]]
        self.assertTrue(len(delete_token_calls) > 0)
        mock_redis.delete.assert_called_once()

    # -------------------------------------------------------------------------
    # 5. Chat Safety Filter Counter Reset
    # -------------------------------------------------------------------------
    async def test_chat_safety_resets_single_char_on_normal_message(self):
        from app.services.chat_safety_filter import filter_chat_content

        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_redis = AsyncMock()

        res = await filter_chat_content(
            content="Hello, how was your day?",
            chat_id=chat_id,
            user_id=user_id,
            redis=mock_redis,
        )
        self.assertFalse(res.is_moderated)
        mock_redis.delete.assert_called_once_with(f"chat:safety:single_chars:{chat_id}:{user_id}")

    # -------------------------------------------------------------------------
    # 6. Chat Rejection for Banned Recipient
    # -------------------------------------------------------------------------
    async def test_send_message_rejects_banned_recipient(self):
        from app.routers import chats
        from app.models.schemas.chat import SendMessageRequest

        user_id = uuid.uuid4()
        other_id = uuid.uuid4()
        chat_id = uuid.uuid4()

        with patch.object(chats, "_assert_participant", new_callable=AsyncMock) as mock_assert_part, \
             patch.object(chats, "get_effective_user_tier", new_callable=AsyncMock) as mock_tier, \
             patch.object(chats, "sliding_window_rate_limit", new_callable=AsyncMock) as mock_rate_limit:

            mock_assert_part.return_value = {
                "id": chat_id,
                "participant_1_id": user_id,
                "participant_2_id": other_id,
                "is_unmatched": False,
                "expires_at": None,
            }

            mock_db = MagicMock()
            mock_conn = _mock_async_conn()
            mock_conn.fetchval.side_effect = [None, "banned"]
            mock_db.acquire.return_value.__aenter__.return_value = mock_conn

            current_user = {"id": user_id}
            body = SendMessageRequest(message_type="text", content="Hey there")
            mock_redis = AsyncMock()

            with self.assertRaises(HTTPException) as ctx:
                await chats.send_message(chat_id, body, current_user, mock_db, mock_redis)
            self.assertEqual(ctx.exception.status_code, 410)
            self.assertIn("Recipient account is no longer active", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 7. UpdatePromptsBody Duplicate Validation
    # -------------------------------------------------------------------------
    def test_update_prompts_body_validates_uniqueness(self):
        from app.models.schemas.user import UpdatePromptsBody, PromptItem

        # Duplicate positions
        with self.assertRaises(ValueError):
            UpdatePromptsBody(prompts=[
                PromptItem(prompt_key="fav_food", response_text="Pappad and Khichdi", position=1),
                PromptItem(prompt_key="hobbies", response_text="Reading Jain philosophy", position=1),
            ])

        # Duplicate questions/keys
        with self.assertRaises(ValueError):
            UpdatePromptsBody(prompts=[
                PromptItem(prompt_key="fav_food", response_text="Pappad and Khichdi", position=1),
                PromptItem(prompt_key="fav_food", response_text="Different answer", position=2),
            ])

    # -------------------------------------------------------------------------
    # 8. Location Verification Persistence
    # -------------------------------------------------------------------------
    async def test_verify_location_persists_coordinates_in_zone(self):
        from app.routers import location
        from app.routers.location import VerifyLocationRequest

        with patch.object(location, "verify_location_anti_spoofing") as mock_spoof, \
             patch.object(location, "verify_location_zone") as mock_zone, \
             patch.object(location, "sliding_window_rate_limit", new_callable=AsyncMock) as mock_limit:

            mock_spoof.return_value = (True, None)
            mock_zone.return_value = (True, {
                "id": "mum_mmr",
                "name": "Mumbai MMR",
                "state": "Maharashtra",
                "distance_to_center_km": 5.2,
            })

            user_id = uuid.uuid4()
            current_user = {"id": user_id}
            body = VerifyLocationRequest(latitude=19.0760, longitude=72.8777)
            mock_request = MagicMock()
            mock_request.client.host = "1.2.3.4"
            mock_request.headers = {}
            mock_redis = AsyncMock()

            mock_pool = MagicMock()
            mock_conn = _mock_async_conn()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

            res = await location.verify_location(body, mock_request, mock_redis, current_user, mock_pool)
            self.assertTrue(res["data"]["allowed"])

            execute_calls = [c for c in mock_conn.execute.call_args_list if "UPDATE users" in c[0][0]]
            self.assertTrue(len(execute_calls) > 0)
            self.assertIn("ST_SetSRID(ST_MakePoint($1, $2), 4326)", execute_calls[0][0][0])


if __name__ == "__main__":
    unittest.main()
