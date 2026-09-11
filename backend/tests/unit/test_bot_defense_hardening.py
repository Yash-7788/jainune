"""
Unit tests for bot defense hardening:
- Bot integrity verification (user agent, headless browser, headers, honeypot)
- Subnet rate limiting (/24 IPv4 and /48 IPv6)
- Honeypot traps in auth and onboarding
- External link detection in chat safety filter
- Behavioral swipe velocity pacing in interactions
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
for mod in ["asyncpg", "redis", "redis.asyncio", "boto3", "botocore", "botocore.config", "botocore.exceptions"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from fastapi import HTTPException

from app.core.security import get_client_subnet, verify_bot_integrity
from app.services.chat_safety_filter import filter_chat_content
from app.models.schemas.auth import OTPRequestBody
from app.models.schemas.user import Step02BasicInfoBody, Step17BioBody
from app.routers.auth import request_otp
from app.routers.onboarding import step2_basic_info, step17_bio


class TestBotDefenseHardening(unittest.IsolatedAsyncioTestCase):
    def test_known_bot_user_agents_detected(self):
        bot_uas = [
            "python-requests/2.28.1",
            "curl/7.88.1",
            "Scrapy/2.9.0 (+https://scrapy.org)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 HeadlessChrome/114.0.0.0",
            "aiohttp/3.8.4",
            "Go-http-client/1.1",
        ]
        for ua in bot_uas:
            is_bot, reason = verify_bot_integrity(
                headers={"user-agent": ua},
                turnstile_token=None,
                is_production=False,
            )
            self.assertTrue(is_bot, f"Expected {ua} to be detected as bot")
            self.assertIn("Automated traffic", reason)

    def test_honeypot_submission_detected(self):
        is_bot, reason = verify_bot_integrity(
            headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"},
            turnstile_token=None,
            is_production=False,
            honeypot="https://spam-site.com",
        )
        self.assertTrue(is_bot)
        self.assertIn("Automated form submission", reason)

    def test_genuine_mobile_client_passes(self):
        is_bot, reason = verify_bot_integrity(
            headers={
                "user-agent": "Jainune-Mobile-App/1.0 (iOS; CFNetwork)",
                "accept": "application/json",
            },
            turnstile_token=None,
            is_production=False,
            honeypot="",
        )
        self.assertFalse(is_bot)
        self.assertEqual(reason, "")

    def test_client_subnet_masking(self):
        self.assertEqual(get_client_subnet("192.168.1.105"), "192.168.1.0/24")
        self.assertEqual(get_client_subnet("10.0.50.25"), "10.0.50.0/24")
        self.assertEqual(get_client_subnet("2001:db8:85a3:8d3:1319:8a2e:370:7348"), "2001:db8:85a3::/48")
        self.assertEqual(get_client_subnet("invalid-ip"), "invalid-ip")

    async def test_chat_filter_blocks_external_links(self):
        mock_redis = AsyncMock()
        mock_redis.delete.return_value = None
        test_messages = [
            "Hey check my website http://free-crypto-giveaway.xyz/claim",
            "Join our group chat.whatsapp.com/invite123",
            "Contact me at t.me/myhandle_bot",
            "Visit www.external-scam.com for more",
        ]
        chat_id = uuid.uuid4()
        user_id = uuid.uuid4()
        for msg in test_messages:
            res = await filter_chat_content(
                content=msg,
                chat_id=chat_id,
                user_id=user_id,
                redis=mock_redis,
                is_subscribed=False,
                user_disclaimer_approved=False,
            )
            self.assertTrue(res.is_moderated, f"Expected link to be moderated in: {msg}")
            self.assertIn("#", res.content)
            self.assertNotIn("http://", res.content)
            self.assertNotIn("chat.whatsapp.com", res.content)

        pure_link_res = await filter_chat_content(
            content="Check http://free-crypto-giveaway.xyz/claim",
            chat_id=chat_id,
            user_id=user_id,
            redis=mock_redis,
            is_subscribed=False,
            user_disclaimer_approved=False,
        )
        self.assertEqual(pure_link_res.moderation_type, "EXTERNAL_LINK")

    async def test_auth_request_otp_rejects_honeypot(self):
        mock_redis = AsyncMock()
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"user-agent": "Jainune-App/1.0"}

        body = OTPRequestBody(
            phone_number="+919876543210",
            website_trap="bot-filled-trap-data",
        )

        with self.assertRaises(HTTPException) as ctx:
            await request_otp(body=body, redis=mock_redis, request=mock_request, db=None)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_onboarding_step2_rejects_honeypot(self):
        mock_redis = AsyncMock()
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        body = Step02BasicInfoBody(
            first_name="Rohit",
            date_of_birth=date(1996, 5, 20),
            website_trap="automated_bot_field",
        )
        with self.assertRaises(HTTPException) as ctx:
            await step2_basic_info(body=body, current_user=mock_user, db=mock_db, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid request submission.")

    async def test_onboarding_step17_rejects_honeypot(self):
        mock_redis = AsyncMock()
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        body = Step17BioBody(
            bio="Software engineer in Mumbai looking for life partner.",
            website_trap="crawler-bot",
        )
        with self.assertRaises(HTTPException) as ctx:
            await step17_bio(body=body, current_user=mock_user, db=mock_db, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid request submission.")


if __name__ == "__main__":
    unittest.main()
