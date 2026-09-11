"""
Shared asyncpg connection pool and event loop manager for Celery worker processes.
Reuses a single event loop and connection pool per worker process instead of
creating and destroying them on every individual task invocation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg
try:
    from celery.signals import worker_process_init, worker_process_shutdown
except Exception:
    class _DummySignal:
        @staticmethod
        def connect(fn: Any) -> Any:
            return fn
    worker_process_init = _DummySignal()  # type: ignore
    worker_process_shutdown = _DummySignal()  # type: ignore

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
    falling back to asyncio.run if outside a Celery worker.
    """
    global _worker_loop
    if _worker_loop is not None and not _worker_loop.is_closed():
        return _worker_loop.run_until_complete(coro)
    return asyncio.run(coro)


async def get_worker_conn() -> asyncpg.Connection | PooledConnectionProxy:
    """Acquires a pooled connection if worker pool is initialized on the current loop,
    otherwise falls back to a standalone connection.
    """
    global _worker_pool, _worker_loop
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if (
        _worker_pool is not None
        and _worker_loop is not None
        and not _worker_loop.is_closed()
        and (current_loop is None or current_loop is _worker_loop)
    ):
        conn = await _worker_pool.acquire()
        return PooledConnectionProxy(conn, _worker_pool)

    return await asyncpg.connect(settings.database_url, timeout=10)


@worker_process_init.connect
def on_worker_process_init(**kwargs: Any) -> None:
    """Initialize persistent event loop and connection pool per Celery worker child process."""
    global _worker_loop, _worker_pool
    try:
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
        _worker_pool = _worker_loop.run_until_complete(
            asyncpg.create_pool(
                settings.database_url,
                min_size=settings.database_pool_min_size,
                max_size=min(settings.database_pool_max_size, 10),
                timeout=10,
            )
        )
        log.info("Initialized Celery worker connection pool (min=%d, max=%d)", 
                 settings.database_pool_min_size, min(settings.database_pool_max_size, 10))
    except Exception as exc:
        log.warning("Failed to initialize worker connection pool; falling back to per-task connections: %s", exc)


@worker_process_shutdown.connect
def on_worker_process_shutdown(**kwargs: Any) -> None:
    """Gracefully close connection pool and event loop on worker child process exit."""
    global _worker_loop, _worker_pool
    if _worker_pool is not None and _worker_loop is not None and not _worker_loop.is_closed():
        try:
            _worker_loop.run_until_complete(_worker_pool.close())
            log.info("Closed Celery worker connection pool")
        except Exception as exc:
            log.warning("Error closing worker pool on shutdown: %s", exc)
        _worker_pool = None

    if _worker_loop is not None and not _worker_loop.is_closed():
        try:
            _worker_loop.close()
        except Exception:
            pass
        _worker_loop = None
