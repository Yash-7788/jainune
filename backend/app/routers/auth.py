import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    sliding_window_rate_limit,
    verify_otp,
)
from app.dependencies import DBDep, RedisDep
from app.main import err, ok
from app.models.schemas.auth import (
    AccessTokenResponse,
    OTPRequestBody,
    OTPRequestResponse,
    OTPVerifyBody,
    TokenRefreshBody,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

OTP_TTL_SECONDS = 180
OTP_RATE_WINDOW_SECONDS = 3600
OTP_RATE_LIMIT = 3


# ── POST /v1/auth/otp/request ─────────────────────────────────────────────────

@router.post("/otp/request")
async def request_otp(body: OTPRequestBody, redis: RedisDep) -> dict:
    # Rate limit: 3 OTP requests per phone per hour
    rate_key = f"auth:otp_rate:{body.phone_number}"
    await sliding_window_rate_limit(rate_key, OTP_RATE_LIMIT, OTP_RATE_WINDOW_SECONDS, redis)

    otp = generate_otp()
    otp_hash = hash_otp(body.phone_number, otp)

    # Store HMAC in Redis, never the raw OTP
    session_key = f"auth:otp:{body.phone_number}"
    await redis.set(session_key, otp_hash.encode(), ex=OTP_TTL_SECONDS)

    # Send via MSG91
    await _send_otp_msg91(body.phone_number, otp)

    return ok(OTPRequestResponse(
        phone_number=body.phone_number,
        retry_after_seconds=60,
        expires_in_seconds=OTP_TTL_SECONDS,
    ).model_dump())


# ── POST /v1/auth/otp/verify ──────────────────────────────────────────────────

@router.post("/otp/verify")
async def verify_otp_endpoint(body: OTPVerifyBody, db: DBDep, redis: RedisDep) -> dict:
    await verify_otp(body.phone_number, body.otp, redis)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, onboarding_completed FROM users WHERE phone_number = $1",
            body.phone_number,
        )

        is_new_user = row is None
        onboarding_completed = False

        if is_new_user:
            user_id = await conn.fetchval(
                "INSERT INTO users (phone_number) VALUES ($1) RETURNING id",
                body.phone_number,
            )
        else:
            user_id = row["id"]
            onboarding_completed = row["onboarding_completed"] or False

        # Issue tokens
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token()
        refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
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

    return ok(TokenResponse(
        user_id=str(user_id),
        is_new_user=is_new_user,
        onboarding_completed=onboarding_completed,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    ).model_dump())


# ── POST /v1/auth/token/refresh ───────────────────────────────────────────────

@router.post("/token/refresh")
async def refresh_token_endpoint(body: TokenRefreshBody, db: DBDep, redis: RedisDep) -> dict:
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, expires_at FROM refresh_tokens
            WHERE token_hash = $1
            """,
            token_hash,
        )

        if not row or row["expires_at"] < datetime.now(timezone.utc):
            # Possible theft: purge all sessions for user if token was already used
            if row:
                await conn.execute(
                    "DELETE FROM refresh_tokens WHERE user_id = $1",
                    row["user_id"],
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            )

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

    return ok(AccessTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    ).model_dump())


# ── MSG91 SMS dispatch ────────────────────────────────────────────────────────

async def _send_otp_msg91(phone_number: str, otp: str) -> None:
    # Strip leading + for MSG91
    mobile = phone_number.lstrip("+")
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            "https://api.msg91.com/api/v5/otp",
            params={
                "authkey": settings.msg91_auth_key,
                "template_id": settings.msg91_otp_template_id,
                "mobile": mobile,
                "otp": otp,
            },
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SMS gateway unavailable. Retry shortly.",
            )
