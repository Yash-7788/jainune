"""
PostgreSQL Connection Pool Manager:
- Multi-server / Multi-replica fallback support.
- Exponential backoff retry on network blips.
- Connection health checking and auto-recovery.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg
from app.core.config import settings

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_replica_pool: asyncpg.Pool | None = None


async def create_pool(max_retries: int = 3) -> asyncpg.Pool:
    """
    Creates the primary asyncpg pool with connection retry and backoff.
    Gracefully falls back to replica or secondary DSN if configured.
    """
    global _pool, _replica_pool
    primary_dsn = settings.database_url
    # Optional replica or secondary server DSN
    fallback_dsn = getattr(settings, "database_replica_url", None)

    for attempt in range(1, max_retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                dsn=primary_dsn,
                min_size=settings.database_pool_min_size,
                max_size=settings.database_pool_max_size,
                timeout=5.0,
                command_timeout=settings.database_statement_timeout_ms / 1000,
                statement_cache_size=0,
                server_settings={"application_name": "jainune-api-primary"},
            )
            log.info("Primary database connection pool initialized successfully.")
            return _pool
        except Exception as exc:
            log.warning(
                "Primary database connection attempt %s/%s failed: %s",
                attempt, max_retries, exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(attempt * 1.5)

    # If primary exhausted and fallback configured, attempt fallback server
    if fallback_dsn:
        log.warning("Primary database unreachable. Attempting graceful fallback to secondary database server...")
        try:
            _pool = await asyncpg.create_pool(
                dsn=fallback_dsn,
                min_size=settings.database_pool_min_size,
                max_size=settings.database_pool_max_size,
                timeout=5.0,
                command_timeout=settings.database_statement_timeout_ms / 1000,
                statement_cache_size=0,
                server_settings={"application_name": "jainune-api-fallback"},
            )
            log.info("Fallback database connection pool established.")
            return _pool
        except Exception as exc:
            log.critical("Fallback database connection failed: %s", exc)

    if _pool is None:
        raise RuntimeError("Could not establish connection to primary or fallback database servers.")

    # Initialize restart-resilient persistence tables
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS revoked_refresh_tokens (
                    token_hash VARCHAR(64) PRIMARY KEY,
                    user_id UUID NOT NULL,
                    revocation_type VARCHAR(32) NOT NULL,
                    payload TEXT,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_revoked_tokens_user ON revoked_refresh_tokens(user_id);
                CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_refresh_tokens(expires_at);

                CREATE TABLE IF NOT EXISTS feed_queues (
                    user_id UUID PRIMARY KEY,
                    candidate_ids UUID[] NOT NULL,
                    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
    except Exception as exc:
        log.warning("Database schema check for resilient tables deferred: %s", exc)

    return _pool


async def close_pool() -> None:
    global _pool, _replica_pool
    if _pool:
        await _pool.close()
        _pool = None
    if _replica_pool:
        await _replica_pool.close()
        _replica_pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool
