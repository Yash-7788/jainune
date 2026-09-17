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


class TestDecoupledBilling(unittest.IsolatedAsyncioTestCase):

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
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Mock existing_sub is None (new purchase)
        mock_conn.fetchrow.side_effect = [
            None,  # Check store_subscriptions
            {"subscription_valid_until": None},  # Check user current valid
        ]
        mock_conn.execute.return_value = None

        body = GooglePlayVerifyBody(
            orderId="GPA.1234-5678-9012-34567",
            packageName="com.jainune.app",
            productId="jainune_premium_799",
            purchaseTime=1700000000000,
            purchaseToken="test_token_abc_123",
        )

        res = await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res["success"])
        self.assertTrue(res["activated"])
        self.assertEqual(res["tier"], "premium_799")
        self.assertEqual(res["spins_granted"], 15)
        self.assertEqual(res["roses_granted"], 3)
        self.assertIn("expires_at", res)

        # Ensure user update, arcade spins insert, and store_subscriptions insert were executed
        self.assertEqual(mock_conn.execute.call_count, 3)

    async def test_04_verify_google_play_replay_defense(self):
        """Verify POST /verify-google-play returns idempotent response for same user, rejects different user."""
        user_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        expiry = datetime.now(timezone.utc) + timedelta(days=25)

        # Scenario A: Same user re-submits receipt (idempotent success)
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "status": "active",
            "expires_at": expiry,
        }

        body = GooglePlayVerifyBody(
            orderId="GPA.1234-5678-9012-34567",
            packageName="com.jainune.app",
            productId="jainune_base_399",
            purchaseTime=1700000000000,
            purchaseToken="test_token_abc_123",
        )

        res = await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res["success"])
        self.assertTrue(res["idempotent"])
        self.assertEqual(res["expires_at"], expiry.isoformat())

        # Scenario B: Different user attempts to claim the same order ID (replay attack)
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "user_id": other_user_id,
            "status": "active",
            "expires_at": expiry,
        }

        with self.assertRaises(HTTPException) as ctx:
            await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_05_verify_google_play_consumable_arcade_spins(self):
        """Verify consumable arcade spin purchase credits spins and records consumed status."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id)}

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_conn.fetchrow.return_value = None  # Not previously claimed
        mock_conn.execute.return_value = None

        body = GooglePlayVerifyBody(
            orderId="GPA.9999-8888-7777-66666",
            packageName="com.jainune.app",
            productId="arcade_spins_10",
            purchaseTime=1700000000000,
            purchaseToken="token_spins_10",
        )

        res = await verify_google_play(body=body, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res["success"])
        self.assertTrue(res["consumable"])
        self.assertEqual(res["spins_added"], 10)

    async def test_06_razorpay_web_checkout_renders_html(self):
        """Verify GET /razorpay/checkout generates HTML checkout page pointing to web-verify."""
        user_id = str(uuid.uuid4())
        mock_pool = MagicMock()

        with patch("app.services.payment_service.create_order", new_callable=AsyncMock) as mock_order:
            mock_order.return_value = {
                "order_id": "order_mock_razorpay_123",
                "amount": 79900,
                "amount_paisa": 79900,
                "currency": "INR",
                "razorpay_key": "rzp_test_mock",
            }

            resp = await razorpay_web_checkout(
                plan_id="jainune_premium_799",
                user_id=user_id,
                pool=mock_pool,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            html_text = resp.body.decode("utf-8")
            self.assertIn("SECURE PWA CHECKOUT", html_text)
            self.assertIn("Premium Plan", html_text)
            self.assertIn("799", html_text)
            self.assertIn("order_mock_razorpay_123", html_text)
            self.assertIn("/v1/payments/razorpay/verify-web", html_text)

    async def test_07_razorpay_web_verify_success(self):
        """Verify POST /v1/payments/razorpay/verify-web cryptographically verifies signature without Bearer auth."""
        from app.routers.subscriptions import razorpay_web_verify, VerifyPaymentBody
        user_id = uuid.uuid4()
        order_id = "order_test_web_verify_123"

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_conn.fetchrow.side_effect = [
            # 1. Fetch payment_intent
            {"user_id": user_id, "status": "created", "amount": 79900, "plan_id": "jainune_premium_799"},
            # 2. Fetch subscription_valid_until after capture
            {"subscription_valid_until": datetime.now(timezone.utc) + timedelta(days=30)},
        ]

        with patch("app.services.payment_service.verify_payment_signature", return_value=True), \
             patch("app.services.payment_service.process_payment_captured", new_callable=AsyncMock) as mock_captured:
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
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_conn.fetchrow.return_value = None  # Not previously claimed
        mock_conn.execute.return_value = None

        # Test Rose
        body_rose = GooglePlayVerifyBody(
            orderId="GPA.rose-1111-2222-33333",
            packageName="com.jainune.app",
            productId="rose_single_49",
            purchaseTime=1700000000000,
            purchaseToken="token_rose",
        )
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
        res_superlike = await verify_google_play(body=body_superlike, current_user=current_user, pool=mock_pool, redis=None)
        self.assertTrue(res_superlike["success"])
        self.assertEqual(res_superlike["superlikes_added"], 1)


if __name__ == "__main__":
    unittest.main()
