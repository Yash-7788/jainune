"""
Telemetry router — client event sink with Redis EMA buffer.

POST /v1/telemetry/events

Accepts batched UI events from the mobile client.
Events are validated, enriched with server timestamp, then:
  1. Written to a Redis stream (telemetry:stream) for async processing
  2. Critical view-time events trigger EMA vector nudge via Lua script

The async telemetry_worker drains the stream and writes to DB.
"""
from __future__ import annotations

import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.dependencies import CurrentUser, DBDep, RedisDep

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
        if v is not None and v < 0:
            raise ValueError("duration_ms must be non-negative")
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
    Accepts up to 100 events per call. Events are pushed to Redis stream
    `telemetry:stream` with MAXLEN 50000 (trim on insert).

    Long-dwell events (profile_view_end with duration >= 12s) also trigger
    a mild EMA vector attraction nudge identical to the interactions router.

    Events with unknown target_user_id (not in DB) are silently dropped to
    prevent enumeration attacks.
    """
    actor_id = uuid.UUID(str(current_user["id"]))
    server_ts = int(time.time() * 1000)

    accepted = 0
    dropped = 0

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
            import json
            entry["payload"] = json.dumps(event.payload, default=str)

        try:
            # Push to Redis stream — MAXLEN cap prevents unbounded growth
            await redis.xadd(
                "telemetry:stream",
                entry,
                maxlen=50_000,
                approximate=True,
            )
            accepted += 1
        except Exception:
            dropped += 1
            continue

        # ── EMA attraction for long dwell on profile_view_end ────────────────
        if (
            event.event_type == "profile_view_end"
            and event.target_user_id is not None
            and event.duration_ms is not None
            and event.duration_ms >= _DWELL_ATTRACTION_THRESHOLD_S * 1000
        ):
            # Fire-and-forget vector nudge (same 10% attraction as explicit like)
            try:
                await redis.xadd(
                    "vector:update:queue",
                    {
                        "actor_id": str(actor_id),
                        "target_id": str(event.target_user_id),
                        "direction": "attract",
                        "alpha": "0.05",  # half-strength vs explicit like
                        "reason": "dwell_signal",
                    },
                    maxlen=10_000,
                    approximate=True,
                )
            except Exception:
                pass  # Non-critical

    return TelemetryResponse(accepted=accepted, dropped=dropped)
