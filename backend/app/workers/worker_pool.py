"""
Shared asyncpg connection pool and event loop manager for background worker processes.
Uses a single event loop and connection pool per process instead of creating/destroying
per-task. statement_cache_size=0 is required for PgBouncer transaction-mode (port 6543).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg

from app.core.config import settings

log = logging.getLogger(__name__)

_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_pool: asyncpg.Pool | None = None


class PooledConnectionProxy:
    """Wraps an asyncpg connection checked out from the worker pool.
    Calling await proxy.close() releases the connection back to the pool
    rather than closing the physical TCP socket.
    """

    def __init__(self, conn: asyncpg.Connection, pool: asyncpg.Pool):
        self._conn = conn
        self._pool = pool
        self._released = False

    async def close(self) -> None:
        if not self._released:
            self._released = True
            try:
                await self._pool.release(self._conn)
            except Exception as exc:
                log.warning("Failed to release connection back to pool: %s", exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def run_worker_task(coro: Any) -> Any:
    """Executes a coroutine on the long-lived worker process event loop,
    falling back to asyncio.run if outside a worker.
    """
    global _worker_loop
    if _worker_loop is not None and not _worker_loop.is_closed():
        return _worker_loop.run_until_complete(coro)
    return asyncio.run(coro)


async def get_worker_conn() -> asyncpg.Connection | PooledConnectionProxy:
    """Acquires a pooled connection if worker pool is initialized on the current loop,
    otherwise lazily initializes the pool, falling back to a standalone connection on error.
    statement_cache_size=0 required for PgBouncer transaction mode (port 6543).
    """
    global _worker_pool, _worker_loop
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    # Lazy pool initialization
    if _worker_pool is None or getattr(_worker_pool, "_closed", False):
        try:
            target_loop = current_loop or get_worker_loop()
            _worker_pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=settings.database_pool_min_size,
                max_size=min(settings.database_pool_max_size, 10),
                timeout=10,
                statement_cache_size=0,  # PgBouncer transaction mode (port 6543)
            )
            _worker_loop = target_loop
        except Exception as exc:
            log.warning("Lazy worker pool init failed, falling back to standalone connection: %s", exc)
            return await asyncpg.connect(settings.database_url, timeout=10, statement_cache_size=0)

    if (
        _worker_pool is not None
        and not getattr(_worker_pool, "_closed", False)
        and (_worker_loop is None or current_loop is None or current_loop is _worker_loop)
    ):
        conn = await _worker_pool.acquire()
        return PooledConnectionProxy(conn, _worker_pool)

    return await asyncpg.connect(settings.database_url, timeout=10, statement_cache_size=0)
