"""
Push notification service — Firebase Cloud Messaging (FCM) v1 HTTP API.

Uses service-account JWT auth (not legacy server key).
All sends are fire-and-forget; failures are logged, not raised.

Notification types dispatched:
  - new_match       → "You matched with {name}! Say hello 👋"
  - new_message     → "{name}: {preview}"
  - new_like        → "{name} liked your profile" (gold/platinum only)
  - match_expiring  → "Your match with {name} expires in 24 hours!"
  - daily_digest    → "X people liked your profile today"
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

_FCM_ENDPOINT = (
    f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send"
)
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# Module-level token cache: (access_token, expiry_timestamp)
_token_cache: tuple[str, float] = ("", 0.0)


def _load_service_account() -> dict[str, Any]:
    path = settings.fcm_service_account_path
    if not os.path.exists(path):
        raise FileNotFoundError(f"FCM service account not found: {path}")
    with open(path) as f:
        return json.load(f)


def _build_jwt(sa: dict[str, Any]) -> str:
    """Build a signed JWT for Google OAuth2 token exchange."""
    import base64
    import json as _json

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa["client_email"],
        "scope": _FCM_SCOPE,
        "aud": _GOOGLE_TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header_b64 = b64(_json.dumps(header).encode())
    payload_b64 = b64(_json.dumps(payload).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    private_key = serialization.load_pem_private_key(
        sa["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_b64}.{payload_b64}.{b64(signature)}"


async def _get_access_token() -> str:
    """Fetch (or return cached) FCM OAuth2 access token."""
    global _token_cache
    token, expiry = _token_cache
    if token and time.time() < expiry - 60:  # 60s grace
        return token

    sa = _load_service_account()
    jwt = _build_jwt(sa)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["access_token"]
    expiry = time.time() + data.get("expires_in", 3600)
    _token_cache = (token, expiry)
    return token


async def send_push(
    device_token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """
    Send a single FCM push notification.
    Returns True on success, False on failure (never raises).
    """
    if not device_token:
        return False

    try:
        access_token = await _get_access_token()
    except Exception as exc:
        log.error("FCM token fetch failed: %s", exc)
        return False

    message: dict[str, Any] = {
        "message": {
            "token": device_token,
            "notification": {"title": title, "body": body},
            "android": {
                "notification": {"channel_id": "jainune_default", "priority": "HIGH"},
                "priority": "HIGH",
            },
            "apns": {
                "payload": {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}},
                "headers": {"apns-priority": "10"},
            },
        }
    }
    if data:
        message["message"]["data"] = data

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _FCM_ENDPOINT,
                json=message,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                return True
            log.warning(
                "FCM send failed: status=%d body=%s token_prefix=%s",
                resp.status_code,
                resp.text[:200],
                device_token[:10],
            )
            return False
    except Exception as exc:
        log.error("FCM send exception: %s", exc)
        return False


async def send_push_multicast(
    device_tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> dict[str, int]:
    """
    Fan-out push to multiple tokens. Returns {"success": N, "failure": M}.
    Uses gather for concurrency; tokens are deduplicated.
    """
    import asyncio

    tokens = list(set(t for t in device_tokens if t))
    if not tokens:
        return {"success": 0, "failure": 0}

    results = await asyncio.gather(
        *[send_push(tok, title, body, data) for tok in tokens],
        return_exceptions=True,
    )
    success = sum(1 for r in results if r is True)
    return {"success": success, "failure": len(tokens) - success}
