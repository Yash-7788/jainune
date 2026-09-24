"""
Subscriptions router — Razorpay order creation, payment verification, and webhook.

POST /v1/subscriptions/order          → create Razorpay order (authenticated)
POST /v1/subscriptions/verify         → verify client-side payment signature
POST /v1/subscriptions/webhook        → Razorpay server-to-server webhook (no auth)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import asyncpg

from app.core.config import settings
from app.core.database import get_pool
from app.core.security import sliding_window_rate_limit
from app.dependencies import get_current_user, get_redis_client
import redis.asyncio as aioredis
from app.models.schemas.payment import (
    CreateOrderBody,
    OrderResponse,
    PlansListResponse,
    SubscriptionStatusResponse,
    VerifyPaymentBody,
)
from app.services import payment_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/subscriptions", tags=["Subscriptions"])


async def _fetch_captured_razorpay_payment(payment_id: str, order_id: str) -> dict[str, Any]:
    """Fetch authoritative payment state; a signed checkout callback alone is not proof of capture."""
    try:
        fetched = await asyncio.to_thread(_rzp_payment_fetch, payment_id)
    except Exception as exc:
        log.warning("Razorpay payment status lookup failed for %s: %s", payment_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to confirm payment capture with Razorpay. Please retry shortly.",
        ) from exc

    if not isinstance(fetched, dict):
        fetched = dict(fetched)
    if fetched.get("order_id") != order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment does not belong to this order.")
    if fetched.get("status") != "captured":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has not been captured by Razorpay.")
    if fetched.get("amount") is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Razorpay did not return a captured amount.")
    return fetched


def _rzp_payment_fetch(payment_id: str) -> Any:
    """Synchronous SDK access isolated for asyncio.to_thread and easy unit testing."""
    return payment_service._rzp_client().payment.fetch(payment_id)


# ---------------------------------------------------------------------------
# Plans catalogue
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=PlansListResponse, status_code=status.HTTP_200_OK)
async def list_plans() -> dict:
    """Returns active subscription plans for mobile checkout."""
    plans = payment_service.get_active_subscription_plans()
    return {"plans": plans}


# ---------------------------------------------------------------------------
# Create Razorpay order
# ---------------------------------------------------------------------------


@router.post("/order", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: CreateOrderBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Server-side Razorpay order creation.
    The returned order_id + amount are passed to Razorpay Checkout on the client.
    """
    await sliding_window_rate_limit(
        f"ratelimit:subscriptions:order:{current_user['user_id']}", 10, 60, redis
    )
    idemp_key = None
    if x_idempotency_key:
        idemp_key = f"idempotency:order:{current_user['user_id']}:{x_idempotency_key}"
        try:
            cached = await redis.get(idemp_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        result = await payment_service.create_order(
            user_id=current_user["user_id"],
            plan_id=body.plan_id.value,
            pool=pool,
        )
        if idemp_key:
            try:
                await redis.set(idemp_key, json.dumps(result), ex=3600)
            except Exception:
                pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result


# ---------------------------------------------------------------------------
# Client-side payment verification
# ---------------------------------------------------------------------------


@router.post("/verify", status_code=status.HTTP_200_OK)
async def verify_payment(
    body: VerifyPaymentBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Client posts callback data for server-side HMAC check.
    Security protections:
      - Validates caller is the owner of the payment_intent (anti-hijack)
      - HMAC-SHA256 signature verification (anti-spoof)
      - Redis distributed lock on order_id (anti-race/double-spend)
      - Idempotent return if already captured
    """
    await sliding_window_rate_limit(
        f"ratelimit:subscriptions:verify:{current_user['user_id']}", 20, 60, redis
    )
    # 1. Verify caller owns the order and validate amount
    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            "SELECT user_id, status, amount, plan_id FROM payment_intents WHERE razorpay_order_id = $1",
            body.razorpay_order_id,
        )
    if intent is None:
        raise HTTPException(status_code=404, detail="Payment order not found")

    if str(intent["user_id"]) != str(current_user["user_id"]):
        log.warning("User %s attempted to verify order %s belonging to %s", current_user["user_id"], body.razorpay_order_id, intent["user_id"])
        raise HTTPException(status_code=403, detail="Order does not belong to the authenticated user")

    plan = payment_service.PLAN_CATALOGUE.get(intent.get("plan_id"))
    if plan and intent.get("amount") is not None and intent["amount"] != plan["amount"]:
        raise HTTPException(status_code=400, detail="Payment intent amount mismatch with plan price")

    if intent["status"] == "captured":
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT subscription_valid_until FROM users WHERE id = $1",
                intent["user_id"],
            )
        v_until = row.get("subscription_valid_until") if row else None
        return {
            "success": True,
            "activated": True,
            "expires_at": v_until.isoformat() if v_until else "",
            "message": "Payment already verified.",
            "status": "already_captured",
        }

    # 2. Verify HMAC signature
    valid = payment_service.verify_payment_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    )
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # 3. Redis distributed lock to prevent concurrent double-processing
    from app.core.redis import get_redis
    lock_key = f"lock:payment:order:{body.razorpay_order_id}"
    lock_token = uuid.uuid4().hex
    r = None
    lock_acquired = True
    try:
        r = redis
        lock_acquired = await r.set(lock_key, lock_token, nx=True, ex=30)
    except Exception:
        pass  # DB transaction FOR UPDATE gate is fallback

    if not lock_acquired:
        raise HTTPException(status_code=409, detail="Payment verification is already in progress")

    try:
        payment_entity = await _fetch_captured_razorpay_payment(
            body.razorpay_payment_id,
            body.razorpay_order_id,
        )
    except HTTPException:
        if r and lock_acquired:
            try:
                await r.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                    1, lock_key, lock_token,
                )
            except Exception:
                pass
        raise

    try:
        await payment_service.process_payment_captured(
            event={
                "payload": {
                    "payment": {
                        "entity": payment_entity,
                    }
                }
            },
            pool=pool,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if r and lock_acquired:
            try:
                release_script = """
                    if redis.call("get", KEYS[1]) == ARGV[1] then
                        return redis.call("del", KEYS[1])
                    else
                        return 0
                    end
                """
                await r.eval(release_script, 1, lock_key, lock_token)
            except Exception:
                pass

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription_valid_until FROM users WHERE id = $1",
            intent["user_id"],
        )
    v_until = dict(row).get("subscription_valid_until") if row else None

    return {
        "success": True,
        "activated": True,
        "expires_at": v_until.isoformat() if v_until else "",
        "message": "Payment verified. Account upgraded.",
    }


class SyncSubscriptionBody(BaseModel):
    razorpay_order_id: Optional[str] = Field(None, pattern=r"^order_[a-zA-Z0-9_-]+$", max_length=64)
    provider: Optional[str] = Field(None, pattern=r"^(razorpay|app_store|play_billing)$")
    store_status: Optional[str] = Field(None, pattern=r"^(active|renewed|in_grace_period|billing_retry|account_hold|revoked|expired)$")
    original_transaction_id: Optional[str] = Field(None, max_length=128)


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_subscription(
    body: Optional[SyncSubscriptionBody] = None,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis_client),
):
    """
    Directly reconciles payment status with Razorpay or mobile App Stores.
    Recovers from network drops, dropped webhooks, or unverified payments.
    Rate limited to prevent gateway quota abuse.
    """
    user_id = current_user["user_id"]
    if redis:
        await sliding_window_rate_limit(f"ratelimit:subscriptions:sync:{user_id}", 10, 60, redis)

    if body and body.store_status and body.provider in ("app_store", "play_billing"):
        # Store lifecycle events must come via /store-notification (authenticated server-to-server).
        # Allowing clients to self-report store_status is a privilege escalation vector.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store subscription events must be submitted via the server-to-server webhook endpoint.",
        )

    order_id = body.razorpay_order_id if body and body.razorpay_order_id else None

    async with pool.acquire() as conn:
        if not order_id:
            row = await conn.fetchrow(
                """
                SELECT razorpay_order_id, status FROM payment_intents
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user_id,
            )
            if not row:
                return {"synced": False, "activated": False, "message": "No recent payment orders found."}
            order_id = row["razorpay_order_id"]
            if row["status"] == "captured":
                user_row = await conn.fetchrow(
                    "SELECT subscription_tier, subscription_valid_until FROM users WHERE id = $1",
                    user_id,
                )
                v_until = user_row["subscription_valid_until"] if user_row else None
                from app.services.payment_service import get_effective_user_tier
                effective_tier = await get_effective_user_tier(user_id, conn)
                return {
                    "synced": True,
                    "activated": True,
                    "status": "already_captured",
                    "tier": effective_tier,
                    "expires_at": v_until.isoformat() if v_until else None,
                }
        else:
            row = await conn.fetchrow(
                "SELECT user_id, status FROM payment_intents WHERE razorpay_order_id = $1",
                order_id,
            )
            if not row or str(row["user_id"]) != str(user_id):
                raise HTTPException(status_code=403, detail="Order not found or does not belong to user")

    try:
        res = await payment_service.sync_order_with_razorpay(order_id, pool)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class RefundRequestBody(BaseModel):
    razorpay_payment_id: str = Field(..., pattern=r"^(pay|order)_[a-zA-Z0-9_-]+$", min_length=5, max_length=64)
    reason: Optional[str] = Field("user_cancellation", max_length=256)


@router.post("/refund", status_code=status.HTTP_200_OK)
async def request_refund(
    body: RefundRequestBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis_client),
):
    """
    Customer refund request for unfulfilled or failed transactions (Last Resort):
    Active fulfilled subscription passes are non-refundable passes.
    Refunds are permitted only for stuck, unfulfilled, or duplicate debits.
    When refund is issued, subscription is unconditionally revoked.
    """
    user_id = current_user["user_id"]
    if redis:
        await sliding_window_rate_limit(f"ratelimit:subscriptions:refund:{user_id}", 5, 300, redis)

    from datetime import datetime, timezone
    user_id = current_user["user_id"]
    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            """
            SELECT user_id, amount, status, razorpay_order_id, razorpay_payment_id, plan_id FROM payment_intents
            WHERE razorpay_payment_id = $1
            """,
            body.razorpay_payment_id,
        )
        if not intent:
            intent = await conn.fetchrow(
                """
                SELECT user_id, amount, status, razorpay_order_id, razorpay_payment_id, plan_id FROM payment_intents
                WHERE razorpay_order_id = $1
                """,
                body.razorpay_payment_id,
            )
        if not intent:
            raise HTTPException(status_code=404, detail="Payment record not found")
        if str(intent["user_id"]) != str(user_id):
            raise HTTPException(status_code=403, detail="Payment does not belong to authenticated user")
        if intent["status"] == "refunded":
            return {"success": True, "message": "Payment has already been refunded.", "status": "already_refunded"}
        if intent["status"] != "captured":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only captured transactions can be refunded. Uncaptured or failed debits auto-reverse via bank within 5 business days.",
            )

        # B-1: Arcade micro-transactions are digital consumables — non-refundable once credited
        plan = payment_service.PLAN_CATALOGUE.get(intent.get("plan_id"))
        if plan and plan.get("type") == "arcade":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Serendipity Arcade micro-transactions are non-refundable once credited.",
            )

        # B-1: Prevent refund abuse on active or previously-fulfilled passes
        user_row = await conn.fetchrow(
            "SELECT subscription_tier, subscription_valid_until FROM users WHERE id = $1",
            user_id,
        )
        now_utc = datetime.now(timezone.utc)
        is_active_fulfilled = (
            user_row
            and user_row["subscription_tier"] != "free"
            and user_row["subscription_valid_until"]
            and user_row["subscription_valid_until"] > now_utc
            and intent["status"] == "captured"
        )
        if is_active_fulfilled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active or fulfilled Jainune+ passes are non-refundable once fulfilled. If you experienced a billing issue, please contact support@jainune.com.",
            )

        # B-2: Resolve valid Razorpay payment ID (pay_*) to prevent gateway crash on order_* inputs
        payment_id_to_refund = intent.get("razorpay_payment_id") or (
            body.razorpay_payment_id if body.razorpay_payment_id.startswith("pay_") else None
        )
        if not payment_id_to_refund:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot refund transaction without a valid gateway payment ID (pay_*). Please contact support@jainune.com.",
            )

    try:
        result = await payment_service.initiate_refund(
            payment_id=payment_id_to_refund,
            amount_paise=intent["amount"],
            reason=body.reason or "customer_recovery_unfulfilled",
            pool=pool,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Webhook (no auth header — Razorpay sends from its servers)
# ---------------------------------------------------------------------------


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Razorpay webhook endpoint.
    Must be registered in Razorpay dashboard pointing to /v1/subscriptions/webhook.

    Supported events:
      - payment.captured  → upgrade subscription
      - payment.refunded  → downgrade to free
    """
    body_bytes = await request.body()

    if not payment_service.verify_webhook_signature(body_bytes, x_razorpay_signature):
        log.warning("Webhook HMAC mismatch — possible spoofed request")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_name: str = event.get("event", "")
    log.info("Razorpay webhook received: %s", event_name)

    if event_name in ("payment.captured", "order.paid"):
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_entity = event.get("payload", {}).get("order", {}).get("entity", {})
        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id") or order_entity.get("id")
        from app.core.redis import get_redis
        r = None
        order_lock_key = f"lock:payment:order:{order_id}" if order_id else None
        proc_lock_key = f"lock:payment:proc:{payment_id}" if payment_id else None
        order_lock_token = uuid.uuid4().hex
        proc_lock_token = uuid.uuid4().hex
        order_lock_acquired = False
        proc_lock_acquired = False
        try:
            r = get_redis()
            if payment_id and r:
                processed_val = await r.get(f"payment:processed:{payment_id}")
                if processed_val and isinstance(processed_val, (bytes, str)) and processed_val in (b"1", "1", b"true", "true"):
                    return {"received": True, "status": "already_processed"}
                proc_lock_acquired = await r.set(proc_lock_key, proc_lock_token, nx=True, ex=30)
                if not proc_lock_acquired:
                    return {"received": True, "status": "lock_busy"}
            if order_lock_key and r:
                order_lock_acquired = await r.set(order_lock_key, order_lock_token, nx=True, ex=30)
                if not order_lock_acquired:
                    if proc_lock_acquired:
                        release_script = """
                            if redis.call("get", KEYS[1]) == ARGV[1] then
                                return redis.call("del", KEYS[1])
                            else
                                return 0
                            end
                        """
                        try:
                            await r.eval(release_script, 1, proc_lock_key, proc_lock_token)
                        except Exception:
                            pass
                    return {"received": True, "status": "lock_busy"}
        except Exception:
            pass  # Fallback to DB transaction FOR UPDATE gate

        try:
            await payment_service.process_payment_captured(event, pool)
            if r and payment_id:
                try:
                    await r.set(f"payment:processed:{payment_id}", "1", ex=86400)
                except Exception:
                    pass
        except ValueError as exc:
            log.error("Payment validation error on webhook: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            if r:
                release_script = """
                    if redis.call("get", KEYS[1]) == ARGV[1] then
                        return redis.call("del", KEYS[1])
                    else
                        return 0
                    end
                """
                try:
                    if proc_lock_key and proc_lock_acquired:
                        await r.eval(release_script, 1, proc_lock_key, proc_lock_token)
                    if order_lock_key and order_lock_acquired:
                        await r.eval(release_script, 1, order_lock_key, order_lock_token)
                except Exception:
                    pass
    elif event_name in ("payment.refunded", "refund.processed", "refund.created"):
        await payment_service.process_refund(event, pool)
    elif event_name in ("payment.failed", "payment.dispute.created"):
        await payment_service.process_payment_failed(event, pool)
    else:
        log.debug("Unhandled webhook event: %s", event_name)

    # Always return 200 to acknowledge receipt
    return {"received": True}


class StoreNotificationBody(BaseModel):
    store: str = Field(..., pattern=r"^(apple|google)$")
    user_id: Optional[str] = None
    event_type: str = Field(..., pattern=r"^(active|renewed|in_grace_period|billing_retry|account_hold|revoked|expired)$")
    original_transaction_id: Optional[str] = None
    sku: Optional[str] = None
    event_id: Optional[str] = None
    timestamp: Optional[datetime] = None


@router.post("/store-notification", status_code=status.HTTP_200_OK)
async def store_notification_webhook(
    body: StoreNotificationBody,
    pool: asyncpg.Pool = Depends(get_pool),
    x_store_token: Optional[str] = Header(None, alias="X-Store-Webhook-Token"),
):
    """
    Apple StoreKit / Google Play RTDN server-to-server webhook.
    Handles grace periods, billing retries, account holds, and refund revocations.
    """
    expected_secret = getattr(settings, "store_webhook_secret", None) or getattr(settings, "webhook_secret", "")
    import hmac as _hmac
    if not expected_secret or not x_store_token or not _hmac.compare_digest(x_store_token, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid store webhook token")

    if not body.event_id and not body.original_transaction_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store notification must include either event_id or original_transaction_id for idempotency.",
        )

    if not body.user_id and not body.original_transaction_id:
        return {"received": True, "status": "missing_identifier"}

    uid: Optional[UUID] = None
    if body.user_id:
        try:
            uid = UUID(body.user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")

    event_ts = int(body.timestamp.timestamp()) if body.timestamp else None

    res = await payment_service.process_store_subscription_event(
        user_id=uid,
        store=body.store,
        event_type=body.event_type,
        pool=pool,
        original_transaction_id=body.original_transaction_id,
        sku=body.sku,
        event_id=body.event_id,
        event_timestamp=event_ts,
    )
    return {"received": True, "result": res}


@router.post("/cancel", status_code=status.HTTP_200_OK)
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis_client),
):
    """
    Subscription cancellation status check.
    Jainune subscriptions are fixed-duration passes (non-recurring) with no auto-renewal.
    Confirms no recurring billing exists and reports active access window.
    """
    user_id = UUID(str(current_user.get("id") or current_user.get("user_id")))
    if redis:
        await sliding_window_rate_limit(f"ratelimit:subscriptions:cancel:{user_id}", 5, 300, redis)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription_tier, subscription_valid_until FROM users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        valid_until = row["subscription_valid_until"] or datetime.now(timezone.utc)
    return {
        "success": True,
        "message": "Subscription is a non-recurring pass. No auto-renewal will occur.",
        "access_until": valid_until.isoformat() if hasattr(valid_until, "isoformat") else str(valid_until),
    }


# ---------------------------------------------------------------------------
# Google Play Billing verification (Android In-App Purchases)
# ---------------------------------------------------------------------------


class GooglePlayVerifyBody(BaseModel):
    orderId: str = Field(..., min_length=1, max_length=128)
    packageName: Optional[str] = "com.jainune.app"
    productId: str = Field(..., min_length=1, max_length=64)
    purchaseTime: Optional[Any] = None
    purchaseToken: str = Field(..., min_length=1, max_length=4096)


@router.post("/verify-google-play", status_code=status.HTTP_200_OK)
async def verify_google_play(
    body: GooglePlayVerifyBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis_client),
):
    """
    Validates Google Play Billing purchases and activates subscriptions or credits consumables.
    Google purchase tokens are the server-enforced identity. Subscription renewals
    on the same token only grant renewal bonuses when Google's verified expiry advances.
    """
    raw_uid = current_user.get("user_id") or current_user.get("id")
    try:
        user_uuid = UUID(str(raw_uid))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format.")

    if redis:
        await sliding_window_rate_limit(f"ratelimit:sub:verify_google:{user_uuid}", 20, 60, redis)

    order_id = body.orderId.strip()
    sku = body.productId.strip()
    purchase_token = body.purchaseToken.strip()

    if not order_id or not sku or not purchase_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required receipt fields.")

    if body.packageName and body.packageName != "com.jainune.app" and settings.environment == "production":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application package name.")

    plan_info = payment_service.PLAN_CATALOGUE.get(sku)
    sku_lower = sku.lower()
    is_subscription = sku_lower in ("jainune_base_399", "jainune_premium_799", "jainune_ultra_1499") or (plan_info and plan_info.get("type") == "subscription")
    is_arcade = sku_lower.startswith("arcade_") or (plan_info and plan_info.get("type") == "arcade")
    is_rose = sku_lower.startswith("rose_") or (plan_info and plan_info.get("type") == "rose")
    is_superlike = "slingshot" in sku_lower or "superlike" in sku_lower or (plan_info and plan_info.get("type") == "superlike")

    if not is_subscription and not is_arcade and not is_rose and not is_superlike:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unrecognized product SKU: {sku}")

    # Server-to-Server Google Android Publisher API verification (prevents forged receipts)
    from app.services.google_play_verifier import verify_google_play_purchase
    pkg = body.packageName or "com.jainune.app"
    verified = await verify_google_play_purchase(
        package_name=pkg,
        product_id=sku,
        purchase_token=purchase_token,
        is_subscription=is_subscription,
    )
    provider_order_id = str(verified.get("orderId") or order_id).strip()
    if not provider_order_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google Play did not return a transaction identifier.")
    if len(provider_order_id) > 128:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google Play returned a transaction identifier that cannot be stored safely.")

    verified_expiry = verified.get("_verified_expires_at") if is_subscription else None
    if is_subscription and not isinstance(verified_expiry, datetime):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google Play did not return a verified subscription expiry.")
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serialize provider-token processing across API workers and webhook callers.
            await conn.fetchval(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"google-play:{purchase_token}",
            )
            existing_rows = await conn.fetch(
                """
                SELECT id, user_id, original_transaction_id, latest_transaction_id,
                       status, expires_at, sku
                FROM store_subscriptions
                WHERE store = 'google'
                  AND (
                      original_transaction_id = $1
                      OR latest_transaction_id = $1
                      OR (length(latest_transaction_id) = 128
                          AND left($1, 128) = latest_transaction_id)
                  )
                ORDER BY created_at ASC, id ASC
                FOR UPDATE
                """,
                purchase_token,
            )
            if existing_rows:
                owners = {str(row["user_id"]) for row in existing_rows}
                if owners != {str(user_uuid)}:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This purchase token has already been claimed by another account.",
                    )
                existing_sub = existing_rows[0]
                if existing_sub.get("sku") and existing_sub["sku"] != sku:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This purchase token belongs to a different product.")

                if not is_subscription:
                    return {
                        "success": True,
                        "activated": True,
                        "consumable": True,
                        "idempotent": True,
                        "message": "Purchase was already applied.",
                    }

                previous_expiry = existing_sub.get("expires_at")
                new_period = previous_expiry is None or verified_expiry > previous_expiry
                effective_expiry = max(previous_expiry, verified_expiry) if previous_expiry else verified_expiry
                target_tier = plan_info.get("tier") if plan_info else "base_399"
                spins_to_grant = int(plan_info.get("spins", 0)) if plan_info else 0
                roses_to_grant = int(plan_info.get("roses", 0)) if plan_info else 0
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier = $1,
                           subscription_valid_until = GREATEST(COALESCE(subscription_valid_until, $2), $2),
                           billing_status = 'active',
                           super_connect_credits = COALESCE(super_connect_credits, 0) + $3,
                           last_active_at = NOW()
                     WHERE id = $4
                    """,
                    target_tier, effective_expiry, roses_to_grant if new_period else 0, user_uuid,
                )
                if new_period and spins_to_grant:
                    await conn.execute(
                        """
                        INSERT INTO user_arcade_wallet (user_id, available_spins, updated_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (user_id) DO UPDATE
                        SET available_spins = user_arcade_wallet.available_spins + EXCLUDED.available_spins,
                            updated_at = NOW()
                        """,
                        user_uuid, spins_to_grant,
                    )
                await conn.execute(
                    """
                    UPDATE store_subscriptions
                       SET original_transaction_id = $1,
                           latest_transaction_id = CASE WHEN $2 THEN $3 ELSE latest_transaction_id END,
                           sku = $4,
                           status = 'active',
                           expires_at = $5,
                           last_event_type = CASE WHEN $2 THEN 'renewed' ELSE last_event_type END,
                           last_event_timestamp = CASE WHEN $2 THEN GREATEST(COALESCE(last_event_timestamp, 0), $6) ELSE last_event_timestamp END,
                           updated_at = NOW()
                     WHERE id = $7
                    """,
                    purchase_token, new_period, provider_order_id, sku, effective_expiry,
                    int(datetime.now(timezone.utc).timestamp()), existing_sub["id"],
                )
                return {
                    "success": True,
                    "activated": True,
                    "idempotent": not new_period,
                    "tier": target_tier,
                    "expires_at": effective_expiry.isoformat(),
                    "spins_granted": spins_to_grant if new_period else 0,
                    "roses_granted": roses_to_grant if new_period else 0,
                }

            user_row = await conn.fetchrow("SELECT id FROM users WHERE id = $1 FOR UPDATE", user_uuid)
            if not user_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

            now_utc = datetime.now(timezone.utc)
            if is_subscription:
                new_valid = verified_expiry
                target_tier = plan_info.get("tier") if plan_info else "base_399"
                spins_to_grant = int(plan_info.get("spins", 0)) if plan_info else 0
                roses_to_grant = int(plan_info.get("roses", 0)) if plan_info else 0
                await conn.execute(
                    """
                    INSERT INTO store_subscriptions (
                        user_id, store, original_transaction_id, latest_transaction_id,
                        sku, status, expires_at, last_event_type, last_event_timestamp,
                        created_at, updated_at
                    ) VALUES ($1, 'google', $2, $3, $4, 'active', $5, 'active', $6, NOW(), NOW())
                    """,
                    user_uuid, purchase_token, provider_order_id, sku, new_valid, int(now_utc.timestamp()),
                )
                await conn.execute(
                    """
                    UPDATE users
                       SET subscription_tier = $1,
                           subscription_valid_until = GREATEST(COALESCE(subscription_valid_until, $2), $2),
                           billing_status = 'active',
                           super_connect_credits = COALESCE(super_connect_credits, 0) + $3,
                           last_active_at = NOW()
                     WHERE id = $4
                    """,
                    target_tier, new_valid, roses_to_grant, user_uuid,
                )
                if spins_to_grant:
                    await conn.execute(
                        """
                        INSERT INTO user_arcade_wallet (user_id, available_spins, updated_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (user_id) DO UPDATE
                        SET available_spins = user_arcade_wallet.available_spins + EXCLUDED.available_spins,
                            updated_at = NOW()
                        """,
                        user_uuid, spins_to_grant,
                    )
                log.info("Activated Google Play subscription for user %s: sku=%s, tier=%s, roses=+%d, spins=+%d, valid_until=%s", user_uuid, sku, target_tier, roses_to_grant, spins_to_grant, new_valid)
                return {
                    "success": True,
                    "activated": True,
                    "tier": target_tier,
                    "expires_at": new_valid.isoformat(),
                    "spins_granted": spins_to_grant,
                    "roses_granted": roses_to_grant,
                }

            await conn.execute(
                """
                INSERT INTO store_subscriptions (
                    user_id, store, original_transaction_id, latest_transaction_id,
                    sku, status, created_at, updated_at
                ) VALUES ($1, 'google', $2, $3, $4, 'consumed', NOW(), NOW())
                """,
                user_uuid, purchase_token, provider_order_id, sku,
            )

            if is_arcade:
                spins_to_add = int(plan_info.get("spins", 1)) if plan_info else (3 if "3" in sku_lower else (10 if "10" in sku_lower else 1))
                await conn.execute(
                    """
                    INSERT INTO user_arcade_wallet (user_id, available_spins, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                    SET available_spins = user_arcade_wallet.available_spins + EXCLUDED.available_spins,
                        updated_at = NOW()
                    """,
                    user_uuid, spins_to_add,
                )
                return {"success": True, "activated": True, "consumable": True, "spins_added": spins_to_add}

            if is_rose:
                roses_to_add = int(plan_info.get("roses", 1)) if plan_info else 1
                await conn.execute(
                    "UPDATE users SET super_connect_credits = COALESCE(super_connect_credits, 0) + $1, last_active_at = NOW() WHERE id = $2",
                    roses_to_add, user_uuid,
                )
                return {"success": True, "activated": True, "consumable": True, "roses_added": roses_to_add}

            if is_superlike:
                superlikes_to_add = int(plan_info.get("superlikes", 1)) if plan_info else 1
                await conn.execute(
                    "UPDATE users SET super_connect_credits = COALESCE(super_connect_credits, 0) + $1, last_active_at = NOW() WHERE id = $2",
                    superlikes_to_add, user_uuid,
                )
                return {"success": True, "activated": True, "consumable": True, "superlikes_added": superlikes_to_add}


# ---------------------------------------------------------------------------
# Razorpay Web Checkout (iOS PWA and Web Clients)
# ---------------------------------------------------------------------------


@router.get("/razorpay/checkout", response_class=HTMLResponse)
async def razorpay_web_checkout(
    plan_id: str,
    user_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Renders standalone Razorpay web checkout page for iOS PWA and web clients.
    Bypasses Apple 30% tax with 100% web compliance.
    """
    plan = payment_service.PLAN_CATALOGUE.get(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan_id")

    try:
        user_uuid = UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id format")

    order_res = await payment_service.create_order(str(user_uuid), plan_id, pool)
    order_id = order_res["order_id"]
    amount_inr = plan["amount"] // 100
    plan_label = plan.get("label", plan_id.replace("_", " ").title())

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jainune Membership Checkout</title>
  <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #FFFDF9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #FFFFFF; border: 2.5px solid #000000; border-radius: 16px; padding: 32px 24px; box-shadow: 4px 4px 0 #000000; text-align: center; max-width: 360px; width: 90%; }}
    .badge {{ display: inline-block; background: #FFE5EC; color: #FF4D6D; border: 1.5px solid #000000; border-radius: 999px; padding: 4px 12px; font-weight: bold; font-size: 13px; margin-bottom: 12px; }}
    h2 {{ margin: 8px 0; font-size: 24px; color: #111; }}
    .price {{ font-size: 32px; font-weight: 800; color: #111; margin: 16px 0; }}
    .btn {{ background: #FF4D6D; color: #FFFFFF; font-weight: 700; border: 2px solid #000000; border-radius: 12px; padding: 14px 20px; font-size: 16px; cursor: pointer; width: 100%; box-shadow: 3px 3px 0 #000000; transition: transform 0.1s; }}
    .btn:active {{ transform: translate(2px, 2px); box-shadow: 1px 1px 0 #000000; }}
    .footer {{ font-size: 12px; color: #666; margin-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">SECURE PWA CHECKOUT</div>
    <h2>{plan_label}</h2>
    <div class="price">₹{amount_inr}</div>
    <p style="color: #555; font-size: 14px;">Instant activation for Jainune members</p>
    <button id="pay-btn" class="btn">Pay ₹{amount_inr} with Razorpay</button>
    <div class="footer">UPI, Debit/Credit Card, NetBanking supported.</div>
  </div>
  <script>
    var options = {{
      "key": "{settings.razorpay_key_id}",
      "amount": {plan["amount"]},
      "currency": "INR",
      "name": "Jainune",
      "description": "{plan_label} Membership",
      "order_id": "{order_id}",
      "handler": function (response) {{
        fetch("/v1/payments/razorpay/verify-web", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature
          }})
        }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
          if (data && data.success) {{
            alert("Payment successful! Your membership has been activated.");
            if (window.opener) {{ window.close(); }} else {{ window.location.href = "/"; }}
          }} else {{
            alert("Payment verification failed: " + (data.detail || data.message || "Please contact support"));
          }}
        }}).catch(function(err) {{
          alert("Payment verification failed. Please contact support.");
        }});
      }},
      "theme": {{ "color": "#FF4D6D" }}
    }};
    var rzp = new Razorpay(options);
    document.getElementById('pay-btn').onclick = function(e) {{
      rzp.open();
      e.preventDefault();
    }};
    window.onload = function() {{
      setTimeout(function() {{ rzp.open(); }}, 400);
    }};
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)


async def razorpay_web_verify(
    body: VerifyPaymentBody,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Public HMAC-verified endpoint for web / PWA checkout completion.
    Verifies payment signature cryptographically without requiring Bearer token.
    """
    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            "SELECT user_id, status, amount, plan_id FROM payment_intents WHERE razorpay_order_id = $1",
            body.razorpay_order_id,
        )
    if intent is None:
        raise HTTPException(status_code=404, detail="Payment order not found")

    plan = payment_service.PLAN_CATALOGUE.get(intent.get("plan_id"))
    if plan and intent.get("amount") is not None and intent["amount"] != plan["amount"]:
        raise HTTPException(status_code=400, detail="Payment intent amount mismatch with plan price")

    if intent["status"] == "captured":
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT subscription_valid_until FROM users WHERE id = $1",
                intent["user_id"],
            )
        v_until = row.get("subscription_valid_until") if row else None
        return {
            "success": True,
            "activated": True,
            "expires_at": v_until.isoformat() if v_until else "",
            "message": "Payment already verified.",
            "status": "already_captured",
        }

    # Cryptographic HMAC-SHA256 signature verification
    valid = payment_service.verify_payment_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    )
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Redis distributed lock to prevent concurrent double-processing
    lock_key = f"lock:payment:order:{body.razorpay_order_id}"
    lock_token = uuid.uuid4().hex
    r = None
    lock_acquired = True
    try:
        r = redis
        lock_acquired = await r.set(lock_key, lock_token, nx=True, ex=30)
    except Exception:
        pass

    if not lock_acquired:
        raise HTTPException(status_code=409, detail="Payment verification is already in progress")

    try:
        payment_entity = await _fetch_captured_razorpay_payment(
            body.razorpay_payment_id,
            body.razorpay_order_id,
        )
    except HTTPException:
        if r and lock_acquired:
            try:
                await r.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                    1, lock_key, lock_token,
                )
            except Exception:
                pass
        raise

    try:
        await payment_service.process_payment_captured(
            event={
                "payload": {
                    "payment": {
                        "entity": payment_entity,
                    }
                }
            },
            pool=pool,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if r and lock_acquired:
            try:
                release_script = """
                    if redis.call("get", KEYS[1]) == ARGV[1] then
                        return redis.call("del", KEYS[1])
                    else
                        return 0
                    end
                """
                await r.eval(release_script, 1, lock_key, lock_token)
            except Exception:
                pass

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription_valid_until FROM users WHERE id = $1",
            intent["user_id"],
        )
    v_until = dict(row).get("subscription_valid_until") if row else None

    return {
        "success": True,
        "activated": True,
        "expires_at": v_until.isoformat() if v_until else "",
        "message": "Payment verified. Account upgraded.",
    }


# Dedicated alias router for /v1/payments/* endpoints
payments_router = APIRouter(prefix="/v1/payments", tags=["Payments"])
payments_router.add_api_route("/razorpay/checkout", razorpay_web_checkout, methods=["GET"], response_class=HTMLResponse)
payments_router.add_api_route("/razorpay/verify-web", razorpay_web_verify, methods=["POST"])
payments_router.add_api_route("/razorpay/webhook", razorpay_webhook, methods=["POST"])


