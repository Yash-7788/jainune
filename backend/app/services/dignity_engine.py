"""
Dignity engine — user reporting, badge scoring, and trust-score computation.

The dignity engine enforces Jainune's core value: respectful, dignified interactions.

Components:
  1. Report ingestion        — accepts user-filed reports with reason codes
  2. Auto-action thresholds — shadow-ban / suspend when report count breaches limit
  3. Badge scoring           — awarded by the community (positive reinforcement)
  4. Trust score             — composite score influencing feed rank boost

Trust Score Formula (0–100):
  base = 50
  + photo_verified      → +10
  + voice_snapshot      → +5
  + report_penalty      → −10 per confirmed report (capped at −40)
  + badge_bonus         → +3 per badge (capped at +15)
  + tenure_bonus        → +1 per 30 days, capped at +10
  = clamped to [0, 100]
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORT_REASONS = frozenset(
    {
        "harassment",
        "fake_profile",
        "inappropriate_content",
        "hate_speech",
        "spam",
        "underage",
        "scam",
        "other",
    }
)

# After this many confirmed reports, auto-suspend
AUTO_SUSPEND_THRESHOLD = 5
# After this many, permanently ban
AUTO_BAN_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Report ingestion
# ---------------------------------------------------------------------------


async def file_report(
    reporter_id: UUID,
    reported_id: UUID,
    reason: str,
    detail: str | None,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """
    Insert a report record. Returns the report id.
    Rate-limited at the router level (max 5 reports per 24h per reporter).
    """
    if reason not in REPORT_REASONS:
        raise ValueError(f"Invalid reason. Must be one of: {sorted(REPORT_REASONS)}")

    if reporter_id == reported_id:
        raise ValueError("Cannot report yourself")

    async with pool.acquire() as conn:
        # Check for duplicate report in last 7 days
        duplicate = await conn.fetchval(
            """
            SELECT id FROM reports
            WHERE reporter_id = $1 AND reported_id = $2
              AND created_at > NOW() - INTERVAL '7 days'
            """,
            reporter_id,
            reported_id,
        )
        if duplicate:
            return {"id": duplicate, "duplicate": True}

        report_id = await conn.fetchval(
            """
            INSERT INTO reports (reporter_id, reported_id, reason, detail)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            reporter_id,
            reported_id,
            reason,
            detail,
        )

        # Evaluate auto-action thresholds
        await _evaluate_auto_action(reported_id, conn)

    return {"id": report_id, "duplicate": False}


async def _evaluate_auto_action(
    user_id: UUID,
    conn: asyncpg.Connection,
) -> None:
    """Check report counts and trigger auto-suspend/ban if thresholds hit."""
    confirmed_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM reports
        WHERE reported_id = $1 AND resolved = FALSE
        """,
        user_id,
    )

    if confirmed_count >= AUTO_BAN_THRESHOLD:
        new_status = "banned"
    elif confirmed_count >= AUTO_SUSPEND_THRESHOLD:
        new_status = "suspended"
    else:
        return

    current_status = await conn.fetchval(
        "SELECT account_status FROM users WHERE id = $1",
        user_id,
    )

    if current_status in ("banned", "deleted"):
        return  # already actioned

    await conn.execute(
        """
        UPDATE users
           SET account_status = $1, updated_at = NOW()
         WHERE id = $2
        """,
        new_status,
        user_id,
    )
    log.warning(
        "Auto-action: user %s set to %s (report_count=%d)",
        user_id,
        new_status,
        confirmed_count,
    )


# ---------------------------------------------------------------------------
# Badge scoring
# ---------------------------------------------------------------------------


VALID_BADGES = frozenset(
    {
        "punctual",
        "respects_diet",
        "real_photos",
        "great_conversation",
        "courteous",
    }
)


async def award_badge(
    from_user_id: UUID,
    to_user_id: UUID,
    badge: str,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """
    Award a dignity badge after a chat concludes (match closed or 7-day window).
    One badge per pair per badge type.
    """
    if badge not in VALID_BADGES:
        raise ValueError(f"Invalid badge. Must be one of: {sorted(VALID_BADGES)}")

    if from_user_id == to_user_id:
        raise ValueError("Cannot badge yourself")

    async with pool.acquire() as conn:
        # Ensure users had a match (were connected)
        connected = await conn.fetchval(
            """
            SELECT id FROM matches
            WHERE ((user_a = $1 AND user_b = $2)
                OR (user_a = $2 AND user_b = $1)
                OR (user_a_id = $1 AND user_b_id = $2)
                OR (user_a_id = $2 AND user_b_id = $1))
              AND status IN ('active', 'matched', 'closed')
            """,
            from_user_id,
            to_user_id,
        )
        if not connected:
            raise ValueError("Can only badge users you were matched with")

        existing = await conn.fetchval(
            """
            SELECT id FROM dignity_badges
            WHERE from_user_id = $1 AND to_user_id = $2 AND badge = $3
            """,
            from_user_id,
            to_user_id,
            badge,
        )
        if existing:
            return {"id": existing, "duplicate": True}

        badge_id = await conn.fetchval(
            """
            INSERT INTO dignity_badges (from_user_id, to_user_id, badge)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            from_user_id,
            to_user_id,
            badge,
        )

        # Recompute recipient's trust score
        await recompute_trust_score(to_user_id, conn)

    return {"id": badge_id, "duplicate": False}


# ---------------------------------------------------------------------------
# Trust score computation
# ---------------------------------------------------------------------------


async def recompute_trust_score(
    user_id: UUID,
    conn: asyncpg.Connection,
) -> int:
    """
    Recompute and persist trust_score for user_id. Returns new score.
    Called after: report filed, badge awarded, photo verified, voice snapshot uploaded.
    """
    row = await conn.fetchrow(
        """
        SELECT
            u.is_photo_verified,
            u.created_at,
            (SELECT COUNT(*) FROM media
             WHERE user_id = u.id AND media_type = 'voice' AND status = 'approved'
            ) AS has_voice,
            (SELECT COUNT(*) FROM reports
             WHERE reported_id = u.id AND resolved = FALSE
            ) AS pending_reports,
            (SELECT COUNT(*) FROM dignity_badges
             WHERE to_user_id = u.id
            ) AS badge_count
        FROM users u
        WHERE u.id = $1
        """,
        user_id,
    )

    if row is None:
        return 50

    score = 50

    if row["is_photo_verified"]:
        score += 10
    if row["has_voice"] > 0:
        score += 5

    # Penalty: −10 per confirmed report, capped at −40
    report_penalty = min(int(row["pending_reports"]) * 10, 40)
    score -= report_penalty

    # Badge bonus: +3 per badge, capped at +15
    badge_bonus = min(int(row["badge_count"]) * 3, 15)
    score += badge_bonus

    # Tenure bonus: +1 per 30 days, capped at +10
    if row["created_at"]:
        days = (datetime.now(tz=timezone.utc) - row["created_at"]).days
        tenure_bonus = min(days // 30, 10)
        score += tenure_bonus

    score = max(0, min(100, score))

    await conn.execute(
        "UPDATE users SET trust_score = $1, updated_at = NOW() WHERE id = $2",
        score,
        user_id,
    )

    return score
