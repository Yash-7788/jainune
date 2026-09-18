"""
DEPRECATED: Celery application factory and beat schedule.

ARCHITECTURAL UPDATE:
Celery workers and beat daemons have been eliminated in favor of native FastAPI
in-process background tasks (`app.core.background_tasks.enqueue_task`),
10-minute in-process maintenance loop (`app.main._periodic_maintenance_loop`),
and Supabase PostgreSQL pg_cron scheduled jobs.

This module is retained strictly for backward compatibility with legacy imports.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger(__name__)


class DeprecatedCeleryStub:
    """Stub replacement for Celery app to prevent import errors and unbacked task queues."""

    def __init__(self) -> None:
        self.conf = {}

    def task(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            # Attach .delay method directly for backward compatibility
            def _delay(*fn_args: Any, **fn_kwargs: Any) -> Any:
                from app.core.background_tasks import enqueue_task
                import inspect
                if inspect.iscoroutinefunction(fn):
                    return enqueue_task(fn(*fn_args, **fn_kwargs), name=fn.__name__)
                else:
                    return fn(*fn_args, **fn_kwargs)

            setattr(fn, "delay", _delay)
            return fn
        return decorator


celery_app = DeprecatedCeleryStub()
