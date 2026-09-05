"""
Unit tests for Dignity Engine: report filing, badge scoring, and trust score computation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.dignity_engine import (
    AUTO_BAN_THRESHOLD,
    AUTO_SUSPEND_THRESHOLD,
    REPORT_REASONS,
    VALID_BADGES,
    _evaluate_auto_action,
    award_badge,
    file_report,
    recompute_trust_score,
)


@pytest.mark.asyncio
async def test_file_report_invalid_reason():
    pool = MagicMock()
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValueError, match="Invalid reason"):
        await file_report(u1, u2, "non_existent_reason", None, pool)


@pytest.mark.asyncio
async def test_file_report_self_report():
    pool = MagicMock()
    u1 = uuid.uuid4()
    with pytest.raises(ValueError, match="Cannot report yourself"):
        await file_report(u1, u1, "harassment", None, pool)


@pytest.mark.asyncio
async def test_file_report_duplicate():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    report_id = uuid.uuid4()
    conn.fetchval.return_value = report_id  # Duplicate exists

    u1, u2 = uuid.uuid4(), uuid.uuid4()
    result = await file_report(u1, u2, "spam", "detail", pool)

    assert result["duplicate"] is True
    assert result["id"] == report_id


@pytest.mark.asyncio
async def test_file_report_success():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    new_report_id = uuid.uuid4()
    # 1st fetchval: duplicate check -> None
    # 2nd fetchval: INSERT RETURNING id -> new_report_id
    # 3rd fetchval: COUNT(*) in _evaluate_auto_action -> 1
    conn.fetchval.side_effect = [None, new_report_id, 1]

    u1, u2 = uuid.uuid4(), uuid.uuid4()
    result = await file_report(u1, u2, "harassment", "bad behavior", pool)

    assert result["duplicate"] is False
    assert result["id"] == new_report_id


@pytest.mark.asyncio
async def test_auto_action_suspend_and_ban():
    conn = AsyncMock()
    u1 = uuid.uuid4()

    # Case 1: 5 reports -> suspend
    conn.fetchval.side_effect = [AUTO_SUSPEND_THRESHOLD, "active"]
    await _evaluate_auto_action(u1, conn)
    conn.execute.assert_called_once()
    assert "suspended" in conn.execute.call_args[0][1]

    # Case 2: 10 reports -> ban
    conn.reset_mock()
    conn.fetchval.side_effect = [AUTO_BAN_THRESHOLD, "active"]
    await _evaluate_auto_action(u1, conn)
    conn.execute.assert_called_once()
    assert "banned" in conn.execute.call_args[0][1]

    # Case 3: Already banned -> no update
    conn.reset_mock()
    conn.fetchval.side_effect = [AUTO_BAN_THRESHOLD, "banned"]
    await _evaluate_auto_action(u1, conn)
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_award_badge_validation():
    pool = MagicMock()
    u1, u2 = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(ValueError, match="Invalid badge"):
        await award_badge(u1, u2, "super_friendly", pool)

    with pytest.raises(ValueError, match="Cannot badge yourself"):
        await award_badge(u1, u1, "punctual", pool)


@pytest.mark.asyncio
async def test_award_badge_requires_match():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    # No match found
    conn.fetchval.return_value = None

    u1, u2 = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValueError, match="Can only badge users you were matched with"):
        await award_badge(u1, u2, "respects_diet", pool)


@pytest.mark.asyncio
async def test_award_badge_duplicate():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    match_id = uuid.uuid4()
    badge_id = uuid.uuid4()
    conn.fetchval.side_effect = [match_id, badge_id]

    u1, u2 = uuid.uuid4(), uuid.uuid4()
    result = await award_badge(u1, u2, "respects_diet", pool)

    assert result["duplicate"] is True
    assert result["id"] == badge_id


@pytest.mark.asyncio
async def test_recompute_trust_score():
    conn = AsyncMock()
    u1 = uuid.uuid4()

    # User with photo verified (+10), voice approved (+5), 1 report (-10), 2 badges (+6), 60 days tenure (+2)
    # Total: 50 + 10 + 5 - 10 + 6 + 2 = 63
    now = datetime.now(tz=timezone.utc)
    created_at = now - timedelta(days=65)
    conn.fetchrow.return_value = {
        "is_photo_verified": True,
        "created_at": created_at,
        "has_voice": 1,
        "pending_reports": 1,
        "badge_count": 2,
    }

    score = await recompute_trust_score(u1, conn)
    assert score == 63
    conn.execute.assert_called_once()
    assert conn.execute.call_args[0][1] == 63


@pytest.mark.asyncio
async def test_trust_score_clamping():
    conn = AsyncMock()
    u1 = uuid.uuid4()

    # Maximum penalties clamp to 0
    conn.fetchrow.return_value = {
        "is_photo_verified": False,
        "created_at": None,
        "has_voice": 0,
        "pending_reports": 10,  # -40 cap
        "badge_count": 0,
    }
    # 50 - 40 = 10
    score = await recompute_trust_score(u1, conn)
    assert score == 10
