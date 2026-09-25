"""
Unit tests for Phase 5 Decoupled Billing Architecture:
- Google Play Billing receipt verification & replay protection
- Consumable SKU handling (arcade spins & standout roses)
- Razorpay Web Checkout HTML generation for iOS PWA
- Subscription plan catalogue tier restructuring (₹399, ₹799, ₹1,499)
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.routers.subscriptions import (
    list_plans,
    verify_google_play,
    razorpay_web_checkout,
    GooglePlayVerifyBody,
)
from app.services.payment_service import get_active_subscription_plans, PLAN_CATALOGUE


def _billing_conn():
    conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    return conn


class TestDecoupledBilling(unittest.IsolatedAsyncioTestCase):

    async def test_google_verifier_accepts_current_entitlement_after_cancel_or_deferred_change(self):
        """Google's legacy API omits paymentState for canceled-but-unexpired plans and uses 3 for deferred changes."""
        from app.services.google_play_verifier import verify_google_play_purchase
        from app.core.config import settings

        expiry_ms = str(int((datetime.now(timezone.utc) + timedelta(days=10)).timestamp() * 1000))

        class _Response:
            status_code = 200
            text = ""

            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        class _Client:
            def __init__(self, response):
                self.response = response

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                return self.response

        orig_env = settings.environment
        settings.environment = "production"
        try:
            for provider_data in (
                {"paymentState": 3, "expiryTimeMillis": expiry_ms},
                {"cancelReason": 0, "expiryTimeMillis": expiry_ms},
            ):
                with patch("app.services.google_play_verifier._load_google_play_credentials", return_value={"test": True}), \
                     patch("app.services.google_play_verifier.get_google_publisher_token", new_callable=AsyncMock, return_value="token"), \
                     patch("app.services.google_play_verifier.httpx.AsyncClient", return_value=_Client(_Response(provider_data))):
                    result = await verify_google_play_purchase(
                        package_name="com.jainune.app",
                        product_id="jainune_base_399",
                        purchase_token="provider-token",
                        is_subscription=True,
                    )
                self.assertGreater(result["_verified_expires_at"], datetime.now(timezone.utc))

            with patch("app.services.google_play_verifier._load_google_play_credentials", return_value={"test": True}), \
                 patch("app.services.google_play_verifier.get_google_publisher_token", new_callable=AsyncMock, return_value="token"), \
                 patch("app.services.google_play_verifier.httpx.AsyncClient", return_value=_Client(_Response({"paymentState": 0, "expiryTimeMillis": expiry_ms}))):
                with self.assertRaises(HTTPException) as ctx:
                    await verify_google_play_purchase(
                        package_name="com.jainune.app",
                        product_id="jainune_base_399",
                        purchase_token="pending-token",
                        is_subscription=True,
                    )
                self.assertEqual(ctx.exception.status_code, 402)
        finally:
            settings.environment = orig_env

    def test_01_plan_catalogue_contains_phase5_tiers_and_consumables(self):
        """Verify PLAN_CATALOGUE has base_399, premium_799, ultra_1499, and consumable SKUs."""
        self.assertIn("jainune_base_399", PLAN_CATALOGUE)
        self.assertEqual(PLAN_CATALOGUE["jainune_base_399"]["amount"], 39900)
        self.assertEqual(PLAN_CATALOGUE["jainune_base_399"]["tier"], "base_399")

        self.assertIn("jainune_premium_799", PLAN_CATALOGUE)
        self.assertEqual(PLAN_CATALOGUE["jainune_premium_799"]["amount"], 79900)
        self.assertEqual(PLAN_CATALOGUE["jainune_premium_799"]["tier"], "premium_799")

        self.assertIn("jainune_ultra_1499", PLAN_CATALOGUE)
        self.assertEqual(PLAN_CATALOGUE["jainune_ultra_1499"]["amount"], 149900)
        self.assertEqual(PLAN_CATALOGUE["jainune_ultra_1499"]["tier"], "ultra_1499")

        self.assertIn("arcade_spins_3", PLAN_CATALOGUE)
        self.assertEqual(PLAN_CATALOGUE["arcade_spins_3"]["amount"], 7900)
        self.assertEqual(PLAN_CATALOGUE["arcade_spins_3"]["spins"], 3)

        self.assertIn("arcade_spins_10", PLAN_CATALOGUE)
        self.assertEqual(PLAN_CATALOGUE["arcade_spins_10"]["amount"], 19900)
        self.assertEqual(PLAN_CATALOGUE["arcade_spins_10"]["spins"], 10)

        self.assertIn("rose_single_49", PLAN_CATALOGUE)
        self.assertEqual(PLAN_CATALOGUE["rose_single_49"]["amount"], 4900)

    async def test_02_list_plans_returns_active_tiers(self):
        """Verify list_plans returns active ₹399, ₹799, and ₹1,499 tiers."""
        plans_data = get_active_subscription_plans()
        self.assertEqual(len(plans_data), 3)

        plan_ids = [p["plan_id"] for p in plans_data]
        self.assertListEqual(plan_ids, ["jainune_base_399", "jainune_premium_799", "jainune_ultra_1499"])

        amounts = [p["amount_inr"] for p in plans_data]
        self.assertListEqual(amounts, [399, 799, 1499])

        res = await list_plans()
        self.assertIn("plans", res)
        self.assertEqual(len(res["plans"]), 3)

    async def test_03_verify_google_play_subscription_activation(self):
        """Verify POST /verify-google-play activates subscription, grants bonus spins/roses, and records store_subscription."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Mock existing_sub is None (new purchase)
        mock_conn.fetchrow.return_value = {"id": user_id}
        mock_conn.execute.return_value = None

        body = GooglePlayVerifyBody(
            orderId="GPA.1234-5678-9012-34567",
            packageName="com.jainune.app",
            productId="jainune_premium_799",
            purchaseTime=1700000000000,
            purchaseToken="test_token_abc_123",
        )

        with patch("app.services.google_play_verifier.verify_google_play_purchase", new_callable=AsyncMock) as verify:
            verify.return_value = {
                "verified": True,
                "orderId": body.orderId,
                "_verified_expires_at": datetime.now(timezone.utc) + timedelta(days=30),
            }
            res = await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res["success"])
        self.assertTrue(res["activated"])
        self.assertEqual(res["tier"], "premium_799")
        self.assertEqual(res["spins_granted"], 15)
        self.assertEqual(res["roses_granted"], 3)
        self.assertIn("expires_at", res)

        # Ensure user update, arcade spins insert, and store_subscriptions insert were executed
        self.assertEqual(mock_conn.execute.call_count, 3)
        self.assertIn(body.purchaseToken, mock_conn.execute.call_args_list[0].args)

    async def test_04_verify_google_play_replay_defense(self):
        """Verify POST /verify-google-play returns idempotent response for same user, rejects different user."""
        user_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        expiry = datetime.now(timezone.utc) + timedelta(days=25)

        # Scenario A: Same user re-submits receipt (idempotent success)
        mock_conn.fetch.return_value = [{
            "id": uuid.uuid4(),
            "user_id": user_id,
            "status": "active",
            "expires_at": expiry,
            "sku": "jainune_base_399",
            "original_transaction_id": "legacy-order",
            "latest_transaction_id": "test_token_abc_123",
        }]

        body = GooglePlayVerifyBody(
            orderId="GPA.1234-5678-9012-34567",
            packageName="com.jainune.app",
            productId="jainune_base_399",
            purchaseTime=1700000000000,
            purchaseToken="test_token_abc_123",
        )

        with patch("app.services.google_play_verifier.verify_google_play_purchase", new_callable=AsyncMock) as verify:
            verify.return_value = {
                "verified": True,
                "orderId": body.orderId,
                "_verified_expires_at": expiry,
            }
            res = await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res["success"])
        self.assertTrue(res["idempotent"])
        self.assertEqual(res["expires_at"], expiry.isoformat())

        # Scenario B: Different user attempts to claim the same order ID (replay attack)
        mock_conn.fetch.return_value = [{
            "id": uuid.uuid4(),
            "user_id": other_user_id,
            "status": "active",
            "expires_at": expiry,
            "sku": "jainune_base_399",
            "original_transaction_id": "legacy-order",
            "latest_transaction_id": "test_token_abc_123",
        }]

        with patch("app.services.google_play_verifier.verify_google_play_purchase", new_callable=AsyncMock) as verify:
            verify.return_value = {
                "verified": True,
                "orderId": body.orderId,
                "_verified_expires_at": expiry,
            }
            with self.assertRaises(HTTPException) as ctx:
                await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_05_verify_google_play_consumable_arcade_spins(self):
        """Verify consumable arcade spin purchase credits spins and records consumed status."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_conn.fetchrow.return_value = {"id": user_id}
        mock_conn.execute.return_value = None

        body = GooglePlayVerifyBody(
            orderId="GPA.9999-8888-7777-66666",
            packageName="com.jainune.app",
            productId="arcade_spins_10",
            purchaseTime=1700000000000,
            purchaseToken="token_spins_10",
        )

        with patch("app.services.google_play_verifier.verify_google_play_purchase", new_callable=AsyncMock) as verify:
            verify.return_value = {"verified": True, "orderId": body.orderId}
            res = await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res["success"])
        self.assertTrue(res["consumable"])
        self.assertEqual(res["spins_added"], 10)

    async def test_06_razorpay_web_checkout_renders_html(self):
        """The public page displays an existing authenticated order without creating one."""
        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.fetchrow.return_value = {
            "plan_id": "jainune_premium_799",
            "amount": 79900,
            "status": "created",
        }

        with patch("app.services.payment_service.create_order", new_callable=AsyncMock) as mock_order:
            resp = await razorpay_web_checkout(
                order_id="order_mock_razorpay_123",
                return_origin="https://app.jainune.com",
                pool=mock_pool,
            )
            mock_order.assert_not_awaited()
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            self.assertIn("nonce-", resp.headers["content-security-policy"])
            html_text = resp.body.decode("utf-8")
            self.assertIn("SECURE PWA CHECKOUT", html_text)
            self.assertIn("Premium Plan", html_text)
            self.assertIn("799", html_text)
            self.assertIn("order_mock_razorpay_123", html_text)
            self.assertIn("/v1/payments/razorpay/verify-web", html_text)
            self.assertIn("https://app.jainune.com/subscriptions", html_text)

    async def test_06_checkout_rejects_external_return_origin(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as caught:
            await razorpay_web_checkout(
                order_id="order_mock_razorpay_123",
                return_origin="https://attacker.example",
                pool=MagicMock(),
            )
        self.assertEqual(caught.exception.status_code, 400)

    async def test_07_razorpay_web_verify_success(self):
        """Verify POST /v1/payments/razorpay/verify-web cryptographically verifies signature without Bearer auth."""
        from app.routers.subscriptions import razorpay_web_verify, VerifyPaymentBody
        user_id = uuid.uuid4()
        order_id = "order_test_web_verify_123"

        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_conn.fetchrow.side_effect = [
            # 1. Fetch payment_intent
            {"user_id": user_id, "status": "created", "amount": 79900, "plan_id": "jainune_premium_799"},
            # 2. Fetch subscription_valid_until after capture
            {"subscription_valid_until": datetime.now(timezone.utc) + timedelta(days=30)},
        ]

        with patch("app.services.payment_service.verify_payment_signature", return_value=True), \
             patch("app.routers.subscriptions._fetch_captured_razorpay_payment", new_callable=AsyncMock) as fetch_capture, \
             patch("app.services.payment_service.process_payment_captured", new_callable=AsyncMock) as mock_captured:
            fetch_capture.return_value = {"order_id": order_id, "id": "pay_test_web_456", "status": "captured", "amount": 79900}
            body = VerifyPaymentBody(
                razorpay_order_id=order_id,
                razorpay_payment_id="pay_test_web_456",
                razorpay_signature="sig_valid_test_hash",
            )
            res = await razorpay_web_verify(body=body, pool=mock_pool, redis=None)
            self.assertTrue(res["success"])
            self.assertTrue(res["activated"])
            self.assertIn("expires_at", res)
            mock_captured.assert_called_once()

    async def test_08_verify_google_play_rose_and_superlike(self):
        """Verify consumable rose and superlike purchases credit super_connect_credits."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_conn.fetchrow.return_value = {"id": user_id}
        mock_conn.execute.return_value = None

        # Test Rose
        body_rose = GooglePlayVerifyBody(
            orderId="GPA.rose-1111-2222-33333",
            packageName="com.jainune.app",
            productId="rose_single_49",
            purchaseTime=1700000000000,
            purchaseToken="token_rose",
        )
        with patch("app.services.google_play_verifier.verify_google_play_purchase", new_callable=AsyncMock) as verify:
            verify.return_value = {"verified": True, "orderId": body_rose.orderId}
            res_rose = await verify_google_play(body=body_rose, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res_rose["success"])
        self.assertEqual(res_rose["roses_added"], 1)

        # Test Superlike
        body_superlike = GooglePlayVerifyBody(
            orderId="GPA.superlike-4444-5555-66666",
            packageName="com.jainune.app",
            productId="slingshot_superlike_29",
            purchaseTime=1700000000000,
            purchaseToken="token_superlike",
        )
        with patch("app.services.google_play_verifier.verify_google_play_purchase", new_callable=AsyncMock) as verify:
            verify.return_value = {"verified": True, "orderId": body_superlike.orderId}
            res_superlike = await verify_google_play(body=body_superlike, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res_superlike["success"])
        self.assertEqual(res_superlike["superlikes_added"], 1)

    async def test_google_play_verification_production_unconfigured_raises_503(self):
        """In production environment without service account credentials, verification MUST reject with 503."""
        from fastapi import HTTPException
        from app.core.config import settings
        from app.routers.subscriptions import verify_google_play, GooglePlayVerifyBody

        current_user = {
            "id": "11111111-1111-1111-1111-111111111111",
            "gender": "male",
            "subscription_tier": "free",
        }
        mock_pool = MagicMock()
        mock_conn = _billing_conn()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        body = GooglePlayVerifyBody(
            orderId="GPA.fake-order-id-12345",
            packageName="com.jainune.app",
            productId="jainune_ultra_1499",
            purchaseTime=1700000000000,
            purchaseToken="fake_token_exploit",
        )

        orig_env = settings.environment
        orig_json = settings.google_play_service_account_json
        try:
            settings.environment = "production"
            settings.google_play_service_account_json = ""
            with self.assertRaises(HTTPException) as ctx:
                await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
            self.assertEqual(ctx.exception.status_code, 503)
        finally:
            settings.environment = orig_env
            settings.google_play_service_account_json = orig_json


if __name__ == "__main__":
    unittest.main()
