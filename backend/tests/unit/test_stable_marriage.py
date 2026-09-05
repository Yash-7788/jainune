"""
Unit tests for Gale-Shapley Stable Marriage engine.
Uses standard library unittest.
"""

from __future__ import annotations

import unittest
from app.services.stable_marriage import StableMarriageEngine


class TestStableMarriage(unittest.TestCase):

    def setUp(self):
        self.engine = StableMarriageEngine()

    def test_empty_users(self):
        """Less than 2 users returns empty proposals."""
        self.assertEqual(self.engine.compute([], {}), [])
        self.assertEqual(self.engine.compute([{"id": "u1", "gender": "man"}], {}), [])

    def test_standard_stable_matching(self):
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
        feed_queues = {
            "p1": ["r1", "r2"],
            "p2": ["r1", "r2"],
            "r1": ["p1", "p2"],
            "r2": ["p2", "p1"],
        }

        proposals = self.engine.compute(users, feed_queues)
        self.assertEqual(len(proposals), 2)

        pairs = set()
        for prop in proposals:
            pairs.add(frozenset({prop["user_a"], prop["user_b"]}))

        self.assertIn(frozenset({"p1", "r1"}), pairs)
        self.assertIn(frozenset({"p2", "r2"}), pairs)

    def test_proposals_score_calculation(self):
        users = [
            {"id": "p1", "gender": "man", "show_me": "women"},
            {"id": "r1", "gender": "woman", "show_me": "men"},
        ]
        feed_queues = {
            "p1": ["r1"],
            "r1": ["p1"],
        }
        proposals = self.engine.compute(users, feed_queues)
        self.assertEqual(len(proposals), 1)
        self.assertGreater(proposals[0]["score"], 0)


if __name__ == "__main__":
    unittest.main()
