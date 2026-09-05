"""
Integration tests for Authentication Pipeline:
- OTP Request (with MSG91 mocked and sliding-window rate limit)
- OTP Verification (new vs returning user, token issuance)
- Refresh Token rotation and session revocation
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.security import hash_otp


@pytest.mark.asyncio
async def test_request_otp_success(client: AsyncClient, fake_redis):
    phone = "+919876543210"
    with patch("app.routers.auth._send_otp_msg91", new_callable=AsyncMock) as mock_sms:
        resp = await client.post("/v1/auth/otp/request", json={"phone_number": phone})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["phone_number"] == phone
        assert data["data"]["retry_after_seconds"] == 60
        mock_sms.assert_called_once()

    # Verify session key set in redis
    stored = await fake_redis.get(f"auth:otp:{phone}")
    assert stored is not None


@pytest.mark.asyncio
async def test_request_otp_rate_limiting(client: AsyncClient):
    phone = "+919999999999"
    with patch("app.routers.auth._send_otp_msg91", new_callable=AsyncMock):
        # 3 allowed per hour
        for _ in range(3):
            resp = await client.post("/v1/auth/otp/request", json={"phone_number": phone})
            assert resp.status_code == 200

        # 4th request must be rate-limited (HTTP 429)
        resp = await client.post("/v1/auth/otp/request", json={"phone_number": phone})
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_verify_otp_new_user(client: AsyncClient, fake_redis, mock_pool):
    pool, conn = mock_pool
    phone = "+919123456789"
    otp = "123456"

    # Pre-seed OTP in redis
    otp_hash = hash_otp(phone, otp)
    await fake_redis.set(f"auth:otp:{phone}", otp_hash)

    # DB mocks: user does not exist (new user)
    new_user_id = uuid.uuid4()
    conn.fetchrow.return_value = None
    conn.fetchval.return_value = new_user_id

    resp = await client.post(
        "/v1/auth/otp/verify",
        json={"phone_number": phone, "otp": otp},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["is_new_user"] is True
    assert body["data"]["onboarding_completed"] is False
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]


@pytest.mark.asyncio
async def test_verify_otp_invalid_code(client: AsyncClient, fake_redis):
    phone = "+919123456780"
    otp = "654321"

    # Pre-seed OTP in redis
    otp_hash = hash_otp(phone, otp)
    await fake_redis.set(f"auth:otp:{phone}", otp_hash)

    resp = await client.post(
        "/v1/auth/otp/verify",
        json={"phone_number": phone, "otp": "000000"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_refresh_rotation(client: AsyncClient, mock_pool):
    pool, conn = mock_pool
    uid = uuid.uuid4()

    # DB mock: valid active refresh token exists
    conn.fetchrow.return_value = {
        "user_id": uid,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    }

    resp = await client.post(
        "/v1/auth/token/refresh",
        json={"refresh_token": "rt_existing_sample_token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]
    # Verify DB update executed to rotate token
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_token_refresh_invalid_or_expired(client: AsyncClient, mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = None

    resp = await client.post(
        "/v1/auth/token/refresh",
        json={"refresh_token": "rt_invalid_token"},
    )
    assert resp.status_code == 401
