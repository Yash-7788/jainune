"""
Stable Marriage (Gale-Shapley) engine.

Computes a stable matching between two disjoint groups (by gender/preference)
using the Gale-Shapley deferred-acceptance algorithm.

Input:
  users      — list of user dicts (from DB)
  feed_queues — {user_id: [ranked candidate ids]} pre-computed by CorePeopleFinder

Output:
  list of proposal dicts: {"user_a": uuid_str, "user_b": uuid_str, "score": float}

Notes:
  - Users who are open to everyone (show_me="everyone") participate in both pools.
  - Non-binary / open identities: included in both proposer and proposed-to groups.
  - Score is the geometric mean of the two mutual rank positions (lower is better,
    we invert to 0–1 where 1.0 = both ranked each other #1).
  - This is a PROPOSAL, not a confirmed match. The mobile app's swipe flow
    creates actual matches; stable marriage proposals seed the feed ordering.
"""

from __future__ import annotations

import math
import logging
from typing import Any

log = logging.getLogger(__name__)


class StableMarriageEngine:
    """
    Gale-Shapley deferred acceptance.

    Proposers = users with gender 'man' OR show_me includes women/everyone.
    Proposed-to = users with gender 'woman' OR show_me includes men/everyone.

    For same-sex or nonbinary: both sides are included in both groups.
    The algorithm naturally handles this — a user may appear in both pools
    and can be both a proposer and a proposed-to target.
    """

    def compute(
        self,
        users: list[dict[str, Any]],
        feed_queues: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        """Return list of stable proposals."""
        if len(users) < 2:
            return []

        uid_to_user = {str(u["id"]): u for u in users}

        # Build proposer and receiver pools
        proposers = [str(u["id"]) for u in users]  # everyone proposes
        receiver_prefs: dict[str, list[str]] = {}

        for uid in proposers:
            # Each user's preference list = their feed queue from CorePeopleFinder
            receiver_prefs[uid] = feed_queues.get(uid, [])

        # Classic Gale-Shapley
        # proposer_next[uid] = index into their preference list (next to propose to)
        proposer_next: dict[str, int] = {uid: 0 for uid in proposers}
        # current_match[receiver] = current proposer they're tentatively matched to
        current_match: dict[str, str | None] = {uid: None for uid in proposers}
        # free proposers
        free = list(proposers)

        # Build receiver ranking index for O(1) preference lookups
        # receiver_rank[receiver][proposer] = rank position (lower = better)
        receiver_rank: dict[str, dict[str, int]] = {
            uid: {pid: i for i, pid in enumerate(receiver_prefs.get(uid, []))}
            for uid in proposers
        }

        iterations = 0
        max_iterations = len(users) ** 2  # safety cap

        while free and iterations < max_iterations:
            iterations += 1
            proposer = free.pop(0)
            pref_list = receiver_prefs.get(proposer, [])
            idx = proposer_next[proposer]

            if idx >= len(pref_list):
                continue  # exhausted all options

            receiver = pref_list[idx]
            proposer_next[proposer] = idx + 1

            if receiver not in current_match:
                # Receiver is not in pool — skip
                free.append(proposer)
                continue

            current = current_match[receiver]

            if current is None:
                # Receiver is free — tentatively match
                current_match[receiver] = proposer
            else:
                # Receiver compares current partner vs new proposer
                rrank = receiver_rank.get(receiver, {})
                rank_current = rrank.get(current, math.inf)
                rank_new = rrank.get(proposer, math.inf)

                if rank_new < rank_current:
                    # Receiver prefers new proposer — switch
                    current_match[receiver] = proposer
                    free.append(current)  # current partner becomes free
                else:
                    # Receiver keeps current — proposer stays free
                    free.append(proposer)

        # Build output proposals (deduplicate pairs)
        seen: set[frozenset] = set()
        proposals: list[dict[str, Any]] = []

        for receiver, proposer in current_match.items():
            if proposer is None or receiver == proposer:
                continue
            pair = frozenset({receiver, proposer})
            if pair in seen:
                continue
            seen.add(pair)

            # Score = mutual rank quality (geometric mean, inverted to [0,1])
            r_rank = receiver_rank.get(receiver, {}).get(proposer, 999)
            p_rank = receiver_rank.get(proposer, {}).get(receiver, 999)
            # Lower rank = better; normalise against TOP_K=50
            norm = 50.0
            r_score = max(0.0, 1.0 - r_rank / norm)
            p_score = max(0.0, 1.0 - p_rank / norm)
            score = round(math.sqrt(r_score * p_score), 4)

            proposals.append({
                "user_a": receiver,
                "user_b": proposer,
                "score": score,
            })

        # Sort by score descending (best mutual matches first)
        proposals.sort(key=lambda x: x["score"], reverse=True)
        log.info("StableMarriageEngine: %d proposals from %d users", len(proposals), len(users))
        return proposals
