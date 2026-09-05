import uuid
from datetime import datetime, timezone
from typing import Annotated

import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_pool
from app.core.redis import get_redis
from app.core.security import validate_access_token

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

    if row.get("deleted_at") is not None or row.get("account_status") == "deleted":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been deleted.",
        )

    if row.get("account_status") == "banned":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been permanently banned.",
        )

    suspend_until = row.get("suspend_until")
    if suspend_until and suspend_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User account is temporarily suspended until {suspend_until.isoformat()}.",
        )

    user_dict = UserSession(row)
    user_dict["user_id"] = row["id"]
    return user_dict


CurrentUser = Annotated[dict, Depends(get_current_user)]
