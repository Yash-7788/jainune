"""
Subscriptions router — Razorpay order creation, payment verification, and webhook.

POST /v1/subscriptions/order          → create Razorpay order (authenticated)
POST /v1/subscriptions/verify         → verify client-side payment signature
POST /v1/subscriptions/webhook        → Razorpay server-to-server webhook (no auth)
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from typing import Any, Optional
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
):
    """
    Server-side Razorpay order creation.
    The returned order_id + amount are passed to Razorpay Checkout on the client.
    """
    await sliding_window_rate_limit(
        f"ratelimit:subscriptions:order:{current_user['user_id']}", 10, 60, redis
    )
    try:
        result = await payment_service.create_order(
            user_id=current_user["user_id"],
            plan_id=body.plan_id.value,
            pool=pool,
        )
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
    r = None
    lock_acquired = True
    try:
        r = get_redis()
        lock_acquired = await r.set(lock_key, "1", nx=True, ex=15)
    except Exception:
        pass  # DB transaction FOR UPDATE gate is fallback

    if not lock_acquired:
        raise HTTPException(status_code=409, detail="Payment verification is already in progress")

    payment_entity: dict[str, Any] = {
        "order_id": body.razorpay_order_id,
        "id": body.razorpay_payment_id,
    }
    if intent.get("amount") is not None:
        payment_entity["amount"] = intent["amount"]

    try:
        rzp = payment_service._rzp_client()
        fetched = await asyncio.to_thread(rzp.payment.fetch, body.razorpay_payment_id)
        if fetched and "amount" in fetched:
            payment_entity["amount"] = fetched["amount"]
    except Exception:
        pass  # Fallback to intent amount if offline or rzp client unavailable

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
                await r.delete(lock_key)
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
    razorpay_order_id: Optional[str] = Field(None, max_length=64)


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_subscription(
    body: Optional[SyncSubscriptionBody] = None,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Directly reconciles payment status with Razorpay.
    Recovers from network drops, dropped webhooks, or unverified payments.
    """
    user_id = current_user["user_id"]
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
                return {
                    "synced": True,
                    "activated": True,
                    "status": "already_captured",
                    "tier": user_row["subscription_tier"] if user_row else "jainune_plus",
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
    razorpay_payment_id: str = Field(..., min_length=5, max_length=64)
    reason: Optional[str] = Field("user_cancellation", max_length=256)


@router.post("/refund", status_code=status.HTTP_200_OK)
async def request_refund(
    body: RefundRequestBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Customer refund request for charged payments:
    Verifies caller ownership of the payment and initiates Razorpay gateway refund,
    crediting funds back to the user's source bank / UPI account.
    """
    user_id = current_user["user_id"]
    async with pool.acquire() as conn:
        intent = await conn.fetchrow(
            """
            SELECT user_id, amount, status FROM payment_intents
            WHERE razorpay_payment_id = $1
            """,
            body.razorpay_payment_id,
        )
    if not intent:
        raise HTTPException(status_code=404, detail="Payment record not found")
    if str(intent["user_id"]) != str(user_id):
        raise HTTPException(status_code=403, detail="Payment does not belong to authenticated user")
    if intent["status"] == "refunded":
        return {"success": True, "message": "Payment has already been refunded.", "status": "already_refunded"}

    try:
        result = await payment_service.initiate_refund(
            payment_id=body.razorpay_payment_id,
            amount_paise=intent["amount"],
            reason=body.reason or "customer_request",
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

    import json
    try:
        event = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_name: str = event.get("event", "")
    log.info("Razorpay webhook received: %s", event_name)

    if event_name == "payment.captured":
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id")
        from app.core.redis import get_redis
        r = None
        order_lock_key = f"lock:payment:order:{order_id}" if order_id else None
        order_lock_acquired = True
        try:
            r = get_redis()
            if payment_id:
                processed = await r.set(f"payment:processed:{payment_id}", "1", nx=True, ex=86400)
                if not processed:
                    return {"received": True, "status": "already_processed"}
            if order_lock_key:
                order_lock_acquired = await r.set(order_lock_key, "1", nx=True, ex=15)
                if not order_lock_acquired:
                    return {"received": True, "status": "lock_busy"}
        except Exception:
            pass  # Fallback to DB transaction FOR UPDATE gate

        try:
            await payment_service.process_payment_captured(event, pool)
        except ValueError as exc:
            log.error("Payment validation error on webhook: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            if r and order_lock_key and order_lock_acquired:
                try:
                    await r.delete(order_lock_key)
                except Exception:
                    pass
    elif event_name == "payment.refunded":
        await payment_service.process_refund(event, pool)
    elif event_name == "payment.failed":
        await payment_service.process_payment_failed(event, pool)
    else:
        log.debug("Unhandled webhook event: %s", event_name)

    # Always return 200 to acknowledge receipt
    return {"received": True}


@router.post("/cancel", status_code=status.HTTP_200_OK)
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Subscription cancellation status check.
    Jainune subscriptions are fixed-duration passes (non-recurring) with no auto-renewal.
    Confirms no recurring billing exists and reports active access window.
    """
    from datetime import datetime, timezone
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription_tier, subscription_valid_until FROM users WHERE id = $1",
            current_user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        valid_until = row["subscription_valid_until"] or datetime.now(timezone.utc)
    return {
        "success": True,
        "message": "Subscription is a non-recurring pass. No auto-renewal will occur.",
        "access_until": valid_until.isoformat() if hasattr(valid_until, "isoformat") else str(valid_until),
    }
