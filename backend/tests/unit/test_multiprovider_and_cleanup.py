"""
Unit tests for Multi-Provider Auth, Smart Disposable Email Blocking,
Hard Account Deletion / Memory Freeing, and Non-Technical Error Handling.
"""

from __future__ import annotations

import sys
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()
if "redis.asyncio" not in sys.modules:
    sys.modules["redis.asyncio"] = MagicMock()

from app.core.errors import resolve_friendly_error, create_error_envelope
from app.services.account_service import purge_user_account, soft_delete_user_account
from app.services.email_verifier import is_disposable_email, verify_bot_integrity


class TestEmailAndBotVerification(unittest.TestCase):

    def test_allowed_popular_email_domains_pass(self):
        """Major consumer providers (Gmail, Outlook, Yahoo, iCloud, Proton, Zoho, Rediffmail) must pass."""
        allowed_samples = [
            "priya.jain@gmail.com",
            "rahul.shah@outlook.com",
            "amit.patel@yahoo.com",
            "rohit.mehta@yahoo.co.in",
            "neha.doshi@icloud.com",
            "anand.k@proton.me",
            "support@zoho.com",
            "sanjay.jain@rediffmail.com",
            "admin@jainune.com",
        ]
        for email in allowed_samples:
            is_disp, reason = is_disposable_email(email)
            self.assertFalse(is_disp, f"Expected {email} to be allowed, but got: {reason}")
            self.assertEqual(reason, "")

    def test_unapproved_and_disposable_domains_blocked(self):
        """Unapproved custom domains and disposable domains must be blocked."""
        blocked_samples = [
            "test@mailinator.com",
            "hello@guerrillamail.com",
            "fake@tempmail.com",
            "user@10minutemail.com",
            "temp@yopmail.fr",
            "test@burnermail.io",
            "drop@dropmail.me",
            "random@customunverifieddomain.org",
            "scam@fake-inbox-temp.net",
        ]
        for email in blocked_samples:
            is_disp, reason = is_disposable_email(email)
            self.assertTrue(is_disp, f"Expected {email} to be blocked")
            self.assertIn("supported email provider", reason.lower())

    def test_disposable_custom_domain_fallback_mode(self):
        """When allow_custom_domains=True, disposable heuristics and lists are enforced."""
        is_disp, reason = is_disposable_email("test@mailinator.com", allow_custom_domains=True)
        self.assertTrue(is_disp)
        self.assertIn("not permitted", reason.lower())

        is_disp, reason = is_disposable_email("user@temp-burner-box.org", allow_custom_domains=True)
        self.assertTrue(is_disp)
        self.assertIn("not allowed", reason.lower())

        is_disp, reason = is_disposable_email("user@quick.buzz", allow_custom_domains=True)
        self.assertTrue(is_disp)

    def test_invalid_email_format(self):
        """Malformed email strings must be rejected."""
        invalid_samples = ["notanemail", "user@", "@domain.com", "user@.com"]
        for email in invalid_samples:
            is_disp, reason = is_disposable_email(email)
            self.assertTrue(is_disp)
            self.assertIn("format", reason.lower())

    def test_bot_integrity_detection(self):
        """Automated scripts, scrapers, and headless tools must be detected."""
        blocked_user_agents = [
            "python-requests/2.31.0",
            "curl/7.88.1",
            "PostmanRuntime/7.32.3",
            "Go-http-client/1.1",
            "Wget/1.21.3",
            "Scrapy/2.11.0",
        ]
        for ua in blocked_user_agents:
            is_bot, msg = verify_bot_integrity({"user-agent": ua})
            self.assertTrue(is_bot, f"Expected bot detection for UA: {ua}")
            self.assertIn("Automated", msg)

        # Valid mobile app UA
        mobile_ua = "Jainune-App/1.0.0 (Android 14; Mobile; Build/UP1A.231005.007)"
        is_bot, msg = verify_bot_integrity({"user-agent": mobile_ua})
        self.assertFalse(is_bot)
        self.assertEqual(msg, "")


class TestAccountPurgeAndMemoryFreeing(unittest.IsolatedAsyncioTestCase):

    async def test_purge_user_account_frees_all_storage_and_cache(self):
        """Account purge must delete S3 objects, cascaded rows, and Redis keys."""
        conn = AsyncMock()
        tx_mock = MagicMock()
        tx_mock.__aenter__ = AsyncMock(return_value=None)
        tx_mock.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=tx_mock)

        redis = AsyncMock()
        redis.delete = AsyncMock(return_value=1)
        redis.scan = AsyncMock(return_value=(0, []))

        user_id = uuid.uuid4()
        conn.fetchrow.return_value = {
            "phone_number": "+919876543210",
            "email": "user@example.com",
        }
        conn.fetch.return_value = [
            {"s3_key": "media/user_1/photo_1.jpg"},
            {"s3_key": "media/user_1/voice_1.m4a"},
        ]

        with patch("app.services.account_service._delete_s3_keys_sync") as mock_s3_del:
            result = await purge_user_account(user_id, conn, redis)

            # Assert S3 deletion called for both files
            mock_s3_del.assert_called_once_with([
                "media/user_1/photo_1.jpg",
                "media/user_1/voice_1.m4a",
            ])

            # Assert DB deletion executed
            executed_queries = [call[0][0] for call in conn.execute.call_args_list]
            self.assertTrue(any("DELETE FROM users WHERE id = $1" in q for q in executed_queries))
            self.assertTrue(any("DELETE FROM user_media WHERE user_id = $1" in q for q in executed_queries))
            self.assertTrue(any("DELETE FROM refresh_tokens WHERE user_id = $1" in q for q in executed_queries))
            self.assertTrue(any("DELETE FROM user_blocks" in q for q in executed_queries))

            # Assert Redis cache & quota memory freed
            redis.delete.assert_called()

            self.assertEqual(result["status"], "purged")
            self.assertEqual(result["media_files_deleted"], 2)

    async def test_soft_delete_user_account_anonymizes_pii(self):
        """Soft delete must anonymize PII and revoke active session."""
        conn = AsyncMock()
        tx_mock = MagicMock()
        tx_mock.__aenter__ = AsyncMock(return_value=None)
        tx_mock.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=tx_mock)

        redis = AsyncMock()
        user_id = uuid.uuid4()

        result = await soft_delete_user_account(user_id, conn, redis)

        executed_queries = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("account_status   = 'deleted'" in q for q in executed_queries))
        self.assertTrue(any("DELETE FROM refresh_tokens" in q for q in executed_queries))
        self.assertEqual(result["status"], "soft_deleted")


class TestUserFriendlyErrorHandling(unittest.TestCase):

    def test_non_technical_humorous_error_resolution(self):
        """Technical exceptions must be converted to warm, witty, non-technical copy."""
        # 1. Disposable email error
        code, title, msg = resolve_friendly_error(400, "Temporary or disposable email addresses are not permitted.")
        self.assertEqual(code, "DISPOSABLE_EMAIL_BLOCKED")
        self.assertIn("Real Connections Only", title)
        self.assertIn("burner inboxes break Cupid's heart", msg)
        self.assertNotIn("400", msg)

        # 2. Bot client detected
        code, title, msg = resolve_friendly_error(403, "Automated or unsupported client detected.")
        self.assertEqual(code, "CLIENT_INTEGRITY_FAILED")
        self.assertIn("Are You a Robot", title)
        self.assertIn("anti-bot radar", msg)
        self.assertNotIn("403", msg)

        # 3. Rate limiting / breather
        code, title, msg = resolve_friendly_error(429, "Too many OTP requests in sliding window")
        self.assertEqual(code, "OTP_RATE_LIMIT")
        self.assertIn("Patience, Young Cupid", title)
        self.assertNotIn("429", msg)

        # 4. Expired session
        code, title, msg = resolve_friendly_error(401, "Invalid or expired token")
        self.assertEqual(code, "SESSION_EXPIRED")
        self.assertIn("Time Flies", title)
        self.assertIn("beauty sleep", msg)

        # 5. Daily connect limits
        code, title, msg = resolve_friendly_error(429, "Daily like limit reached")
        self.assertEqual(code, "DAILY_LIMIT_REACHED")
        self.assertIn("Cupid's Quiver", title)

        # 6. Database / 500 error
        code, title, msg = resolve_friendly_error(500, "asyncpg.exceptions.UniqueViolationError: duplicate key")
        self.assertEqual(code, "TEMPORARY_ERROR")
        self.assertIn("Chai Break", title)
        self.assertNotIn("asyncpg", msg)
        self.assertNotIn("UniqueViolation", msg)
        self.assertNotIn("500", msg)

    def test_error_envelope_structure(self):
        """Standard envelope must encapsulate non-technical error with success: false."""
        envelope = create_error_envelope(
            status_code=400,
            error_code="DISPOSABLE_EMAIL_BLOCKED",
            title="Real Connections Only! 💌",
            user_message="Please use your personal email address.",
        )
        self.assertFalse(envelope["success"])
        self.assertIsNone(envelope["data"])
        self.assertEqual(envelope["error"]["code"], "DISPOSABLE_EMAIL_BLOCKED")
        self.assertEqual(envelope["error"]["title"], "Real Connections Only! 💌")
        self.assertEqual(envelope["error"]["message"], "Please use your personal email address.")
        self.assertEqual(envelope["error"]["user_message"], "Please use your personal email address.")
        self.assertTrue(envelope["meta"]["request_id"].startswith("req_"))


class TestInputSecuritiesAndBounds(unittest.TestCase):

    def test_email_input_security_and_injection_blocks(self):
        """Email inputs must reject injections, control chars, and enforce length bounds."""
        from app.models.schemas.auth import EmailOTPRequestBody
        from pydantic import ValidationError

        # Rejects script injection
        with self.assertRaises(ValidationError):
            EmailOTPRequestBody(email="<script>alert(1)</script>@test.com")

        # Rejects control characters
        with self.assertRaises(ValidationError):
            EmailOTPRequestBody(email="user\x00@test.com")

        # Rejects oversized strings (> 254)
        with self.assertRaises(ValidationError):
            EmailOTPRequestBody(email="a" * 250 + "@example.com")

    def test_phone_number_security_bounds(self):
        """Phone numbers must strictly match Indian mobile format without injection."""
        from app.models.schemas.auth import OTPRequestBody
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            OTPRequestBody(phone_number="+919820098200; DROP TABLE users;")

        with self.assertRaises(ValidationError):
            OTPRequestBody(phone_number="09820098200")

    def test_oauth_id_token_security_bounds(self):
        """OAuth tokens must enforce JWT format and length boundaries."""
        from app.models.schemas.auth import GoogleAuthBody, AppleAuthBody
        from pydantic import ValidationError

        # Rejects non-token strings
        with self.assertRaises(ValidationError):
            GoogleAuthBody(id_token="malicious_payload_with_spaces and ; quotes")

        # Rejects oversized token payloads (> 4096)
        with self.assertRaises(ValidationError):
            AppleAuthBody(id_token="header.payload." + "x" * 4100)


if __name__ == "__main__":
    unittest.main()
