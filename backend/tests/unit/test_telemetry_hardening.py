import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import ValidationError

from app.celery_app import celery_app
from app.routers.telemetry import (
    TelemetryBatch,
    TelemetryEvent,
    _DWELL_ATTRACTION_COOLDOWN_S,
    _DWELL_ATTRACTION_THRESHOLD_S,
    _MAX_DURATION_MS,
    ingest_events,
)


class TestTelemetryHardening:
    """Unit tests for FINDING-09 telemetry fixes."""

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
        mock_redis.set = AsyncMock(return_value=True)  # Lock acquired

        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=None)
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

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

        # Verify redis.set called once for that target
        cooldown_key = f"cooldown:dwell_attract:{actor_id}:{target_id}"
        mock_redis.set.assert_called_once_with(cooldown_key, "1", ex=_DWELL_ATTRACTION_COOLDOWN_S, nx=True)

        # Verify pipe.xadd for vector:update:queue called exactly once
        vector_xadd_calls = [
            call for call in mock_pipe.xadd.call_args_list
            if call[0][0] == "vector:update:queue"
        ]
        assert len(vector_xadd_calls) == 1
        assert vector_xadd_calls[0][0][1]["actor_id"] == str(actor_id)
        assert vector_xadd_calls[0][0][1]["target_id"] == str(target_id)
        assert vector_xadd_calls[0][0][1]["direction"] == "attract"
        assert vector_xadd_calls[0][0][1]["alpha"] == "0.05"

    @pytest.mark.asyncio
    async def test_03_cross_batch_dwell_attraction_cooldown(self):
        """When cooldown key exists in Redis, no vector update is queued."""
        actor_id = uuid.uuid4()
        target_id = uuid.uuid4()
        current_user = {"user_id": str(actor_id)}

        mock_redis = AsyncMock()
        # Cooldown active: NX set returns None / False
        mock_redis.set = AsyncMock(return_value=None)

        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=None)
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        batch = TelemetryBatch(events=[
            TelemetryEvent(
                event_type="profile_view_end",
                target_user_id=target_id,
                duration_ms=20_000,
            )
        ])

        resp = await ingest_events(
            batch=batch,
            current_user=current_user,
            db=AsyncMock(),
            redis=mock_redis,
        )

        assert resp.accepted == 1

        # Stream still receives the raw event
        stream_xadd_calls = [
            call for call in mock_pipe.xadd.call_args_list
            if call[0][0] == "telemetry:stream"
        ]
        assert len(stream_xadd_calls) == 1

        # But zero vector updates queued due to cooldown
        vector_xadd_calls = [
            call for call in mock_pipe.xadd.call_args_list
            if call[0][0] == "vector:update:queue"
        ]
        assert len(vector_xadd_calls) == 0

    def test_04_beat_schedule_contains_aggregate_hourly_metrics(self):
        """Verify aggregate_hourly_metrics is wired in Celery beat_schedule."""
        if hasattr(celery_app.conf.update, "call_args") and celery_app.conf.update.call_args:
            kwargs = celery_app.conf.update.call_args[1]
            schedule = kwargs.get("beat_schedule", {})
        else:
            schedule = celery_app.conf.beat_schedule

        assert "aggregate-hourly-metrics-hourly" in schedule
        entry = schedule["aggregate-hourly-metrics-hourly"]
        assert entry["task"] == "app.workers.telemetry_worker.aggregate_hourly_metrics"
