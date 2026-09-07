import uuid
from datetime import datetime, timezone
from typing import Annotated

import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_pool
from app.core.redis import get_redis
from app.core.security import validate_access_token, sliding_window_rate_limit

_bearer = HTTPBearer()


# ── DB / Redis ────────────────────────────────────────────────────────────────

def get_db() -> asyncpg.Pool:
    return get_pool()


def get_redis_client() -> aioredis.Redis:
    return get_redis()


DBDep = Annotated[asyncpg.Pool, Depends(get_db)]
RedisDep = Annotated[aioredis.Redis, Depends(get_redis_client)]


class UserSession(dict):
    """Dictionary supporting attribute access (e.g. user.id and user['id'])."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'UserSession' object has no attribute '{name}'")


# ── Auth ──────────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: asyncpg.Pool = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_client),
) -> UserSession:
    payload = await validate_access_token(credentials, redis)
    user_id = payload["sub"]

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, phone_number, first_name, gender, show_me,
                   dietary_strictness, eats_root_vegetables, eats_onion_garlic,
                   community_sect, city, state, max_distance_km,
                   open_to_relocation, subscription_tier, account_status,
                   paryushan_mode, is_photo_verified, suspend_until, deleted_at
            FROM users
            WHERE id = $1
            """,
            uuid.UUID(user_id),
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
        )

    user_data = dict(row)
    if user_data.get("deleted_at") is not None or user_data.get("account_status") == "deleted":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been deleted.",
        )

    if user_data.get("account_status") == "banned":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been permanently banned.",
        )

    suspend_until = user_data.get("suspend_until")
    is_suspended = user_data.get("account_status") == "suspended"
    if is_suspended or (suspend_until and suspend_until > datetime.now(timezone.utc)):
        detail_until = suspend_until.isoformat() if suspend_until else "further notice"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User account is temporarily suspended until {detail_until}.",
        )

    user_dict = UserSession(row)
    user_dict["user_id"] = row["id"]
    return user_dict


CurrentUser = Annotated[dict, Depends(get_current_user)]
 
 
# ── Admin Auth ────────────────────────────────────────────────────────────────
 
async def require_admin(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Verify caller has an admin_users row with role in (superadmin, moderator)."""
    user_id = current_user.get("user_id") or current_user.get("id")
    try:
        redis = get_redis()
        await sliding_window_rate_limit(f"ratelimit:admin:{user_id}", 120, 60, redis)
    except HTTPException:
        raise
    except Exception:
        pass

    async with pool.acquire() as conn:
        role = await conn.fetchval(
            "SELECT role FROM admin_users WHERE user_id = $1",
            user_id,
        )
    if role not in ("superadmin", "moderator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    current_user["admin_role"] = role
    return current_user


def require_superadmin(admin: dict = Depends(require_admin)) -> dict:
    if admin.get("admin_role") != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return admin


AdminUser = Annotated[dict, Depends(require_admin)]
SuperAdminUser = Annotated[dict, Depends(require_superadmin)]
