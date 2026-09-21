from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import hmac
import logging
from app.core.config import settings
from app.core.database import get_pool
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    get_trusted_client_ip,
    hash_otp,
    revoke_token,
    sliding_window_rate_limit,
    validate_access_token,
    verify_otp,
)
from app.core.redis import get_redis
from app.core.responses import err, ok
from app.dependencies import CurrentUser, CurrentUserForLogout, DBDep, RedisDep
from app.services.connection_manager import ws_manager
from app.models.schemas.auth import (
    AccessTokenResponse,
    AppleAuthBody,
    EmailOTPRequestBody,
    EmailOTPVerifyBody,
    GoogleAuthBody,
    LogoutBody,
    OTPRequestBody,
    OTPRequestResponse,
    OTPVerifyBody,
    TokenRefreshBody,
    TokenResponse,
)
from app.services.email_verifier import (
    canonicalize_email,
    get_client_subnet,
    is_disposable_email,
    verify_bot_integrity,
)
from app.services.messaging_service import dispatch_phone_otp, send_email_otp

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])
_bearer = HTTPBearer()

OTP_TTL_SECONDS = 180
OTP_RATE_WINDOW_SECONDS = 3600
OTP_RATE_LIMIT = 3

# Allowed email domains allowlist matching mobile client (BUG-037)
ALLOWED_EMAIL_DOMAINS = frozenset({
    "jainune.com",
    # Google
    "gmail.com", "googlemail.com",
    # Microsoft
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "outlook.in", "hotmail.co.in", "live.in",
    # Yahoo
    "yahoo.com", "yahoo.co.in", "yahoo.in", "ymail.com", "rocketmail.com",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # Proton
    "proton.me", "protonmail.com",
    # Zoho
    "zoho.com", "zohomail.in", "zoho.in",
    # Indian
    "rediffmail.com", "sify.com",
    # Other major
    "aol.com", "gmx.com", "mail.com", "fastmail.com", "hey.com",
})


def mask_phone(phone: str) -> str:
    """Mask phone for safe logging and UI display: +91*****1210."""
    if len(phone) >= 8:
        return phone[:4] + "*" * (len(phone) - 8) + phone[-4:]
    return "***"


def mask_email(email: str) -> str:
    """Mask email for safe logging and UI display: p****@domain.com."""
    parts = email.split("@")
    if len(parts) == 2:
        user, domain = parts
        masked = (user[0] + "*" * (len(user) - 1)) if len(user) > 1 else "*"
        return f"{masked}@{domain}"
    return "***"


def _row_val(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError, AttributeError):
        return default


def _assert_account_active(row: Any) -> None:
    if not row:
        return
    deleted_at = _row_val(row, "deleted_at")
    status_val = _row_val(row, "account_status")
    if deleted_at is not None or status_val == "deleted":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been deleted.",
        )
    if status_val == "banned":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been permanently banned.",
        )
    suspend_until = _row_val(row, "suspend_until")
    is_suspended = status_val == "suspended"
    if is_suspended or (suspend_until and suspend_until > datetime.now(timezone.utc)):
        detail_until = suspend_until.isoformat() if suspend_until else "further notice"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User account is temporarily suspended until {detail_until}.",
        )


async def _issue_token_response(
    user_id: uuid.UUID,
    is_new_user: bool,
    onboarding_completed: bool,
    conn,
) -> dict:
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token()
    refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    old_token_hash = await conn.fetchval(
        "SELECT token_hash FROM refresh_tokens WHERE user_id = $1",
        user_id,
    )

    # Atomic transaction for token write and activity timestamp (BUG-073)
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
              SET token_hash = EXCLUDED.token_hash,
                  expires_at = EXCLUDED.expires_at,
                  created_at = NOW()
            """,
            user_id, refresh_hash, expires_at,
        )
        # Touch last active
        await conn.execute("UPDATE users SET last_active_at = NOW() WHERE id = $1", user_id)

    # Track old token as replaced by login rather than rotated/theft (BUG-064)
    # Proactively notify active sessions via in-process ConnectionManager (FINDING-03)
    if old_token_hash:
        try:
            exp_time = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
            await conn.execute(
                """
                INSERT INTO revoked_refresh_tokens (token_hash, user_id, revocation_type, expires_at)
                VALUES ($1, $2, 'replaced_by_login', $3)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                old_token_hash, user_id, exp_time,
            )
        except Exception as e:
            log.warning("Failed to persist session replacement state in DB: %s", e)

        try:
            r = get_redis()
            res = r.set(
                f"auth:replaced_by_login:{old_token_hash}",
                str(user_id),
                ex=settings.refresh_token_expire_days * 86400,
            )
            if hasattr(res, "__await__"):
                await res
            del_res = r.delete(f"user:session:{user_id}")
            if hasattr(del_res, "__await__"):
                await del_res
        except Exception as e:
            log.warning("Failed to record session replacement state in Redis: %s", e)

        try:
            await ws_manager.disconnect_user(
                str(user_id),
                reason="Session expired due to login from another device. Please sign in again.",
            )
        except Exception:
            pass

    return ok(TokenResponse(
        user_id=str(user_id),
        is_new_user=is_new_user,
        onboarding_completed=onboarding_completed,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    ).model_dump())


# ── POST /v1/auth/otp/request ─────────────────────────────────────────────────

@router.post("/otp/request")
async def request_otp(body: OTPRequestBody, redis: RedisDep, request: Request = None, db: DBDep = None) -> dict:
    if body.website_trap and body.website_trap.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to send verification code. Please check your credentials or contact support.",
        )

    # IP & Subnet rate limit: 15 per IP / 30 per /24 subnet per minute
    if request:
        client_ip = get_trusted_client_ip(request)
        await sliding_window_rate_limit(f"ratelimit:auth:otp:ip:{client_ip}", 15, 60, redis)
        client_subnet = get_client_subnet(client_ip)
        await sliding_window_rate_limit(f"ratelimit:auth:otp:subnet:{client_subnet}", 30, 60, redis)

        is_bot, bot_msg = await asyncio.to_thread(
            verify_bot_integrity,
            dict(request.headers),
            body.turnstile_token,
            settings.environment.lower() == "production",
            client_ip,
            body.website_trap,
        )
        if is_bot:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)


    # Pre-check account status to prevent OTP dispatch to banned/suspended accounts
    pool = db
    if pool is None:
        try:
            pool = get_pool()
        except RuntimeError:
            pool = None
    if pool is not None:
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                "SELECT account_status, deleted_at, suspend_until FROM users WHERE phone_number = $1",
                body.phone_number,
            )
            if user_row:
                status_val = user_row["account_status"]
                deleted_at = user_row["deleted_at"]
                suspend_until = user_row["suspend_until"]
                su = (
                    (suspend_until if getattr(suspend_until, "tzinfo", None) else suspend_until.replace(tzinfo=timezone.utc))
                    if isinstance(suspend_until, datetime)
                    else None
                )
                is_suspended = status_val == "suspended" and (
                    suspend_until is None or su is None or su > datetime.now(timezone.utc)
                )
                if status_val in ("banned", "deleted") or deleted_at is not None or is_suspended:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Unable to send verification code. Please check your credentials or contact support.",
                    )

    # Rate limit: 3 OTP requests per phone per hour
    rate_key = f"auth:otp_rate:{body.phone_number}"
    await sliding_window_rate_limit(rate_key, OTP_RATE_LIMIT, OTP_RATE_WINDOW_SECONDS, redis)

    otp = generate_otp()
    otp_hash = hash_otp(body.phone_number, otp)

    # Store HMAC in Redis, never the raw OTP
    session_key = f"auth:otp:{body.phone_number}"
    await redis.set(session_key, otp_hash.encode(), ex=OTP_TTL_SECONDS)
    # Reset attempt counter on fresh OTP request (BUG-008)
    del_res = redis.delete(f"auth:attempts:{body.phone_number}")
    if hasattr(del_res, "__await__"):
        await del_res

    # Dispatch via MSG91 SMS or WhatsApp
    channel = getattr(body, "channel", "sms") or "sms"
    await dispatch_phone_otp(body.phone_number, otp, channel=channel)

    log.info("Dispatched %s OTP to %s", channel.upper(), mask_phone(body.phone_number))
    return ok(OTPRequestResponse(
        phone_number=mask_phone(body.phone_number),
        retry_after_seconds=60,
        expires_in_seconds=OTP_TTL_SECONDS,
    ).model_dump())


# ── POST /v1/auth/otp/verify ──────────────────────────────────────────────────

@router.post("/otp/verify")
async def verify_otp_endpoint(
    body: OTPVerifyBody,
    db: DBDep,
    redis: RedisDep,
    request: Request = None,
) -> dict:
    if request:
        client_ip = get_trusted_client_ip(request)
        await sliding_window_rate_limit(f"ratelimit:auth:otp_verify:ip:{client_ip}", 20, 60, redis)
        client_subnet = get_client_subnet(client_ip)
        await sliding_window_rate_limit(f"ratelimit:auth:otp_verify:subnet:{client_subnet}", 50, 60, redis)

    await verify_otp(body.phone_number, body.otp, redis)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE phone_number = $1",
            body.phone_number,
        )

        is_new_user = row is None
        onboarding_completed = False

        if is_new_user:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (phone_number, auth_provider)
                VALUES ($1, 'phone')
                ON CONFLICT (phone_number) DO NOTHING
                RETURNING id
                """,
                body.phone_number,
            )
            if user_id is None:
                # Row exists but was not returned (conflict on banned/deleted account)
                existing = await conn.fetchrow(
                    "SELECT id, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE phone_number = $1",
                    body.phone_number,
                )
                if not existing:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account not found after conflict resolution")
                _assert_account_active(existing)
                user_id = existing["id"]
                is_new_user = False
                onboarding_completed = _row_val(existing, "onboarding_completed", False) or False
            else:
                onboarding_completed = False
        else:
            _assert_account_active(row)
            user_id = row["id"]
            onboarding_completed = _row_val(row, "onboarding_completed", False) or False

        log.info("User verified via phone: %s", mask_phone(body.phone_number))
        return await _issue_token_response(user_id, is_new_user, onboarding_completed, conn)


async def _extract_phone_verified_user_id(request: Request, redis: RedisDep) -> uuid.UUID | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.security import validate_access_token
        payload = await validate_access_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), redis)
        return uuid.UUID(str(payload["sub"]))
    except Exception:
        return None


# ── POST /v1/auth/email/otp/request ──────────────────────────────────────────

@router.post("/email/otp/request")
async def request_email_otp(request: Request, body: EmailOTPRequestBody, redis: RedisDep, db: DBDep = None) -> dict:
    client_ip = get_trusted_client_ip(request)
    client_subnet = get_client_subnet(client_ip)
    await sliding_window_rate_limit(f"ratelimit:auth:email_otp:subnet:{client_subnet}", 30, 60, redis)

    is_bot, bot_msg = await asyncio.to_thread(
        verify_bot_integrity,
        dict(request.headers),
        body.turnstile_token,
        is_production=settings.environment == "production",
        remote_ip=client_ip,
        honeypot=body.website_trap,
    )
    if is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)


    clean_email = body.email.strip().lower()
    canonical_email = canonicalize_email(clean_email)

    is_disposable, reason = await asyncio.to_thread(is_disposable_email, canonical_email)
    if is_disposable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    domain = canonical_email.split("@")[-1] if "@" in canonical_email else ""
    if domain not in ALLOWED_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration is restricted to supported email providers (Gmail, Outlook, Yahoo, Apple, etc.).",
        )

    # Mandatory Phone Verification Check: Phone number must be verified before email can be linked/used
    phone_user_id = await _extract_phone_verified_user_id(request, redis)
    if not phone_user_id:
        chk_pool = db
        if chk_pool is None:
            try:
                chk_pool = get_pool()
            except RuntimeError:
                chk_pool = None
        if chk_pool is not None:
            async with chk_pool.acquire() as chk_conn:
                existing_user = await chk_conn.fetchrow(
                    "SELECT phone_number FROM users WHERE email = $1 OR email = $2",
                    canonical_email, clean_email,
                )
                if not existing_user or not existing_user.get("phone_number"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Phone verification required: You must verify your mobile number first before using email sign in.",
                    )

    # Check account status before dispatching email OTP (BUG-062)
    pool = db
    if pool is None:
        try:
            pool = get_pool()
        except RuntimeError:
            pool = None
    if pool is not None:
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                "SELECT account_status, deleted_at, suspend_until FROM users WHERE email = $1 OR email = $2",
                canonical_email,
                clean_email,
            )
            if user_row:
                status_val = user_row["account_status"]
                deleted_at = user_row["deleted_at"]
                suspend_until = user_row["suspend_until"]
                su = (
                    (suspend_until if getattr(suspend_until, "tzinfo", None) else suspend_until.replace(tzinfo=timezone.utc))
                    if isinstance(suspend_until, datetime)
                    else None
                )
                is_suspended = status_val == "suspended" and (
                    suspend_until is None or su is None or su > datetime.now(timezone.utc)
                )
                if status_val in ("banned", "deleted") or deleted_at is not None or is_suspended:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Unable to send verification code. Please check your credentials or contact support.",
                    )

    rate_key = f"auth:email_otp_rate:{canonical_email}"
    await sliding_window_rate_limit(rate_key, OTP_RATE_LIMIT, OTP_RATE_WINDOW_SECONDS, redis)

    otp = generate_otp()
    otp_hash = hash_otp(canonical_email, otp)
    session_key = f"auth:email_otp:{canonical_email}"
    await redis.set(session_key, otp_hash.encode(), ex=OTP_TTL_SECONDS)
    # Reset attempt counter on fresh email OTP request (BUG-008)
    del_res = redis.delete(f"auth:email_attempts:{canonical_email}")
    if hasattr(del_res, "__await__"):
        await del_res

    # Deliver branded OTP email
    await send_email_otp(clean_email, otp)

    log.info("Dispatched email OTP to %s", mask_email(clean_email))
    return ok({
        "email": mask_email(clean_email),
        "retry_after_seconds": 60,
        "expires_in_seconds": OTP_TTL_SECONDS,
    })


# ── POST /v1/auth/email/otp/verify ───────────────────────────────────────────

@router.post("/email/otp/verify")
async def verify_email_otp(
    body: EmailOTPVerifyBody,
    db: DBDep,
    redis: RedisDep,
    request: Request = None,
) -> dict:
    if request:
        client_ip = get_trusted_client_ip(request)
        await sliding_window_rate_limit(f"ratelimit:auth:email_verify:ip:{client_ip}", 20, 60, redis)
        client_subnet = get_client_subnet(client_ip)
        await sliding_window_rate_limit(f"ratelimit:auth:email_verify:subnet:{client_subnet}", 50, 60, redis)

    clean_email = body.email.strip().lower()
    canonical_email = canonicalize_email(clean_email)
    rate_key = f"auth:email_attempts:{canonical_email}"
    session_key = f"auth:email_otp:{canonical_email}"

    attempts = await redis.incr(rate_key)
    await redis.expire(rate_key, 300)
    if attempts > 5:
        await redis.delete(session_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP verification attempts exceeded. Request a new OTP.",
        )

    # Atomic GETDEL prevents concurrent requests from double-consuming the same OTP
    _GETDEL_LUA = "local v=redis.call('GET',KEYS[1]); if v then redis.call('DEL',KEYS[1]) end; return v"
    try:
        if hasattr(redis, "getdel"):
            stored_hash = await redis.getdel(session_key)
        else:
            stored_hash = await redis.eval(_GETDEL_LUA, 1, session_key)
    except Exception:
        stored_hash = await redis.get(session_key)
        if stored_hash:
            await redis.delete(session_key)

    if not stored_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP expired or not requested.")

    expected_hash = hash_otp(canonical_email, body.otp)
    stored_str = stored_hash.decode() if isinstance(stored_hash, bytes) else stored_hash
    if not hmac.compare_digest(stored_str, expected_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")

    await redis.delete(rate_key)

    phone_user_id = await _extract_phone_verified_user_id(request, redis)

    async with db.acquire() as conn:
        if phone_user_id:
            # Phone verified in step 1 — link verified email to this phone account
            user_row = await conn.fetchrow(
                "SELECT id, phone_number, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE id = $1",
                phone_user_id,
            )
            if not user_row or not user_row.get("phone_number"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone verification required: You must verify your mobile number first.",
                )
            _assert_account_active(user_row)
            await conn.execute(
                "UPDATE users SET email = $1, is_email_verified = TRUE, last_active_at = NOW() WHERE id = $2",
                canonical_email,
                phone_user_id,
            )
            onboarding_completed = _row_val(user_row, "onboarding_completed", False) or False
            log.info("Linked email to phone user %s: %s", phone_user_id, mask_email(canonical_email))
            return await _issue_token_response(phone_user_id, False, onboarding_completed, conn)
        else:
            # Standalone email verification: only allowed if account already has a verified phone number
            row = await conn.fetchrow(
                "SELECT id, phone_number, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE email = $1 OR email = $2",
                canonical_email,
                clean_email,
            )
            if not row or not row.get("phone_number"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone verification required: You must verify your mobile number before using email sign in.",
                )
            _assert_account_active(row)
            user_id = row["id"]
            onboarding_completed = _row_val(row, "onboarding_completed", False) or False
            return await _issue_token_response(user_id, False, onboarding_completed, conn)


import jwt as pyjwt

_google_jwk_client = pyjwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", cache_keys=True)
_apple_jwk_client = pyjwt.PyJWKClient("https://appleid.apple.com/auth/keys", cache_keys=True)


def _verify_google_token(id_token: str) -> dict:
    if settings.environment != "production" and id_token.startswith("mock_google_token_"):
        return pyjwt.decode(id_token, options={"verify_signature": False})
    try:
        signing_key = _google_jwk_client.get_signing_key_from_jwt(id_token)
        decode_kwargs = {
            "key": signing_key.key,
            "algorithms": ["RS256"],
            "options": {"verify_signature": True},
        }
        if settings.google_client_id:
            decode_kwargs["audience"] = settings.google_client_id
        elif settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth audience not configured for production.",
            )
        else:
            decode_kwargs["options"]["verify_aud"] = False

        payload = pyjwt.decode(id_token, **decode_kwargs)
        if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError("Invalid issuer")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Google ID token signature verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The Google authentication token is invalid or has expired.",
        )


def _verify_apple_token(id_token: str) -> dict:
    if settings.environment != "production" and id_token.startswith("mock_apple_token_"):
        return pyjwt.decode(id_token, options={"verify_signature": False})
    try:
        signing_key = _apple_jwk_client.get_signing_key_from_jwt(id_token)
        decode_kwargs = {
            "key": signing_key.key,
            "algorithms": ["RS256"],
            "options": {"verify_signature": True},
        }
        if settings.apple_bundle_id:
            decode_kwargs["audience"] = settings.apple_bundle_id
        elif settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Apple OAuth audience not configured for production.",
            )
        else:
            decode_kwargs["options"]["verify_aud"] = False

        payload = pyjwt.decode(id_token, **decode_kwargs)
        if payload.get("iss") != "https://appleid.apple.com":
            raise ValueError("Invalid issuer")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Apple ID token signature verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The Apple authentication token is invalid or has expired.",
        )


# ── POST /v1/auth/google ──────────────────────────────────────────────────────

@router.post("/google")
async def google_auth(request: Request, body: GoogleAuthBody, db: DBDep, redis: RedisDep) -> dict:
    client_ip = get_trusted_client_ip(request)
    await sliding_window_rate_limit(f"ratelimit:auth:google:{client_ip}", 20, 60, redis)
    client_subnet = get_client_subnet(client_ip)
    await sliding_window_rate_limit(f"ratelimit:auth:google:subnet:{client_subnet}", 50, 60, redis)

    is_bot, bot_msg = await asyncio.to_thread(
        verify_bot_integrity,
        dict(request.headers),
        body.turnstile_token,
        is_production=settings.environment == "production",
    )
    if is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)

    payload = _verify_google_token(body.id_token)

    iss = payload.get("iss")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer.")

    exp = payload.get("exp")
    if exp and exp < datetime.now(timezone.utc).timestamp():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google authentication has expired.")

    google_sub = payload.get("sub")
    raw_email = payload.get("email", "").strip().lower() if payload.get("email") else None
    email = canonicalize_email(raw_email) if raw_email else None
    email_verified = payload.get("email_verified") in (True, "true", "True")
    verified_email = email if email_verified else None
    name = payload.get("name") or payload.get("given_name")

    if not google_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google account identification missing.")

    if verified_email:
        is_disp, reason = await asyncio.to_thread(is_disposable_email, verified_email, allow_custom_domains=True)
        if is_disp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    phone_user_id = await _extract_phone_verified_user_id(request, redis)

    async with db.acquire() as conn:
        if phone_user_id:
            # Phone verified in step 1 — link Google account to this phone user
            user_row = await conn.fetchrow(
                "SELECT id, phone_number, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE id = $1",
                phone_user_id,
            )
            if not user_row or not user_row.get("phone_number"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone verification required: You must verify your mobile number first.",
                )
            _assert_account_active(user_row)
            await conn.execute(
                """
                UPDATE users
                   SET google_id = $1,
                       email = COALESCE(email, $2),
                       first_name = COALESCE(first_name, $3),
                       is_email_verified = TRUE,
                       last_active_at = NOW()
                 WHERE id = $4
                """,
                str(google_sub),
                verified_email,
                name,
                phone_user_id,
            )
            onboarding_completed = _row_val(user_row, "onboarding_completed", False) or False
            log.info("Linked Google to phone user %s: %s", phone_user_id, mask_email(email) if email else "sub_only")
            return await _issue_token_response(phone_user_id, False, onboarding_completed, conn)
        else:
            # Standalone Google sign-in without active phone-verified session
            # MUST check that user exists AND already has a verified phone_number
            user_row = await conn.fetchrow(
                "SELECT id, phone_number, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE google_id = $1 OR (email IS NOT NULL AND email = $2)",
                str(google_sub), verified_email,
            )
            if not user_row or not user_row.get("phone_number"):
                # Reject bot or unverified user attempting to bypass phone verification
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone verification required: You must verify your mobile number before signing in with Google.",
                )
            _assert_account_active(user_row)
            user_id = user_row["id"]
            onboarding_completed = _row_val(user_row, "onboarding_completed", False) or False
            await conn.execute("UPDATE users SET google_id = $1, last_active_at = NOW() WHERE id = $2 AND google_id IS NULL", str(google_sub), user_id)
            log.info("User authenticated via Google (phone verified): %s", mask_email(email) if email else "sub_only")
            return await _issue_token_response(user_id, False, onboarding_completed, conn)


# ── POST /v1/auth/apple ───────────────────────────────────────────────────────

@router.post("/apple")
async def apple_auth(request: Request, body: AppleAuthBody, db: DBDep, redis: RedisDep) -> dict:
    client_ip = get_trusted_client_ip(request)
    await sliding_window_rate_limit(f"ratelimit:auth:apple:{client_ip}", 20, 60, redis)
    client_subnet = get_client_subnet(client_ip)
    await sliding_window_rate_limit(f"ratelimit:auth:apple:subnet:{client_subnet}", 50, 60, redis)

    is_bot, bot_msg = await asyncio.to_thread(
        verify_bot_integrity,
        dict(request.headers),
        body.turnstile_token,
        is_production=settings.environment == "production",
    )
    if is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)

    payload = _verify_apple_token(body.id_token)

    iss = payload.get("iss")
    if iss != "https://appleid.apple.com":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer.")

    exp = payload.get("exp")
    if exp and exp < datetime.now(timezone.utc).timestamp():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Apple authentication has expired.")

    apple_sub = payload.get("sub")
    raw_email = payload.get("email", "").strip().lower() if payload.get("email") else None
    email = canonicalize_email(raw_email) if raw_email else None
    email_verified = payload.get("email_verified") in (True, "true", "True")
    verified_email = email if email_verified else None
    first_name = body.first_name

    if not apple_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Apple account identification missing.")

    if verified_email:
        is_disp, reason = await asyncio.to_thread(is_disposable_email, verified_email, allow_custom_domains=True)
        if is_disp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    phone_user_id = await _extract_phone_verified_user_id(request, redis)

    async with db.acquire() as conn:
        if phone_user_id:
            # Phone verified in step 1 — link Apple account to this phone user
            user_row = await conn.fetchrow(
                "SELECT id, phone_number, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE id = $1",
                phone_user_id,
            )
            if not user_row or not user_row.get("phone_number"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone verification required: You must verify your mobile number first.",
                )
            _assert_account_active(user_row)
            await conn.execute(
                """
                UPDATE users
                   SET apple_id = $1,
                       email = COALESCE(email, $2),
                       first_name = COALESCE(first_name, $3),
                       is_email_verified = TRUE,
                       last_active_at = NOW()
                 WHERE id = $4
                """,
                str(apple_sub),
                verified_email,
                first_name,
                phone_user_id,
            )
            onboarding_completed = _row_val(user_row, "onboarding_completed", False) or False
            log.info("Linked Apple to phone user %s: %s", phone_user_id, mask_email(email) if email else "sub_only")
            return await _issue_token_response(phone_user_id, False, onboarding_completed, conn)
        else:
            # Standalone Apple sign-in: require that user exists AND has verified phone_number
            row = await conn.fetchrow(
                "SELECT id, phone_number, onboarding_completed, account_status, deleted_at, suspend_until FROM users WHERE apple_id = $1 OR (email IS NOT NULL AND email = $2)",
                str(apple_sub), verified_email,
            )
            if not row or not row.get("phone_number"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone verification required: You must verify your mobile number before signing in with Apple.",
                )
            _assert_account_active(row)
            user_id = row["id"]
            onboarding_completed = _row_val(row, "onboarding_completed", False) or False
            await conn.execute("UPDATE users SET apple_id = $1, last_active_at = NOW() WHERE id = $2 AND apple_id IS NULL", str(apple_sub), user_id)
            log.info("User authenticated via Apple (phone verified): %s", mask_email(email) if email else "sub_only")
            return await _issue_token_response(user_id, False, onboarding_completed, conn)


def _pack_grace_payload(resp_data: dict) -> str:
    raw_str = json.dumps(resp_data, sort_keys=True)
    sig = hmac.new(settings.jwt_secret_key.encode(), raw_str.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"data": resp_data, "sig": sig})


def _unpack_grace_payload(raw_val: bytes | str) -> dict | None:
    try:
        decoded = raw_val.decode() if isinstance(raw_val, bytes) else raw_val
        wrapper = json.loads(decoded)
        if isinstance(wrapper, dict):
            if "data" in wrapper and "sig" in wrapper:
                raw_data = json.dumps(wrapper["data"], sort_keys=True)
                expected_sig = hmac.new(
                    settings.jwt_secret_key.encode(),
                    raw_data.encode(),
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(wrapper["sig"], expected_sig):
                    return wrapper["data"]
                return None
            if "access_token" in wrapper:
                return wrapper
        return None
    except Exception:
        return None


# ── POST /v1/auth/token/refresh ───────────────────────────────────────────────

@router.post("/token/refresh")
async def refresh_token_endpoint(body: TokenRefreshBody, request: Request, db: DBDep, redis: RedisDep) -> dict:
    client_ip = get_trusted_client_ip(request)
    await sliding_window_rate_limit(f"ratelimit:auth:refresh:{client_ip}", 30, 60, redis)
    client_subnet = get_client_subnet(client_ip)
    await sliding_window_rate_limit(f"ratelimit:auth:refresh:subnet:{client_subnet}", 100, 60, redis)

    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    # 1. Check if token was recently rotated within concurrency grace window (15s)
    cached_grace = await redis.get(f"auth:grace_rt:{token_hash}")
    if cached_grace:
        payload = _unpack_grace_payload(cached_grace)
        if payload:
            return ok(payload)

    # Check if session was replaced by login from another device (BUG-064)
    was_replaced = await redis.get(f"auth:replaced_by_login:{token_hash}")
    if was_replaced:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to login from another device. Please sign in again.",
        )

    # 2. Check for replay/reuse of an already-rotated token past grace window (Theft Detection)
    reused_user_id = await redis.get(f"auth:revoked_rt:{token_hash}")
    if reused_user_id:
        reused_uid = reused_user_id.decode() if isinstance(reused_user_id, bytes) else reused_user_id
        async with db.acquire() as conn:
            await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", uuid.UUID(reused_uid))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions revoked.",
        )

    # Durable check against PostgreSQL if Redis had a cache miss or restarted
    async with db.acquire() as conn:
        rev_row = await conn.fetchrow(
            """
            SELECT revocation_type, user_id, payload, expires_at
            FROM revoked_refresh_tokens
            WHERE token_hash = $1 AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
            """,
            token_hash,
        )
        if rev_row:
            if rev_row["revocation_type"] == "grace" and rev_row.get("payload"):
                try:
                    return ok(json.loads(rev_row["payload"]))
                except Exception:
                    pass
            elif rev_row["revocation_type"] == "replaced_by_login":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session expired due to login from another device. Please sign in again.",
                )
            elif rev_row["revocation_type"] == "revoked":
                await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", rev_row["user_id"])
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token reuse detected. All sessions revoked.",
                )

    async with db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT rt.user_id, rt.expires_at,
                       u.id AS u_id, u.account_status, u.deleted_at, u.suspend_until
                FROM refresh_tokens rt
                LEFT JOIN users u ON u.id = rt.user_id
                WHERE rt.token_hash = $1
                FOR UPDATE OF rt
                """,
                token_hash,
            )

            exp_val = row["expires_at"] if row else None
            is_expired = False
            if isinstance(exp_val, datetime):
                exp_utc = exp_val if exp_val.tzinfo else exp_val.replace(tzinfo=timezone.utc)
                is_expired = exp_utc < datetime.now(timezone.utc)

            if not row or is_expired:
                # Concurrency check: If winner committed while loser waited on lock
                cached_grace = await redis.get(f"auth:grace_rt:{token_hash}")
                if cached_grace:
                    payload = _unpack_grace_payload(cached_grace)
                    if payload:
                        return ok(payload)

                was_replaced = await redis.get(f"auth:replaced_by_login:{token_hash}")
                if was_replaced:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session expired due to login from another device. Please sign in again.",
                    )

                # Recheck revocation/reuse post-lock (O-5)
                reused_user_id = await redis.get(f"auth:revoked_rt:{token_hash}")
                if reused_user_id:
                    reused_uid = reused_user_id.decode() if isinstance(reused_user_id, bytes) else reused_user_id
                    await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", uuid.UUID(reused_uid))
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Refresh token reuse detected. All sessions revoked.",
                    )

                if row:
                    await conn.execute(
                        "DELETE FROM refresh_tokens WHERE user_id = $1",
                        row["user_id"],
                    )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token.",
                )

            # Check account active status
            if "u_id" in row and row["u_id"] is None:
                await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", row["user_id"])
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account not found.",
                )

            try:
                _assert_account_active(row)
            except HTTPException:
                await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", row["user_id"])
                raise

            user_id = row["user_id"]
            access_token = create_access_token(user_id)
            new_refresh = create_refresh_token()
            new_hash = hashlib.sha256(new_refresh.encode()).hexdigest()
            new_expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

            # Rotate: delete old, insert new
            await conn.execute(
                """
                UPDATE refresh_tokens
                SET token_hash = $1, expires_at = $2, created_at = NOW()
                WHERE user_id = $3
                """,
                new_hash, new_expires, user_id,
            )

            resp_data = AccessTokenResponse(
                access_token=access_token,
                refresh_token=new_refresh,
                expires_in=settings.access_token_expire_minutes * 60,
            ).model_dump(mode="json")

            # Persist revocation record to PostgreSQL before releasing lock
            exp_time = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
            grace_exp = datetime.now(timezone.utc) + timedelta(seconds=15)
            try:
                await conn.execute(
                    """
                    INSERT INTO revoked_refresh_tokens (token_hash, user_id, revocation_type, payload, expires_at)
                    VALUES ($1, $2, 'revoked', NULL, $3)
                    ON CONFLICT (token_hash) DO NOTHING
                    """,
                    token_hash, user_id, exp_time,
                )
                await conn.execute(
                    """
                    INSERT INTO revoked_refresh_tokens (token_hash, user_id, revocation_type, payload, expires_at)
                    VALUES ($1, $2, 'grace', $3, $4)
                    ON CONFLICT (token_hash) DO UPDATE SET payload = EXCLUDED.payload, expires_at = EXCLUDED.expires_at
                    """,
                    token_hash, user_id, json.dumps(resp_data), grace_exp,
                )
            except Exception as dberr:
                log.warning("Failed to record durable token revocation in DB: %s", dberr)

            # Set grace window (15s) and revocation record in Redis cache
            try:
                await redis.set(
                    f"auth:grace_rt:{token_hash}",
                    _pack_grace_payload(resp_data),
                    ex=15,
                )
                await redis.set(
                    f"auth:revoked_rt:{token_hash}",
                    str(user_id),
                    ex=settings.refresh_token_expire_days * 86400,
                )
            except Exception:
                pass

    return ok(resp_data)



# ── POST /v1/auth/logout ──────────────────────────────────────────────────────

@router.post("/logout", summary="Logout and invalidate token session")
async def logout_endpoint(
    current_user: CurrentUserForLogout,
    db: DBDep,
    redis: RedisDep,
    body: Optional[LogoutBody] = None,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """
    Session revocation per SECURITY.md Section 2.2:
    1. Blacklists current access token jti in Redis (<1ms lookup).
    2. Revokes active refresh token from PostgreSQL (single active session model).
    3. Scopes push notification token cleanup (user_devices) to current device (retaining other devices for push if not all_devices).
    """
    try:
        payload = await validate_access_token(credentials, redis)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            now = datetime.now(timezone.utc).timestamp()
            ttl = max(1, int(exp - now))
            await revoke_token(jti, ttl, redis)
    except Exception:
        pass  # Token may already be partially invalid

    user_id_raw = current_user.get("user_id") or current_user.get("id")
    user_id = uuid.UUID(str(user_id_raw))
    await sliding_window_rate_limit(f"ratelimit:auth:logout:{user_id}", 30, 60, redis)
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)
        try:
            if body and body.device_id and not body.all_devices:
                await conn.execute(
                    "DELETE FROM user_devices WHERE user_id = $1 AND device_id = $2",
                    user_id,
                    body.device_id,
                )
                remaining_token = await conn.fetchval(
                    "SELECT token FROM user_devices WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1",
                    user_id,
                )
                await conn.execute(
                    "UPDATE users SET fcm_token = $1, updated_at = NOW() WHERE id = $2",
                    remaining_token,
                    user_id,
                )
            elif body and body.all_devices:
                # Explicit all-devices logout: wipe all push registrations
                await conn.execute("DELETE FROM user_devices WHERE user_id = $1", user_id)
                await conn.execute("UPDATE users SET fcm_token = NULL, updated_at = NOW() WHERE id = $1", user_id)
            # else: plain logout with no device_id — leave other devices' push tokens intact
        except Exception as exc:
            log.warning("Failed to clean up user_devices on logout for %s: %s", user_id, exc)

    # Invalidate feed cache and active session keys
    try:
        await redis.delete(f"feed:cache:{user_id}", f"user:session:{user_id}")
    except Exception:
        pass
    if body and body.all_devices:
        try:
            await ws_manager.disconnect_user(str(user_id), reason="You have been logged out on all devices.")
        except Exception:
            pass

    return ok({"message": "You have been logged out successfully."})

