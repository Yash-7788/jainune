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

try:
    import razorpay
except ImportError:
    razorpay = None

try:
    import asyncpg
except ImportError:
    asyncpg = None

from app.core.config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plan catalogue
# ---------------------------------------------------------------------------

PLAN_CATALOGUE: dict[str, dict[str, Any]] = {
    # Jainune+ flagship passes (SUBSCRIPTION_SPEC.md §3.1)
    "jainune_plus_monthly": {
        "tier": "jainune_plus",
        "amount": 49900,
        "currency": "INR",
        "validity_days": 30,
        "type": "subscription",
    },
    "jainune_plus_quarterly": {
        "tier": "jainune_plus",
        "amount": 99900,
        "currency": "INR",
        "validity_days": 90,
        "type": "subscription",
    },
    "jainune_plus_semiannual": {
        "tier": "jainune_plus",
        "amount": 169900,
        "currency": "INR",
        "validity_days": 180,
        "type": "subscription",
    },
    "jainune_plus_annual": {
        "tier": "jainune_plus",
        "amount": 279900,
        "currency": "INR",
        "validity_days": 365,
        "type": "subscription",
    },
    # Standalone 2-digit Serendipity Arcade micro-transactions (SUBSCRIPTION_SPEC.md §4)
    "arcade_wheel_spin": {
        "tier": None,
        "amount": 2900,
        "currency": "INR",
        "validity_days": 0,
        "type": "arcade",
        "spins": 1,
        "dice_rolls": 0,
    },
    "arcade_dice_roll": {
        "tier": None,
        "amount": 1900,
        "currency": "INR",
        "validity_days": 0,
        "type": "arcade",
        "spins": 0,
        "dice_rolls": 1,
    },
    "arcade_3_pack": {
        "tier": None,
        "amount": 4900,
        "currency": "INR",
        "validity_days": 0,
        "type": "arcade",
        "spins": 3,
        "dice_rolls": 3,
    },
    # Legacy tier backwards-compatibility
    "gold_monthly": {
        "tier": "gold",
        "amount": 29900,
        "currency": "INR",
        "validity_days": 30,
        "type": "subscription",
    },
    "gold_quarterly": {
        "tier": "gold",
        "amount": 79900,
        "currency": "INR",
        "validity_days": 90,
        "type": "subscription",
    },
    "platinum_monthly": {
        "tier": "platinum",
        "amount": 59900,
        "currency": "INR",
        "validity_days": 30,
        "type": "subscription",
    },
    "platinum_quarterly": {
        "tier": "platinum",
        "amount": 149900,
        "currency": "INR",
        "validity_days": 90,
        "type": "subscription",
    },
}


def _rzp_client() -> Any:
    """Return authenticated Razorpay client."""
    if razorpay is None:
        raise RuntimeError("razorpay package is not installed")
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
    2. Route by plan type:
       - subscription: update users.subscription_tier and subscription_valid_until.
       - arcade: credit user_arcade_wallet and record arcade_transactions.
    3. Mark intent as captured.
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

        plan_type = plan.get("type", "subscription")

        async with conn.transaction():
            if plan_type == "subscription":
                valid_until = datetime.now(tz=timezone.utc) + timedelta(days=plan["validity_days"])
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier        = $1,
                           subscription_valid_until = $2,
                           updated_at               = NOW()
                     WHERE id = $3
                    """,
                    plan["tier"],
                    valid_until,
                    intent["user_id"],
                )
                log.info(
                    "Subscription upgraded: user=%s tier=%s until=%s",
                    intent["user_id"],
                    plan["tier"],
                    valid_until,
                )
            elif plan_type == "arcade":
                # Micro-transaction: credit user's arcade wallet
                spins = plan.get("spins", 0)
                dice_rolls = plan.get("dice_rolls", 0)
                await conn.execute(
                    """
                    INSERT INTO user_arcade_wallet (user_id, available_spins, available_dice_rolls, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                       SET available_spins       = user_arcade_wallet.available_spins + EXCLUDED.available_spins,
                           available_dice_rolls  = user_arcade_wallet.available_dice_rolls + EXCLUDED.available_dice_rolls,
                           updated_at            = NOW()
                    """,
                    intent["user_id"],
                    spins,
                    dice_rolls,
                )
                await conn.execute(
                    """
                    INSERT INTO arcade_transactions
                        (user_id, action_type, amount_inr, spins_delta, dice_rolls_delta, razorpay_order_id, razorpay_payment_id, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'captured')
                    """,
                    intent["user_id"],
                    intent["plan_id"],
                    plan["amount"] / 100.0,
                    spins,
                    dice_rolls,
                    order_id,
                    payment_id,
                )
                log.info(
                    "Arcade wallet credited: user=%s spins=+%d dice=+%d",
                    intent["user_id"],
                    spins,
                    dice_rolls,
                )

            # Mark intent captured
            await conn.execute(
                """
                UPDATE payment_intents
                   SET status              = 'captured',
                       razorpay_payment_id = $1,
                       captured_at         = NOW()
                 WHERE razorpay_order_id   = $2
                """,
                payment_id,
                order_id,
            )


async def process_refund(
    event: dict[str, Any],
    pool: asyncpg.Pool,
) -> None:
    """Handle payment.refunded — isolate subscription downgrade vs arcade deduction."""
    refund = event.get("payload", {}).get("refund", {}).get("entity", {})
    payment_id: str = refund.get("payment_id", "")

    if not payment_id:
        return

    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            "SELECT user_id, plan_id FROM payment_intents WHERE razorpay_payment_id = $1",
            payment_id,
        )
        if intent is None:
            return

        plan = PLAN_CATALOGUE.get(intent["plan_id"], {})
        plan_type = plan.get("type", "subscription")

        async with conn.transaction():
            if plan_type == "subscription":
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier        = 'free',
                           subscription_valid_until = NULL,
                           updated_at               = NOW()
                     WHERE id = $1
                    """,
                    intent["user_id"],
                )
                log.info("Subscription revoked on refund: user=%s", intent["user_id"])
            elif plan_type == "arcade":
                # Deduct arcade credits without touching subscription
                spins = plan.get("spins", 0)
                dice_rolls = plan.get("dice_rolls", 0)
                await conn.execute(
                    """
                    UPDATE user_arcade_wallet
                       SET available_spins      = GREATEST(0, available_spins - $1),
                           available_dice_rolls = GREATEST(0, available_dice_rolls - $2),
                           updated_at           = NOW()
                     WHERE user_id = $3
                    """,
                    spins,
                    dice_rolls,
                    intent["user_id"],
                )
                await conn.execute(
                    """
                    INSERT INTO arcade_transactions
                        (user_id, action_type, amount_inr, spins_delta, dice_rolls_delta, razorpay_payment_id, status)
                    VALUES ($1, 'refund', $2, $3, $4, $5, 'refunded')
                    """,
                    intent["user_id"],
                    -(plan.get("amount", 0) / 100.0),
                    -spins,
                    -dice_rolls,
                    payment_id,
                )
                log.info("Arcade credits revoked on refund: user=%s", intent["user_id"])

            await conn.execute(
                "UPDATE payment_intents SET status = 'refunded', updated_at = NOW() WHERE razorpay_payment_id = $1",
                payment_id,
            )


async def get_effective_user_tier(
    user_id: Any,
    conn: asyncpg.Connection,
) -> str:
    """
    Returns the real-time active subscription tier for a user.
    If valid_until has expired, lazily auto-downgrades to 'free'.
    """
    row = await conn.fetchrow(
        "SELECT subscription_tier, subscription_valid_until FROM users WHERE id = $1",
        user_id,
    )
    if not row:
        return "free"

    tier = row["subscription_tier"] or "free"
    valid_until = row["subscription_valid_until"]

    if tier != "free":
        if not valid_until or valid_until < datetime.now(tz=timezone.utc):
            # Expired: lazy downgrade
            await conn.execute(
                """
                UPDATE users
                   SET subscription_tier        = 'free',
                       subscription_valid_until = NULL,
                       updated_at               = NOW()
                 WHERE id = $1
                """,
                user_id,
            )
            return "free"

    return tier

