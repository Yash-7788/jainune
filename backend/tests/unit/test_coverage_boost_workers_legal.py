"""
Comprehensive unit tests for workers, legal pages, push notifications, and account service.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from app.routers.legal import (
    privacy_policy,
    terms_of_service,
    child_safety_standards,
    community_guidelines,
    delete_account_portal,
)
from app.workers.telemetry_worker import _flush_async, _aggregate_async
from app.workers.daily_compatible import _run_async
from app.services.push_notifications import (
    prune_invalid_device_token,
    send_push,
    send_push_multicast,
)
from app.services.account_service import (
    soft_delete_user_account,
    purge_user_account,
)


class DummyAsyncTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class TestCoverageBoost(unittest.TestCase):

    def test_legal_endpoints(self):
        """Test all legal and compliance portal routes."""
        p = asyncio.run(privacy_policy())
        self.assertIn("Privacy Policy", str(p))

        t = asyncio.run(terms_of_service())
        self.assertIn("Terms of Service", str(t))

        c = asyncio.run(child_safety_standards())
        self.assertIn("Child Safety", str(c))

        g = asyncio.run(community_guidelines())
        self.assertIn("Community Guidelines", str(g))

        d = asyncio.run(delete_account_portal())
        self.assertIn("Account Deletion", str(d))

    def test_telemetry_worker_flush_empty(self):
        """Test telemetry flush when redis stream has no events."""
        mock_redis = MagicMock()
        mock_redis.xrange = AsyncMock(return_value=[])
        mock_redis.lrange = AsyncMock(return_value=[])
        mock_redis.aclose = AsyncMock()

        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        with patch("app.workers.telemetry_worker._get_redis", new_callable=AsyncMock) as gr, \
             patch("app.workers.telemetry_worker._get_conn", new_callable=AsyncMock) as gc:
            gr.return_value = mock_redis
            gc.return_value = mock_conn
            asyncio.run(_flush_async())

        mock_redis.xrange.assert_called_once()

    def test_telemetry_worker_flush_with_events(self):
        """Test telemetry flush with both stream and list events."""
        mock_redis = MagicMock()
        u1 = uuid.uuid4()
        u2 = uuid.uuid4()
        stream_entry = ("1700000000000-0", {
            "actor_id": str(u1),
            "target_user_id": str(u2),
            "event_type": "profile_view",
            "server_ts": "1700000000000",
            "payload": json.dumps({"source": "feed"}),
        })
        mock_redis.xrange = AsyncMock(side_effect=[
            [stream_entry],
            [("1700000000001-0", {"actor_id": str(u1), "target_id": str(u2), "alpha": "0.1"})],
        ])
        legacy_event = json.dumps({
            "user_id": str(u2),
            "target_id": str(u1),
            "event_type": "like",
            "ts": "1700000001000",
            "duration_ms": 120,
        })
        mock_redis.lrange = AsyncMock(return_value=[legacy_event])
        mock_redis.xdel = AsyncMock()
        mock_redis.ltrim = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": u1}, {"id": u2}])
        mock_conn.executemany = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        with patch("app.workers.telemetry_worker._get_redis", new_callable=AsyncMock) as gr, \
             patch("app.workers.telemetry_worker._get_conn", new_callable=AsyncMock) as gc:
            gr.return_value = mock_redis
            gc.return_value = mock_conn
            asyncio.run(_flush_async())

        mock_conn.executemany.assert_called_once()
        mock_conn.execute.assert_called_once()
        self.assertEqual(mock_redis.xdel.call_count, 2)

    def test_telemetry_worker_aggregate(self):
        """Test telemetry hourly aggregation worker."""
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        with patch("app.workers.telemetry_worker._get_conn", new_callable=AsyncMock) as gc:
            gc.return_value = mock_conn
            asyncio.run(_aggregate_async())

        mock_conn.execute.assert_called_once()

    def test_daily_compatible_worker_empty(self):
        """Test daily compatible worker when no users found."""
        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.close = AsyncMock()

        mock_redis = MagicMock()
        mock_redis.aclose = AsyncMock()

        with patch("app.workers.daily_compatible._get_conn", new_callable=AsyncMock) as gc, \
             patch("app.workers.daily_compatible._get_redis", new_callable=AsyncMock) as gr:
            gc.return_value = mock_conn
            gr.return_value = mock_redis
            asyncio.run(_run_async())

        mock_conn.fetch.assert_called_once()

    def test_daily_compatible_worker_with_users(self):
        """Test daily compatible worker ranking and stable marriage with active users."""
        u1 = uuid.uuid4()
        u2 = uuid.uuid4()
        users = [
            {
                "id": u1,
                "gender": "men",
                "show_me": "women",
                "looking_for": "marriage",
                "dietary_strictness": "jain",
                "community_sect": "shwetambar",
                "city": "mumbai",
                "longitude": 72.8777,
                "latitude": 19.0760,
                "max_distance_km": 50,
                "open_to_relocation": True,
                "subscription_tier": "free",
                "trust_score": 80,
                "paryushan_mode": False,
                "eats_root_vegetables": False,
                "eats_onion_garlic": False,
            },
            {
                "id": u2,
                "gender": "women",
                "show_me": "men",
                "looking_for": "marriage",
                "dietary_strictness": "jain",
                "community_sect": "shwetambar",
                "city": "mumbai",
                "longitude": 72.8777,
                "latitude": 19.0760,
                "max_distance_km": 50,
                "open_to_relocation": True,
                "subscription_tier": "free",
                "trust_score": 80,
                "paryushan_mode": False,
                "eats_root_vegetables": False,
                "eats_onion_garlic": False,
            },
        ]
        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(side_effect=[users, []])
        mock_conn.executemany = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.aclose = AsyncMock()

        with patch("app.workers.daily_compatible._get_conn", new_callable=AsyncMock) as gc, \
             patch("app.workers.daily_compatible._get_redis", new_callable=AsyncMock) as gr, \
             patch("app.workers.daily_compatible.CorePeopleFinder.rank_candidates", new_callable=AsyncMock) as rc:
            gc.return_value = mock_conn
            gr.return_value = mock_redis
            rc.side_effect = [
                [{"id": u2, "compatibility_score": 0.9}],
                [{"id": u1, "compatibility_score": 0.9}],
            ]
            asyncio.run(_run_async())

        self.assertTrue(mock_conn.executemany.called)

    def test_push_notifications_prune_device_token(self):
        """Test pruning invalid FCM device tokens."""
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        asyncio.run(prune_invalid_device_token("bad_token_123", conn=mock_conn))
        mock_conn.execute.assert_called_once()

    def test_push_notifications_send_push_no_token(self):
        """Test send_push gracefully handles empty device tokens."""
        res = asyncio.run(send_push(
            device_token="",
            title="Hello",
            body="World",
        ))
        self.assertFalse(res)

    def test_push_notifications_multicast_empty(self):
        """Test send_push_multicast with empty list returns empty result."""
        res = asyncio.run(send_push_multicast(
            device_tokens=[],
            title="Broadcast",
            body="Announcement",
        ))
        self.assertEqual(res, {"success": 0, "failure": 0})

    def test_push_notifications_expo_and_fcm(self):
        """Test expo push and FCM push paths with mocked client."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"data": [{"status": "ok"}]}'

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            expo_res = asyncio.run(send_push(
                device_token="ExponentPushToken[xxxxxxxxxxxx]",
                title="Hello",
                body="Expo",
            ))
            self.assertTrue(expo_res)

        with patch("app.services.push_notifications._get_access_token", new_callable=AsyncMock, return_value="fcm_mock_token"), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            fcm_res = asyncio.run(send_push(
                device_token="raw_device_token_abc123",
                title="Hello",
                body="FCM",
                data={"key": "val"},
            ))
            self.assertTrue(fcm_res)

    def test_account_service_soft_delete_and_hard_purge(self):
        """Test account service soft delete and hard purge flows."""
        uid = uuid.uuid4()
        mock_conn = MagicMock()
        mock_conn.transaction.return_value = DummyAsyncTx()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_conn.fetch = AsyncMock(return_value=[{"s3_key": "photos/test.jpg"}])
        mock_conn.fetchrow = AsyncMock(return_value={
            "phone_number": "1234567890",
            "email": "test@example.com",
            "subscription_tier": "free",
            "subscription_valid_until": None,
        })

        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))

        with patch("app.services.account_service._delete_s3_keys_sync", return_value=None):
            soft_res = asyncio.run(soft_delete_user_account(uid, mock_conn, mock_redis, reason="test"))
            self.assertEqual(soft_res["status"], "soft_deleted")

            purge_res = asyncio.run(purge_user_account(uid, mock_conn, mock_redis))
            self.assertEqual(purge_res["status"], "purged")

    def test_stable_marriage_non_bipartite_pool(self):
        """Test Gale-Shapley engine with open/nonbinary pool covering generalized reciprocal deferred acceptance."""
        from app.services.stable_marriage import StableMarriageEngine
        engine = StableMarriageEngine()
        u1 = str(uuid.uuid4())
        u2 = str(uuid.uuid4())
        u3 = str(uuid.uuid4())
        users = [
            {"id": u1, "gender": "nonbinary", "show_me": "everyone"},
            {"id": u2, "gender": "man", "show_me": "everyone"},
            {"id": u3, "gender": "woman", "show_me": "everyone"},
        ]
        queues = {
            u1: [u2, u3],
            u2: [u1, u3],
            u3: [u1, u2],
        }
        res = engine.compute(users, queues)
        self.assertIsInstance(res, list)

    def test_users_router_endpoints_direct(self):
        """Test users router endpoints directly via unit test."""
        from app.routers.users import pause_account, unpause_account, list_blocked_users
        uid = uuid.uuid4()
        user = {"user_id": uid, "id": uid}
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_conn.fetch = AsyncMock(return_value=[{"blocked_id": uuid.uuid4(), "created_at": "2026-01-01"}])

        class MockDB:
            def acquire(self):
                class CM:
                    async def __aenter__(self): return mock_conn
                    async def __aexit__(self, *args): pass
                return CM()

        pool = MockDB()
        res_pause = asyncio.run(pause_account(user, pool))
        self.assertTrue(res_pause["is_paused"])

        res_unpause = asyncio.run(unpause_account(user, pool))
        self.assertFalse(res_unpause["is_paused"])

        res_blocks = asyncio.run(list_blocked_users(user, pool))
        self.assertEqual(len(res_blocks["blocked_users"]), 1)

    def test_chats_router_endpoints_direct(self):
        """Test chats router endpoints directly via unit test."""
        from app.routers.chats import mark_read, unmatch_chat
        uid = uuid.uuid4()
        other_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        user = {"id": uid, "user_id": uid}
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": chat_id,
            "participant_1_id": uid,
            "participant_2_id": other_id,
            "is_unmatched": False,
            "is_expired": False,
            "expires_at": None,
            "match_id": uuid.uuid4(),
        })
        mock_conn.transaction.return_value = DummyAsyncTx()

        class MockDB:
            def acquire(self):
                class CM:
                    async def __aenter__(self): return mock_conn
                    async def __aexit__(self, *args): pass
                return CM()

        pool = MockDB()
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pipeline.return_value = MagicMock(execute=AsyncMock())

        res_read = asyncio.run(mark_read(chat_id, user, pool, redis=mock_redis))
        self.assertEqual(res_read.status_code, 204)

        res_unmatch = asyncio.run(unmatch_chat(chat_id, user, pool, redis=mock_redis))
        self.assertTrue(res_unmatch["success"])

    def test_onboarding_direct_steps(self):
        """Direct unit execution of all onboarding steps 2-21 for 100% reliable coverage."""
        from app.models.schemas.user import (
            Step02BasicInfoBody, Step03GenderBody, Step04ShowMeBody, Step05LookingForBody,
            Step06DietaryStrictnessBody, Step07DietaryDetailsBody, Step08CommunitySectBody,
            Step09ParyushanBody, Step10CityBody, Step12DistanceBody, Step13RelocationBody,
            Step14HeightBody, Step15CareerBody, Step16EducationBody, Step17BioBody,
            Step18PromptsBody, Step19PhotosBody, Step20VoiceSnapshotBody, Step21ConsentBody
        )
        from app.routers.onboarding import (
            step2_basic_info, step3_gender, step4_show_me, step5_looking_for,
            step6_dietary_strictness, step7_dietary_details, step8_community_sect,
            step9_paryushan, step10_city, step12_distance, step13_relocation,
            step14_height, step15_career, step16_education, step17_bio,
            step18_prompts, step19_photos, step20_voice_snapshot, step21_consent
        )
        uid = uuid.uuid4()
        mid = uuid.uuid4()
        class MockUser:
            def __init__(self, u): self.id = u
            def get(self, k, d=None): return self.id if k in ("user_id", "id") else d
            def __getitem__(self, k): return self.id

        user = MockUser(uid)
        mock_conn = MagicMock()
        del mock_conn.acquire
        mock_conn.fetchrow = AsyncMock(return_value={"onboarding_completed": False, "location": True, "id": mid})
        mock_conn.fetch = AsyncMock(return_value=[{"id": mid, "prompt_key": "q1", "response_text": "a", "position": 1}])
        mock_conn.fetchval = AsyncMock(return_value=True)
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_conn.transaction.return_value = DummyAsyncTx()

        class MockDB:
            def acquire(self):
                class CM:
                    async def __aenter__(self): return mock_conn
                    async def __aexit__(self, *args): pass
                return CM()

        db = MockDB()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=True)
        redis.pipeline.return_value = MagicMock(execute=AsyncMock())

        s2 = asyncio.run(step2_basic_info(Step02BasicInfoBody(first_name="Aarav", date_of_birth="1998-05-15"), user, db, redis))
        self.assertTrue(s2["success"])
        s3 = asyncio.run(step3_gender(Step03GenderBody(gender="man"), user, db, redis))
        self.assertTrue(s3["success"])
        s4 = asyncio.run(step4_show_me(Step04ShowMeBody(show_me="women"), user, db, redis))
        self.assertTrue(s4["success"])
        s5 = asyncio.run(step5_looking_for(Step05LookingForBody(looking_for="marriage"), user, db, redis))
        self.assertTrue(s5["success"])
        s6 = asyncio.run(step6_dietary_strictness(Step06DietaryStrictnessBody(dietary_strictness="pure_jain"), user, db, redis))
        self.assertTrue(s6["success"])
        s7 = asyncio.run(step7_dietary_details(Step07DietaryDetailsBody(eats_root_vegetables=False, eats_onion_garlic=False), user, db, redis))
        self.assertTrue(s7["success"])
        s8 = asyncio.run(step8_community_sect(Step08CommunitySectBody(community_sect="shwetambar_murtipujak"), user, db, redis))
        self.assertTrue(s8["success"])
        s9 = asyncio.run(step9_paryushan(Step09ParyushanBody(paryushan_mode=True), user, db, redis))
        self.assertTrue(s9["success"])
        s10 = asyncio.run(step10_city(Step10CityBody(city="Mumbai", state="Maharashtra"), user, db, redis))
        self.assertTrue(s10["success"])
        s12 = asyncio.run(step12_distance(Step12DistanceBody(max_distance_km=50), user, db, redis))
        self.assertTrue(s12["success"])
        s13 = asyncio.run(step13_relocation(Step13RelocationBody(open_to_relocation=True), user, db, redis))
        self.assertTrue(s13["success"])
        s14 = asyncio.run(step14_height(Step14HeightBody(height_cm=175), user, db, redis))
        self.assertTrue(s14["success"])
        s15 = asyncio.run(step15_career(Step15CareerBody(job_title="Engineer", company="Tech"), user, db, redis))
        self.assertTrue(s15["success"])
        s16 = asyncio.run(step16_education(Step16EducationBody(education="B.Tech"), user, db, redis))
        self.assertTrue(s16["success"])
        s17 = asyncio.run(step17_bio(Step17BioBody(bio="Devout Jain looking for companion"), user, db, redis))
        self.assertTrue(s17["success"])
        s18 = asyncio.run(step18_prompts(Step18PromptsBody(prompts=[{"prompt_key": "q1", "response_text": "Ahimsa always", "position": 1}]), user, db, redis))
        self.assertTrue(s18["success"])
        s19 = asyncio.run(step19_photos(Step19PhotosBody(media_ids=[mid]), user, db, redis))
        self.assertTrue(s19["success"])
        s20 = asyncio.run(step20_voice_snapshot(Step20VoiceSnapshotBody(media_id=mid), user, db, redis))
        self.assertTrue(s20["success"])
        s21 = asyncio.run(step21_consent(Step21ConsentBody(core_matchmaking=True, family_contact_gotra=False, relocation_intercity=True, marketing=False), user, db, redis))
        self.assertTrue(s21["success"])
