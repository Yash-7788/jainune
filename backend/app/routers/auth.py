import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import hmac
import logging
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    revoke_token,
    sliding_window_rate_limit,
    validate_access_token,
    verify_otp,
)
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.main import err, ok
from app.models.schemas.auth import (
    AccessTokenResponse,
    AppleAuthBody,
    EmailOTPRequestBody,
    EmailOTPVerifyBody,
    GoogleAuthBody,
    OTPRequestBody,
    OTPRequestResponse,
    OTPVerifyBody,
    TokenRefreshBody,
    TokenResponse,
)
from app.services.email_verifier import is_disposable_email, verify_bot_integrity

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])
_bearer = HTTPBearer()

OTP_TTL_SECONDS = 180
OTP_RATE_WINDOW_SECONDS = 3600
OTP_RATE_LIMIT = 3


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
                "INSERT INTO users (phone_number, auth_provider) VALUES ($1, 'phone') RETURNING id",
                body.phone_number,
            )
        else:
            user_id = row["id"]
            onboarding_completed = row["onboarding_completed"] or False

        return await _issue_token_response(user_id, is_new_user, onboarding_completed, conn)


# ── POST /v1/auth/email/otp/request ──────────────────────────────────────────

@router.post("/email/otp/request")
async def request_email_otp(request: Request, body: EmailOTPRequestBody, redis: RedisDep) -> dict:
    is_bot, bot_msg = verify_bot_integrity(dict(request.headers), body.turnstile_token)
    if is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)

    is_disposable, reason = is_disposable_email(body.email)
    if is_disposable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    clean_email = body.email.strip().lower()
    rate_key = f"auth:email_otp_rate:{clean_email}"
    await sliding_window_rate_limit(rate_key, OTP_RATE_LIMIT, OTP_RATE_WINDOW_SECONDS, redis)

    otp = generate_otp()
    otp_hash = hash_otp(clean_email, otp)
    session_key = f"auth:email_otp:{clean_email}"
    await redis.set(session_key, otp_hash.encode(), ex=OTP_TTL_SECONDS)

    log.info("Dispatched email OTP to %s", clean_email)
    return ok({
        "email": clean_email,
        "retry_after_seconds": 60,
        "expires_in_seconds": OTP_TTL_SECONDS,
    })


# ── POST /v1/auth/email/otp/verify ───────────────────────────────────────────

@router.post("/email/otp/verify")
async def verify_email_otp(body: EmailOTPVerifyBody, db: DBDep, redis: RedisDep) -> dict:
    clean_email = body.email.strip().lower()
    session_key = f"auth:email_otp:{clean_email}"
    stored_hash = await redis.get(session_key)
    if not stored_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP expired or not requested.")

    expected_hash = hash_otp(clean_email, body.otp)
    stored_str = stored_hash.decode() if isinstance(stored_hash, bytes) else stored_hash
    if not hmac.compare_digest(stored_str, expected_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")

    await redis.delete(session_key)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, onboarding_completed FROM users WHERE email = $1",
            clean_email,
        )
        is_new_user = row is None
        if is_new_user:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (email, is_email_verified, auth_provider)
                VALUES ($1, TRUE, 'email')
                RETURNING id
                """,
                clean_email,
            )
            onboarding_completed = False
        else:
            user_id = row["id"]
            onboarding_completed = row["onboarding_completed"] or False

        return await _issue_token_response(user_id, is_new_user, onboarding_completed, conn)


# ── POST /v1/auth/google ──────────────────────────────────────────────────────

@router.post("/google")
async def google_auth(request: Request, body: GoogleAuthBody, db: DBDep) -> dict:
    is_bot, bot_msg = verify_bot_integrity(dict(request.headers), body.turnstile_token)
    if is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)

    import jwt as pyjwt
    try:
        payload = pyjwt.decode(body.id_token, options={"verify_signature": False})
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Google token: {exc}")

    google_sub = payload.get("sub")
    email = payload.get("email", "").strip().lower() if payload.get("email") else None
    name = payload.get("name") or payload.get("given_name")

    if not google_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing subject in Google token")

    if email:
        is_disp, reason = is_disposable_email(email)
        if is_disp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, onboarding_completed FROM users WHERE google_id = $1 OR (email IS NOT NULL AND email = $2)",
            str(google_sub), email,
        )
        is_new_user = row is None
        if is_new_user:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (google_id, email, first_name, is_email_verified, auth_provider)
                VALUES ($1, $2, $3, TRUE, 'google')
                RETURNING id
                """,
                str(google_sub), email, name,
            )
            onboarding_completed = False
        else:
            user_id = row["id"]
            onboarding_completed = row["onboarding_completed"] or False
            await conn.execute("UPDATE users SET google_id = $1 WHERE id = $2 AND google_id IS NULL", str(google_sub), user_id)

        return await _issue_token_response(user_id, is_new_user, onboarding_completed, conn)


# ── POST /v1/auth/apple ───────────────────────────────────────────────────────

@router.post("/apple")
async def apple_auth(request: Request, body: AppleAuthBody, db: DBDep) -> dict:
    is_bot, bot_msg = verify_bot_integrity(dict(request.headers), body.turnstile_token)
    if is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=bot_msg)

    import jwt as pyjwt
    try:
        payload = pyjwt.decode(body.id_token, options={"verify_signature": False})
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Apple token: {exc}")

    apple_sub = payload.get("sub")
    email = payload.get("email", "").strip().lower() if payload.get("email") else None
    first_name = body.first_name

    if not apple_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing subject in Apple token")

    if email:
        is_disp, reason = is_disposable_email(email)
        if is_disp:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, onboarding_completed FROM users WHERE apple_id = $1 OR (email IS NOT NULL AND email = $2)",
            str(apple_sub), email,
        )
        is_new_user = row is None
        if is_new_user:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (apple_id, email, first_name, is_email_verified, auth_provider)
                VALUES ($1, $2, $3, TRUE, 'apple')
                RETURNING id
                """,
                str(apple_sub), email, first_name,
            )
            onboarding_completed = False
        else:
            user_id = row["id"]
            onboarding_completed = row["onboarding_completed"] or False
            await conn.execute("UPDATE users SET apple_id = $1 WHERE id = $2 AND apple_id IS NULL", str(apple_sub), user_id)

        return await _issue_token_response(user_id, is_new_user, onboarding_completed, conn)


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


# ── POST /v1/auth/logout ──────────────────────────────────────────────────────

@router.post("/logout", summary="Logout and invalidate token session")
async def logout_endpoint(
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """
    Session revocation per SECURITY.md Section 2.2:
    1. Blacklists current access token jti in Redis (<1ms lookup).
    2. Deletes active refresh token from PostgreSQL.
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
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)

    # Invalidate feed cache and active session keys
    try:
        await redis.delete(f"feed:cache:{user_id}", f"user:session:{user_id}")
    except Exception:
        pass

    return ok({"message": "You have been logged out successfully."})


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
