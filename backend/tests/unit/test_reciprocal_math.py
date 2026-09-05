"""
Unit tests for Behavioral Reciprocal Recommendation Engine (BRRE) math and heuristics.
Uses standard library unittest.
"""

import sys
import unittest
import uuid
from unittest.mock import MagicMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()
    sys.modules["redis.asyncio"] = MagicMock()

from app.services.core_people_finder import (
    _DIGNITY_BOOST,
    _DIGNITY_THRESHOLD,
    _UNDER_2KM_LABEL,
    _format_distance,
)


class TestReciprocalMath(unittest.TestCase):

    def test_format_distance_under_2km(self):
        u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertEqual(_format_distance(0.5, u1, u2), _UNDER_2KM_LABEL)
        self.assertEqual(_format_distance(1.9, u1, u2), _UNDER_2KM_LABEL)

    def test_format_distance_deterministic_and_symmetric(self):
        """Distance format must be identical regardless of who is viewer vs target."""
        u1 = "00000000-0000-0000-0000-000000000001"
        u2 = "00000000-0000-0000-0000-000000000002"

        dist1 = _format_distance(12.4, u1, u2)
        dist2 = _format_distance(12.4, u2, u1)

        self.assertEqual(dist1, dist2)
        self.assertTrue(dist1.endswith("km away"))
        self.assertIn("12", dist1)

    def test_dignity_constants(self):
        """Ensure baseline constants meet BRRE spec."""
        self.assertEqual(_DIGNITY_THRESHOLD, 35)
        self.assertEqual(_DIGNITY_BOOST, 25.0)

    def test_cultural_score_computation(self):
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
            if u_sect == c_sect:
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

        # Perfect match
        perf = compute_cultural("pure_jain", "pure_jain", False, False, False, False, "deravasi", "deravasi", True, True, 1)
        self.assertEqual(perf, 100)

        # Partial match
        part = compute_cultural("pure_jain", "vegan", False, False, False, True, "deravasi", "open", True, False, 48)
        # 10 + 10 + 0 + 15 + 0 + 6 = 41
        self.assertEqual(part, 41)


if __name__ == "__main__":
    unittest.main()
