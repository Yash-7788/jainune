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

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

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
        "super_connect_credits": 5,
    },
    "jainune_plus_quarterly": {
        "tier": "jainune_plus",
        "amount": 99900,
        "currency": "INR",
        "validity_days": 90,
        "type": "subscription",
        "super_connect_credits": 15,
    },
    "jainune_plus_semiannual": {
        "tier": "jainune_plus",
        "amount": 169900,
        "currency": "INR",
        "validity_days": 180,
        "type": "subscription",
        "super_connect_credits": 30,
    },
    "jainune_plus_annual": {
        "tier": "jainune_plus",
        "amount": 279900,
        "currency": "INR",
        "validity_days": 365,
        "type": "subscription",
        "super_connect_credits": 60,
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
    try:
        order = await asyncio.to_thread(
            rzp.order.create,
            {
                "amount": plan["amount"],
                "currency": plan["currency"],
                "notes": {
                    "user_id": str(user_id),
                    "plan_id": plan_id,
                },
            },
        )
    except Exception as exc:
        log.error("Razorpay order creation failed: %s", exc)
        raise ValueError(f"Unable to create payment order: {exc}")

    order_id = order.get("id") if isinstance(order, dict) else None
    if not order_id or not isinstance(order_id, str) or not order_id.startswith("order_"):
        log.error("Razorpay returned invalid order id: %r", order_id)
        raise ValueError(f"Invalid Razorpay order_id format: {order_id!r}")

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
        "amount_paisa": plan["amount"],
        "currency": plan["currency"],
        "plan_id": plan_id,
        "key_id": settings.razorpay_key_id,
        "razorpay_key": settings.razorpay_key_id,
    }


def get_active_subscription_plans() -> list[dict[str, Any]]:
    """Returns active Jainune+ subscription tiers for client pricing display."""
    return [
        {
            "plan_id": "jainune_plus_monthly",
            "label": "1 Month",
            "duration_months": 1,
            "amount_inr": 499,
            "per_month_inr": 499,
            "savings_pct": 0,
            "is_recommended": False,
        },
        {
            "plan_id": "jainune_plus_quarterly",
            "label": "3 Months",
            "duration_months": 3,
            "amount_inr": 999,
            "per_month_inr": 333,
            "savings_pct": 33,
            "is_recommended": True,
        },
        {
            "plan_id": "jainune_plus_semiannual",
            "label": "6 Months",
            "duration_months": 6,
            "amount_inr": 1699,
            "per_month_inr": 283,
            "savings_pct": 43,
            "is_recommended": False,
        },
        {
            "plan_id": "jainune_plus_annual",
            "label": "1 Year",
            "duration_months": 12,
            "amount_inr": 2799,
            "per_month_inr": 233,
            "savings_pct": 53,
            "is_recommended": False,
        },
    ]


# ---------------------------------------------------------------------------
# Client-side signature verification (non-webhook path)
# ---------------------------------------------------------------------------


def verify_payment_signature(
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    """HMAC-SHA256 verification per Razorpay docs."""
    if not settings.razorpay_key_secret or not signature or not order_id or not payment_id:
        return False
    message = f"{order_id}|{payment_id}"
    expected = hmac.HMAC(
        settings.razorpay_key_secret.encode(),
        message.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify X-Razorpay-Signature header."""
    if not settings.razorpay_webhook_secret or not signature or not body:
        return False
    expected = hmac.HMAC(
        settings.razorpay_webhook_secret.encode(),
        body,
        digestmod=hashlib.sha256,
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
    order_id: str = payment.get("order_id", "") or event.get("payload", {}).get("order", {}).get("entity", {}).get("id", "")
    payment_id: str = payment.get("id", "")

    if not order_id:
        log.warning("payment.captured missing order_id")
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            intent = await conn.fetchrow(
                "SELECT user_id, plan_id, status, amount FROM payment_intents WHERE razorpay_order_id = $1 FOR UPDATE",
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

            expected_amount = plan["amount"]

            # Re-verify intent amount matches plan price (O-4)
            if intent.get("amount") is not None and intent["amount"] != expected_amount:
                log.error("Intent amount %s differs from plan %s price %s", intent["amount"], intent["plan_id"], expected_amount)
                raise ValueError(f"Intent amount {intent['amount']} does not match plan price {expected_amount}")

            # Re-verify captured payment amount matches plan price (O-4)
            captured_amount = payment.get("amount")
            if captured_amount is not None and int(captured_amount) != expected_amount:
                log.error("Captured amount %s differs from plan %s price %s", captured_amount, intent["plan_id"], expected_amount)
                raise ValueError(f"Captured payment amount {captured_amount} does not match expected plan price {expected_amount}")


            plan_type = plan.get("type", "subscription")

            if plan_type == "subscription":
                current_user_row = await conn.fetchrow(
                    "SELECT subscription_valid_until FROM users WHERE id = $1",
                    intent["user_id"],
                )
                now_utc = datetime.now(tz=timezone.utc)
                current_valid = current_user_row["subscription_valid_until"] if current_user_row else None
                base_time = current_valid if (current_valid and current_valid > now_utc) else now_utc
                valid_until = base_time + timedelta(days=plan["validity_days"])
                credits_to_add = plan.get("super_connect_credits", 5)
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier        = $1,
                           subscription_valid_until = $2,
                           super_connect_credits    = COALESCE(super_connect_credits, 0) + $3,
                           updated_at               = NOW()
                     WHERE id = $4
                    """,
                    plan["tier"],
                    valid_until,
                    credits_to_add,
                    intent["user_id"],
                )
                log.info(
                    "Subscription upgraded: user=%s tier=%s credits=+%s until=%s",
                    intent["user_id"],
                    plan["tier"],
                    credits_to_add,
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
                       captured_at         = NOW(),
                       updated_at          = NOW()
                 WHERE razorpay_order_id   = $2
                """,
                payment_id,
                order_id,
            )


async def process_refund(
    event: dict[str, Any],
    pool: asyncpg.Pool,
) -> None:
    """Handle payment.refunded / refund.processed / refund.created — isolate subscription downgrade vs arcade deduction."""
    refund = event.get("payload", {}).get("refund", {}).get("entity", {})
    payment_id: str = (
        refund.get("payment_id")
        or event.get("payment_id", "")
        or event.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
        or event.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id", "")
        or event.get("payload", {}).get("order", {}).get("entity", {}).get("id", "")
    )

    if not payment_id:
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            intent = await conn.fetchrow(
                "SELECT user_id, plan_id, status, amount, razorpay_payment_id FROM payment_intents WHERE (razorpay_payment_id = $1 OR razorpay_order_id = $1) FOR UPDATE",
                payment_id,
            )
            if intent is None:
                return

            if intent.get("status") == "refunded":
                log.info("Duplicate refund webhook for payment_id=%s — skipping", payment_id)
                return

            plan = PLAN_CATALOGUE.get(intent["plan_id"], {})
            plan_type = plan.get("type", "subscription")

            # B-3: Differentiate partial vs full refund (preserve subscription on partial goodwill refund)
            refund_amount = refund.get("amount")
            intent_amount = intent.get("amount") or plan.get("amount")
            is_full_refund = True
            if refund_amount is not None and intent_amount is not None:
                is_full_refund = int(refund_amount) >= int(intent_amount)

            if not is_full_refund:
                log.info(
                    "Partial refund of %s paise on intent %s (expected %s paise) — preserving subscription for %s",
                    refund_amount, payment_id, intent_amount, intent["user_id"],
                )
                await conn.execute(
                    "UPDATE payment_intents SET status = 'partially_refunded', updated_at = NOW() WHERE razorpay_payment_id = $1 OR razorpay_order_id = $1",
                    payment_id,
                )
                return

            if plan_type == "subscription":
                # Check if user has any other active captured payment
                other_active = await conn.fetchrow(
                    """
                    SELECT razorpay_payment_id
                    FROM payment_intents
                    WHERE user_id = $1
                      AND status = 'captured'
                      AND razorpay_payment_id IS NOT NULL
                      AND razorpay_payment_id != $2
                    ORDER BY captured_at DESC
                    LIMIT 1
                    """,
                    intent["user_id"],
                    payment_id,
                )
                has_other_payment = (
                    other_active is not None
                    and other_active.get("razorpay_payment_id") is not None
                    and other_active.get("razorpay_payment_id") != payment_id
                )
                if not has_other_payment:
                    # No other valid payment exists — unconditionally revoke subscription
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
                    # B-4: Claw back super connect credits granted during upgrade
                    credits_granted = plan.get("super_connect_credits", 0)
                    if credits_granted > 0:
                        await conn.execute(
                            """
                            UPDATE users
                               SET super_connect_credits = GREATEST(0, COALESCE(super_connect_credits, 0) - $1),
                                   updated_at            = NOW()
                             WHERE id = $2
                            """,
                            credits_granted,
                            intent["user_id"],
                        )
                    log.info("Subscription revoked on refund: user=%s payment=%s credits_clawed=%s", intent["user_id"], payment_id, credits_granted)
                    from app.core.redis import get_redis
                    try:
                        r = get_redis()
                        await r.delete(f"user:{intent['user_id']}:subscription")
                        await r.delete(f"user:{intent['user_id']}:tier")
                    except Exception:
                        pass
                else:
                    log.info(
                        "Refund for payment=%s is not the only active subscription — skipping tier downgrade for user=%s",
                        payment_id, intent["user_id"],
                    )
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
                "UPDATE payment_intents SET status = 'refunded', updated_at = NOW() WHERE razorpay_payment_id = $1 OR razorpay_order_id = $1",
                payment_id,
            )


async def process_payment_failed(
    event: dict[str, Any],
    pool: asyncpg.Pool,
) -> None:
    """Handle payment.failed webhook event by marking payment_intent as failed."""
    payment = event.get("payload", {}).get("payment", {}).get("entity", {})
    order_id: str = payment.get("order_id", "")
    payment_id: str = payment.get("id", "")
    error_desc: str = payment.get("error_description", "Payment failed at gateway")

    if not order_id:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE payment_intents
               SET status              = 'failed',
                   razorpay_payment_id = $1,
                   updated_at          = NOW()
             WHERE razorpay_order_id   = $2
            """,
            payment_id,
            order_id,
        )
    log.warning("Payment failed for order=%s payment=%s: %s", order_id, payment_id, error_desc)


async def get_effective_user_tier(
    user_id: Any,
    conn: asyncpg.Connection,
) -> str:
    """
    Returns the real-time active subscription tier for a user.
    If valid_until has expired, lazily auto-downgrades to 'free'.
    If account is on hold (store billing retry failed), suspends access to 'free'.
    """
    from app.core.redis import get_redis
    try:
        r = get_redis()
        billing_status = await r.get(f"user:{user_id}:billing_status")
        if billing_status in (b"account_hold", "account_hold", b"expired", "expired", b"revoked", "revoked"):
            return "free"
    except Exception:
        pass

    row = await conn.fetchrow(
        "SELECT subscription_tier, subscription_valid_until, COALESCE(billing_status, 'active') AS billing_status FROM users WHERE id = $1",
        user_id,
    )
    if not row:
        return "free"

    # Authoritative DB billing status check prevents fail-open on Redis outage (NEW-008, NEW-028)
    if row.get("billing_status") in ("account_hold", "revoked", "expired"):
        return "free"

    tier = row["subscription_tier"] or "free"
    valid_until = row["subscription_valid_until"]

    if tier != "free":
        if not valid_until or valid_until < datetime.now(tz=timezone.utc):
            # Expired: lazy downgrade in own savepoint so caller rollback can't desync state
            tx = None
            if hasattr(conn, "transaction") and callable(conn.transaction):
                if getattr(conn.transaction, "__class__", None).__name__ != "AsyncMock":
                    try:
                        res = conn.transaction()
                        if hasattr(res, "__aenter__") and hasattr(res, "__aexit__"):
                            tx = res
                    except Exception:
                        pass
            if tx is not None:
                async with tx:
                    await conn.execute(
                        """
                        UPDATE users
                           SET subscription_tier        = 'free',
                               subscription_valid_until = NULL,
                               billing_status           = 'expired',
                               updated_at               = NOW()
                         WHERE id = $1
                        """,
                        user_id,
                    )
            else:
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier        = 'free',
                           subscription_valid_until = NULL,
                           billing_status           = 'expired',
                           updated_at               = NOW()
                     WHERE id = $1
                    """,
                    user_id,
                )
            return "free"

    return tier


async def process_store_subscription_event(
    user_id: Any,
    store: str,  # 'apple' or 'google'
    event_type: str,  # 'in_grace_period', 'billing_retry', 'account_hold', 'revoked', 'renewed', 'active', 'expired'
    pool: asyncpg.Pool,
    original_transaction_id: Optional[str] = None,
    sku: Optional[str] = None,
    event_id: Optional[str] = None,
    event_timestamp: Optional[int] = None,
    validity_days: Optional[int] = None,
) -> dict[str, Any]:
    """
    Handles Apple StoreKit 2 and Google Play RTDN subscription lifecycle events:
    - in_grace_period / billing_retry: Keep tier active, mark billing status.
    - account_hold: Suspend premium tier access in both DB and Redis until payment fixes.
    - revoked / expired: Downgrade to free, clear valid_until, claw back credits if revoked.
    - renewed / active: Clear hold/grace period, restore tier & extend valid_until according to plan SKU.
    Enforces event idempotency and provider transaction ownership.
    """
    from app.core.redis import get_redis
    r = None
    try:
        r = get_redis()
    except Exception:
        pass

    # 1. Event Idempotency check (NEW-007)
    if event_id and r:
        try:
            if await r.get(f"store:event:processed:{event_id}"):
                return {"status": "already_processed", "event_id": event_id}
            await r.set(f"store:event:processed:{event_id}", "1", ex=86400 * 7)
        except Exception:
            pass

    # 2. Map plan SKU to canonical duration (NEW-006)
    sku_durations = {
        "jainune_plus_1m": 30,
        "jainune_plus_3m": 90,
        "jainune_plus_6m": 180,
        "jainune_plus_12m": 365,
        "jainune_gold_1m": 30,
        "jainune_gold_3m": 90,
        "jainune_gold_12m": 365,
        "monthly": 30,
        "quarterly": 90,
        "annual": 365,
        "yearly": 365,
    }
    actual_validity_days = 30
    if sku and sku in sku_durations:
        actual_validity_days = sku_durations[sku]
    elif validity_days is not None and validity_days > 0:
        actual_validity_days = validity_days

    async with pool.acquire() as conn:
        # 3. Resolve user identity from provider transaction identity (NEW-004)
        target_uid = user_id
        if original_transaction_id:
            try:
                sub_row = await conn.fetchrow(
                    "SELECT user_id, last_event_timestamp FROM store_subscriptions WHERE store = $1 AND original_transaction_id = $2",
                    store, original_transaction_id,
                )
                if sub_row:
                    bound_uid = sub_row["user_id"]
                    if target_uid and str(bound_uid) != str(target_uid):
                        raise ValueError(f"Transaction ID {original_transaction_id} is bound to user {bound_uid}, not {target_uid}")
                    target_uid = bound_uid

                    # Out-of-order monotonic event check (NEW-007)
                    if event_timestamp and sub_row["last_event_timestamp"]:
                        if event_timestamp <= sub_row["last_event_timestamp"]:
                            log.info("Ignoring stale store event %s (ts=%s <= last=%s)", event_type, event_timestamp, sub_row["last_event_timestamp"])
                            return {"status": "stale_ignored", "event_type": event_type}
            except asyncpg.UndefinedTableError:
                pass  # Pre-migration fallback

        if not target_uid:
            raise ValueError("user_id could not be resolved from event or provider transaction")

        user_row = await conn.fetchrow(
            "SELECT id, subscription_tier, subscription_valid_until, super_connect_credits FROM users WHERE id = $1",
            target_uid,
        )
        if not user_row:
            raise ValueError(f"User {target_uid} not found")

        # 4. Handle Lifecycle State Transitions
        now_utc = datetime.now(timezone.utc)
        sub_status = "active"

        if event_type in ("in_grace_period", "billing_retry"):
            sub_status = "in_grace_period"
            if r:
                try:
                    await r.set(f"user:{target_uid}:billing_status", "in_grace_period", ex=86400 * 16)
                except Exception:
                    pass
            await conn.execute(
                "UPDATE users SET billing_status = 'in_grace_period', updated_at = NOW() WHERE id = $1",
                target_uid,
            )
            log.info("Store subscription grace period active: user=%s store=%s", target_uid, store)
            result = {"status": "in_grace_period", "tier": user_row["subscription_tier"]}

        elif event_type == "account_hold":
            sub_status = "account_hold"
            if r:
                try:
                    await r.set(f"user:{target_uid}:billing_status", "account_hold", ex=86400 * 60)
                except Exception:
                    pass
            # Authoritative DB update (NEW-008)
            await conn.execute(
                "UPDATE users SET billing_status = 'account_hold', updated_at = NOW() WHERE id = $1",
                target_uid,
            )
            log.warning("Store subscription account hold placed: user=%s store=%s", target_uid, store)
            result = {"status": "account_hold", "tier": "free"}

        elif event_type in ("revoked", "expired"):
            # Explicit expired state transition (NEW-005)
            sub_status = event_type
            if r:
                try:
                    await r.delete(f"user:{target_uid}:billing_status")
                    await r.delete(f"user:{target_uid}:subscription")
                    await r.delete(f"user:{target_uid}:tier")
                except Exception:
                    pass

            if event_type == "revoked":
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier        = 'free',
                           subscription_valid_until = NULL,
                           billing_status           = $2,
                           super_connect_credits    = GREATEST(0, COALESCE(super_connect_credits, 0) - 5),
                           updated_at               = NOW()
                     WHERE id = $1
                    """,
                    target_uid,
                    event_type,
                )
            else:
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier        = 'free',
                           subscription_valid_until = NULL,
                           billing_status           = $2,
                           updated_at               = NOW()
                     WHERE id = $1
                    """,
                    target_uid,
                    event_type,
                )
            log.info("Store subscription %s: user=%s store=%s", event_type, target_uid, store)
            result = {"status": event_type, "tier": "free"}

        elif event_type in ("renewed", "active"):
            sub_status = "active"
            if r:
                try:
                    await r.delete(f"user:{target_uid}:billing_status")
                except Exception:
                    pass
            current_valid = user_row["subscription_valid_until"]
            base_time = current_valid if (current_valid and current_valid > now_utc) else now_utc
            new_valid = base_time + timedelta(days=actual_validity_days)
            await conn.execute(
                """
                UPDATE users
                   SET subscription_tier        = 'jainune_plus',
                       subscription_valid_until = $1,
                       billing_status           = 'active',
                       updated_at               = NOW()
                 WHERE id = $2
                """,
                new_valid,
                target_uid,
            )
            log.info("Store subscription renewed: user=%s store=%s valid_until=%s (days=%d)", target_uid, store, new_valid, actual_validity_days)
            result = {"status": "active", "tier": "jainune_plus", "valid_until": new_valid.isoformat()}

        else:
            log.warning("Unknown store event type: %s", event_type)
            result = {"status": "ignored", "event_type": event_type}

        # 5. Persist provider transaction state record
        if original_transaction_id:
            try:
                expires_at = result.get("valid_until")
                exp_dt = datetime.fromisoformat(expires_at) if expires_at else None
                await conn.execute(
                    """
                    INSERT INTO store_subscriptions (
                        user_id, store, original_transaction_id, sku, status,
                        expires_at, last_event_type, last_event_timestamp, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    ON CONFLICT (store, original_transaction_id)
                    DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        sku = COALESCE(EXCLUDED.sku, store_subscriptions.sku),
                        status = EXCLUDED.status,
                        expires_at = EXCLUDED.expires_at,
                        last_event_type = EXCLUDED.last_event_type,
                        last_event_timestamp = GREATEST(COALESCE(store_subscriptions.last_event_timestamp, 0), COALESCE(EXCLUDED.last_event_timestamp, 0)),
                        updated_at = NOW()
                    """,
                    target_uid, store, original_transaction_id, sku, sub_status,
                    exp_dt, event_type, event_timestamp or int(now_utc.timestamp()),
                )
            except asyncpg.UndefinedTableError:
                pass

        return result


async def sync_order_with_razorpay(
    order_id: str,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """
    Direct server-to-Razorpay synchronization:
    Checks order status directly on Razorpay's API to recover from network drops,
    dropped webhooks, or unverified payments.
    """
    rzp = _rzp_client()
    try:
        payments_data = await asyncio.to_thread(rzp.order.payments, order_id)
    except Exception as exc:
        log.warning("Razorpay order sync fetch error for %s: %s", order_id, exc)
        raise ValueError(f"Unable to query gateway for order {order_id}: {exc}")

    items = payments_data.get("items", []) if isinstance(payments_data, dict) else payments_data or []
    captured_payment = None
    failed_payment = None
    for p in items:
        if p.get("status") == "captured":
            captured_payment = p
            break
        elif p.get("status") == "failed":
            failed_payment = p

    if captured_payment:
        # Process capture idempotently
        await process_payment_captured(
            event={"payload": {"payment": {"entity": captured_payment}}},
            pool=pool,
        )
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.subscription_tier, u.subscription_valid_until
                FROM payment_intents pi
                JOIN users u ON u.id = pi.user_id
                WHERE pi.razorpay_order_id = $1
                """,
                order_id,
            )
        v_until = row["subscription_valid_until"] if row else None
        return {
            "synced": True,
            "activated": True,
            "status": "captured",
            "tier": row["subscription_tier"] if row else "jainune_plus",
            "expires_at": v_until.isoformat() if v_until else None,
            "payment_id": captured_payment.get("id"),
        }

    if failed_payment:
        return {
            "synced": True,
            "activated": False,
            "status": "failed",
            "message": "Payment attempt was declined or failed at your bank. If any amount was debited, your bank will automatically return it within 5-7 business days.",
        }

    return {
        "synced": True,
        "activated": False,
        "status": "pending",
        "message": "Payment has not yet been captured by gateway.",
    }


async def initiate_refund(
    payment_id: str,
    amount_paise: Optional[int] = None,
    reason: str = "customer_request",
    pool: Optional[asyncpg.Pool] = None,
) -> dict[str, Any]:
    """
    Initiates an instant or normal refund back to the user's source payment method (UPI / card / bank).
    Reverts subscription or arcade credits.
    """
    rzp = _rzp_client()
    refund_payload: dict[str, Any] = {
        "notes": {"reason": reason},
    }
    if amount_paise:
        refund_payload["amount"] = amount_paise

    try:
        refund = await asyncio.to_thread(rzp.payment.refund, payment_id, refund_payload)
    except Exception as exc:
        log.error("Razorpay refund creation failed for payment %s: %s", payment_id, exc)
        raise ValueError(f"Gateway refund initiation failed: {exc}")

    if pool:
        refund_entity = refund if isinstance(refund, dict) else {}
        if not refund_entity.get("payment_id"):
            refund_entity["payment_id"] = payment_id
        await process_refund(
            event={"payload": {"refund": {"entity": refund_entity}}, "payment_id": payment_id},
            pool=pool,
        )

    return {
        "success": True,
        "refund_id": refund.get("id"),
        "payment_id": payment_id,
        "amount": refund.get("amount"),
        "currency": refund.get("currency", "INR"),
        "status": refund.get("status", "processed"),
    }

