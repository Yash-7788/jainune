"""
Unit tests for Monetization Security, Payment Idempotency, Arcade Micro-Transactions,
and Granular Refund Isolation.
"""

from __future__ import annotations

import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()
if "redis.asyncio" not in sys.modules:
    sys.modules["redis.asyncio"] = MagicMock()

from fastapi import HTTPException

from app.models.schemas.payment import PlanId, SubscriptionTier, VerifyPaymentBody
from app.routers.subscriptions import verify_payment
from app.services.payment_service import (
    PLAN_CATALOGUE,
    get_effective_user_tier,
    process_payment_captured,
    process_refund,
)


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


class TestMonetizationSecurity(unittest.IsolatedAsyncioTestCase):

    async def test_verify_payment_forbidden_for_non_owner(self):
        """Attacker attempting to verify someone else's order must receive 403."""
        pool, conn = _make_mock_pool()

        legit_owner_id = uuid.uuid4()
        attacker_id = uuid.uuid4()

        conn.fetchrow.return_value = {
            "user_id": legit_owner_id,
            "status": "created",
        }

        body = VerifyPaymentBody(
            razorpay_order_id="order_attacker_hijack",
            razorpay_payment_id="pay_123",
            razorpay_signature="sig_123",
        )

        with self.assertRaises(HTTPException) as ctx:
            await verify_payment(
                body=body,
                current_user={"user_id": attacker_id},
                pool=pool,
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Order does not belong", ctx.exception.detail)

    async def test_verify_payment_idempotency_already_captured(self):
        """Re-submitting an already captured payment returns idempotent status without re-executing."""
        pool, conn = _make_mock_pool()

        user_id = uuid.uuid4()
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "status": "captured",
        }

        body = VerifyPaymentBody(
            razorpay_order_id="order_dup_123",
            razorpay_payment_id="pay_dup_123",
            razorpay_signature="sig_dup_123",
        )

        res = await verify_payment(
            body=body,
            current_user={"user_id": user_id},
            pool=pool,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "already_captured")

    async def test_arcade_wheel_spin_credits_wallet(self):
        """Micro-transaction payment for arcade_wheel_spin credits user_arcade_wallet."""
        pool, conn = _make_mock_pool()

        user_id = uuid.uuid4()
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "arcade_wheel_spin",
            "status": "created",
        }

        event = {
            "payload": {
                "payment": {
                    "entity": {
                        "order_id": "order_spin_1",
                        "id": "pay_spin_1",
                    }
                }
            }
        }

        await process_payment_captured(event, pool)

        # Ensure user_arcade_wallet was updated with spins=1
        sql_calls = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("user_arcade_wallet" in s for s in sql_calls))
        self.assertTrue(any("arcade_transactions" in s for s in sql_calls))

    async def test_refund_isolation_arcade_does_not_wipe_subscription(self):
        """Refunding an arcade roll deducts spins but leaves subscription untouched."""
        pool, conn = _make_mock_pool()

        user_id = uuid.uuid4()
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "arcade_dice_roll",
        }

        event = {
            "payload": {
                "refund": {
                    "entity": {
                        "payment_id": "pay_dice_1",
                    }
                }
            }
        }

        await process_refund(event, pool)

        sql_calls = [call[0][0] for call in conn.execute.call_args_list]
        # Must update arcade wallet, NOT users.subscription_tier
        self.assertTrue(any("user_arcade_wallet" in s for s in sql_calls))
        self.assertFalse(any("subscription_tier        = 'free'" in s for s in sql_calls))

    async def test_refund_subscription_reverts_to_free(self):
        """Refunding a subscription resets tier to free."""
        pool, conn = _make_mock_pool()

        user_id = uuid.uuid4()
        conn.fetchrow.return_value = {
            "user_id": user_id,
            "plan_id": "jainune_plus_annual",
        }

        event = {
            "payload": {
                "refund": {
                    "entity": {
                        "payment_id": "pay_sub_1",
                    }
                }
            }
        }

        await process_refund(event, pool)

        sql_calls = [call[0][0] for call in conn.execute.call_args_list]
        self.assertTrue(any("subscription_tier        = 'free'" in s for s in sql_calls))

    async def test_lazy_subscription_downgrade(self):
        """get_effective_user_tier auto-downgrades in DB if validity period expired."""
        conn = AsyncMock()
        user_id = uuid.uuid4()

        # Expired yesterday
        expired_date = datetime.now(tz=timezone.utc) - timedelta(days=1)
        conn.fetchrow.return_value = {
            "subscription_tier": "jainune_plus",
            "subscription_valid_until": expired_date,
        }

        tier = await get_effective_user_tier(user_id, conn)
        self.assertEqual(tier, "free")
        conn.execute.assert_called_once()
        self.assertIn("subscription_tier        = 'free'", conn.execute.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
