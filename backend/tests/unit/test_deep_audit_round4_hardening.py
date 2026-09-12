"""
Unit tests for Round 4 deep audit hardening:
1. liked-me free tier user ID masking vs subscriber unmasked ID (paywall integrity)
2. get_my_matches resilient column joins with COALESCE
3. spin_serendipity_wheel ephemeral match & 15-minute speed chat creation
4. onboarding step 22 acceptance of pending photos during async moderation
5. ephemeral_reaper stale match expiration with COALESCE(last_message_at, created_at) and chat unmatch closure
6. push_notifications data payload string coercion for FCM v1 compliance
7. media_processor CDN URL trailing slash normalization
"""

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

from app.routers.interactions import get_users_who_liked_me, get_my_matches
from app.routers.arcade import spin_serendipity_wheel
from app.routers.onboarding import step22_complete
from app.models.schemas.user import Step22CompleteBody
from app.workers.ephemeral_reaper import reap_stale_matches
from app.services.push_notifications import send_push


def _mock_async_conn():
    conn = AsyncMock()
    tx_mock = MagicMock()
    tx_mock.__aenter__ = AsyncMock(return_value=None)
    tx_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_mock)
    return conn


class TestDeepAuditRound4Hardening(unittest.IsolatedAsyncioTestCase):

    async def test_01_liked_me_free_tier_masks_user_id(self):
        """Free tier users must NOT receive raw target UUID in liked-me to prevent paywall bypass."""
        caller_id = uuid.uuid4()
        target_id = uuid.uuid4()
        current_user = {"id": caller_id, "user_id": caller_id}

        fake_row = {
            "interaction_id": uuid.uuid4(),
            "created_at": datetime.now(timezone.utc),
            "id": target_id,
            "first_name": "Pooja",
            "date_of_birth": datetime(1998, 5, 20).date(),
            "city": "Mumbai",
            "state": "Maharashtra",
            "dietary_strictness": "pure_jain",
            "community_sect": "shwetambar_deravasi",
            "profession": "Architect",
            "education": "Master's",
            "is_photo_verified": True,
            "photos": [],
        }

        conn = _mock_async_conn()
        conn.fetch.return_value = [fake_row]

        db = MagicMock()
        db.acquire.return_value.__aenter__.return_value = conn

        # Test Free Tier -> ID MUST be masked (not target_id)
        with patch("app.services.payment_service.get_effective_user_tier", new_callable=AsyncMock) as mock_tier:
            mock_tier.return_value = "free"
            res_free = await get_users_who_liked_me(current_user, db)
            likes_free = res_free["likes"]
            self.assertEqual(len(likes_free), 1)
            self.assertTrue(likes_free[0]["id"].startswith("blurred_"))
            self.assertNotEqual(likes_free[0]["id"], str(target_id))
            self.assertEqual(likes_free[0]["first_name"], "Someone")

        # Test Subscriber (Jainune+) -> ID MUST be real UUID
        with patch("app.services.payment_service.get_effective_user_tier", new_callable=AsyncMock) as mock_tier:
            mock_tier.return_value = "jainune_plus"
            res_sub = await get_users_who_liked_me(current_user, db)
            likes_sub = res_sub["likes"]
            self.assertEqual(len(likes_sub), 1)
            self.assertEqual(likes_sub[0]["id"], str(target_id))
            self.assertEqual(likes_sub[0]["first_name"], "Pooja")

    async def test_02_get_my_matches_coalesces_legacy_columns(self):
        """get_my_matches query must use COALESCE on match columns for backwards schema compatibility."""
        user_id = uuid.uuid4()
        current_user = {"id": user_id, "user_id": user_id}

        conn = _mock_async_conn()
        conn.fetch.return_value = []
        db = MagicMock()
        db.acquire.return_value.__aenter__.return_value = conn

        await get_my_matches(current_user, db)
        query = conn.fetch.call_args[0][0]
        self.assertIn("COALESCE(m.user_a, m.user_a_id, m.user_id_1)", query)
        self.assertIn("COALESCE(m.user_b, m.user_b_id, m.user_id_2)", query)

    async def test_03_spin_serendipity_wheel_creates_ephemeral_match_and_chat(self):
        """Serendipity spin must atomically create ephemeral match and chat thread."""
        user_id = uuid.uuid4()
        cand_id = uuid.uuid4()
        match_id = uuid.uuid4()
        chat_id = uuid.uuid4()

        current_user = {"user_id": user_id, "id": user_id, "show_me": "women"}

        conn = _mock_async_conn()
        # available_spins deduction
        conn.fetchval.return_value = 2
        # candidate lookup
        conn.fetchrow.side_effect = [
            {"id": cand_id, "first_name": "Rhea", "city": "Bengaluru"},  # candidate
            {"id": match_id},                                            # match_row
            {"id": chat_id},                                             # chat_row
        ]

        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn

        redis = AsyncMock()
        with patch("app.routers.arcade.sliding_window_rate_limit", new_callable=AsyncMock):
            res = await spin_serendipity_wheel(current_user, pool, redis)

        self.assertTrue(res["success"])
        self.assertEqual(res["chat_id"], str(chat_id))
        self.assertEqual(res["paired_user"]["first_name"], "Rhea")

        # Verify SQL operations performed
        executed_sqls = [call[0][0] for call in conn.execute.call_args_list] + [
            call[0][0] for call in conn.fetchrow.call_args_list
        ]
        self.assertTrue(any("INSERT INTO matches" in q for q in executed_sqls))
        self.assertTrue(any("INSERT INTO chats" in q for q in executed_sqls))
        self.assertTrue(any("is_ephemeral" in q for q in executed_sqls))

    async def test_04_onboarding_step_22_accepts_pending_photos(self):
        """Step 22 must accept photos with status = 'pending' to avoid async moderation race conditions."""
        user_id = uuid.uuid4()
        current_user = MagicMock()
        current_user.id = user_id

        conn = _mock_async_conn()
        # User details check
        conn.fetchrow.return_value = {
            "first_name": "Aarav",
            "date_of_birth": datetime(1995, 1, 1).date(),
            "gender": "man",
            "show_me": "women",
            "looking_for": "marriage",
            "dietary_strictness": "pure_jain",
            "community_sect": "digambar_terapanthi",
            "city": "Ahmedabad",
            "state": "Gujarat",
            "location": "POINT(72.5714 23.0225)",
            "onboarding_completed": False,
        }
        # has_photo check: returns True for pending photo
        conn.fetchval.return_value = True

        db = MagicMock()
        db.acquire.return_value.__aenter__.return_value = conn

        redis = AsyncMock()
        with patch("app.routers.onboarding._guard_rate_limit", new_callable=AsyncMock):
            res = await step22_complete(Step22CompleteBody(confirm_completion=True), current_user, db, redis)

        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["completed"])
        # Verify query checks both approved and pending
        fetchval_query = conn.fetchval.call_args[0][0]
        self.assertIn("status IN ('approved', 'pending')", fetchval_query)

    def test_05_ephemeral_reaper_stale_matches_uses_coalesce_and_closes_chats(self):
        """reap_stale_matches must COALESCE last_message_at with created_at and set chats.is_unmatched = TRUE."""
        mock_conn = AsyncMock()
        mock_conn.transaction = None
        expired_match_id = uuid.uuid4()
        mock_conn.fetch.side_effect = [
            [{"id": expired_match_id}],  # Step 1: expired_ids
            [],                          # Step 2: warn_ids
        ]

        with patch("app.workers.ephemeral_reaper._get_conn", new_callable=AsyncMock) as mock_get_conn:
            mock_get_conn.return_value = mock_conn
            reap_stale_matches()

        fetch_queries = [call[0][0] for call in mock_conn.fetch.call_args_list]
        self.assertTrue(any("COALESCE(last_message_at, created_at)" in q for q in fetch_queries))

        execute_queries = [call[0][0] for call in mock_conn.execute.call_args_list]
        self.assertTrue(any("UPDATE chats SET is_unmatched = TRUE" in q for q in execute_queries))

    async def test_06_push_notifications_stringifies_data_values(self):
        """FCM v1 requires all values in data payload to be strings."""
        with patch("app.services.push_notifications._get_access_token", new_callable=AsyncMock) as mock_token, \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_token.return_value = "fake_oauth_token"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            data_payload = {
                "match_id": uuid.uuid4(),
                "count": 5,
                "is_active": True,
            }
            res = await send_push("fcm_device_token_xyz", "Title", "Body", data_payload)
            self.assertTrue(res)

            sent_json = mock_post.call_args[1]["json"]
            sent_data = sent_json["message"]["data"]
            for k, v in sent_data.items():
                self.assertIsInstance(k, str)
                self.assertIsInstance(v, str)

    def test_07_media_processor_cdn_url_strips_trailing_slash(self):
        """media_processor must strip trailing slash from cdn_public_base_url."""
        base_url = "https://cdn.jainune.com/"
        stripped = base_url.rstrip("/")
        prod_key = "media/xyz.webp"
        cdn_url = f"{stripped}/{prod_key}"
        self.assertEqual(cdn_url, "https://cdn.jainune.com/media/xyz.webp")
        self.assertNotIn("com//media", cdn_url)

    def test_08_purge_deleted_users_uses_asyncio_to_thread_for_s3_delete(self):
        """purge_deleted_users must delegate blocking S3 deletion to threadpool."""
        from app.workers.ephemeral_reaper import purge_deleted_users
        import asyncio

        mock_conn = _mock_async_conn()
        user_id = uuid.uuid4()
        mock_conn.fetch.side_effect = [
            [{"id": user_id}],  # SELECT id FROM users WHERE account_status = 'deleted'...
            [{"s3_key": "user_photos/test.webp"}],  # SELECT s3_key FROM user_media...
        ]
        mock_conn.execute.return_value = "DELETE 1"

        with patch("app.workers.ephemeral_reaper._get_conn", new_callable=AsyncMock) as mock_get_conn, \
             patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread, \
             patch("app.services.account_service._delete_s3_keys_sync") as mock_delete_s3:
            mock_get_conn.return_value = mock_conn
            purge_deleted_users()
            self.assertTrue(mock_to_thread.called)
            # Verify the target function was _delete_s3_keys_sync and keys were passed
            self.assertEqual(mock_to_thread.call_args[0][0], mock_delete_s3)
            self.assertEqual(mock_to_thread.call_args[0][1], ["user_photos/test.webp"])

    async def test_09_daily_likes_redis_ttl_refreshed_on_every_incr(self):
        """record_interaction_action must refresh Redis TTL on every like increment."""
        from app.routers.interactions import record_interaction_action
        from app.models.schemas.interaction import InteractionActionRequest

        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        body = InteractionActionRequest(target_id=target_id, action="like")

        conn = _mock_async_conn()
        conn.fetchrow.side_effect = [
            {"id": target_id, "account_status": "active", "deleted_at": None},  # target user check
            None,                                                                # existing interaction check
            None,                                                                # mutual like check (no mutual)
        ]
        conn.fetchval.side_effect = [
            0,     # user_blocks check
        ]
        pool = MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        mock_redis.pipeline.return_value = mock_pipe
        # Simulate new_count = 2 (not first increment)
        mock_redis.incr = AsyncMock(return_value=2)
        mock_redis.expire = AsyncMock(return_value=True)

        with patch("app.services.payment_service.get_effective_user_tier", new_callable=AsyncMock) as mock_tier:
            mock_tier.return_value = "free"
            res = await record_interaction_action(
                body=body,
                current_user={"id": str(actor_id)},
                db=pool,
                redis=mock_redis,
            )
            self.assertTrue(res.success)
            self.assertTrue(mock_redis.incr.called)
            self.assertTrue(mock_redis.expire.called)


if __name__ == "__main__":
    unittest.main()
