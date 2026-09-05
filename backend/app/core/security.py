import hmac
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis.asyncio as aioredis
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer = HTTPBearer()

# Load RSA keys once at import time
with open(settings.jwt_private_key_path, "rb") as f:
    _RSA_PRIVATE_KEY = f.read()

with open(settings.jwt_public_key_path, "rb") as f:
    _RSA_PUBLIC_KEY = f.read()


# ── OTP ─────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Cryptographically secure 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)


def hash_otp(phone_number: str, otp: str) -> str:
    """HMAC-SHA256 of phone+otp with pepper. Never store raw OTP."""
    return hmac.new(
        settings.otp_pepper_secret.encode(),
        f"{phone_number}:{otp}".encode(),
        hashlib.sha256,
    ).hexdigest()


async def verify_otp(
    phone_number: str,
    submitted_otp: str,
    redis: aioredis.Redis,
) -> bool:
    rate_key = f"auth:attempts:{phone_number}"
    session_key = f"auth:otp:{phone_number}"

    attempts = await redis.incr(rate_key)
    if attempts == 1:
        await redis.expire(rate_key, 300)
    if attempts > 5:
        await redis.delete(session_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP verification attempts exceeded. Request a new OTP.",
        )

    stored_hash = await redis.get(session_key)
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not requested.",
        )

    expected = hash_otp(phone_number, submitted_otp)
    if not hmac.compare_digest(stored_hash.decode(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OTP code.",
        )

    await redis.delete(session_key)
    await redis.delete(rate_key)
    return True


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": "jainune-api",
        "aud": "jainune-client",
    }
    return jwt.encode(payload, _RSA_PRIVATE_KEY, algorithm="RS256")


def create_refresh_token() -> str:
    """Cryptographically random 48-byte hex refresh token."""
    return f"rt_{secrets.token_hex(48)}"


async def validate_access_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    redis: aioredis.Redis | None = None,
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            _RSA_PUBLIC_KEY,
            algorithms=["RS256"],
            issuer="jainune-api",
            audience="jainune-client",
            options={"require": ["exp", "iss", "aud", "jti", "sub"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
        )

    if redis is not None:
        jti = payload["jti"]
        if await redis.exists(f"token:blacklist:{jti}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked.",
            )

    return payload


async def revoke_token(jti: str, ttl_seconds: int, redis: aioredis.Redis) -> None:
    """Add jti to Redis blacklist for remaining token lifetime."""
    await redis.set(f"token:blacklist:{jti}", "1", ex=ttl_seconds)


# ── Rate Limiting ────────────────────────────────────────────────────────────

async def sliding_window_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
    redis: aioredis.Redis,
) -> None:
    """Sliding-window rate limiter using Redis sorted set."""
    import time
    now_ms = int(time.time() * 1000)
    window_start = now_ms - (window_seconds * 1000)

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now_ms): now_ms})
    pipe.zcard(key)
    pipe.expire(key, window_seconds + 1)
    results = await pipe.execute()
    count = results[2]

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded.",
        )


async def validate_access_token_raw(
    token: str,
    redis: aioredis.Redis | None = None,
) -> dict:
    """
    Validate a raw JWT string (used by WebSocket endpoints where Bearer
    header is not available and the token arrives as a query parameter).
    """
    try:
        payload = jwt.decode(
            token,
            _RSA_PUBLIC_KEY,
            algorithms=["RS256"],
            issuer="jainune-api",
            audience="jainune-client",
            options={"require": ["exp", "iss", "aud", "jti", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    if redis is not None:
        jti = payload["jti"]
        if await redis.exists(f"token:blacklist:{jti}"):
            raise ValueError("Token has been revoked.")

    return payload

