"""
Native tracked background task supervisor for FastAPI.
Replaces Celery with in-process asyncio tasks, exponential backoff retries,
strong garbage-collection retention, and graceful shutdown awaiting.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, Coroutine, Set, Union

log = logging.getLogger(__name__)

# Strong reference set preventing Python GC from prematurely dropping in-flight tasks
_background_tasks: Set[asyncio.Task] = set()


def enqueue_task(
    target: Union[Callable[..., Coroutine[Any, Any, Any]], Coroutine[Any, Any, Any]],
    *args: Any,
    retries: int = 3,
    name: str = "background_task",
    **kwargs: Any,
) -> asyncio.Task:
    """
    Enqueues an async callable or coroutine into the background task supervisor.
    - If target is a coroutine function/callable, each retry creates a fresh coroutine.
    - Protected by strong reference against garbage collection.
    - Automatic exponential backoff retry on transient errors.
    - Cleanly drains during application shutdown.
    """
    async def _runner() -> None:
        for attempt in range(1, retries + 1):
            try:
                if callable(target):
                    res = target(*args, **kwargs)
                    if inspect.isawaitable(res):
                        await res
                else:
                    if attempt > 1:
                        log.warning("Raw coroutine %s cannot be re-invoked on retry. Pass callable instead.", name)
                        return
                    await target
                return
            except asyncio.CancelledError:
                log.debug("Background task %s was cancelled.", name)
                raise
            except Exception as exc:
                if attempt < retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    log.warning(
                        "Background task %s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        name, attempt, retries, exc, backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    log.error(
                        "Background task %s failed permanently after %d attempts: %s",
                        name, retries, exc, exc_info=True,
                    )

    task = asyncio.create_task(_runner(), name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def await_background_tasks(timeout: float = 5.0) -> None:
    """Awaits all pending background tasks during application shutdown."""
    if not _background_tasks:
        return

    count = len(_background_tasks)
    log.info("Draining %d in-flight background task(s) on shutdown...", count)
    try:
        await asyncio.wait_for(
            asyncio.gather(*list(_background_tasks), return_exceptions=True),
            timeout=timeout,
        )
        log.info("All background tasks finished cleanly.")
    except asyncio.TimeoutError:
        log.warning("Timed out awaiting %d background task(s) during shutdown.", len(_background_tasks))
