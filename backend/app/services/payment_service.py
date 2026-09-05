"""
Razorpay payment service.

Responsibilities:
  - Create Razorpay orders (server-side)
  - Verify HMAC signature on client-side payment confirmation
  - Process webhook events (payment.captured / subscription events)
  - Persist subscription upgrades to the users table

Plan pricing (INR, in paise):
  gold_monthly      → ₹299   (29900 paise)
  gold_quarterly    → ₹799   (79900 paise)
  platinum_monthly  → ₹599   (59900 paise)
  platinum_quarterly → ₹1499 (149900 paise)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import razorpay
import asyncpg

from app.core.config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plan catalogue
# ---------------------------------------------------------------------------

PLAN_CATALOGUE: dict[str, dict[str, Any]] = {
    "gold_monthly": {
        "tier": "gold",
        "amount": 29900,
        "currency": "INR",
        "validity_days": 30,
    },
    "gold_quarterly": {
        "tier": "gold",
        "amount": 79900,
        "currency": "INR",
        "validity_days": 90,
    },
    "platinum_monthly": {
        "tier": "platinum",
        "amount": 59900,
        "currency": "INR",
        "validity_days": 30,
    },
    "platinum_quarterly": {
        "tier": "platinum",
        "amount": 149900,
        "currency": "INR",
        "validity_days": 90,
    },
}


def _rzp_client() -> razorpay.Client:
    """Return authenticated Razorpay client."""
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------


async def create_order(
    user_id: str,
    plan_id: str,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Create a Razorpay order and persist an intent record."""
    plan = PLAN_CATALOGUE.get(plan_id)
    if plan is None:
        raise ValueError(f"Unknown plan: {plan_id}")

    rzp = _rzp_client()
    order = rzp.order.create(
        {
            "amount": plan["amount"],
            "currency": plan["currency"],
            "notes": {
                "user_id": str(user_id),
                "plan_id": plan_id,
            },
        }
    )

    # Persist intent so webhook can look up user_id and plan from order_id
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payment_intents
                (razorpay_order_id, user_id, plan_id, amount, currency, status)
            VALUES ($1, $2, $3, $4, $5, 'created')
            ON CONFLICT (razorpay_order_id) DO NOTHING
            """,
            order["id"],
            user_id,
            plan_id,
            plan["amount"],
            plan["currency"],
        )

    return {
        "order_id": order["id"],
        "amount": plan["amount"],
        "currency": plan["currency"],
        "plan_id": plan_id,
        "key_id": settings.razorpay_key_id,
    }


# ---------------------------------------------------------------------------
# Client-side signature verification (non-webhook path)
# ---------------------------------------------------------------------------


def verify_payment_signature(
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    """HMAC-SHA256 verification per Razorpay docs."""
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify X-Razorpay-Signature header."""
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def process_payment_captured(
    event: dict[str, Any],
    pool: asyncpg.Pool,
) -> None:
    """
    Handle payment.captured webhook event.

    1. Look up payment_intent by order_id.
    2. Derive subscription tier and validity from plan.
    3. Update users table: subscription_tier, subscription_valid_until.
    4. Mark intent as captured.
    """
    payment = event.get("payload", {}).get("payment", {}).get("entity", {})
    order_id: str = payment.get("order_id", "")
    payment_id: str = payment.get("id", "")

    if not order_id:
        log.warning("payment.captured missing order_id")
        return

    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            "SELECT user_id, plan_id, status FROM payment_intents WHERE razorpay_order_id = $1",
            order_id,
        )
        if intent is None:
            log.error("No payment_intent for order_id=%s", order_id)
            return

        if intent["status"] == "captured":
            log.info("Duplicate webhook for order_id=%s — skipping", order_id)
            return

        plan = PLAN_CATALOGUE.get(intent["plan_id"])
        if plan is None:
            log.error("Unknown plan %s for order_id=%s", intent["plan_id"], order_id)
            return

        valid_until = datetime.now(tz=timezone.utc) + timedelta(days=plan["validity_days"])

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE users
                   SET subscription_tier       = $1,
                       subscription_valid_until = $2,
                       updated_at               = NOW()
                 WHERE id = $3
                """,
                plan["tier"],
                valid_until,
                intent["user_id"],
            )
            await conn.execute(
                """
                UPDATE payment_intents
                   SET status            = 'captured',
                       razorpay_payment_id = $1,
                       captured_at       = NOW()
                 WHERE razorpay_order_id = $2
                """,
                payment_id,
                order_id,
            )

    log.info(
        "Subscription upgraded: user=%s tier=%s until=%s",
        intent["user_id"],
        plan["tier"],
        valid_until,
    )


async def process_refund(
    event: dict[str, Any],
    pool: asyncpg.Pool,
) -> None:
    """Handle payment.refunded — downgrade user back to free."""
    refund = event.get("payload", {}).get("refund", {}).get("entity", {})
    payment_id: str = refund.get("payment_id", "")

    if not payment_id:
        return

    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            "SELECT user_id FROM payment_intents WHERE razorpay_payment_id = $1",
            payment_id,
        )
        if intent is None:
            return

        await conn.execute(
            """
            UPDATE users
               SET subscription_tier       = 'free',
                   subscription_valid_until = NULL,
                   updated_at               = NOW()
             WHERE id = $1
            """,
            intent["user_id"],
        )

    log.info("Subscription revoked on refund: user=%s", intent["user_id"])
