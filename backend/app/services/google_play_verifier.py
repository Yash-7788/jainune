"""
Google Play Billing Server-to-Server Verification Service.

Validates in-app purchases and subscriptions against Google's Android Publisher API v3
using Service Account credentials. Eliminates client-side receipt forgery.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

log = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

# In-memory OAuth2 token cache: (access_token, expiry_timestamp)
_token_cache: tuple[str, float] = ("", 0.0)


def _load_google_play_credentials() -> Optional[dict[str, Any]]:
    """Loads Google Play service account credentials from file path or raw JSON."""
    raw = getattr(settings, "google_play_service_account_json", "") or os.environ.get(
        "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", ""
    )
    if not raw:
        return None

    raw_clean = raw.strip()
    # Check if path to file
    if os.path.exists(raw_clean):
        with open(raw_clean, "r", encoding="utf-8") as f:
            return json.load(f)

    # Otherwise parse as JSON string
    try:
        return json.loads(raw_clean)
    except Exception as exc:
        log.warning("Failed to parse GOOGLE_PLAY_SERVICE_ACCOUNT_JSON: %s", exc)
        return None


def _build_signed_jwt(sa: dict[str, Any]) -> str:
    """Builds signed RS256 JWT for Google OAuth2 token exchange."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa["client_email"],
        "scope": _ANDROID_PUBLISHER_SCOPE,
        "aud": _GOOGLE_TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header_b64 = b64(json.dumps(header).encode())
    payload_b64 = b64(json.dumps(payload).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    private_key = serialization.load_pem_private_key(
        sa["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_b64}.{payload_b64}.{b64(signature)}"


async def get_google_publisher_token() -> str:
    """Acquires or reuses cached Google Android Publisher OAuth2 access token."""
    global _token_cache
    cached_token, expiry = _token_cache
    if cached_token and time.time() < expiry - 120:
        return cached_token

    sa = _load_google_play_credentials()
    if not sa:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Play billing verification is not configured on this server.",
        )

    signed_jwt = _build_signed_jwt(sa)
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
            },
        )
        if res.status_code != 200:
            log.error("Google OAuth2 token exchange failed: %s - %s", res.status_code, res.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to authenticate with Google Play services.",
            )

        data = res.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        _token_cache = (token, time.time() + expires_in)
        return token


async def verify_google_play_purchase(
    package_name: str,
    product_id: str,
    purchase_token: str,
    is_subscription: bool = False,
) -> Dict[str, Any]:
    """
    Validates a purchase token directly with Google Android Publisher API v3.
    Rejects spoofed receipts, revoked tokens, and refunded orders.
    """
    creds = _load_google_play_credentials()
    is_prod = getattr(settings, "environment", "").lower() == "production"

    # In non-production development or testing, permit mock tokens if credentials are unset
    if not creds:
        if not is_prod:
            log.warning("Google Play service account unset in dev/test. Mocking verification for token %s", purchase_token[:10])
            mock_data = {
                "verified": True,
                "mock": True,
                "orderId": f"GPA.mock-{int(time.time())}",
                "purchaseState": 0,
                "paymentState": 1,
                "expiryTimeMillis": str(int((time.time() + 30 * 24 * 60 * 60) * 1000)),
            }
            if is_subscription:
                mock_data["_verified_expires_at"] = datetime.fromtimestamp(
                    int(mock_data["expiryTimeMillis"]) / 1000,
                    tz=timezone.utc,
                )
            return mock_data
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Play verification service is not configured on this server.",
        )

    # In development/testing, permit explicitly tagged test tokens
    if not is_prod and purchase_token.startswith("test_"):
        mock_data = {
            "verified": True,
            "mock": True,
            "orderId": f"GPA.test-{purchase_token}",
            "purchaseState": 0,
            "paymentState": 1,
            "expiryTimeMillis": str(int((time.time() + 30 * 24 * 60 * 60) * 1000)),
        }
        if is_subscription:
            mock_data["_verified_expires_at"] = datetime.fromtimestamp(
                int(mock_data["expiryTimeMillis"]) / 1000,
                tz=timezone.utc,
            )
        return mock_data

    token = await get_google_publisher_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        if is_subscription:
            url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
                f"{package_name}/purchases/subscriptions/{product_id}/tokens/{purchase_token}"
            )
        else:
            url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
                f"{package_name}/purchases/products/{product_id}/tokens/{purchase_token}"
            )

        try:
            res = await client.get(url, headers=headers)
        except Exception as exc:
            log.error("Google Play verification network failure: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Timed out connecting to Google Play verification service.",
            )

        if res.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Purchase receipt not found on Google Play.",
            )
        elif res.status_code == 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid purchase token or malformed Google Play request.",
            )
        elif res.status_code != 200:
            log.error("Google Play returned unexpected status %s: %s", res.status_code, res.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Play verification service returned an unexpected error.",
            )

        data = res.json()

        # Validate purchase states
        if is_subscription:
            try:
                expires_at_ms = int(data["expiryTimeMillis"])
                verified_expires_at = datetime.fromtimestamp(expires_at_ms / 1000, tz=timezone.utc)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Google Play did not return a valid subscription expiry.",
                ) from exc
            if verified_expires_at <= datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google Play subscription has expired.",
                )

            # paymentState 1/2 means paid/free trial; 3 means a deferred
            # plan change while the existing paid term remains active. Google
            # omits paymentState for canceled subscriptions even when the user
            # retains access through expiryTimeMillis, so accept that response
            # only when it explicitly includes a cancellation reason.
            payment_state = data.get("paymentState")
            canceled_but_unexpired = payment_state is None and data.get("cancelReason") in (0, 1, 2, 3)
            if payment_state not in (1, 2, 3) and not canceled_but_unexpired:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Google Play subscription is not paid, in a free trial, or currently entitled.",
                )
            data["_verified_expires_at"] = verified_expires_at
        else:
            # purchaseState: 0 = Purchased, 1 = Canceled, 2 = Pending
            purchase_state = data.get("purchaseState")
            if purchase_state != 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google Play purchase has been canceled or is pending.",
                )

        return data
