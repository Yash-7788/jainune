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
import uuid
from datetime import datetime, timezone

import asyncpg
import redis.asyncio as aioredis

from app.celery_app import celery_app
from app.core.config import settings

log = logging.getLogger(__name__)

STREAM_KEY = "telemetry:stream"
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
    """Drain the Redis telemetry stream and buffer and bulk-insert into Postgres."""
    asyncio.run(_flush_async())


async def _flush_async() -> None:
    redis = await _get_redis()
    conn = await _get_conn()

    try:
        events = []

        # 1. Drain from Redis Stream (telemetry:stream written by POST /v1/telemetry/events)
        stream_entries = await redis.xrange(STREAM_KEY, count=DRAIN_BATCH)
        if stream_entries:
            del_ids = []
            for stream_id, entry in stream_entries:
                del_ids.append(stream_id)
                events.append(entry)
            await redis.xdel(STREAM_KEY, *del_ids)

        # 2. Drain legacy list buffer if any items present
        remaining_budget = DRAIN_BATCH - len(events)
        if remaining_budget > 0:
            raw_events: list[str] = await redis.lrange(BUFFER_KEY, 0, remaining_budget - 1)
            if raw_events:
                await redis.ltrim(BUFFER_KEY, len(raw_events), -1)
                for raw in raw_events:
                    try:
                        events.append(json.loads(raw))
                    except Exception:
                        pass

        if not events:
            return

        # Build INSERT rows — coerce types
        rows = []
        for e in events:
            try:
                actor_id = e.get("actor_id") or e.get("user_id")
                target_id = e.get("target_user_id") or e.get("target_id")
                event_type = e.get("event_type", "unknown")
                server_ts = e.get("server_ts") or e.get("ts") or e.get("client_ts")

                if server_ts and str(server_ts).isdigit():
                    occ_at = datetime.fromtimestamp(int(server_ts) / 1000.0, tz=timezone.utc)
                else:
                    occ_at = datetime.now(tz=timezone.utc)

                meta_dict = {}
                if e.get("payload"):
                    payload_val = e["payload"]
                    meta_dict["payload"] = json.loads(payload_val) if isinstance(payload_val, str) else payload_val
                if e.get("duration_ms"):
                    meta_dict["duration_ms"] = e["duration_ms"]
                if e.get("batch_id"):
                    meta_dict["batch_id"] = e["batch_id"]
                if e.get("meta"):
                    meta_dict["meta"] = e["meta"]

                # Parse UUIDs safely
                actor_uuid = None
                if actor_id:
                    try:
                        actor_uuid = uuid.UUID(str(actor_id))
                    except (ValueError, TypeError):
                        pass

                target_uuid = None
                if target_id:
                    try:
                        target_uuid = uuid.UUID(str(target_id))
                    except (ValueError, TypeError):
                        pass

                rows.append((
                    event_type,
                    actor_uuid,
                    target_uuid,
                    occ_at,
                    json.dumps(meta_dict),
                ))
            except Exception as exc:
                log.warning("Skipping malformed telemetry event: %s", exc)

        if rows:
            # Validate user existence to prevent ForeignKeyViolationError dropping the batch
            all_uids = {r[1] for r in rows if r[1]} | {r[2] for r in rows if r[2]}
            if all_uids:
                valid_uids_rows = await conn.fetch(
                    "SELECT id FROM users WHERE id = ANY($1::uuid[])",
                    list(all_uids),
                )
                valid_ids = {r["id"] for r in valid_uids_rows}
            else:
                valid_ids = set()

            sanitized_rows = []
            for ev_type, a_uuid, t_uuid, occ, meta_str in rows:
                if a_uuid and a_uuid not in valid_ids:
                    continue  # Actor user no longer exists in DB
                t_final = t_uuid if (t_uuid and t_uuid in valid_ids) else None
                sanitized_rows.append((ev_type, a_uuid, t_final, occ, meta_str))

            if sanitized_rows:
                await conn.executemany(
                    """
                    INSERT INTO telemetry_events
                        (event_type, user_id, target_id, occurred_at, meta)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT DO NOTHING
                    """,
                    sanitized_rows,
                )
                log.info("flush_telemetry_buffer: flushed %d events", len(sanitized_rows))

        # 3. Drain and process vector:update:queue stream (BUG-032)
        vector_entries = await redis.xrange("vector:update:queue", count=1000)
        if vector_entries:
            v_del_ids = []
            for stream_id, v_entry in vector_entries:
                v_del_ids.append(stream_id)
                try:
                    actor_uid = uuid.UUID(v_entry.get("actor_id"))
                    target_uid = uuid.UUID(v_entry.get("target_id"))
                    alpha = float(v_entry.get("alpha", 0.05))
                    await conn.execute(
                        """
                        UPDATE user_behavior_vectors uv
                        SET revealed_preference_vector = (
                            uv.revealed_preference_vector + (
                                t.revealed_preference_vector - uv.revealed_preference_vector
                            ) * $3
                        )
                        FROM user_behavior_vectors t
                        WHERE uv.user_id = $1
                          AND t.user_id  = $2
                          AND t.revealed_preference_vector IS NOT NULL
                          AND uv.revealed_preference_vector IS NOT NULL
                        """,
                        actor_uid,
                        target_uid,
                        alpha,
                    )
                except Exception as v_exc:
                    log.warning("Failed processing vector update %s: %s", stream_id, v_exc)
            if v_del_ids:
                await redis.xdel("vector:update:queue", *v_del_ids)
                log.info("flush_telemetry_buffer: processed %d vector updates", len(v_del_ids))
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
