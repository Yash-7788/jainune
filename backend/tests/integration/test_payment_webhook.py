"""
Integration tests for Subscription & Payment flows:
- Order creation (POST /v1/subscriptions/order)
- Client payment verification (POST /v1/subscriptions/verify)
- Razorpay Webhook handling (POST /v1/subscriptions/webhook)
  - HMAC signature verification
  - payment.captured tier upgrade
  - payment.refunded tier downgrade
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_create_order(authed_client, mock_pool):
    client, user_id = authed_client
    pool, conn = mock_pool

    mock_rzp = MagicMock()
    mock_rzp.order.create.return_value = {"id": "order_mock_12345"}

    with patch("app.services.payment_service._rzp_client", return_value=mock_rzp):
        resp = await client.post(
            "/v1/subscriptions/order",
            json={"plan_id": "gold_monthly"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["order_id"] == "order_mock_12345"
        assert data["amount"] == 29900
        assert data["currency"] == "INR"
        assert data["plan_id"] == "gold_monthly"
        conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_verify_payment_signature_invalid(client: AsyncClient):
    resp = await client.post(
        "/v1/subscriptions/verify",
        json={
            "razorpay_order_id": "order_123",
            "razorpay_payment_id": "pay_123",
            "razorpay_signature": "invalid_signature",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_payment_signature_valid(client: AsyncClient, mock_pool):
    pool, conn = mock_pool
    order_id = "order_valid_123"
    payment_id = "pay_valid_123"
    msg = f"{order_id}|{payment_id}"
    valid_sig = hmac.new(
        settings.razorpay_key_secret.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()

    conn.fetchrow.return_value = {
        "user_id": str(uuid.uuid4()),
        "plan_id": "gold_monthly",
        "status": "created",
    }

    resp = await client.post(
        "/v1/subscriptions/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_webhook_invalid_signature(client: AsyncClient):
    payload = json.dumps({"event": "payment.captured"}).encode()
    resp = await client.post(
        "/v1/subscriptions/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "bogus_signature",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_payment_captured(client: AsyncClient, mock_pool):
    pool, conn = mock_pool
    target_user_id = str(uuid.uuid4())
    order_id = "order_webhook_test_1"

    payload_dict = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "order_id": order_id,
                    "id": "pay_webhook_test_1",
                }
            }
        },
    }
    payload_bytes = json.dumps(payload_dict).encode()
    valid_sig = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    conn.fetchrow.return_value = {
        "user_id": target_user_id,
        "plan_id": "platinum_monthly",
        "status": "created",
    }

    resp = await client.post(
        "/v1/subscriptions/webhook",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": valid_sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    # Verify updates to users table and payment_intents table
    assert conn.execute.call_count >= 2


@pytest.mark.asyncio
async def test_webhook_payment_refunded(client: AsyncClient, mock_pool):
    pool, conn = mock_pool
    target_user_id = str(uuid.uuid4())
    order_id = "order_refund_test"

    payload_dict = {
        "event": "payment.refunded",
        "payload": {
            "payment": {
                "entity": {
                    "order_id": order_id,
                    "id": "pay_refund_1",
                }
            }
        },
    }
    payload_bytes = json.dumps(payload_dict).encode()
    valid_sig = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    conn.fetchrow.return_value = {
        "user_id": target_user_id,
        "plan_id": "gold_monthly",
    }

    resp = await client.post(
        "/v1/subscriptions/webhook",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": valid_sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    conn.execute.assert_called_once()
