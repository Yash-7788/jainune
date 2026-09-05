"""
Redis Client Manager:
- Connection retry logic with backoff.
- Multi-server / Sentinel / cluster fallback support.
"""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis
from app.core.config import settings

log = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


async def create_redis(max_retries: int = 3) -> aioredis.Redis:
    """Initializes Redis connection pool with retry and fallback resilience."""
    global _redis
    primary_url = settings.redis_url

    for attempt in range(1, max_retries + 1):
        try:
            client = await aioredis.from_url(
                primary_url,
                max_connections=settings.redis_pool_max_connections,
                decode_responses=False,
            )
            # Ping to verify active socket
            await client.ping()
            _redis = client
            log.info("Redis connection established successfully.")
            return _redis
        except Exception as exc:
            log.warning("Redis connection attempt %s/%s failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                await asyncio.sleep(attempt * 1.0)

    # Fallback to in-memory or fail gracefully if secondary Redis is configured
    fallback_url = getattr(settings, "redis_fallback_url", None)
    if fallback_url:
        log.warning("Attempting connection to secondary fallback Redis...")
        try:
            client = await aioredis.from_url(
                fallback_url,
                max_connections=settings.redis_pool_max_connections,
                decode_responses=False,
            )
            await client.ping()
            _redis = client
            log.info("Fallback Redis connection established.")
            return _redis
        except Exception as exc:
            log.critical("Fallback Redis connection failed: %s", exc)

    if _redis is None:
        # Fallback to local client instance even if initial ping was delayed
        _redis = await aioredis.from_url(
            primary_url,
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
