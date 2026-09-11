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
        conn.fetch = AsyncMock(return_value=[])
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

    async def test_06_admin_report_resolution_invalidates_tokens_and_session(self):
        """Verify resolve_report deletes refresh tokens and Redis sessions when user is banned (BUG-045)."""
        from app.routers.admin import resolve_report, ResolveReportBody
        reported_id = uuid.uuid4()
        report_id = uuid.uuid4()
        admin_dict = {"user_id": uuid.uuid4(), "admin_role": "superadmin"}

        executed_sqls = []
        class DummyTransaction:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_conn = MagicMock()
        mock_conn.transaction = MagicMock(return_value=DummyTransaction())
        mock_conn.fetchrow = AsyncMock(return_value={"id": report_id, "reported_id": reported_id, "resolved": False})
        async def fake_exec(sql, *args):
            executed_sqls.append((sql, args))
            return "UPDATE 1"
        mock_conn.execute = AsyncMock(side_effect=fake_exec)

        class MockAcquire:
            async def __aenter__(self):
                return mock_conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=MockAcquire())

        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock()

        with patch("app.routers.admin.get_redis", return_value=mock_redis), \
             patch("app.routers.admin.recompute_trust_score", new_callable=AsyncMock):
            body = ResolveReportBody(action_taken="banned", notes="TOS violation")
            res = await resolve_report(report_id=report_id, body=body, admin=admin_dict, pool=mock_pool)

        self.assertTrue(res["resolved"])
        token_deletes = [s for s, a in executed_sqls if "DELETE FROM refresh_tokens" in s]
        self.assertTrue(len(token_deletes) > 0, "DELETE FROM refresh_tokens was not executed!")
        mock_redis.delete.assert_awaited()

    async def test_07_dilemma_feed_cursor_pagination(self):
        """Verify get_dilemma_feed uses keyset pagination when cursor is supplied (BUG-050)."""
        from app.routers.arcade import get_dilemma_feed
        user_dict = {"user_id": uuid.uuid4()}
        mock_rows = [
            {"id": uuid.uuid4(), "question_text": "Q1", "option_a": "A", "option_b": "B", "tags": [], "total_votes_a": 10, "total_votes_b": 5, "user_choice": "a"}
        ]
        executed_sqls = []
        mock_conn = MagicMock()
        async def fake_fetch(sql, *args):
            executed_sqls.append(sql)
            return mock_rows
        mock_conn.fetch = AsyncMock(side_effect=fake_fetch)

        class MockAcquire:
            async def __aenter__(self):
                return mock_conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=MockAcquire())

        cursor_str = "2026-09-01T12:00:00Z"
        res = await get_dilemma_feed(current_user=user_dict, pool=mock_pool, cursor=cursor_str, limit=10)
        self.assertEqual(len(res), 1)
        self.assertTrue(any("d.created_at < $2" in s for s in executed_sqls), "Cursor condition missing from query")

    async def test_08_presign_upload_get_max_limits(self):
        """Verify presign_upload_get sets file_size_bytes to 10MB for photo and 5MB for voice (BUG-055)."""
        from app.routers.media import presign_upload_get, _MAX_PHOTO_BYTES, _MAX_VOICE_BYTES
        mock_user = {"id": uuid.uuid4()}
        mock_db = MagicMock()
        mock_redis = MagicMock()

        captured_requests = []
        async def fake_request_upload(body, user, db, redis):
            captured_requests.append(body)
            from app.routers.media import UploadRequestResponse
            return UploadRequestResponse(media_id=uuid.uuid4(), presigned_url="https://s3...", s3_key="test")

        with patch("app.routers.media.request_upload", side_effect=fake_request_upload):
            await presign_upload_get(current_user=mock_user, db=mock_db, redis=mock_redis, type="photo")
            await presign_upload_get(current_user=mock_user, db=mock_db, redis=mock_redis, type="voice")

        self.assertEqual(len(captured_requests), 2)
        self.assertEqual(captured_requests[0].file_size_bytes, _MAX_PHOTO_BYTES)
        self.assertEqual(captured_requests[1].file_size_bytes, _MAX_VOICE_BYTES)

    def test_09_notification_worker_send_daily_digest_multicast_batching(self):
        """Verify send_daily_digest batches tokens via send_push_multicast in chunks of 500 (BUG-051)."""
        from app.workers.notification_worker import send_daily_digest
        mock_rows = [
            {"fcm_token": f"token_{i}", "like_count": 3}
            for i in range(1200)
        ]
        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.close = AsyncMock()

        multicast_calls = []
        async def fake_multicast(tokens, title, body, data, db_conn=None):
            multicast_calls.append(tokens)
            return {"success": len(tokens), "failure": 0}

        with patch("app.workers.notification_worker._get_conn", new_callable=AsyncMock, return_value=mock_conn), \
             patch("app.workers.notification_worker.send_push_multicast", side_effect=fake_multicast):
            send_daily_digest()

        # 1200 tokens with like_count=3 should be split into batches of 500, 500, 200
        self.assertEqual(len(multicast_calls), 3)
        self.assertEqual(len(multicast_calls[0]), 500)
        self.assertEqual(len(multicast_calls[1]), 500)
        self.assertEqual(len(multicast_calls[2]), 200)

    async def test_10_celery_worker_pooled_connection_proxy(self):
        """Verify PooledConnectionProxy delegates methods and releases connection back to pool on close (BUG-053)."""
        from app.workers.worker_pool import PooledConnectionProxy
        mock_raw_conn = MagicMock()
        mock_raw_conn.fetchrow = AsyncMock(return_value={"val": 42})
        mock_pool = MagicMock()
        mock_pool.release = AsyncMock()

        proxy = PooledConnectionProxy(mock_raw_conn, mock_pool)
        res = await proxy.fetchrow("SELECT 42")
        self.assertEqual(res["val"], 42)

        await proxy.close()
        mock_pool.release.assert_awaited_once_with(mock_raw_conn)

    async def test_11_list_chats_uses_lateral_join_for_photo(self):
        """Verify list_chats uses LATERAL JOIN for photos avoiding correlated N+1 subqueries (BUG-048)."""
        from app.routers.chats import list_chats
        current_user = {"id": uuid.uuid4()}
        chat_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        match_id = uuid.uuid4()

        mock_rows = [
            {
                "id": chat_id,
                "match_id": match_id,
                "is_ephemeral": False,
                "expires_at": None,
                "other_user_id": other_user_id,
                "other_user_first_name": "Riya",
                "other_user_photo_url": "https://cdn.jainune.com/riya.jpg",
                "last_message_text": "Namaste",
                "last_message_at": None,
                "unread_count": 0,
            }
        ]

        executed_sqls = []
        mock_conn = MagicMock()
        async def fake_fetch(sql, *args):
            executed_sqls.append(sql)
            return mock_rows
        mock_conn.fetch = AsyncMock(side_effect=fake_fetch)

        class MockAcquire:
            async def __aenter__(self):
                return mock_conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_db = MagicMock()
        mock_db.acquire = MagicMock(return_value=MockAcquire())

        resp = await list_chats(current_user=current_user, db=mock_db)
        self.assertEqual(len(resp.threads), 1)
        self.assertEqual(resp.threads[0].other_user_first_name, "Riya")
        self.assertEqual(resp.threads[0].other_user_photo_url, "https://cdn.jainune.com/riya.jpg")
        self.assertEqual(len(executed_sqls), 1)
        self.assertIn("LEFT JOIN LATERAL", executed_sqls[0])
        self.assertIn("user_media", executed_sqls[0])

    async def test_12_admin_broadcast_rate_limit_fail_closed(self):
        """Verify admin trigger_campaign_broadcast fails closed (503) if rate limit/Redis fails (BUG-056)."""
        from app.routers.admin import trigger_campaign_broadcast, BroadcastCampaignBody
        from fastapi import HTTPException

        admin_dict = {"user_id": uuid.uuid4(), "admin_role": "superadmin"}
        body = BroadcastCampaignBody(
            campaign_name="special_event",
            title="Special Event",
            message="Join our community meetup tonight!",
            channels=["email"],
            target_segment="free",
        )

        with patch("app.routers.admin.get_redis", side_effect=Exception("Redis connection error")):
            with self.assertRaises(HTTPException) as ctx:
                await trigger_campaign_broadcast(body=body, admin=admin_dict, pool=MagicMock())
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("Rate limiting unavailable", ctx.exception.detail)

    def test_13_migration_0016_0018_and_maintenance_scripts(self):
        """Verify migration 0016, 0018, and maintenance scripts (BUG-060, BUG-061)."""
        from pathlib import Path

        base_dir = Path(__file__).resolve().parent.parent.parent
        mig_16 = base_dir / "migrations" / "0016_concurrent_spatial_and_vector_maintenance.sql"
        mig_18 = base_dir / "migrations" / "0018_interactions_actor_target_unique_constraint.sql"
        maint_script = base_dir / "scripts" / "maintenance" / "reindex_concurrent.sql"

        self.assertTrue(mig_16.exists(), "Migration 0016 not found")
        content_16 = mig_16.read_text(encoding="utf-8")
        self.assertIn("CREATE INDEX CONCURRENTLY", content_16)
        self.assertNotIn("BEGIN;", content_16)
        self.assertNotIn("COMMIT;", content_16)

        self.assertTrue(maint_script.exists(), "Maintenance script reindex_concurrent.sql not found")
        content_maint = maint_script.read_text(encoding="utf-8")
        self.assertIn("REINDEX INDEX CONCURRENTLY", content_maint)

        self.assertTrue(mig_18.exists(), "Migration 0018 not found")
        content_18 = mig_18.read_text(encoding="utf-8")
        self.assertIn("uq_interactions_actor_target", content_18)
        self.assertIn("UNIQUE (actor_id, target_id)", content_18)

    def test_14_migration_runner_handles_concurrently_without_transaction(self):
        """Verify run_migrations checks CONCURRENTLY / VACUUM (BUG-060)."""
        from pathlib import Path

        base_dir = Path(__file__).resolve().parent.parent.parent
        runner_file = base_dir / "run_migrations.py"
        self.assertTrue(runner_file.exists())
        content = runner_file.read_text(encoding="utf-8")
        self.assertIn('"CONCURRENTLY" in sql_content.upper()', content)


if __name__ == "__main__":
    unittest.main()


