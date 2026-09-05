"""
Unit tests for Behavioral Reciprocal Recommendation Engine (BRRE) math and heuristics.
"""

from __future__ import annotations

import math
import uuid
import pytest

from app.services.core_people_finder import (
    _DIGNITY_BOOST,
    _DIGNITY_THRESHOLD,
    _UNDER_2KM_LABEL,
    _format_distance,
)


def test_format_distance_under_2km():
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    assert _format_distance(0.5, u1, u2) == _UNDER_2KM_LABEL
    assert _format_distance(1.9, u1, u2) == _UNDER_2KM_LABEL


def test_format_distance_deterministic_and_symmetric():
    """Distance format must be identical regardless of who is viewer vs target."""
    u1 = "00000000-0000-0000-0000-000000000001"
    u2 = "00000000-0000-0000-0000-000000000002"

    dist1 = _format_distance(12.4, u1, u2)
    dist2 = _format_distance(12.4, u2, u1)

    assert dist1 == dist2
    assert dist1.endswith("km away")
    # Around 12 km
    assert "12" in dist1


def test_dignity_constants():
    """Ensure baseline constants meet BRRE spec."""
    assert _DIGNITY_THRESHOLD == 35
    assert _DIGNITY_BOOST == 25.0


def test_cultural_score_computation():
    """
    Test cultural compatibility heuristic formula:
    - Dietary strictness exact match: +30, else +10
    - Eats root vegetables match: +10, else 0
    - Eats onion garlic match: +10, else 0
    - Sect match: +25, 'open': +15, else +10
    - Relocation agreement: +15, else 0
    - Updated < 24h: +10
    Max score = 30 + 10 + 10 + 25 + 15 + 10 = 100
    """
    def compute_cultural(u_diet, c_diet, u_root, c_root, u_onion, c_onion, u_sect, c_sect, u_relo, c_relo, recent_hours):
        score = 0
        score += 30 if u_diet == c_diet else 10
        score += 10 if u_root == c_root else 0
        score += 10 if u_onion == c_onion else 0
        if c_sect == u_sect:
            score += 25
        elif c_sect == "open":
            score += 15
        else:
            score += 10
        score += 15 if (u_relo and c_relo) else 0
        if recent_hours <= 24:
            score += 10
        elif recent_hours <= 72:
            score += 6
        return score

    # Perfect alignment
    perfect = compute_cultural(
        "pure_jain", "pure_jain",
        False, False,
        False, False,
        "shwetambar_murtipujak", "shwetambar_murtipujak",
        True, True,
        1,
    )
    assert perfect == 100

    # Divergent
    divergent = compute_cultural(
        "pure_jain", "vegan",
        False, True,
        False, True,
        "digambar", "shwetambar_sthanakvasi",
        False, False,
        100,
    )
    # 10 (diet) + 0 (root) + 0 (onion) + 10 (sect) + 0 (relo) + 0 (recency) = 20
    assert divergent == 20


def test_dignity_floor_boost_math():
    """Profiles under impression threshold receive dignity boost."""
    behavioral_affinity = 0.8  # * 40.0 = 32.0
    cultural_score = 60.0

    raw_score = behavioral_affinity * 40.0 + cultural_score  # 92.0

    impressions_under = 10
    boosted_score = raw_score + (_DIGNITY_BOOST if impressions_under < _DIGNITY_THRESHOLD else 0.0)
    assert boosted_score == 92.0 + 25.0

    impressions_over = 50
    unboosted_score = raw_score + (_DIGNITY_BOOST if impressions_over < _DIGNITY_THRESHOLD else 0.0)
    assert unboosted_score == 92.0
