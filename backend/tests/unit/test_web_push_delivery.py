"""Browser push delivery must preserve native tokens and reject arbitrary URLs."""

import json
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import push_notifications as push


class TestWebPushDelivery(unittest.IsolatedAsyncioTestCase):
    def test_endpoint_allowlist_blocks_ssrf_targets(self):
        self.assertTrue(push.valid_web_push_endpoint("https://web.push.apple.com/Q123"))
        self.assertTrue(push.valid_web_push_endpoint("https://fcm.googleapis.com/fcm/send/abc"))
        for endpoint in (
            "http://web.push.apple.com/Q123",
            "https://web.push.apple.com.evil.test/Q123",
            "https://127.0.0.1/internal",
            "https://web.push.apple.com:8443/Q123",
            "https://user@web.push.apple.com/Q123",
        ):
            self.assertFalse(push.valid_web_push_endpoint(endpoint), endpoint)

    async def test_user_tokens_include_native_and_browser_subscriptions(self):
        conn = SimpleNamespace(fetch=AsyncMock(side_effect=[
            [{"token": "ExponentPushToken[native]"}],
            [{"endpoint": "https://web.push.apple.com/Q123", "p256dh": "public", "auth": "secret"}],
        ]))
        tokens = await push.get_user_device_tokens(uuid.uuid4(), conn)
        self.assertEqual(tokens[0], "ExponentPushToken[native]")
        self.assertEqual(push._decode_web_subscription(tokens[1])["endpoint"], "https://web.push.apple.com/Q123")

    async def test_browser_send_uses_vapid_and_prunes_expired_endpoint(self):
        token = push._encode_web_subscription({
            "endpoint": "https://web.push.apple.com/Q123", "p256dh": "public", "auth": "secret",
        })
        sender = AsyncMock()
        conn = SimpleNamespace(execute=AsyncMock())
        with patch.dict(sys.modules, {"pywebpush": SimpleNamespace(webpush_async=sender)}), \
             patch.object(push.settings, "web_push_vapid_private_key", "private"), \
             patch.object(push.settings, "web_push_vapid_subject", "mailto:test@example.com"):
            self.assertTrue(await push.send_push(token, "New match", "Say hello", {"type": "new_match"}, conn))
            payload = json.loads(sender.await_args.kwargs["data"])
            self.assertEqual(payload["data"]["type"], "new_match")
            self.assertEqual(sender.await_args.kwargs["ttl"], 3600)

            # Exceptions, unlike arbitrary objects, carry the failed response status.
            class GoneError(Exception):
                status_code = 410
            sender.side_effect = GoneError("gone")
            self.assertFalse(await push.send_push(token, "New match", "Say hello", {}, conn))
            conn.execute.assert_awaited_once()
            self.assertIn("web_push_subscriptions", conn.execute.await_args.args[0])

    async def test_daily_digest_reaches_web_only_user(self):
        from app.workers import notification_worker

        user_id = uuid.uuid4()
        conn = SimpleNamespace(fetch=AsyncMock(side_effect=[
            [{"user_id": user_id, "fcm_token": None, "like_count": 2}],
            [],
            [{"user_id": user_id, "endpoint": "https://web.push.apple.com/Q123",
              "p256dh": "public", "auth": "secret"}],
        ]))
        multicast = AsyncMock(return_value={"success": 1, "failure": 0})
        with patch.object(notification_worker, "_get_conn", AsyncMock(return_value=conn)), \
             patch.object(notification_worker, "_release_conn", AsyncMock()), \
             patch.object(notification_worker, "send_push_multicast", multicast):
            await notification_worker.send_daily_digest_notification()
        self.assertTrue(multicast.await_args.args[0][0].startswith("webpush:"))
        self.assertEqual(conn.fetch.await_count, 3)  # Digest, native tokens, browser tokens.
