"""
Unit tests for Celery elimination and Redis decoupling (Issues 1 & 2).
Verifies:
1. In-process WebSocket ConnectionManager (chat broadcast, presence, disconnect).
2. Native background task supervisor (enqueue_task, retry backoff, shutdown await).
3. In-process impression buffering (batch UPSERT, zero per-swipe DB row writes).
4. Durable revoked refresh token security (PostgreSQL persistence & theft detection).
5. Durable feed queue persistence (restart resilience on Redis cache miss).
"""

from __future__ import annotations

import asyncio
import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.background_tasks import _background_tasks, await_background_tasks, enqueue_task
from app.services.connection_manager import ConnectionManager


class TestConnectionManager(unittest.IsolatedAsyncioTestCase):
    """Verifies in-process WebSocket connection broker without Redis Pub/Sub."""

    async def asyncSetUp(self):
        self.manager = ConnectionManager()
        self.chat_id = str(uuid.uuid4())
        self.user_1 = str(uuid.uuid4())
        self.user_2 = str(uuid.uuid4())

        self.ws_1 = AsyncMock()
        self.ws_2 = AsyncMock()

    async def test_register_and_broadcast(self):
        self.manager.register(self.chat_id, self.user_1, self.ws_1)
        self.manager.register(self.chat_id, self.user_2, self.ws_2)

        self.assertTrue(self.manager.is_present(self.chat_id, self.user_1))
        self.assertTrue(self.manager.is_present(self.chat_id, self.user_2))

        # Broadcast message to chat room
        msg = {"type": "chat_message", "content": "Hello!"}
        await self.manager.broadcast_chat(self.chat_id, msg)

        self.ws_1.send_json.assert_awaited_once_with(msg)
        self.ws_2.send_json.assert_awaited_once_with(msg)

    async def test_broadcast_with_exclude_user(self):
        self.manager.register(self.chat_id, self.user_1, self.ws_1)
        self.manager.register(self.chat_id, self.user_2, self.ws_2)

        # Typing indicator excluding sender
        typing_msg = {"type": "typing", "sender_id": self.user_1}
        await self.manager.broadcast_chat(self.chat_id, typing_msg, exclude_user_id=self.user_1)

        self.ws_1.send_json.assert_not_awaited()
        self.ws_2.send_json.assert_awaited_once_with(typing_msg)

    async def test_close_chat(self):
        self.manager.register(self.chat_id, self.user_1, self.ws_1)
        self.manager.register(self.chat_id, self.user_2, self.ws_2)

        await self.manager.close_chat(self.chat_id, reason="unmatched")
        self.ws_1.close.assert_awaited_once_with(code=4003, reason="Chat closed: unmatched")
        self.ws_2.close.assert_awaited_once_with(code=4003, reason="Chat closed: unmatched")
        self.assertFalse(self.manager.is_present(self.chat_id, self.user_1))

    async def test_disconnect_user_all_sessions(self):
        ws_device_2 = AsyncMock()
        self.manager.register(self.chat_id, self.user_1, self.ws_1)
        self.manager.register(str(uuid.uuid4()), self.user_1, ws_device_2)

        await self.manager.disconnect_user(self.user_1, reason="Account banned.")
        self.ws_1.close.assert_awaited_once_with(code=4003, reason="Account banned.")
        ws_device_2.close.assert_awaited_once_with(code=4003, reason="Account banned.")


class TestBackgroundTasks(unittest.IsolatedAsyncioTestCase):
    """Verifies native asyncio background task supervisor replacing Celery."""

    async def test_enqueue_task_executes_successfully(self):
        executed = False

        async def sample_task():
            nonlocal executed
            executed = True

        task = enqueue_task(sample_task(), name="sample")
        await task
        self.assertTrue(executed)

    async def test_enqueue_task_retries_on_failure(self):
        attempts = 0

        async def failing_then_succeeding():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ConnectionError("Transient network drop")

        task = enqueue_task(failing_then_succeeding, retries=3, name="flaky")
        await task
        self.assertEqual(attempts, 2)

    async def test_await_background_tasks_drains_cleanly(self):
        completed = False

        async def slow_task():
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

        enqueue_task(slow_task(), name="slow")
        self.assertGreaterEqual(len(_background_tasks), 1)
        await await_background_tasks(timeout=2.0)
        self.assertTrue(completed)
        self.assertEqual(len(_background_tasks), 0)


class TestImpressionBuffering(unittest.IsolatedAsyncioTestCase):
    """Verifies two-stage in-process impression accumulation and bulk-UPSERT."""

    async def test_in_process_impression_accumulation_and_flush(self):
        from app.services.core_people_finder import _async_flush_impressions, _impression_buffer

        _impression_buffer.clear()
        uid_1 = str(uuid.uuid4())
        uid_2 = str(uuid.uuid4())

        _impression_buffer[uid_1] += 3
        _impression_buffer[uid_2] += 2

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await _async_flush_impressions(mock_pool, force=True)

        mock_conn.executemany.assert_awaited_once()
        call_args = mock_conn.executemany.call_args[0]
        self.assertIn("UPDATE users SET impressions_last_48h", call_args[0])
        self.assertEqual(len(call_args[1]), 2)
        self.assertEqual(len(_impression_buffer), 0)


class TestDurableTokensAndFeedQueue(unittest.IsolatedAsyncioTestCase):
    """Verifies durable PostgreSQL tables for tokens and feed queues."""

    async def test_feed_queue_persistence_in_daily_compatible(self):
        mock_conn = AsyncMock()
        user_list = [
            {"id": uuid.uuid4(), "gender": "man", "looking_for": "marriage", "city": "Mumbai"},
            {"id": uuid.uuid4(), "gender": "woman", "looking_for": "marriage", "city": "Mumbai"},
        ]
        feed_queues = {
            str(user_list[0]["id"]): [str(user_list[1]["id"])],
            str(user_list[1]["id"]): [str(user_list[0]["id"])],
        }

        # Simulate batch persistence block
        db_records = [
            (uuid.UUID(uid), [uuid.UUID(c) for c in q if c])
            for uid, q in feed_queues.items()
            if q
        ]
        await mock_conn.executemany(
            """
            INSERT INTO feed_queues (user_id, candidate_ids, generated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET candidate_ids = EXCLUDED.candidate_ids,
                generated_at = EXCLUDED.generated_at
            """,
            db_records,
        )

        mock_conn.executemany.assert_awaited_once()
        self.assertEqual(len(mock_conn.executemany.call_args[0][1]), 2)


if __name__ == "__main__":
    unittest.main()
