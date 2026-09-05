"""
Subscriptions router — Razorpay order creation, payment verification, and webhook.

POST /v1/subscriptions/order          → create Razorpay order (authenticated)
POST /v1/subscriptions/verify         → verify client-side payment signature
POST /v1/subscriptions/webhook        → Razorpay server-to-server webhook (no auth)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

import asyncpg

from app.core.config import settings
from app.core.database import get_pool
from app.core.security import get_current_user
from app.models.schemas.payment import (
    CreateOrderBody,
    OrderResponse,
    SubscriptionStatusResponse,
    VerifyPaymentBody,
)
from app.services import payment_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/subscriptions", tags=["Subscriptions"])


# ---------------------------------------------------------------------------
# Create Razorpay order
# ---------------------------------------------------------------------------


@router.post("/order", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: CreateOrderBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Server-side Razorpay order creation.
    The returned order_id + amount are passed to Razorpay Checkout on the client.
    """
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
):
    """
    Optional: client posts callback data for server-side HMAC check.
    If valid, we upgrade the subscription immediately (webhook is the canonical path,
    this is the fallback for immediate UX feedback).
    """
    valid = payment_service.verify_payment_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    )
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Simulate a captured event for the upgrade path
    await payment_service.process_payment_captured(
        event={
            "payload": {
                "payment": {
                    "entity": {
                        "order_id": body.razorpay_order_id,
                        "id": body.razorpay_payment_id,
                    }
                }
            }
        },
        pool=pool,
    )

    return {"success": True, "message": "Payment verified. Subscription upgraded."}


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
        if payment_id:
            from app.core.redis import get_redis
            try:
                r = get_redis()
                lock_acquired = await r.set(f"payment:processed:{payment_id}", "1", nx=True, ex=86400)
                if not lock_acquired:
                    return {"received": True, "status": "already_processed"}
            except Exception:
                pass  # Fallback to DB idempotency gate
        await payment_service.process_payment_captured(event, pool)
    elif event_name == "payment.refunded":
        await payment_service.process_refund(event, pool)
    else:
        log.debug("Unhandled webhook event: %s", event_name)

    # Always return 200 to acknowledge receipt
    return {"received": True}
