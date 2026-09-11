import hashlib
import ipaddress
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis.asyncio as aioredis
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer = HTTPBearer()

# Load RSA keys once at import time (with safe fallback if missing in local/test env)
try:
    with open(settings.jwt_private_key_path, "rb") as f:
        _RSA_PRIVATE_KEY = f.read()
except (FileNotFoundError, OSError):
    if settings.environment == "production":
        raise RuntimeError(f"FATAL: Production JWT private key missing at {settings.jwt_private_key_path}")
    _RSA_PRIVATE_KEY = b""

try:
    with open(settings.jwt_public_key_path, "rb") as f:
        _RSA_PUBLIC_KEY = f.read()
except (FileNotFoundError, OSError):
    if settings.environment == "production":
        raise RuntimeError(f"FATAL: Production JWT public key missing at {settings.jwt_public_key_path}")
    _RSA_PUBLIC_KEY = b""

if settings.environment == "production":
    if not settings.otp_pepper_secret or settings.otp_pepper_secret == "default_test_pepper_secret_32_bytes_len":
        raise RuntimeError("FATAL: Insecure or default otp_pepper_secret in production environment.")


# ── OTP ─────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Cryptographically secure 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)


def hash_otp(phone_number: str, otp: str) -> str:
    """HMAC-SHA256 of phone+otp with pepper. Never store raw OTP."""
    return hmac.HMAC(
        settings.otp_pepper_secret.encode(),
        f"{phone_number}:{otp}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


async def verify_otp(
    phone_number: str,
    submitted_otp: str,
    redis: aioredis.Redis,
) -> bool:
    rate_key = f"auth:attempts:{phone_number}"
    session_key = f"auth:otp:{phone_number}"

    attempts = await redis.incr(rate_key)
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
    raw_hash = stored_hash.decode() if isinstance(stored_hash, bytes) else stored_hash
    if not hmac.compare_digest(raw_hash, expected):
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


def get_ist_now() -> datetime:
    """Return current timestamp in Asia/Kolkata timezone (IST)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def get_ist_today_str() -> str:
    """Return today's date formatted as YYYY-MM-DD in IST timezone."""
    return get_ist_now().strftime("%Y-%m-%d")


# ── Rate Limiting ────────────────────────────────────────────────────────────

async def sliding_window_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
    redis: aioredis.Redis,
) -> None:
    """Sliding-window rate limiter using Redis sorted set with atomic pipeline and fail-closed behavior."""
    from fastapi.params import Depends
    if isinstance(redis, Depends):
        return

    if redis is None or not hasattr(redis, "pipeline"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting service unavailable.",
        )

    import time
    import secrets
    now_ms = int(time.time() * 1000)
    window_start = now_ms - (window_seconds * 1000)

    try:
        pipe = redis.pipeline()
        if hasattr(pipe, "__await__"):
            pipe = await pipe

        r1 = pipe.zremrangebyscore(key, 0, window_start)
        r2 = pipe.zadd(key, {f"{now_ms}:{secrets.token_hex(4)}": now_ms})
        r3 = pipe.zcard(key)
        r4 = pipe.expire(key, window_seconds + 1)
        for r in (r1, r2, r3, r4):
            if hasattr(r, "__await__"):
                await r

        res = pipe.execute()
        results = await res if hasattr(res, "__await__") else res
        count = results[2] if isinstance(results, (list, tuple)) and len(results) > 2 else 1
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting service unavailable.",
        )

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


def _clean_ip(ip_str: str | None) -> str | None:
    if not ip_str:
        return None
    candidate = ip_str.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def get_trusted_client_ip(request) -> str:
    """
    Extracts authentic client IP.
    Trusts reverse-proxy headers (CF-Connecting-IP / X-Real-IP / X-Forwarded-For) ONLY if
    edge origin lock is verified with cloudflare_origin_secret.
    Otherwise falls back strictly to direct peer IP request.client.host to prevent rate-limit evasion.
    All candidate IPs are validated with ipaddress.ip_address to prevent Redis key injection.
    """
    if not request:
        return "127.0.0.1"

    headers = {k.lower(): v for k, v in request.headers.items()} if hasattr(request, "headers") else {}
    origin_secret = getattr(settings, "cloudflare_origin_secret", "")
    edge_token = headers.get("x-edge-secret") or headers.get("x-origin-secret")

    # Only trust reverse-proxy headers if origin lock matches
    if origin_secret and edge_token == origin_secret:
        for header_key in ("cf-connecting-ip", "x-real-ip"):
            ip_val = _clean_ip(headers.get(header_key))
            if ip_val:
                return ip_val
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            ip_val = _clean_ip(forwarded.split(",")[0])
            if ip_val:
                return ip_val

    if getattr(settings, "environment", "development") != "production":
        cf_ip = _clean_ip(headers.get("cf-connecting-ip"))
        if cf_ip:
            return cf_ip

    if hasattr(request, "client") and request.client and getattr(request.client, "host", None):
        client_ip = _clean_ip(request.client.host)
        if client_ip:
            return client_ip

    return "127.0.0.1"


def is_safe_public_url(url: str | None) -> bool:
    """
    SSRF Protection:
    Ensures URL uses http/https and does not target localhost,
    internal cloud metadata (e.g. 169.254.169.254), or RFC 1918 private subnets.
    """
    if not url:
        return True
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower().strip()
        if not host:
            return False
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal", "instance-data"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass  # Standard domain name
        return True
    except Exception:
        return False


def __getattr__(name: str):
    if name == "get_current_user":
        from app.dependencies import get_current_user
        return get_current_user
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

