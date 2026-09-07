"""
Unit tests for Messaging Services (SMS, WhatsApp, Email) and Payment Recovery/Refunds.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

for mod in ["asyncpg", "redis", "redis.asyncio", "boto3", "botocore", "botocore.exceptions", "celery", "celery.schedules", "razorpay"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from fastapi import HTTPException
from app.services.messaging_service import (
    send_sms_otp,
    send_whatsapp_otp,
    send_email_otp,
    dispatch_phone_otp,
    send_promotional_sms,
    send_promotional_whatsapp,
    send_promotional_email,
    broadcast_promotional_campaign,
)
from app.services.payment_service import (
    sync_order_with_razorpay,
    initiate_refund,
    process_refund,
)
from app.routers.subscriptions import sync_subscription, request_refund, SyncSubscriptionBody, RefundRequestBody
from app.routers.admin import trigger_campaign_broadcast, admin_refund_subscription, BroadcastCampaignBody, AdminRefundBody
from app.routers.auth import request_otp, request_email_otp
from app.models.schemas.auth import OTPRequestBody, EmailOTPRequestBody


class TestMessagingAndPaymentRecovery(unittest.IsolatedAsyncioTestCase):

    async def test_01_sms_otp_mock_dispatch(self):
        """Verify send_sms_otp succeeds without error in test mode."""
        await send_sms_otp("+919876543210", "123456")

    async def test_02_whatsapp_otp_mock_dispatch_and_routing(self):
        """Verify WhatsApp OTP routing and dispatch in test mode."""
        await dispatch_phone_otp("+919876543210", "654321", channel="whatsapp")
        await dispatch_phone_otp("+919876543210", "654321", channel="sms")

    async def test_03_email_otp_generation(self):
        """Verify send_email_otp executes without throwing errors."""
        await send_email_otp("test@jainune.com", "987654")

    async def test_04_auth_request_otp_whatsapp_channel(self):
        """Verify request_otp supports channel='whatsapp' and sets Redis OTP hash."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        redis.pipeline.return_value = pipe
        redis.set = AsyncMock()

        body = OTPRequestBody(phone_number="+919876543210", channel="whatsapp")
        res = await request_otp(body=body, redis=redis)
        self.assertTrue(res["success"])
        self.assertIn("phone_number", res["data"])
        redis.set.assert_called_once()

    async def test_05_auth_request_email_otp_dispatches_email(self):
        """Verify request_email_otp calls send_email_otp and sets Redis key."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[0, 1, 1, True])
        redis.pipeline.return_value = pipe
        redis.set = AsyncMock()

        request = MagicMock()
        request.headers = {}
        body = EmailOTPRequestBody(email="dev@jainune.com")

        with patch("app.routers.auth.send_email_otp", new_callable=AsyncMock) as mock_send:
            res = await request_email_otp(request=request, body=body, redis=redis)
            self.assertTrue(res["success"])
            mock_send.assert_called_once()

    async def test_06_sync_order_with_razorpay_captured(self):
        """Verify sync_order_with_razorpay identifies captured payment on gateway and updates DB."""
        mock_rzp = MagicMock()
        mock_rzp.order.payments.return_value = {
            "items": [
                {
                    "id": "pay_captured_123",
                    "order_id": "order_sync_123",
                    "status": "captured",
                    "amount": 99900,
                }
            ]
        }

        user_id = uuid.uuid4()

        class DummyTransaction:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_conn = MagicMock()
        mock_conn.transaction = MagicMock(return_value=DummyTransaction())
        mock_conn.fetchrow = AsyncMock(side_effect=[
            # intent in process_payment_captured
            {"user_id": user_id, "plan_id": "jainune_plus_quarterly", "status": "created", "amount": 99900},
            # current_user_row
            {"subscription_valid_until": None},
            # query after capture
            {"subscription_tier": "jainune_plus", "subscription_valid_until": None},
        ])
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.payment_service._rzp_client", return_value=mock_rzp):
            res = await sync_order_with_razorpay("order_sync_123", mock_pool)

        self.assertTrue(res["synced"])
        self.assertTrue(res["activated"])
        self.assertEqual(res["status"], "captured")
        self.assertEqual(res["payment_id"], "pay_captured_123")

    async def test_07_initiate_refund_calls_gateway(self):
        """Verify initiate_refund triggers Razorpay refund API."""
        mock_rzp = MagicMock()
        mock_rzp.payment.refund.return_value = {
            "id": "rfnd_test_999",
            "payment_id": "pay_test_999",
            "amount": 99900,
            "currency": "INR",
            "status": "processed",
        }

        with patch("app.services.payment_service._rzp_client", return_value=mock_rzp):
            res = await initiate_refund(
                payment_id="pay_test_999",
                amount_paise=99900,
                reason="duplicate_charge",
                pool=None,
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["refund_id"], "rfnd_test_999")
        self.assertEqual(res["status"], "processed")

    async def test_08_subscriptions_sync_endpoint(self):
        """Verify POST /v1/subscriptions/sync endpoint triggers gateway sync."""
        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={"user_id": user_id, "status": "created"})

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        body = SyncSubscriptionBody(razorpay_order_id="order_sync_abc")

        with patch("app.services.payment_service.sync_order_with_razorpay", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = {"synced": True, "activated": True, "status": "captured"}
            res = await sync_subscription(body=body, current_user=current_user, pool=mock_pool)
            self.assertTrue(res["activated"])
            mock_sync.assert_called_once_with("order_sync_abc", mock_pool)

    async def test_09_subscriptions_refund_endpoint_rejects_unowned_payment(self):
        """Verify POST /v1/subscriptions/refund rejects requests when payment belongs to another user."""
        user_id = uuid.uuid4()
        attacker_id = uuid.uuid4()
        current_user = {"user_id": attacker_id}

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={"user_id": user_id, "amount": 99900, "status": "captured"})

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        body = RefundRequestBody(razorpay_payment_id="pay_victim_123")

        with self.assertRaises(HTTPException) as ctx:
            await request_refund(body=body, current_user=current_user, pool=mock_pool)

        self.assertEqual(ctx.exception.status_code, 403)

    async def test_10_promotional_messaging_dispatch(self):
        """Verify promotional SMS, WhatsApp, and Email dispatch functions."""
        sms_res = await send_promotional_sms("+919876543210", "Special launch offer!")
        self.assertTrue(sms_res["success"])
        self.assertEqual(sms_res["channel"], "sms")

        wa_res = await send_promotional_whatsapp(
            "+919876543210",
            template_name="jainune_launch",
            parameters={"name": "Aarav"},
            fallback_message="Jai Jinendra! Special offer.",
        )
        self.assertTrue(wa_res["success"])

        email_res = await send_promotional_email(
            "aarav@jainune.com",
            subject="Special Jainune+ Offer",
            title="Unlock Deep Jain Filters",
            body_text="Save 53% on annual membership pass today.",
            offer_badge="Limited Time",
            cta_title="Claim Offer",
            cta_url="https://jainune.com/plans",
        )
        self.assertTrue(email_res)

    async def test_11_promotional_campaign_broadcast(self):
        """Verify broadcast_promotional_campaign iterates users and sends messages."""
        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"id": uuid.uuid4(), "phone_number": "+919876543210", "email": "user1@jainune.com", "first_name": "Aarav"},
            {"id": uuid.uuid4(), "phone_number": "+919876543211", "email": "user2@jainune.com", "first_name": "Priya"},
        ])

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        stats = await broadcast_promotional_campaign(
            pool=mock_pool,
            campaign_name="diwali_offer",
            title="Diwali Special Offer",
            message="Get 53% discount on Jainune+ passes.",
            channels=["email", "sms"],
            target_segment="free",
        )

        self.assertEqual(stats["campaign"], "diwali_offer")
        self.assertEqual(stats["targeted"], 2)
        self.assertEqual(stats["email_sent"], 2)
        self.assertEqual(stats["sms_sent"], 2)

    async def test_12_refund_active_fulfilled_pass_blocked(self):
        """Verify active fulfilled pass cannot be refunded self-service by user."""
        from datetime import datetime, timezone, timedelta
        user_id = uuid.uuid4()
        current_user = {"user_id": user_id}

        mock_conn = MagicMock()
        # intent
        mock_conn.fetchrow = AsyncMock(side_effect=[
            {"user_id": user_id, "amount": 99900, "status": "captured", "razorpay_order_id": "order_123"},
            # user_row with active subscription
            {"subscription_tier": "jainune_plus", "subscription_valid_until": datetime.now(timezone.utc) + timedelta(days=30)},
        ])

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        body = RefundRequestBody(razorpay_payment_id="pay_active_123")

        with self.assertRaises(HTTPException) as ctx:
            await request_refund(body=body, current_user=current_user, pool=mock_pool)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("non-refundable", ctx.exception.detail)

    async def test_13_process_refund_revokes_subscription(self):
        """Verify process_refund downgrades user to free and nullifies validity."""
        user_id = uuid.uuid4()

        class DummyTransaction:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_conn = MagicMock()
        mock_conn.transaction = MagicMock(return_value=DummyTransaction())
        mock_conn.fetchrow = AsyncMock(side_effect=[
            # intent
            {"user_id": user_id, "plan_id": "jainune_plus_monthly", "status": "captured"},
            # other_active: None
            None,
        ])
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await process_refund(
            event={"payload": {"refund": {"entity": {"payment_id": "pay_revoked_123"}}}},
            pool=mock_pool,
        )

        # Confirm users table updated to 'free'
        mock_conn.execute.assert_any_call(
            """
                        UPDATE users
                           SET subscription_tier        = 'free',
                               subscription_valid_until = NULL,
                               updated_at               = NOW()
                         WHERE id = $1
                        """,
            user_id,
        )

    async def test_14_admin_endpoints(self):
        """Verify admin campaign broadcast and admin refund endpoints execute properly."""
        admin_user = {"user_id": uuid.uuid4(), "role": "admin"}
        mock_pool = MagicMock()

        # Test admin campaign broadcast
        with patch("app.services.messaging_service.broadcast_promotional_campaign", new_callable=AsyncMock) as mock_bcast:
            mock_bcast.return_value = {"campaign": "test", "sent": 10}
            bcast_body = BroadcastCampaignBody(
                campaign_name="test_camp",
                title="Greetings",
                message="Warm wishes from Jainune",
                channels=["email"],
            )
            res = await trigger_campaign_broadcast(body=bcast_body, admin=admin_user, pool=mock_pool)
            self.assertTrue(res["success"])
            mock_bcast.assert_called_once()

        # Test admin refund
        superadmin_user = {"user_id": uuid.uuid4(), "role": "superadmin"}
        with patch("app.services.payment_service.initiate_refund", new_callable=AsyncMock) as mock_refund:
            mock_refund.return_value = {"success": True, "refund_id": "rfnd_admin_123"}
            ref_body = AdminRefundBody(
                razorpay_payment_id="pay_admin_target_123",
                reason="billing_dispute_settled",
            )
            ref_res = await admin_refund_subscription(body=ref_body, admin=superadmin_user, pool=mock_pool)
            self.assertTrue(ref_res["success"])
            mock_refund.assert_called_once()

    async def test_15_sanitization_phone_and_email(self):
        """Verify phone and email sanitizers strictly enforce valid formats and reject injection."""
        from app.services.messaging_service import _sanitize_phone, _sanitize_email

        self.assertEqual(_sanitize_phone("+919876543210"), "+919876543210")
        with self.assertRaises(HTTPException):
            _sanitize_phone("not_a_phone")
        with self.assertRaises(HTTPException):
            _sanitize_phone("+1234")  # too short
        with self.assertRaises(HTTPException):
            _sanitize_phone("+919876543210; DROP TABLE users;")

        self.assertEqual(_sanitize_email("user@example.com"), "user@example.com")
        with self.assertRaises(HTTPException):
            _sanitize_email("user\r\nBcc: evil@attacker.com")
        with self.assertRaises(HTTPException):
            _sanitize_email("invalid-email-address")

    async def test_16_otp_format_validation(self):
        """Verify OTP sending functions reject non-6-digit payloads."""
        with self.assertRaises(HTTPException):
            await send_sms_otp("+919876543210", "12345")
        with self.assertRaises(HTTPException):
            await send_sms_otp("+919876543210", "1234567")
        with self.assertRaises(HTTPException):
            await send_sms_otp("+919876543210", "abcdef")
        with self.assertRaises(HTTPException):
            await send_whatsapp_otp("+919876543210", "12a456")
        with self.assertRaises(HTTPException):
            await send_email_otp("test@jainune.com", "12345")

    async def test_17_crlf_and_html_injection_prevention(self):
        """Verify promotional email sanitizes HTML and blocks javascript: URI execution."""
        with patch("app.services.messaging_service.send_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = None
            ok = await send_promotional_email(
                to_email="test@jainune.com",
                subject="Big News",
                title="<script>alert('xss')</script>",
                body_text="Click here: <b>bold</b>",
                cta_url="javascript:alert(1)",
            )
            self.assertTrue(ok)
            mock_email.assert_called_once()
            args, kwargs = mock_email.call_args
            to_e, subj, html_b, text_b = args
            self.assertNotIn("<script>", html_b)
            self.assertIn("&lt;script&gt;", html_b)
            self.assertNotIn("javascript:alert(1)", html_b)
            self.assertIn("https://jainune.com", html_b)

    async def test_18_verify_payment_body_schema_hardening(self):
        """Verify VerifyPaymentBody rejects malformed patterns or injection payloads."""
        from app.models.schemas.payment import VerifyPaymentBody
        from pydantic import ValidationError

        valid = VerifyPaymentBody(
            razorpay_order_id="order_valid_123",
            razorpay_payment_id="pay_valid_123",
            razorpay_signature="sig_valid_123",
        )
        self.assertEqual(valid.razorpay_order_id, "order_valid_123")

        with self.assertRaises(ValidationError):
            VerifyPaymentBody(
                razorpay_order_id="order_123; DROP TABLE",
                razorpay_payment_id="pay_123",
                razorpay_signature="sig_123",
            )

    async def test_19_admin_pii_redaction_for_moderators(self):
        """Verify list_users and get_user_detail mask phone numbers and email for moderator roles."""
        from app.routers.admin import list_users, get_user_detail
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        user_uuid = uuid.uuid4()

        mock_conn.fetch = AsyncMock(return_value=[
            {"id": user_uuid, "phone_number": "+919876543210", "first_name": "Priya", "account_status": "active", "subscription_tier": "free", "trust_score": 90, "created_at": "2026-01-01"}
        ])
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Moderator sees masked phone
        mod_admin = {"user_id": uuid.uuid4(), "admin_role": "moderator"}
        res = await list_users(admin=mod_admin, pool=mock_pool)
        self.assertEqual(res["users"][0]["phone_number"], "+919*****3210")

        # Superadmin sees unmasked phone
        super_admin = {"user_id": uuid.uuid4(), "admin_role": "superadmin"}
        super_res = await list_users(admin=super_admin, pool=mock_pool)
        self.assertEqual(super_res["users"][0]["phone_number"], "+919876543210")

        # Detail view masking
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": user_uuid,
            "phone_number": "+919876543210",
            "email": "priya@example.com",
            "first_name": "Priya",
        })
        mod_detail = await get_user_detail(user_id=user_uuid, admin=mod_admin, pool=mock_pool)
        self.assertEqual(mod_detail["phone_number"], "+919*****3210")
        self.assertEqual(mod_detail["email"], "p****@example.com")


if __name__ == "__main__":
    unittest.main()
