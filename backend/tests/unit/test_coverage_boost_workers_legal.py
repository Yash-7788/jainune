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

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)  # lock acquired
        mock_redis.delete = AsyncMock()
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

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)  # lock acquired
        mock_redis.delete = AsyncMock()
        mock_pipe = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
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

    # ── Auth helper pure-function coverage ────────────────────────────────────

    def test_auth_mask_phone_long(self):
        from app.routers.auth import mask_phone
        result = mask_phone("+919876541210")
        self.assertIn("*", result)
        self.assertTrue(result.startswith("+919"))
        self.assertTrue(result.endswith("1210"))

    def test_auth_mask_phone_short(self):
        from app.routers.auth import mask_phone
        result = mask_phone("123")
        self.assertEqual(result, "***")

    def test_auth_mask_email_normal(self):
        from app.routers.auth import mask_email
        result = mask_email("priya@gmail.com")
        self.assertIn("@gmail.com", result)
        self.assertTrue(result.startswith("p"))

    def test_auth_mask_email_single_char(self):
        from app.routers.auth import mask_email
        result = mask_email("a@b.com")
        self.assertIn("@b.com", result)

    def test_auth_mask_email_no_at(self):
        from app.routers.auth import mask_email
        result = mask_email("notanemail")
        self.assertEqual(result, "***")

    def test_auth_assert_account_active_none_row(self):
        from app.routers.auth import _assert_account_active
        # When row is falsy, function returns early (no exception)
        result = _assert_account_active(None)
        self.assertIsNone(result)

    def test_auth_assert_account_active_ok(self):
        from app.routers.auth import _assert_account_active
        row = {"account_status": "active", "deleted_at": None, "suspend_until": None}
        # Should not raise
        _assert_account_active(row)

    def test_auth_assert_account_active_suspended(self):
        from app.routers.auth import _assert_account_active
        from fastapi import HTTPException
        from datetime import datetime, timezone, timedelta
        future = datetime.now(timezone.utc) + timedelta(days=1)
        row = {"account_status": "active", "deleted_at": None, "suspend_until": future}
        with self.assertRaises(HTTPException):
            _assert_account_active(row)

    def test_auth_pack_unpack_grace_payload(self):
        from app.routers.auth import _pack_grace_payload, _unpack_grace_payload
        data = {"access_token": "tok123", "user_id": "uid456"}
        packed = _pack_grace_payload(data)
        self.assertIsInstance(packed, str)
        unpacked = _unpack_grace_payload(packed)
        self.assertIsNotNone(unpacked)
        self.assertEqual(unpacked["access_token"], "tok123")

    def test_auth_unpack_grace_payload_invalid(self):
        from app.routers.auth import _unpack_grace_payload
        result = _unpack_grace_payload(b"not-valid-json{{{")
        self.assertIsNone(result)

    def test_auth_assert_account_active_deleted(self):
        from app.routers.auth import _assert_account_active
        from fastapi import HTTPException
        row = {"account_status": "active", "deleted_at": "2024-01-01", "suspend_until": None}
        with self.assertRaises(HTTPException):
            _assert_account_active(row)

    def test_auth_assert_account_active_banned(self):
        from app.routers.auth import _assert_account_active
        from fastapi import HTTPException
        row = {"account_status": "banned", "deleted_at": None, "suspend_until": None}
        with self.assertRaises(HTTPException):
            _assert_account_active(row)

    def test_auth_verify_google_token_mock_path(self):
        """Test _verify_google_token mock branch by patching pyjwt.decode."""
        from app.routers.auth import _verify_google_token
        from unittest.mock import patch as mpatch
        fake_payload = {"sub": "12345", "email": "test@gmail.com", "iss": "accounts.google.com"}
        mock_token = "mock_google_token_anything"
        with mpatch("app.routers.auth.settings") as ms, \
             mpatch("app.routers.auth.pyjwt") as mock_pyjwt:
            ms.environment = "staging"
            mock_pyjwt.decode.return_value = fake_payload
            result = _verify_google_token(mock_token)
        self.assertEqual(result["sub"], "12345")

    def test_auth_verify_apple_token_mock_path(self):
        """Test _verify_apple_token mock branch by patching pyjwt.decode."""
        from app.routers.auth import _verify_apple_token
        from unittest.mock import patch as mpatch
        fake_payload = {"sub": "apple_uid", "iss": "https://appleid.apple.com"}
        mock_token = "mock_apple_token_anything"
        with mpatch("app.routers.auth.settings") as ms, \
             mpatch("app.routers.auth.pyjwt") as mock_pyjwt:
            ms.environment = "staging"
            mock_pyjwt.decode.return_value = fake_payload
            result = _verify_apple_token(mock_token)
        self.assertEqual(result["sub"], "apple_uid")

    def test_auth_verify_google_token_invalid_raises(self):
        """Test _verify_google_token with truly bad token raises HTTPException."""
        from app.routers.auth import _verify_google_token
        from fastapi import HTTPException
        from unittest.mock import patch as mpatch, MagicMock
        with mpatch("app.routers.auth.settings") as ms:
            ms.environment = "production"
            ms.google_client_id = None
            with mpatch("app.routers.auth._google_jwk_client") as mock_client:
                mock_client.get_signing_key_from_jwt.side_effect = Exception("bad key")
                with self.assertRaises(HTTPException):
                    _verify_google_token("definitely.not.valid")

    # ── Feed router direct coverage ───────────────────────────────────────────

    def test_feed_get_daily_compatible_with_candidate(self):
        """Cover get_daily_compatible lines 118-139 — candidate present."""
        from app.routers.feed import get_daily_compatible
        uid = uuid.uuid4()
        user = {"id": str(uid), "onboarding_completed": True}
        db = MagicMock()
        redis = AsyncMock()
        candidate = {
            "id": str(uuid.uuid4()),
            "pairing_algorithm": "brre_v2",
            "_behavioral_affinity": 0.9,
            "_cultural_score": 0.8,
        }
        with patch("app.routers.feed.sliding_window_rate_limit", new=AsyncMock()), \
             patch("app.routers.feed.fetch_daily_compatible", new=AsyncMock(return_value=candidate)):
            result = asyncio.run(get_daily_compatible(user, db, redis))
        self.assertIsNotNone(result.locked_until)
        self.assertEqual(result.pairing_algorithm, "brre_v2")
        # Internal fields stripped
        self.assertNotIn("_behavioral_affinity", result.candidate or {})

    def test_feed_get_daily_compatible_no_candidate(self):
        """Cover get_daily_compatible — no candidate (None)."""
        from app.routers.feed import get_daily_compatible
        uid = uuid.uuid4()
        user = {"id": str(uid)}
        db = MagicMock()
        redis = AsyncMock()
        with patch("app.routers.feed.sliding_window_rate_limit", new=AsyncMock()), \
             patch("app.routers.feed.fetch_daily_compatible", new=AsyncMock(return_value=None)):
            result = asyncio.run(get_daily_compatible(user, db, redis))
        self.assertIsNone(result.candidate)
        self.assertEqual(result.pairing_algorithm, "none")

    def test_feed_get_feed_cache_hit_path(self):
        """Cover get_feed cache-hit branch (refresh=False, cache populated) lines 45-60."""
        from app.routers.feed import get_feed
        uid = uuid.uuid4()
        user = {"id": str(uid), "location": None}
        db = MagicMock()
        redis = AsyncMock()
        cached_profiles = [{"id": str(uuid.uuid4())} for _ in range(20)]
        feed_result = {
            "candidates": [{"id": str(uuid.uuid4()), "_behavioral_affinity": 0.5, "_cultural_score": 0.3}],
            "total": 1,
            "has_more": False,
            "batch_id": str(uuid.uuid4()),
            "exhausted": False,
        }
        with patch("app.routers.feed.sliding_window_rate_limit", new=AsyncMock()), \
             patch("app.services.core_people_finder._get_cached_feed", new=AsyncMock(return_value=cached_profiles)), \
             patch("app.routers.feed.fetch_recommended_feed", new=AsyncMock(return_value=feed_result)):
            result = asyncio.run(get_feed(user, db, redis, limit=15, refresh=False))
        self.assertIsInstance(result.candidates, list)

    def test_feed_get_feed_refresh_path(self):
        """Cover get_feed force-refresh path lines 63-98 (DB acquire branch)."""
        from app.routers.feed import get_feed
        uid = uuid.uuid4()
        user = {"id": str(uid), "location": None}
        db = MagicMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"location": None, "revealed_preference_vector": None})
        db.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
        redis = AsyncMock()
        feed_result = {
            "candidates": [{"id": str(uuid.uuid4()), "_behavioral_affinity": 0.5, "_cultural_score": 0.3}],
            "total": 1,
            "has_more": False,
            "batch_id": str(uuid.uuid4()),
            "exhausted": False,
        }
        with patch("app.routers.feed.sliding_window_rate_limit", new=AsyncMock()), \
             patch("app.routers.feed.fetch_recommended_feed", new=AsyncMock(return_value=feed_result)):
            result = asyncio.run(get_feed(user, db, redis, limit=15, refresh=True))
        self.assertIsInstance(result.candidates, list)

    def test_feed_get_feed_refresh_user_not_found(self):
        """Cover get_feed 404 branch when DB returns None (lines 74-78)."""
        from app.routers.feed import get_feed
        from fastapi import HTTPException
        uid = uuid.uuid4()
        user = {"id": str(uid)}
        db = MagicMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        db.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
        redis = AsyncMock()
        with patch("app.routers.feed.sliding_window_rate_limit", new=AsyncMock()):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_feed(user, db, redis, limit=15, refresh=True))
        self.assertEqual(ctx.exception.status_code, 404)

    # ── Payment service pure function coverage ────────────────────────────────

    def test_payment_get_active_subscription_plans(self):
        from app.services.payment_service import get_active_subscription_plans
        plans = get_active_subscription_plans()
        self.assertIsInstance(plans, list)
        self.assertGreater(len(plans), 0)
        plan_ids = [p["plan_id"] for p in plans]
        self.assertIn("jainune_plus_monthly", plan_ids)
        self.assertIn("jainune_plus_quarterly", plan_ids)

    def test_payment_verify_signature_empty_inputs(self):
        from app.services.payment_service import verify_payment_signature
        # Empty inputs return False without raising
        self.assertFalse(verify_payment_signature("", "", ""))
        self.assertFalse(verify_payment_signature("order_id", "pay_id", ""))

    def test_payment_verify_signature_valid_hmac(self):
        import hashlib, hmac as hmaclib
        from app.services.payment_service import verify_payment_signature
        from unittest.mock import patch as mpatch
        secret = "test_razorpay_secret"
        order_id = "order_abc123"
        payment_id = "pay_xyz456"
        message = f"{order_id}|{payment_id}"
        expected_sig = hmaclib.HMAC(secret.encode(), message.encode(), digestmod=hashlib.sha256).hexdigest()
        with mpatch("app.services.payment_service.settings") as ms:
            ms.razorpay_key_secret = secret
            result = verify_payment_signature(order_id, payment_id, expected_sig)
        self.assertTrue(result)

    def test_payment_verify_signature_wrong_hmac(self):
        from app.services.payment_service import verify_payment_signature
        from unittest.mock import patch as mpatch
        with mpatch("app.services.payment_service.settings") as ms:
            ms.razorpay_key_secret = "secret"
            result = verify_payment_signature("order1", "pay1", "wrongsig")
        self.assertFalse(result)

    def test_payment_verify_webhook_signature_empty(self):
        from app.services.payment_service import verify_webhook_signature
        self.assertFalse(verify_webhook_signature(b"", ""))
        self.assertFalse(verify_webhook_signature(b"body", ""))

    def test_payment_verify_webhook_signature_valid(self):
        import hashlib, hmac as hmaclib
        from app.services.payment_service import verify_webhook_signature
        from unittest.mock import patch as mpatch
        secret = "webhook_secret"
        body = b'{"event":"payment.captured"}'
        sig = hmaclib.HMAC(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
        with mpatch("app.services.payment_service.settings") as ms:
            ms.razorpay_webhook_secret = secret
            result = verify_webhook_signature(body, sig)
        self.assertTrue(result)

    def test_payment_plan_catalogue_lookup(self):
        from app.services.payment_service import PLAN_CATALOGUE
        self.assertIn("jainune_plus_monthly", PLAN_CATALOGUE)
        plan = PLAN_CATALOGUE["jainune_plus_monthly"]
        self.assertIn("amount", plan)
        self.assertIn("currency", plan)
        self.assertEqual(plan["type"], "subscription")

    def test_payment_create_order_unknown_plan_raises(self):
        from app.services.payment_service import create_order
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(create_order("user_id", "nonexistent_plan", None))
        self.assertIn("Unknown plan", str(ctx.exception))

    def test_subscriptions_list_plans_router(self):
        """Cover subscriptions.py list_plans endpoint (lines 48-51)."""
        from app.routers.subscriptions import list_plans
        result = asyncio.run(list_plans())
        self.assertIn("plans", result)
        self.assertGreater(len(result["plans"]), 0)

    # ── security.py verify_otp direct coverage ────────────────────────────────

    def test_security_verify_otp_success(self):
        """Cover verify_otp happy path: lines 63-89."""
        from app.core.security import verify_otp, hash_otp
        from fastapi import HTTPException
        phone = "+919999999999"
        otp = "123456"
        stored = hash_otp(phone, otp).encode()
        redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])
        redis.pipeline = MagicMock(return_value=mock_pipe)
        redis.get = AsyncMock(return_value=stored)
        redis.delete = AsyncMock()
        result = asyncio.run(verify_otp(phone, otp, redis))
        self.assertTrue(result)
        self.assertEqual(redis.delete.call_count, 2)

    def test_security_verify_otp_rate_limited(self):
        """Cover verify_otp rate-limit branch: lines 65-70."""
        from app.core.security import verify_otp
        from fastapi import HTTPException
        redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[6, True])
        redis.pipeline = MagicMock(return_value=mock_pipe)
        redis.delete = AsyncMock()
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(verify_otp("+919999999998", "000000", redis))
        self.assertEqual(ctx.exception.status_code, 429)

    def test_security_verify_otp_expired(self):
        """Cover verify_otp no-stored-hash branch: lines 72-77."""
        from app.core.security import verify_otp
        from fastapi import HTTPException
        redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])
        redis.pipeline = MagicMock(return_value=mock_pipe)
        redis.get = AsyncMock(return_value=None)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(verify_otp("+919999999997", "000000", redis))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_security_verify_otp_wrong_code(self):
        """Cover verify_otp invalid-OTP branch: lines 79-85."""
        from app.core.security import verify_otp
        from fastapi import HTTPException
        redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.incr = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, True])
        redis.pipeline = MagicMock(return_value=mock_pipe)
        redis.get = AsyncMock(return_value=b"wrong_hash_value_that_will_not_match")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(verify_otp("+919999999996", "000000", redis))
        self.assertEqual(ctx.exception.status_code, 401)

    # ── core responses & errors direct coverage ──────────────────────────────

    def test_core_responses_ok_and_err(self):
        """Cover app.core.responses.ok and app.core.responses.err."""
        from app.core.responses import ok, err
        r_ok = ok({"key": "val"}, meta={"total": 1})
        self.assertTrue(r_ok["success"])
        self.assertEqual(r_ok["meta"]["total"], 1)

        r_err = err("RESOURCE_NOT_FOUND", "Item not found", details=["id: 123"])
        self.assertFalse(r_err["success"])
        self.assertEqual(r_err["error"]["code"], "RESOURCE_NOT_FOUND")
        self.assertEqual(r_err["error"]["details"], ["id: 123"])

    def test_core_errors_handlers_and_helpers(self):
        """Cover app.core.errors exception handlers and friendly resolution."""
        from app.core.errors import (
            resolve_friendly_error,
            create_error_envelope,
            http_exception_handler,
            validation_exception_handler,
            unhandled_exception_handler,
        )
        from fastapi.exceptions import RequestValidationError
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        # Fallback friendly error (line 172)
        code, title, msg = resolve_friendly_error(999, "unknown arbitrary error")
        self.assertEqual(code, "UNEXPECTED_ERROR")

        # Envelope
        env = create_error_envelope(400, "BAD_REQUEST", "Bad Request", "Something broke", raw_details=["extra"])
        self.assertFalse(env["success"])
        self.assertEqual(env["error"]["code"], "BAD_REQUEST")

        # HTTP Exception handler
        mock_req = MagicMock()
        http_exc = HTTPException(status_code=404, detail="Item missing")
        resp = asyncio.run(http_exception_handler(mock_req, http_exc))
        self.assertEqual(resp.status_code, 404)

        # Validation Exception handler (lines 214-216)
        val_exc = RequestValidationError([])
        resp_val = asyncio.run(validation_exception_handler(mock_req, val_exc))
        self.assertEqual(resp_val.status_code, 422)

        # Unhandled Exception handler (lines 219-229)
        unh_exc = RuntimeError("Server panic")
        resp_unh = asyncio.run(unhandled_exception_handler(mock_req, unh_exc))
        self.assertEqual(resp_unh.status_code, 500)

    def test_schemas_interaction_aliases_and_validation(self):
        """Cover app.models.schemas.interaction lines 29, 36, 39."""
        from app.models.schemas.interaction import InteractionActionRequest
        import uuid
        tid = uuid.uuid4()

        # target_user_id alias + superlike normalization
        ic = InteractionActionRequest(target_user_id=tid, action="superlike")
        self.assertEqual(ic.target_id, tid)
        self.assertEqual(ic.action, "super_connect")

        # Invalid action raises ValueError
        with self.assertRaises(ValueError):
            InteractionActionRequest(target_id=tid, action="invalid_super_action")

    def test_bot_defense_turnstile_and_subnet_branches(self):
        """Cover app.core.bot_defense lines 50, 66, 70, 74-96, 120-122."""
        from app.core.bot_defense import get_client_subnet, verify_turnstile_token, verify_bot_integrity
        from unittest.mock import patch, MagicMock

        # Subnet empty/none (line 50)
        self.assertEqual(get_client_subnet(None), "127.0.0.0/24")
        self.assertEqual(get_client_subnet(""), "127.0.0.0/24")

        # Turnstile token validations (lines 66, 70)
        self.assertFalse(verify_turnstile_token(None))
        self.assertFalse(verify_turnstile_token(""))
        self.assertFalse(verify_turnstile_token("short"))
        self.assertFalse(verify_turnstile_token("invalid_token"))

        # Turnstile success path (lines 74-90)
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"success": true}'
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with patch("app.core.config.settings.turnstile_secret_key", "secret123"):
                self.assertTrue(verify_turnstile_token("token_that_is_long_enough", remote_ip="1.2.3.4"))

        # Turnstile exception path (lines 94-96)
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            with patch("app.core.config.settings.turnstile_secret_key", "secret123"):
                self.assertFalse(verify_turnstile_token("token_that_is_long_enough"))

        # Bot integrity headers lookup (is_bot returns False for legitimate agent)
        is_bot, reason = verify_bot_integrity({"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"})
        self.assertFalse(is_bot)

        # Bot integrity detects bot UA
        is_bot, reason = verify_bot_integrity({"user-agent": "python-requests/2.28"})
        self.assertTrue(is_bot)



