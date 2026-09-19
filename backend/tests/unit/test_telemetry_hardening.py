"""
Telemetry hardening tests — updated for OPTIMIZE.md in-memory buffer implementation.

OPTIMIZE.md §4: Zero Redis for telemetry. Events buffered in-process,
flushed to Postgres via _periodic_maintenance_loop every 10 min.
Celery beat + Redis stream approach replaced.
"""
import uuid
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import ValidationError

from app.routers.telemetry import (
    TelemetryBatch,
    TelemetryEvent,
    _DWELL_ATTRACTION_COOLDOWN_S,
    _DWELL_ATTRACTION_THRESHOLD_S,
    _MAX_DURATION_MS,
    _telemetry_buffer,
    _vector_update_queue,
    _dwell_cooldowns,
    ingest_events,
)


class TestTelemetryHardening:
    """Unit tests for telemetry in-memory buffer implementation (OPTIMIZE.md §4)."""

    def test_01_duration_ms_bounds_validation(self):
        """Rejects negative and excessive duration_ms, allows valid durations."""
        # Negative rejected
        with pytest.raises(ValidationError) as exc:
            TelemetryEvent(event_type="profile_view_end", duration_ms=-1)
        assert "duration_ms must be non-negative" in str(exc.value)

        # > 1 hour rejected
        with pytest.raises(ValidationError) as exc:
            TelemetryEvent(event_type="profile_view_end", duration_ms=_MAX_DURATION_MS + 1)
        assert "duration_ms cannot exceed" in str(exc.value)

        # Exact upper bound allowed
        e1 = TelemetryEvent(event_type="profile_view_end", duration_ms=_MAX_DURATION_MS)
        assert e1.duration_ms == 3_600_000

        # Normal value allowed
        e2 = TelemetryEvent(event_type="profile_view_end", duration_ms=12_000)
        assert e2.duration_ms == 12_000

        # None allowed
        e3 = TelemetryEvent(event_type="profile_view_start", duration_ms=None)
        assert e3.duration_ms is None

    @pytest.mark.asyncio
    async def test_02_in_batch_dwell_attraction_deduplication(self):
        """Multiple dwell events for same target in one batch produce at most one vector update."""
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        current_user = {"user_id": str(actor_id)}

        mock_redis = AsyncMock()

        # Clear module-level state to isolate test
        _telemetry_buffer.clear()
        _vector_update_queue.clear()
        _dwell_cooldowns.clear()

        # 5 duplicate dwell events for same target in one batch
        events = [
            TelemetryEvent(
                event_type="profile_view_end",
                target_user_id=target_id,
                duration_ms=15_000,
            )
            for _ in range(5)
        ]
        batch = TelemetryBatch(events=events)

        resp = await ingest_events(
            batch=batch,
            current_user=current_user,
            db=AsyncMock(),
            redis=mock_redis,
        )

        assert resp.accepted == 5
        assert resp.dropped == 0

        # All 5 events buffered in-memory (no Redis xadd)
        assert len(_telemetry_buffer) == 5

        # Deduplication: at most 1 vector update queued despite 5 dwell events
        actor_target_updates = [
            v for v in _vector_update_queue
            if v["actor_id"] == str(actor_id) and v["target_id"] == str(target_id)
        ]
        assert len(actor_target_updates) == 1
        assert actor_target_updates[0]["alpha"] == "0.05"

    @pytest.mark.asyncio
    async def test_03_cross_batch_dwell_attraction_cooldown(self):
        """When cooldown is active in-memory, no second vector update is queued."""
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        current_user = {"user_id": str(actor_id)}

        mock_redis = AsyncMock()

        # Clear state
        _telemetry_buffer.clear()
        _vector_update_queue.clear()
        _dwell_cooldowns.clear()

        dwell_event = TelemetryEvent(
            event_type="profile_view_end",
            target_user_id=target_id,
            duration_ms=20_000,
        )
        batch = TelemetryBatch(events=[dwell_event])

        # First call — cooldown not yet active
        resp1 = await ingest_events(
            batch=batch,
            current_user=current_user,
            db=AsyncMock(),
            redis=mock_redis,
        )
        assert resp1.accepted == 1
        assert len(_vector_update_queue) == 1  # queued

        # Second call — cooldown now active, no duplicate
        resp2 = await ingest_events(
            batch=batch,
            current_user=current_user,
            db=AsyncMock(),
            redis=mock_redis,
        )
        assert resp2.accepted == 1
        # Still only 1 vector update despite second batch
        actor_target_updates = [
            v for v in _vector_update_queue
            if v["actor_id"] == str(actor_id) and v["target_id"] == str(target_id)
        ]
        assert len(actor_target_updates) == 1

    def test_04_telemetry_flush_is_wired_in_maintenance_loop(self):
        """Verify _async_flush_telemetry is called from _periodic_maintenance_loop in main.py."""
        import inspect
        import app.main as main_module
        src = inspect.getsource(main_module._periodic_maintenance_loop)
        assert "_async_flush_telemetry" in src, (
            "_async_flush_telemetry must be called in _periodic_maintenance_loop"
        )
        assert "from app.routers.telemetry import _async_flush_telemetry" in src
