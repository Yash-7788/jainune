"""
Telemetry router — client event sink with in-memory buffer.

POST /v1/telemetry/events
POST /v1/telemetry/interaction-event

Events are validated and appended to an in-process list.
The periodic_maintenance_loop in main.py flushes the buffer to Postgres every 10 min.
Zero Redis for telemetry storage — Upstash 10k/day quota reserved for OTP/rate-limit only.

Rate limiting (sliding_window_rate_limit) still uses Redis for brute-force protection.
Dwell-based vector attraction: queued in-memory, flushed with telemetry batch.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])

# ---------------------------------------------------------------------------
# Allowed event types (validated server-side; clients cannot inject arbitrary types)
# ---------------------------------------------------------------------------

_ALLOWED_EVENTS = {
    "profile_view_start",
    "profile_view_end",
    "photo_swipe",
    "prompt_expand",
    "voice_play_start",
    "voice_play_end",
    "app_foreground",
    "app_background",
    "feed_scroll",
    "daily_compatible_view",
}

# EMA events that should trigger a mild vector attraction (long dwell = implicit positive signal)
_ATTRACTION_EVENTS = {"profile_view_end", "voice_play_end", "prompt_expand"}

# View time threshold (seconds) above which we treat a profile view as implicit like signal
_DWELL_ATTRACTION_THRESHOLD_S = 12

# Maximum reasonable duration for any single telemetry event (1 hour)
_MAX_DURATION_MS = 3_600_000

# Per (actor_id, target_id) cooldown for dwell-based vector attraction (1 hour), in seconds
_DWELL_ATTRACTION_COOLDOWN_S = 3600

# ---------------------------------------------------------------------------
# In-memory telemetry buffer (replaces Redis xadd stream)
# Flushed to Postgres every 10 min by _periodic_maintenance_loop in main.py
# ---------------------------------------------------------------------------

_telemetry_buffer: list[dict] = []
_telemetry_lock = asyncio.Lock()

# In-memory dwell attraction queue (replaces vector:update:queue Redis stream)
_vector_update_queue: list[dict] = []
_vector_lock = asyncio.Lock()

# In-memory cooldown set for dwell attraction (actor_id:target_id, expires via timestamp)
_dwell_cooldowns: dict[str, float] = {}
_cooldown_lock = asyncio.Lock()


async def _check_dwell_cooldown(actor_id: str, target_id: str) -> bool:
    """Returns True if cooldown not active (OK to queue). Sets cooldown on first call."""
    key = f"{actor_id}:{target_id}"
    now = time.monotonic()
    async with _cooldown_lock:
        exp = _dwell_cooldowns.get(key, 0.0)
        if exp > now:
            return False  # still cooling down
        _dwell_cooldowns[key] = now + _DWELL_ATTRACTION_COOLDOWN_S
        # Prune expired keys periodically
        if len(_dwell_cooldowns) > 5000:
            cutoff = now
            expired = [k for k, v in _dwell_cooldowns.items() if v < cutoff]
            for k in expired:
                del _dwell_cooldowns[k]
        return True


async def _async_flush_telemetry(pool) -> None:
    """
    Drain in-memory telemetry buffer + vector update queue to Postgres.
    Called by _periodic_maintenance_loop every 10 min.
    """
    # Swap out buffers atomically
    async with _telemetry_lock:
        if not _telemetry_buffer:
            events_snapshot = []
        else:
            events_snapshot = _telemetry_buffer.copy()
            _telemetry_buffer.clear()

    async with _vector_lock:
        if not _vector_update_queue:
            vector_snapshot = []
        else:
            vector_snapshot = _vector_update_queue.copy()
            _vector_update_queue.clear()

    if not events_snapshot and not vector_snapshot:
        return

    try:
        async with pool.acquire() as conn:
            # ── Flush telemetry events ───────────────────────────────────────
            if events_snapshot:
                rows = []
                all_uids: set[uuid.UUID] = set()
                for e in events_snapshot:
                    a = e.get("actor_id")
                    t = e.get("target_user_id")
                    if a:
                        try:
                            all_uids.add(uuid.UUID(str(a)))
                        except (ValueError, TypeError):
                            pass
                    if t:
                        try:
                            all_uids.add(uuid.UUID(str(t)))
                        except (ValueError, TypeError):
                            pass

                valid_ids: set[uuid.UUID] = set()
                if all_uids:
                    valid_rows = await conn.fetch(
                        "SELECT id FROM users WHERE id = ANY($1::uuid[])",
                        list(all_uids),
                    )
                    valid_ids = {r["id"] for r in valid_rows}

                for e in events_snapshot:
                    try:
                        actor_id_raw = e.get("actor_id")
                        target_id_raw = e.get("target_user_id")
                        event_type = e.get("event_type", "unknown")
                        server_ts = e.get("server_ts")

                        if server_ts and str(server_ts).isdigit():
                            occ_at = datetime.fromtimestamp(int(server_ts) / 1000.0, tz=timezone.utc)
                        else:
                            occ_at = datetime.now(tz=timezone.utc)

                        actor_uuid = uuid.UUID(str(actor_id_raw)) if actor_id_raw else None
                        if actor_uuid and actor_uuid not in valid_ids:
                            continue  # actor no longer in DB

                        target_uuid = None
                        if target_id_raw:
                            try:
                                t_uid = uuid.UUID(str(target_id_raw))
                                target_uuid = t_uid if t_uid in valid_ids else None
                            except (ValueError, TypeError):
                                pass

                        meta: dict = {}
                        for key in ("payload", "duration_ms", "batch_id"):
                            if e.get(key) is not None:
                                val = e[key]
                                meta[key] = json.loads(val) if isinstance(val, str) and key == "payload" else val

                        rows.append((event_type, actor_uuid, target_uuid, occ_at, json.dumps(meta)))
                    except Exception as exc:
                        log.warning("Skipping malformed telemetry event: %s", exc)

                if rows:
                    await conn.executemany(
                        """
                        INSERT INTO telemetry_events
                            (event_type, user_id, target_id, occurred_at, meta)
                        VALUES ($1, $2, $3, $4, $5::jsonb)
                        ON CONFLICT DO NOTHING
                        """,
                        rows,
                    )
                    log.info("_async_flush_telemetry: flushed %d events", len(rows))

            # ── Flush dwell vector updates ───────────────────────────────────
            if vector_snapshot:
                vec_sql = """
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
                """
                for v in vector_snapshot:
                    try:
                        await conn.execute(
                            vec_sql,
                            uuid.UUID(v["actor_id"]),
                            uuid.UUID(v["target_id"]),
                            float(v.get("alpha", 0.05)),
                        )
                    except Exception as exc:
                        log.warning("Vector update failed: %s", exc)
                log.info("_async_flush_telemetry: processed %d vector updates", len(vector_snapshot))

    except Exception as exc:
        log.error("_async_flush_telemetry failed: %s", exc, exc_info=True)
        # Return events to buffer so they aren't lost
        async with _telemetry_lock:
            _telemetry_buffer.extend(events_snapshot)
        async with _vector_lock:
            _vector_update_queue.extend(vector_snapshot)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TelemetryEvent(BaseModel):
    event_type: str
    target_user_id: Optional[uuid.UUID] = None  # profile being viewed/swiped
    batch_id: Optional[str] = None              # ties events to a feed batch
    duration_ms: Optional[int] = None           # for view_end events
    payload: Optional[dict] = None              # freeform metadata (photo index etc.)
    client_ts: Optional[int] = None             # epoch ms from client clock

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in _ALLOWED_EVENTS:
            raise ValueError(f"Unknown event_type '{v}'. Allowed: {_ALLOWED_EVENTS}")
        return v

    @field_validator("duration_ms")
    @classmethod
    def validate_duration(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if v < 0:
                raise ValueError("duration_ms must be non-negative")
            if v > _MAX_DURATION_MS:
                raise ValueError(f"duration_ms cannot exceed {_MAX_DURATION_MS}ms (1 hour)")
        return v


class TelemetryBatch(BaseModel):
    events: List[TelemetryEvent] = Field(..., min_length=1, max_length=100)


class TelemetryResponse(BaseModel):
    accepted: int
    dropped: int = 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/events",
    response_model=TelemetryResponse,
    summary="Ingest batched telemetry events",
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_events(
    batch: TelemetryBatch,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> TelemetryResponse:
    """
    Accepts up to 100 events per call. Events are appended to an in-memory
    buffer flushed to Postgres every 10 min by the maintenance loop.
    Zero Redis writes for event storage — only rate-limit key updated.

    Long-dwell events (profile_view_end with duration >= 12s) also queue a
    mild EMA vector attraction nudge flushed in the same maintenance cycle.
    """
    actor_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    await sliding_window_rate_limit(f"ratelimit:telemetry:batch:{actor_id}", 120, 60, redis)

    server_ts = int(time.time() * 1000)
    seen_dwell_targets: set[uuid.UUID] = set()
    entries: list[dict] = []

    for event in batch.events:
        entry: dict = {
            "actor_id": str(actor_id),
            "event_type": event.event_type,
            "server_ts": str(server_ts),
        }
        if event.target_user_id:
            entry["target_user_id"] = str(event.target_user_id)
        if event.batch_id:
            entry["batch_id"] = event.batch_id
        if event.duration_ms is not None:
            entry["duration_ms"] = str(event.duration_ms)
        if event.client_ts:
            entry["client_ts"] = str(event.client_ts)
        if event.payload:
            entry["payload"] = json.dumps(event.payload, default=str)
        entries.append(entry)

        # ── Queue dwell-based EMA attraction (in-memory, no Redis) ──────────
        if (
            event.event_type == "profile_view_end"
            and event.target_user_id is not None
            and event.duration_ms is not None
            and event.duration_ms >= _DWELL_ATTRACTION_THRESHOLD_S * 1000
            and event.target_user_id not in seen_dwell_targets
        ):
            seen_dwell_targets.add(event.target_user_id)
            if await _check_dwell_cooldown(str(actor_id), str(event.target_user_id)):
                async with _vector_lock:
                    _vector_update_queue.append({
                        "actor_id": str(actor_id),
                        "target_id": str(event.target_user_id),
                        "alpha": "0.05",
                        "reason": "dwell_signal",
                    })

    async with _telemetry_lock:
        _telemetry_buffer.extend(entries)

    return TelemetryResponse(accepted=len(batch.events), dropped=0)


_ALLOWED_INTERACTION_ACTIONS = {"like", "pass", "super_connect", "superlike", "view", "skip"}


class InteractionEventPayload(BaseModel):
    target_user_id: uuid.UUID
    action: str
    total_dwell_ms: int = 0
    photo_dwell_ms: int = 0
    prompt_dwell_ms: int = 0
    voice_played_ratio: float = 0.0
    comment_char_count: int = 0

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in _ALLOWED_INTERACTION_ACTIONS:
            raise ValueError(f"Unknown action '{v}'. Allowed: {_ALLOWED_INTERACTION_ACTIONS}")
        return v


@router.post(
    "/interaction-event",
    response_model=TelemetryResponse,
    summary="Ingest single interaction telemetry event",
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_interaction_event(
    event: InteractionEventPayload,
    current_user: CurrentUser,
    redis: RedisDep,
) -> TelemetryResponse:
    """Accepts single user interaction dwell telemetry event from mobile feed.
    Buffered in-memory; flushed to Postgres in the 10-min maintenance cycle.
    """
    actor_id = str(current_user.get("user_id") or current_user.get("id"))
    await sliding_window_rate_limit(f"ratelimit:telemetry:event:{actor_id}", 60, 60, redis)
    server_ts = int(time.time() * 1000)
    entry = {
        "actor_id": actor_id,
        "event_type": f"interaction_{event.action}",
        "target_user_id": str(event.target_user_id),
        "duration_ms": str(event.total_dwell_ms),
        "server_ts": str(server_ts),
        "payload": json.dumps(event.model_dump(), default=str),
    }
    async with _telemetry_lock:
        _telemetry_buffer.append(entry)
    return TelemetryResponse(accepted=1, dropped=0)
