import redis.asyncio as aioredis
from app.core.config import settings

_redis: aioredis.Redis | None = None


async def create_redis() -> aioredis.Redis:
    global _redis
    _redis = await aioredis.from_url(
        settings.redis_url,
        max_connections=settings.redis_pool_max_connections,
        decode_responses=False,
    )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis client not initialized")
    return _redis
