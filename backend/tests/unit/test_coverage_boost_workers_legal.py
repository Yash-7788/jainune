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
