"""
Unit tests for Gale-Shapley Stable Marriage engine.
"""

from __future__ import annotations

import math
import pytest
from app.services.stable_marriage import StableMarriageEngine


@pytest.fixture
def engine():
    return StableMarriageEngine()


def test_empty_users(engine):
    """Less than 2 users returns empty proposals."""
    assert engine.compute([], {}) == []
    assert engine.compute([{"id": "u1", "gender": "man"}], {}) == []


def test_standard_stable_matching(engine):
    """
    Classic matching test with 2 proposers and 2 receivers.
    Proposers: p1, p2
    Receivers: r1, r2
    """
    users = [
        {"id": "p1", "gender": "man", "show_me": "women"},
        {"id": "p2", "gender": "man", "show_me": "women"},
        {"id": "r1", "gender": "woman", "show_me": "men"},
        {"id": "r2", "gender": "woman", "show_me": "men"},
    ]
    # p1 prefers r1 > r2
    # p2 prefers r1 > r2
    # r1 prefers p1 > p2
    # r2 prefers p2 > p1
    feed_queues = {
        "p1": ["r1", "r2"],
        "p2": ["r1", "r2"],
        "r1": ["p1", "p2"],
        "r2": ["p2", "p1"],
    }

    proposals = engine.compute(users, feed_queues)
    assert len(proposals) == 2

    # Map pairings
    pairs = set()
    for prop in proposals:
        pairs.add(frozenset({prop["user_a"], prop["user_b"]}))

    assert frozenset({"p1", "r1"}) in pairs
    assert frozenset({"p2", "r2"}) in pairs


def test_proposals_score_calculation(engine):
    """
    Verify mutual score calculation:
    score = sqrt((1 - r_rank/50) * (1 - p_rank/50))
    When both rank each other #0 (1st choice), score is 1.0.
    """
    users = [
        {"id": "u1", "gender": "man"},
        {"id": "u2", "gender": "woman"},
    ]
    feed_queues = {
        "u1": ["u2"],
        "u2": ["u1"],
    }
    proposals = engine.compute(users, feed_queues)
    assert len(proposals) == 1
    assert proposals[0]["score"] == 1.0


def test_unmatched_when_preferences_empty(engine):
    """If user preference lists are empty, no proposals formed."""
    users = [
        {"id": "u1", "gender": "man"},
        {"id": "u2", "gender": "woman"},
    ]
    feed_queues = {
        "u1": [],
        "u2": [],
    }
    proposals = engine.compute(users, feed_queues)
    assert proposals == []


def test_deduplication_of_pairs(engine):
    """Ensure no duplicate pair is returned regardless of orientation."""
    users = [
        {"id": "u1", "gender": "nonbinary"},
        {"id": "u2", "gender": "nonbinary"},
    ]
    feed_queues = {
        "u1": ["u2"],
        "u2": ["u1"],
    }
    proposals = engine.compute(users, feed_queues)
    assert len(proposals) == 1
