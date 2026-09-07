"""
Unit tests for Deep Audit Round 6:
- Stable Marriage strict 1-to-1 matching without duplicate user allocations
- Account service purge deleting all 6 match column aliases & chat aliases
- Account service soft delete unmatching active matches and chats
- User DPDP Act 2023 machine-readable personal data export
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

for mod in ["asyncpg", "redis", "redis.asyncio", "boto3", "botocore", "botocore.exceptions", "celery", "celery.schedules"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from app.services.stable_marriage import StableMarriageEngine
from app.services.account_service import purge_user_account, soft_delete_user_account
from app.routers.users import export_my_data


class TestDeepAuditRound6Hardening(unittest.IsolatedAsyncioTestCase):

    def test_01_stable_marriage_strict_one_to_one(self):
        """Verify StableMarriageEngine guarantees strict 1-to-1 matching without duplicate participants."""
        engine = StableMarriageEngine()
        users = [
            {"id": "user1", "gender": "man", "show_me": "women"},
            {"id": "user2", "gender": "man", "show_me": "women"},
            {"id": "user3", "gender": "woman", "show_me": "men"},
            {"id": "user4", "gender": "woman", "show_me": "men"},
        ]
        # Both user1 and user2 strongly prefer user3, then user4
        feed_queues = {
            "user1": ["user3", "user4"],
            "user2": ["user3", "user4"],
            "user3": ["user1", "user2"],
            "user4": ["user1", "user2"],
        }
        proposals = engine.compute(users, feed_queues)
        self.assertGreater(len(proposals), 0)

        # Check that no user appears more than once across all proposal pairs
        seen_users = set()
        for prop in proposals:
            u_a = prop["user_a"]
            u_b = prop["user_b"]
            self.assertNotIn(u_a, seen_users, f"User {u_a} paired multiple times!")
            self.assertNotIn(u_b, seen_users, f"User {u_b} paired multiple times!")
            seen_users.add(u_a)
            seen_users.add(u_b)

    def test_02_stable_marriage_sorted_by_score_descending(self):
        """Verify returned proposals are sorted by score descending."""
        engine = StableMarriageEngine()
        users = [
            {"id": "m1", "gender": "man", "show_me": "women"},
            {"id": "m2", "gender": "man", "show_me": "women"},
            {"id": "w1", "gender": "woman", "show_me": "men"},
            {"id": "w2", "gender": "woman", "show_me": "men"},
        ]
        feed_queues = {
            "m1": ["w1"],
            "m2": ["w2"],
            "w1": ["m1"],
            "w2": ["m2"],
        }
        proposals = engine.compute(users, feed_queues)
        scores = [p["score"] for p in proposals]
        self.assertEqual(scores, sorted(scores, reverse=True))

    async def test_03_account_purge_cleanses_all_match_and_chat_aliases(self):
        """Verify purge_user_account executes SQL covering all 6 match aliases and 4 chat aliases."""
        user_id = uuid.uuid4()
        executed_sqls = []

        class DummyTransaction:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"phone_number": "+919876543210", "email": "test@jainune.com"})
        conn.fetch = AsyncMock(return_value=[{"s3_key": "photos/test.jpg"}])
        conn.transaction = MagicMock(return_value=DummyTransaction())

        async def fake_execute(sql, *args):
            executed_sqls.append(sql)
            return "DELETE 1"

        conn.execute = AsyncMock(side_effect=fake_execute)
        redis = MagicMock()
        redis.delete = AsyncMock()
        redis.scan_iter = MagicMock()

        async def empty_async_gen():
            if False:
                yield None

        redis.scan_iter.return_value = empty_async_gen()

        with patch("app.services.account_service._delete_s3_keys_sync"):
            result = await purge_user_account(user_id, conn, redis)

        self.assertEqual(result["status"], "purged")

        # Verify matches deletion query includes all aliases
        matches_sql = [s for s in executed_sqls if "DELETE FROM matches" in s]
        self.assertTrue(len(matches_sql) > 0, "DELETE FROM matches query not executed")
        m_sql = matches_sql[0]
        self.assertIn("user_a", m_sql)
        self.assertIn("user_b", m_sql)
        self.assertIn("user_id_1", m_sql)
        self.assertIn("user_id_2", m_sql)
        self.assertIn("user_a_id", m_sql)
        self.assertIn("user_b_id", m_sql)

        # Verify chats deletion query includes participant aliases
        chats_sql = [s for s in executed_sqls if "DELETE FROM chats" in s]
        self.assertTrue(len(chats_sql) > 0, "DELETE FROM chats query not executed")
        c_sql = chats_sql[0]
        self.assertIn("participant_a", c_sql)
        self.assertIn("participant_b", c_sql)
        self.assertIn("participant_1_id", c_sql)
        self.assertIn("participant_2_id", c_sql)

    async def test_04_account_soft_delete_unmatches_matches_and_chats(self):
        """Verify soft_delete_user_account sets matches status='unmatched' and chats is_unmatched=TRUE."""
        user_id = uuid.uuid4()
        executed_sqls = []

        class DummyTransaction:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"phone_number": "+919876543210", "email": "test@jainune.com"})
        conn.transaction = MagicMock(return_value=DummyTransaction())

        async def fake_execute(sql, *args):
            executed_sqls.append(sql)
            return "UPDATE 1"

        conn.execute = AsyncMock(side_effect=fake_execute)
        redis = MagicMock()
        redis.delete = AsyncMock()

        result = await soft_delete_user_account(user_id, conn, redis)
        self.assertEqual(result["status"], "soft_deleted")

        # Verify matches update sets unmatched
        match_updates = [s for s in executed_sqls if "UPDATE matches" in s and "status = 'unmatched'" in s]
        self.assertTrue(len(match_updates) > 0, "Matches not set to unmatched during soft delete")

        # Verify chats update sets is_unmatched = TRUE
        chat_updates = [s for s in executed_sqls if "UPDATE chats" in s and "is_unmatched = TRUE" in s]
        self.assertTrue(len(chat_updates) > 0, "Chats not marked is_unmatched = TRUE during soft delete")

    async def test_05_dpdp_data_export_structure(self):
        """Verify GET /v1/users/me/export returns machine-readable personal data with DPDP metadata."""
        user_id = uuid.uuid4()
        mock_user = {"user_id": user_id}

        mock_profile = {
            "id": user_id,
            "phone_number": "+919876543210",
            "email": "user@example.com",
            "first_name": "Aarav",
            "subscription_tier": "gold",
        }
        mock_prompts = [{"prompt_key": "favorite_jain_dish", "response_text": "Khichdi", "position": 1}]
        mock_media = [{"id": uuid.uuid4(), "media_type": "photo", "cdn_url": "https://cdn.jainune.com/1.jpg"}]
        mock_blocks = [{"blocked_id": uuid.uuid4(), "reason": "harassment"}]
        mock_wallet = {"available_spins": 5, "available_dice_rolls": 2}

        class MockAcquire:
            async def __aenter__(self):
                mock_conn = MagicMock()
                mock_conn.fetchrow = AsyncMock(side_effect=[mock_profile, mock_wallet])
                mock_conn.fetch = AsyncMock(side_effect=[mock_prompts, mock_media, mock_blocks])
                return mock_conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=MockAcquire())

        res = await export_my_data(current_user=mock_user, pool=mock_pool)
        self.assertIn("export_metadata", res)
        self.assertEqual(res["export_metadata"]["compliance"], "DPDP Act 2023 / Digital Personal Data Protection")
        self.assertEqual(res["profile"]["first_name"], "Aarav")
        self.assertEqual(len(res["prompts"]), 1)
        self.assertEqual(len(res["media"]), 1)
        self.assertEqual(len(res["blocks"]), 1)
        self.assertEqual(res["arcade_wallet"]["available_spins"], 5)


if __name__ == "__main__":
    unittest.main()
