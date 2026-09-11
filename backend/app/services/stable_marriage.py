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
        """Return list of stable, mutually acceptable proposals."""
        if len(users) < 2:
            return []

        uid_to_user = {str(u["id"]): u for u in users}
        normalized_queues = {
            str(k): [str(cid) for cid in v] for k, v in feed_queues.items()
        }

        # Check if user pool cleanly partitions into heterosexual bipartite sets
        men = [
            uid for uid, u in uid_to_user.items()
            if u.get("gender") in ("man", "men") and u.get("show_me") in ("woman", "women", None)
        ]
        women = [
            uid for uid, u in uid_to_user.items()
            if u.get("gender") in ("woman", "women") and u.get("show_me") in ("man", "men", None)
        ]

        is_pure_bipartite = (
            len(men) > 0
            and len(women) > 0
            and (len(men) + len(women) == len(uid_to_user))
        )

        candidates: list[dict[str, Any]] = []

        if is_pure_bipartite:
            # Deterministic, optimal bipartite Gale-Shapley (proposers = men, receivers = women)
            proposers = list(men)
            receivers = set(women)
            free = list(proposers)
            proposer_next = {uid: 0 for uid in proposers}
            current_match: dict[str, str | None] = {uid: None for uid in receivers}

            receiver_rank: dict[str, dict[str, int]] = {
                uid: {pid: i for i, pid in enumerate(normalized_queues.get(uid, []))}
                for uid in receivers
            }
            proposer_rank: dict[str, dict[str, int]] = {
                uid: {rid: i for i, rid in enumerate(normalized_queues.get(uid, []))}
                for uid in proposers
            }

            iterations = 0
            max_iterations = len(users) ** 2

            while free and iterations < max_iterations:
                iterations += 1
                proposer = free.pop(0)
                pref_list = normalized_queues.get(proposer, [])
                idx = proposer_next[proposer]

                if idx >= len(pref_list):
                    continue  # exhausted options

                receiver = pref_list[idx]
                proposer_next[proposer] = idx + 1

                if receiver not in receivers:
                    free.append(proposer)
                    continue

                # Mutual acceptability check: receiver must have proposer in preferences
                rrank = receiver_rank.get(receiver, {})
                if proposer not in rrank:
                    # Receiver does not want proposer; proposer remains free to propose next
                    free.append(proposer)
                    continue

                rank_new = rrank[proposer]
                current = current_match[receiver]

                if current is None:
                    current_match[receiver] = proposer
                else:
                    rank_current = rrank.get(current, math.inf)
                    if rank_new < rank_current:
                        current_match[receiver] = proposer
                        free.append(current)
                    else:
                        free.append(proposer)

            for receiver, proposer in current_match.items():
                if proposer is None:
                    continue
                r_rank = receiver_rank.get(receiver, {}).get(proposer, 999)
                p_rank = proposer_rank.get(proposer, {}).get(receiver, 999)
                norm = 50.0
                r_score = max(0.0, 1.0 - r_rank / norm)
                p_score = max(0.0, 1.0 - p_rank / norm)
                score = round(math.sqrt(r_score * p_score), 4)
                if score > 0:
                    candidates.append({
                        "user_a": receiver,
                        "user_b": proposer,
                        "score": score,
                    })
        else:
            # Generalized reciprocal deferred-acceptance matching for open / non-binary / mixed pools
            all_uids = list(uid_to_user.keys())
            free = list(all_uids)
            proposer_next = {uid: 0 for uid in all_uids}
            current_match = {uid: None for uid in all_uids}

            user_rank: dict[str, dict[str, int]] = {
                uid: {target: i for i, target in enumerate(normalized_queues.get(uid, []))}
                for uid in all_uids
            }

            iterations = 0
            max_iterations = len(users) ** 2

            while free and iterations < max_iterations:
                iterations += 1
                proposer = free.pop(0)
                pref_list = normalized_queues.get(proposer, [])
                idx = proposer_next[proposer]

                if idx >= len(pref_list):
                    continue

                receiver = pref_list[idx]
                proposer_next[proposer] = idx + 1

                if receiver not in current_match or receiver == proposer:
                    free.append(proposer)
                    continue

                rrank = user_rank.get(receiver, {})
                if proposer not in rrank:
                    free.append(proposer)
                    continue

                rank_new = rrank[proposer]
                current = current_match[receiver]

                if current is None:
                    current_match[receiver] = proposer
                else:
                    rank_current = rrank.get(current, math.inf)
                    if rank_new < rank_current:
                        current_match[receiver] = proposer
                        free.append(current)
                    else:
                        free.append(proposer)

            seen_pairs: set[frozenset] = set()
            for receiver, proposer in current_match.items():
                if proposer is None or receiver == proposer:
                    continue
                pair = frozenset({receiver, proposer})
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                r_rank = user_rank.get(receiver, {}).get(proposer, 999)
                p_rank = user_rank.get(proposer, {}).get(receiver, 999)
                norm = 50.0
                r_score = max(0.0, 1.0 - r_rank / norm)
                p_score = max(0.0, 1.0 - p_rank / norm)
                score = round(math.sqrt(r_score * p_score), 4)
                if score > 0:
                    candidates.append({
                        "user_a": receiver,
                        "user_b": proposer,
                        "score": score,
                    })

        # Sort candidate pairs by score descending (highest mutual affinity first)
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # Enforce strict 1-to-1 matching (no user assigned multiple times)
        proposals: list[dict[str, Any]] = []
        matched_users: set[str] = set()
        for cand in candidates:
            if cand["user_a"] not in matched_users and cand["user_b"] not in matched_users:
                matched_users.add(cand["user_a"])
                matched_users.add(cand["user_b"])
                proposals.append(cand)

        log.info("StableMarriageEngine: %d proposals from %d users", len(proposals), len(users))
        return proposals
