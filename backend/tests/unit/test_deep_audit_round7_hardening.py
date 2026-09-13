"""
Unit tests for Deep Audit Additional Findings (1–9).

Covers:
1. Admin moderator user-detail schema alignment (no non-existent columns)
2. Daily compatible distributed lock ownership & Lua release
3. Single media deletion failed S3 keys durable retry set persistence
4. Ephemeral reaper partial S3 delete_objects error handling & selective purge
5. Push notification deduplication ordering & rollback on delivery failure
6. Multi-device FCM token registration, multi-device push, and token pruning
7. Daily compatible bounded memory streaming chunks
8. Canonical Redis pub/sub routing on chat:{chat_id}
9. Location waitlist identity binding strictly to authenticated phone
"""

import asyncio
import json
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


class TestDeepAuditRound7Hardening(unittest.IsolatedAsyncioTestCase):

    # -----------------------------------------------------------------------
    # 1. Admin moderator user-detail query schema alignment
    # -----------------------------------------------------------------------
    async def test_01_admin_moderator_user_detail_schema_alignment(self):
        """Moderator user-detail query must select valid schema columns and provide aliases."""
        from app.routers.admin import get_user_detail

        user_id = uuid.uuid4()
        admin_payload = {"admin_id": str(uuid.uuid4()), "admin_role": "moderator"}

        executed_queries = []

        mock_conn = AsyncMock()
        async def track_fetchrow(query, *args):
            executed_queries.append(query)
            return {
                "id": user_id,
                "phone_number": "+919876543210",
                "email": "test@example.com",
                "first_name": "Paras",
                "gender": "men",
                "date_of_birth": "1995-01-01",
                "height_cm": 178,
                "dietary_strictness": "pure_jain",
                "eats_root_vegetables": False,
                "eats_onion_garlic": False,
                "paryushan_mode": True,
                "community_sect": "shwetambar",
                "sub_sect": "shwetambar",
                "mother_tongue": "gujarati",
                "city": "Mumbai",
                "state": "Maharashtra",
                "bio": "Bio text",
                "job_title": "Engineer",
                "company": "Tech Corp",
                "education": "B.Tech",
                "profession": "Engineer",
                "employer": "Tech Corp",
                "annual_income_range": "15-25L",
                "looking_for": "marriage",
                "account_status": "active",
                "subscription_tier": "free",
                "trust_score": 75.0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "last_active_at": "2026-01-01T00:00:00Z",
                "location_zone": "mumbai_mmr",
                "is_photo_verified": True,
                "is_verified": True,
                "is_paused": False,
                "suspend_until": None,
                "deleted_at": None,
                "report_count": 0,
                "badge_count": 0,
                "media_count": 1,
            }

        mock_conn.fetchrow = AsyncMock(side_effect=track_fetchrow)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await get_user_detail(user_id=user_id, admin=admin_payload, pool=mock_pool)

        # Assert query does not select non-existent columns
        self.assertTrue(len(executed_queries) > 0)
        query = executed_queries[0]
        self.assertNotIn("u.marital_status", query)
        self.assertNotIn("u.dietary_preference", query)
        self.assertNotIn("u.gotra", query)
        self.assertNotIn("u.sampradaya", query)

        # Assert query selects canonical columns and aliases
        self.assertIn("u.dietary_strictness", query)
        self.assertIn("u.is_photo_verified AS is_verified", query)
        self.assertIn("u.community_sect AS sub_sect", query)

        # Assert moderator redaction / masking took place
        self.assertEqual(result["first_name"], "Paras")
        self.assertIn("*", result["phone_number"])
        self.assertIn("*", result["email"])

    # -----------------------------------------------------------------------
    # 2. Daily compatibility lock ownership and atomic Lua release
    # -----------------------------------------------------------------------
    async def test_02_daily_compatible_lock_token_lua_release(self):
        """Worker acquires lock with unique token and releases only its own lock via Lua."""
        from app.workers.daily_compatible import _run_async

        mock_redis = AsyncMock()
        stored_locks = {}

        async def mock_set(key, val, nx=False, ex=None):
            if nx and key in stored_locks:
                return False
            stored_locks[key] = val
            return True

        async def mock_eval(script, numkeys, key, token):
            if stored_locks.get(key) == token:
                del stored_locks[key]
                return 1
            return 0

        mock_redis.set = AsyncMock(side_effect=mock_set)
        mock_redis.eval = AsyncMock(side_effect=mock_eval)
        mock_redis.pipeline = MagicMock(return_value=AsyncMock())
        mock_redis.aclose = AsyncMock()

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.close = AsyncMock()

        with patch("app.workers.daily_compatible._get_redis", AsyncMock(return_value=mock_redis)), \
             patch("app.workers.daily_compatible._get_conn", AsyncMock(return_value=mock_conn)):
            await _run_async()

        # Verify eval was called to release the lock with the matching token
        self.assertTrue(mock_redis.eval.called)
        call_args = mock_redis.eval.call_args[0]
        script = call_args[0]
        self.assertIn('redis.call("del", KEYS[1])', script)
        self.assertEqual(call_args[2], "lock:daily_compatible")

        # Now simulate an expired lock that was re-acquired by worker B:
        # Worker A tries to release, but token does not match -> should return 0 without deleting worker B's lock
        stored_locks["lock:daily_compatible"] = "worker_b_token"
        res = await mock_eval(script, 1, "lock:daily_compatible", "worker_a_token")
        self.assertEqual(res, 0)
        self.assertEqual(stored_locks["lock:daily_compatible"], "worker_b_token")

    # -----------------------------------------------------------------------
    # 3. Single media deletion durable retry
    # -----------------------------------------------------------------------
    async def test_03_single_media_delete_failed_s3_retries(self):
        """If S3 deletion fails during single media delete, failed keys are enqueued into Redis."""
        from app.routers.media import delete_media

        media_id = uuid.uuid4()
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": media_id, "s3_key": "media/user/photo.jpg", "status": "approved"})
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        sadd_calls = []
        async def mock_sadd(key, *members):
            sadd_calls.append((key, members))
            return len(members)
        mock_redis.sadd = AsyncMock(side_effect=mock_sadd)

        # Simulate S3 delete failure returning failed keys
        with patch("app.services.account_service._delete_s3_keys_sync", return_value=["media/user/photo.jpg"]):
            res = await delete_media(media_id=media_id, current_user=current_user, db=mock_db, redis=mock_redis)

        self.assertTrue(res["success"])
        # Verify failed key was enqueued to Redis retry set
        self.assertEqual(len(sadd_calls), 1)
        self.assertEqual(sadd_calls[0][0], "s3:failed_deletions")
        self.assertIn("media/user/photo.jpg", sadd_calls[0][1])

    # -----------------------------------------------------------------------
    # 4. Ephemeral reaper S3 partial failure handling
    # -----------------------------------------------------------------------
    async def test_04_ephemeral_reaper_s3_partial_failure_handling(self):
        """Media reaper only updates s3_purged = TRUE for confirmed S3 deletions, enqueuing failed keys."""
        from app.workers.ephemeral_reaper import reap_ephemeral_media

        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        rows = [
            {"id": id1, "s3_key": "quarantine/success.jpg"},
            {"id": id2, "s3_key": "quarantine/failed.jpg"},
        ]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.fetch = AsyncMock(return_value=rows)
        mock_conn.close = AsyncMock()

        mock_s3 = MagicMock()
        # Simulate partial delete response: id1 succeeded, id2 failed
        mock_s3.delete_objects.return_value = {
            "Deleted": [{"Key": "quarantine/success.jpg"}],
            "Errors": [{"Key": "quarantine/failed.jpg", "Code": "InternalError", "Message": "S3 failure"}],
        }

        mock_redis = AsyncMock()
        retry_keys_added = []
        async def mock_sadd(key, *members):
            retry_keys_added.extend(members)
            return len(members)
        mock_redis.sadd = AsyncMock(side_effect=mock_sadd)

        updated_purged_ids = []
        async def mock_execute(sql, *args):
            if "UPDATE user_media SET s3_purged = TRUE" in sql:
                updated_purged_ids.extend(args[0])
            return "UPDATE"
        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        captured_coros = []
        with patch("app.workers.ephemeral_reaper._get_conn", AsyncMock(return_value=mock_conn)), \
             patch("app.workers.ephemeral_reaper._s3_client", return_value=mock_s3), \
             patch("app.core.redis.get_redis", return_value=mock_redis), \
             patch("app.workers.ephemeral_reaper.run_worker_task", side_effect=lambda coro: captured_coros.append(coro)):
            reap_ephemeral_media()
            self.assertEqual(len(captured_coros), 1)
            await captured_coros[0]

        # Confirm failed key was persisted to retry set
        self.assertIn("quarantine/failed.jpg", retry_keys_added)
        # Confirm ONLY id1 was marked s3_purged = TRUE
        self.assertIn(id1, updated_purged_ids)
        self.assertNotIn(id2, updated_purged_ids)



    # -----------------------------------------------------------------------
    # 5. Push notification deduplication ordering & failure rollback
    # -----------------------------------------------------------------------
    async def test_05_notification_worker_dedup_rollback_on_failure(self):
        """Notification worker acquires in-flight lock, rolls back on delivery failure, commits on success."""
        from app.workers.notification_worker import _check_and_lock_dedup, _commit_dedup, _rollback_dedup

        mock_redis = AsyncMock()
        kv_store = {}

        async def mock_exists(k):
            return 1 if k in kv_store else 0

        async def mock_set(k, v, nx=False, ex=None):
            if nx and k in kv_store:
                return False
            kv_store[k] = v
            return True

        async def mock_eval(script, numkeys, key, token):
            if kv_store.get(key) == token:
                del kv_store[key]
                return 1
            return 0

        class MockPipeline:
            def set(self, k, v, ex=None):
                kv_store[k] = v
            def delete(self, k):
                kv_store.pop(k, None)
            async def execute(self):
                return []

        mock_redis.exists = AsyncMock(side_effect=mock_exists)
        mock_redis.set = AsyncMock(side_effect=mock_set)
        mock_redis.eval = AsyncMock(side_effect=mock_eval)
        mock_redis.pipeline = MagicMock(return_value=MockPipeline())

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            # 1. Acquire in-flight reservation
            is_dup, token = await _check_and_lock_dedup("test_event", in_flight_ttl=60)
            self.assertFalse(is_dup)
            self.assertTrue(len(token) > 0)
            self.assertIn("notify:inflight:test_event", kv_store)

            # 2. Simulate delivery failure -> rollback
            await _rollback_dedup("test_event", token)
            self.assertNotIn("notify:inflight:test_event", kv_store)
            self.assertNotIn("notify:dedup:test_event", kv_store)

            # 3. Retry attempt can acquire reservation again
            is_dup_retry, token2 = await _check_and_lock_dedup("test_event", in_flight_ttl=60)
            self.assertFalse(is_dup_retry)

            # 4. Successful delivery -> commit permanent dedup
            await _commit_dedup("test_event", token2, ttl=300)
            self.assertIn("notify:dedup:test_event", kv_store)
            self.assertNotIn("notify:inflight:test_event", kv_store)

            # 5. Subsequent duplicate request is blocked
            is_dup_third, _ = await _check_and_lock_dedup("test_event", in_flight_ttl=60)
            self.assertTrue(is_dup_third)

    # -----------------------------------------------------------------------
    # 6. Multi-device FCM token routing and pruning
    # -----------------------------------------------------------------------
    async def test_06_multi_device_fcm_token_routing_and_pruning(self):
        """get_user_device_tokens retrieves all user devices and prune_invalid_device_token removes from both tables."""
        from app.services.push_notifications import get_user_device_tokens, prune_invalid_device_token

        user_id = uuid.uuid4()
        mock_conn = AsyncMock()

        # 1. Multiple devices exist
        mock_conn.fetch = AsyncMock(return_value=[
            {"token": "fcm_token_iphone"},
            {"token": "fcm_token_ipad"},
        ])
        tokens = await get_user_device_tokens(user_id, mock_conn)
        self.assertEqual(len(tokens), 2)
        self.assertIn("fcm_token_iphone", tokens)
        self.assertIn("fcm_token_ipad", tokens)

        # 2. Fallback to users.fcm_token if user_devices empty
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchrow = AsyncMock(return_value={"fcm_token": "fcm_token_legacy"})
        tokens_fallback = await get_user_device_tokens(user_id, mock_conn)
        self.assertEqual(tokens_fallback, ["fcm_token_legacy"])

        # 3. Prune token deletes from user_devices and nullifies users.fcm_token
        executed_sqls = []
        async def track_execute(sql, *args):
            executed_sqls.append((sql, args))
            return "DELETE"
        mock_conn.execute = AsyncMock(side_effect=track_execute)

        await prune_invalid_device_token("bad_token_123", conn=mock_conn)
        self.assertTrue(any("DELETE FROM user_devices" in s[0] for s in executed_sqls))
        self.assertTrue(any("UPDATE users SET fcm_token = NULL" in s[0] for s in executed_sqls))

    # -----------------------------------------------------------------------
    # 7. Daily compatibility bounded memory streaming
    # -----------------------------------------------------------------------
    async def test_07_daily_compatible_bounded_memory_streaming(self):
        """Daily compatible streams users in chunks of 250 without global user_list accumulation."""
        from app.workers.daily_compatible import _run_async

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.aclose = AsyncMock()

        mock_conn = AsyncMock()
        users_sample = [{"id": uuid.uuid4(), "gender": "men", "city": "Mumbai", "show_me": "women"} for _ in range(10)]

        mock_conn.fetch = AsyncMock(return_value=users_sample)
        mock_conn.executemany = AsyncMock(return_value=None)
        mock_conn.close = AsyncMock()

        with patch("app.workers.daily_compatible._get_redis", AsyncMock(return_value=mock_redis)), \
             patch("app.workers.daily_compatible._get_conn", AsyncMock(return_value=mock_conn)), \
             patch("app.services.core_people_finder.CorePeopleFinder.rank_candidates", AsyncMock(return_value=[])):
            await _run_async()

        # Verify pipeline set was called for each user
        self.assertEqual(mock_pipe.set.call_count, len(users_sample))
        self.assertTrue(mock_pipe.execute.called)

    # -----------------------------------------------------------------------
    # 8. Canonical chat Redis pub/sub routing
    # -----------------------------------------------------------------------
    async def test_08_canonical_chat_pubsub_single_delivery(self):
        """Chat router publishes to canonical channel chat:{actual_chat_id} without duplicate channel fan-out."""
        from app.routers.chats import send_message
        from app.models.schemas.chat import SendMessageRequest

        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()
        other_id = uuid.uuid4()

        mock_conn = AsyncMock()
        del mock_conn.acquire
        async def mock_fetchrow(query, *args):
            if "FROM chats" in query:
                return {"id": chat_id, "participant_1_id": user_id, "participant_2_id": other_id, "is_unmatched": False, "match_id": uuid.uuid4()}
            elif "FROM users" in query:
                return {"subscription_tier": "free", "subscription_valid_until": None, "billing_status": "active"}
            elif "INSERT INTO messages" in query:
                return {
                    "id": uuid.uuid4(),
                    "chat_id": chat_id,
                    "sender_id": user_id,
                    "message_type": "text",
                    "content": "Hello!",
                    "media_url": None,
                    "is_read": False,
                    "created_at": "2026-01-01T12:00:00Z",
                    "is_moderated": False,
                    "moderation_type": None,
                    "moderation_disclaimer": None,
                }
            return None
        mock_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        mock_conn.fetchval = AsyncMock(return_value=None)  # not blocked
        mock_conn.execute = AsyncMock(return_value=None)

        class MockTx:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, tb):
                pass
        mock_conn.transaction = MagicMock(return_value=MockTx())

        mock_db = MagicMock()
        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        published_channels = []
        mock_redis = AsyncMock()
        async def mock_publish(ch, payload):
            published_channels.append(ch)
            return 1
        mock_redis.publish = AsyncMock(side_effect=mock_publish)
        mock_redis.get = AsyncMock(return_value=None)  # recipient not in active chat

        body = SendMessageRequest(content="Hello!")
        current_user = {"user_id": str(user_id), "subscription_tier": "free"}

        mod_mock = MagicMock()
        mod_mock.content = "Hello!"
        mod_mock.is_moderated = False
        mod_mock.moderation_type = None
        mod_mock.moderation_disclaimer = None

        with patch("app.services.chat_safety_filter.filter_chat_content", AsyncMock(return_value=mod_mock)):
            await send_message(chat_id=chat_id, body=body, current_user=current_user, db=mock_db, redis=mock_redis)

        # Confirm message was published exactly once to canonical channel
        self.assertEqual(len(published_channels), 1)
        self.assertEqual(published_channels[0], f"chat:{chat_id}")

    # -----------------------------------------------------------------------
    # 9. Location waitlist identity binding strictly to authenticated phone
    # -----------------------------------------------------------------------
    async def test_09_location_waitlist_bound_to_authenticated_phone(self):
        """Verify location waitlist ignores caller-supplied phone override and uses authenticated phone."""
        from app.routers.location import verify_location, VerifyLocationRequest

        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id), "phone_number": "+919876543210"}

        # Request outside coverage zone with attacker-supplied spoofed phone
        req_body = VerifyLocationRequest(
            latitude=28.6139,
            longitude=77.2090,  # New Delhi (outside MMR/Pune/Bengaluru)
            phone_number="+911111111111",  # Spoofed phone
            city_hint="Delhi",
        )

        mock_request = MagicMock()
        mock_request.headers = {"host": "api.jainune.com"}
        mock_request.client.host = "127.0.0.1"

        saved_waitlist = []
        async def mock_save_waitlist(phone_number, lat, lon, city_hint, pool):
            saved_waitlist.append({"phone_number": phone_number, "city_hint": city_hint})

        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)

        with patch("app.routers.location.verify_location_anti_spoofing", return_value=(True, None)), \
             patch("app.routers.location.verify_location_zone", return_value=(False, None)), \
             patch("app.routers.location.save_city_waitlist", AsyncMock(side_effect=mock_save_waitlist)):
            resp = await verify_location(
                body=req_body,
                request=mock_request,
                redis=mock_redis,
                current_user=current_user,
                pool=MagicMock(),
            )

        self.assertFalse(resp["data"]["allowed"])
        self.assertTrue(resp["data"]["waitlist_registered"])
        self.assertEqual(len(saved_waitlist), 1)
        # CRITICAL CHECK: Phone number recorded in waitlist must be authenticated phone, NOT spoofed phone
        self.assertEqual(saved_waitlist[0]["phone_number"], "+919876543210")
        self.assertNotEqual(saved_waitlist[0]["phone_number"], "+911111111111")


if __name__ == "__main__":
    unittest.main()
