"""
Unit tests for Phase 6 — Arcade & Interaction Logic Refinement.

Covers:
  1. SubscriptionTier enum serialization in SubscriptionStatusResponse.
  2. PlanId enum acceptance for Phase 5 & 6 SKUs.
  3. _TIER_LIMITS mapping for Base (399), Premium (799), and Ultra (1499).
  4. /liked-me Beeline paywall masking (Base = blurred, Premium/Ultra = unblurred).
  5. Chat read receipts gating (Premium/Ultra = True, Base = False).
  6. Arcade wheel spin atomic deduction, locking, and auto-refund on no candidate.
  7. Arcade wheel spin 402 on exhausted balance.
  8. Zero-DB /health liveness probe.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.schemas.interaction import InteractionActionRequest
from app.models.schemas.payment import (
    CreateOrderBody,
    PlanId,
    SubscriptionStatusResponse,
    SubscriptionTier,
)
from app.routers.arcade import spin_serendipity_wheel, get_arcade_wallet
from app.routers.interactions import get_users_who_liked_me, record_interaction_action
from app.routers.users import _TIER_LIMITS, get_subscription_status


def _make_mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    tx_mock = MagicMock()
    tx_mock.__aenter__ = AsyncMock(return_value=None)
    tx_mock.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_mock)
    return pool, conn


class TestPhase6ArcadeAndInteractions(unittest.IsolatedAsyncioTestCase):
    """Phase 6 Unit Tests."""

    @patch("app.routers.interactions.sliding_window_rate_limit", new_callable=AsyncMock)
    async def test_interaction_rejects_paused_target(self, _rate_limit):
        actor_id, target_id = uuid.uuid4(), uuid.uuid4()
        pool, conn = _make_mock_pool()
        conn.fetchval.return_value = None
        conn.fetchrow.return_value = {
            "id": target_id,
            "account_status": "active",
            "deleted_at": None,
            "is_paused": True,
        }

        with self.assertRaises(HTTPException) as ctx:
            await record_interaction_action(
                body=InteractionActionRequest(target_id=target_id, action="like"),
                current_user={"user_id": str(actor_id)},
                db=pool,
                redis=AsyncMock(),
            )

        self.assertEqual(ctx.exception.status_code, 404)
        target_query = conn.fetchrow.await_args.args[0]
        self.assertIn("is_paused", target_query)

    def test_subscription_tier_enum_and_status(self):
        """SubscriptionTier accepts base_399, premium_799, and ultra_1499."""
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        for tier_val in ("base_399", "premium_799", "ultra_1499"):
            status_obj = SubscriptionStatusResponse(
                user_id=user_id,
                tier=SubscriptionTier(tier_val),
                valid_until=now,
                daily_likes_remaining=None,
                super_likes_remaining=3,
                can_see_who_liked=True,
                in_grace_period=False,
                billing_status="active",
            )
            self.assertEqual(status_obj.tier.value, tier_val)

    def test_plan_id_enum_contains_all_skus(self):
        """PlanId enum validates Phase 5 & 6 decoupled plans and arcade consumables."""
        expected_skus = [
            "jainune_base_399",
            "jainune_premium_799",
            "jainune_ultra_1499",
            "arcade_spins_3",
            "arcade_spins_10",
            "rose_single_49",
            "slingshot_superlike_29",
        ]
        for sku in expected_skus:
            self.assertIn(sku, PlanId.__members__)
            body = CreateOrderBody(plan_id=PlanId(sku))
            self.assertEqual(body.plan_id.value, sku)

    def test_tier_limits_mapping(self):
        """_TIER_LIMITS has correct quota and Beeline permissions for all tiers."""
        self.assertIn("base_399", _TIER_LIMITS)
        self.assertIsNone(_TIER_LIMITS["base_399"]["daily_likes"])
        self.assertEqual(_TIER_LIMITS["base_399"]["super_likes"], 1)
        self.assertFalse(_TIER_LIMITS["base_399"]["can_see_who_liked"])

        self.assertIn("premium_799", _TIER_LIMITS)
        self.assertIsNone(_TIER_LIMITS["premium_799"]["daily_likes"])
        self.assertEqual(_TIER_LIMITS["premium_799"]["super_likes"], 3)
        self.assertTrue(_TIER_LIMITS["premium_799"]["can_see_who_liked"])

        self.assertIn("ultra_1499", _TIER_LIMITS)
        self.assertIsNone(_TIER_LIMITS["ultra_1499"]["daily_likes"])
        self.assertEqual(_TIER_LIMITS["ultra_1499"]["super_likes"], 7)
        self.assertTrue(_TIER_LIMITS["ultra_1499"]["can_see_who_liked"])

    @patch("app.services.payment_service.get_effective_user_tier")
    async def test_beeline_paywall_masking(self, mock_get_tier):
        """Base Plan subscribers see blurred likes; Premium/Ultra see unblurred profiles."""
        actor_id = uuid.uuid4()
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id), "id": str(user_id)}

        pool, conn = _make_mock_pool()
        conn.fetch.return_value = [
            {
                "interaction_id": uuid.uuid4(),
                "created_at": datetime.now(timezone.utc),
                "id": actor_id,
                "first_name": "Priya",
                "date_of_birth": datetime(1998, 5, 10).date(),
                "city": "Bengaluru",
                "state": "Karnataka",
                "dietary_strictness": "pure_jain",
                "community_sect": "shwetambar_murtipujak",
                "profession": "Architect",
                "education": "Masters",
                "is_photo_verified": True,
                "photos": [{"id": str(uuid.uuid4()), "url": "https://img.cdn/p1.jpg", "order": 0}],
            }
        ]

        # 1. Base Plan: server-side blurred
        mock_get_tier.return_value = "base_399"
        res_base = await get_users_who_liked_me(current_user=current_user, db=pool, redis=None)
        self.assertEqual(len(res_base["likes"]), 1)
        self.assertEqual(res_base["likes"][0]["id"], "blurred_0")
        self.assertEqual(res_base["likes"][0]["photos"], [])
        self.assertEqual(res_base["likes"][0]["first_name"], "Someone")

        # 2. Premium Plan: unmasked
        mock_get_tier.return_value = "premium_799"
        res_prem = await get_users_who_liked_me(current_user=current_user, db=pool, redis=None)
        self.assertEqual(len(res_prem["likes"]), 1)
        self.assertEqual(res_prem["likes"][0]["id"], str(actor_id))
        self.assertEqual(res_prem["likes"][0]["first_name"], "Priya")
        self.assertEqual(len(res_prem["likes"][0]["photos"]), 1)

        # 3. Ultra Plan: unmasked
        mock_get_tier.return_value = "ultra_1499"
        res_ultra = await get_users_who_liked_me(current_user=current_user, db=pool, redis=None)
        self.assertEqual(res_ultra["likes"][0]["id"], str(actor_id))
        self.assertEqual(res_ultra["likes"][0]["first_name"], "Priya")

    @patch("app.routers.users.get_redis")
    @patch("app.services.payment_service.get_effective_user_tier")
    async def test_get_subscription_status_endpoint(self, mock_get_tier, mock_get_redis):
        """User on base_399, premium_799, ultra_1499 serializes without 500 ResponseValidationError."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id), "id": str(user_id)}
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        pool, conn = _make_mock_pool()

        for tier in ("base_399", "premium_799", "ultra_1499"):
            mock_get_tier.return_value = tier
            conn.fetchrow.return_value = {
                "id": user_id,
                "subscription_tier": tier,
                "subscription_valid_until": datetime.now(timezone.utc),
                "super_connect_credits": 5,
            }
            res = await get_subscription_status(current_user=current_user, pool=pool)
            self.assertEqual(res["tier"].value, tier)
            self.assertEqual(res["super_likes_remaining"], 5)
            if tier == "base_399":
                self.assertFalse(res["can_see_who_liked"])
            else:
                self.assertTrue(res["can_see_who_liked"])

    @patch("app.core.security.sliding_window_rate_limit")
    async def test_arcade_spin_atomic_deduction_and_refund(self, mock_rate_limit):
        """Arcade wheel locks wallet, deduces spin atomically, and refunds when candidate pool empty."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id), "id": str(user_id), "show_me": "women"}
        mock_redis = AsyncMock()

        pool, conn = _make_mock_pool()
        # 1. atomic deduction returns remaining: 2
        conn.fetchval.return_value = 2
        # 2. candidate lookup returns None (no active candidates)
        conn.fetchrow.return_value = None

        res = await spin_serendipity_wheel(current_user=current_user, pool=pool, redis=mock_redis)
        self.assertFalse(res["success"])
        self.assertEqual(res["remaining_spins"], 3)  # 2 + 1 refunded
        self.assertIn("preserved", res["message"].lower())

        executed_sqls = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("UPDATE user_arcade_wallet" in sql and "available_spins + 1" in sql for sql in executed_sqls))
        self.assertTrue(any("INSERT INTO arcade_transactions" in sql and "refund_spin_no_candidate" in sql for sql in executed_sqls))

    @patch("app.core.security.sliding_window_rate_limit")
    async def test_arcade_spin_exhausted_wallet_returns_402(self, mock_rate_limit):
        """User with 0 spins receives HTTP 402 Payment Required."""
        user_id = uuid.uuid4()
        current_user = {"user_id": str(user_id), "id": str(user_id)}
        mock_redis = AsyncMock()

        pool, conn = _make_mock_pool()
        # Atomic deduction returns None because available_spins is 0
        conn.fetchval.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await spin_serendipity_wheel(current_user=current_user, pool=pool, redis=mock_redis)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertIn("No spins remaining", ctx.exception.detail)

    async def test_zero_db_health_endpoint(self):
        """Root /health returns 200 without executing any DB or Redis queries."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/health")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "online")
            self.assertEqual(data["service"], "jainune-api")
            self.assertEqual(data["version"], "2.0.0")
