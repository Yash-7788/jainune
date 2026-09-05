"""
Telemetry worker — flush in-memory event buffer to persistent storage.

The telemetry router batches events in Redis lists to avoid DB write storms.
This worker drains those lists every minute and bulk-upserts to Postgres.

Redis key convention:
  telemetry:buffer          → LPUSH'd JSON events (list, max 10k items)
  telemetry:hourly:{metric}:{YYYY-MM-DD-HH}  → counter (for aggregate stats)

Tasks:
  flush_telemetry_buffer()   every 1 min (beat)
    → LRANGE + DEL buffer → bulk INSERT INTO telemetry_events
  aggregate_hourly_metrics() every 1 hour (beat — piggybacks on reap_stale_matches crontab)
    → reads telemetry_events for last hour, writes aggregated rows to telemetry_hourly

Telemetry event shape (JSON):
  {
    "event_type": "profile_view" | "like" | "pass" | "app_open" | ...,
    "user_id": "<uuid>",
    "target_id": "<uuid|null>",
    "ts": "<ISO8601 UTC>",
    "meta": { ... }
  }
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import asyncpg
import redis.asyncio as aioredis

from app.celery_app import celery_app
from app.core.config import settings

log = logging.getLogger(__name__)

BUFFER_KEY = "telemetry:buffer"
DRAIN_BATCH = 2000   # max events drained per invocation


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(settings.database_url)


async def _get_redis() -> aioredis.Redis:
    return await aioredis.from_url(settings.redis_url, decode_responses=True)


# ---------------------------------------------------------------------------
# Task: flush buffer
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.telemetry_worker.flush_telemetry_buffer")
def flush_telemetry_buffer() -> None:
    """Drain the Redis telemetry buffer and bulk-insert into Postgres."""
    asyncio.run(_flush_async())


async def _flush_async() -> None:
    redis = await _get_redis()
    conn = await _get_conn()

    try:
        # Atomically pop up to DRAIN_BATCH items
        raw_events: list[str] = await redis.lrange(BUFFER_KEY, 0, DRAIN_BATCH - 1)
        if not raw_events:
            return

        # Remove what we just read
        await redis.ltrim(BUFFER_KEY, len(raw_events), -1)

        events = []
        for raw in raw_events:
            try:
                e = json.loads(raw)
                events.append(e)
            except json.JSONDecodeError:
                log.warning("Invalid telemetry event JSON: %s", raw[:100])

        if not events:
            return

        # Build INSERT rows — coerce types
        rows = []
        for e in events:
            try:
                rows.append((
                    e.get("event_type", "unknown"),
                    e.get("user_id"),
                    e.get("target_id"),
                    e.get("ts") or datetime.now(tz=timezone.utc).isoformat(),
                    json.dumps(e.get("meta") or {}),
                ))
            except Exception as exc:
                log.warning("Skipping malformed telemetry event: %s", exc)

        await conn.executemany(
            """
            INSERT INTO telemetry_events
                (event_type, user_id, target_id, occurred_at, meta)
            VALUES ($1, $2::uuid, $3::uuid, $4::timestamptz, $5::jsonb)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        log.info("flush_telemetry_buffer: flushed %d events", len(rows))
    except Exception as exc:
        log.error("flush_telemetry_buffer failed: %s", exc, exc_info=True)
    finally:
        await conn.close()
        await redis.aclose()


# ---------------------------------------------------------------------------
# Task: aggregate hourly metrics
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.telemetry_worker.aggregate_hourly_metrics")
def aggregate_hourly_metrics() -> None:
    """
    Aggregate telemetry_events from the last hour into telemetry_hourly.
    Called by ephemeral_reaper's hourly crontab to avoid a separate beat entry.
    """
    asyncio.run(_aggregate_async())


async def _aggregate_async() -> None:
    conn = await _get_conn()
    try:
        await conn.execute(
            """
            INSERT INTO telemetry_hourly
                (hour_bucket, event_type, count)
            SELECT
                date_trunc('hour', occurred_at) AS hour_bucket,
                event_type,
                COUNT(*) AS count
            FROM telemetry_events
            WHERE occurred_at >= NOW() - INTERVAL '2 hours'
              AND occurred_at < date_trunc('hour', NOW())
            GROUP BY hour_bucket, event_type
            ON CONFLICT (hour_bucket, event_type)
            DO UPDATE SET count = EXCLUDED.count
            """
        )
        log.info("aggregate_hourly_metrics: done")
    except Exception as exc:
        log.error("aggregate_hourly_metrics failed: %s", exc, exc_info=True)
    finally:
        await conn.close()
