"""
Daily compatible worker — runs Gale-Shapley stable matching at 02:00 IST.

What it does:
  1. Fetches all active, fully-onboarded users with valid location.
  2. Calls core_people_finder to generate ranked candidate lists (top-K per user).
  3. Feeds into the stable_marriage engine for conflict-free pairing.
  4. Writes new match proposals to the `daily_proposals` table.
  5. Dispatches new_match push notifications for mutual acceptances.

The stable marriage step is optional for day-1; core_people_finder alone
produces the ranked queue the mobile feed consumes via GET /v1/feed.
This worker pre-computes and caches that queue in Redis so feed calls are O(1).

Redis key: feed_queue:{user_id}   → JSON list of candidate user_ids (TTL 26h)
"""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
import redis.asyncio as aioredis

from app.celery_app import celery_app
from app.core.config import settings
from app.services.core_people_finder import CorePeopleFinder
from app.services.stable_marriage import StableMarriageEngine

log = logging.getLogger(__name__)

FEED_QUEUE_TTL = 26 * 3600   # 26 hours — covers the day + buffer
TOP_K = 50                    # candidates per user stored in Redis queue
BATCH_SIZE = 500              # users fetched per DB batch


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(settings.database_url)


async def _get_redis() -> aioredis.Redis:
    return await aioredis.from_url(settings.redis_url, decode_responses=True)


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.daily_compatible.run_daily_compatible")
def run_daily_compatible() -> None:
    """Beat-scheduled task: pre-compute feed queues and stable proposals."""
    asyncio.run(_run_async())


async def _run_async() -> None:
    conn = await _get_conn()
    redis = await _get_redis()

    try:
        log.info("run_daily_compatible: start")

        # --- Fetch all eligible users ---
        users = await conn.fetch(
            """
            SELECT
                id, gender, show_me, looking_for,
                dietary_strictness, community_sect,
                ST_X(location::geometry) AS longitude,
                ST_Y(location::geometry) AS latitude,
                max_distance_km, open_to_relocation,
                subscription_tier, trust_score,
                paryushan_mode, eats_root_vegetables, eats_onion_garlic
            FROM users
            WHERE account_status = 'active'
              AND onboarding_completed = TRUE
              AND location IS NOT NULL
            """
        )

        if not users:
            log.info("run_daily_compatible: no eligible users")
            return

        log.info("run_daily_compatible: processing %d users", len(users))
        user_list = [dict(u) for u in users]

        # --- Per-user candidate ranking via CorePeopleFinder ---
        finder = CorePeopleFinder()
        feed_queues: dict[str, list[str]] = {}

        for user in user_list:
            uid = str(user["id"])
            try:
                candidates = await finder.rank_candidates(
                    requester=user,
                    pool_users=user_list,
                    top_k=TOP_K,
                    conn=conn,
                )
                feed_queues[uid] = [str(c["id"]) for c in candidates]
            except Exception as exc:
                log.warning("CorePeopleFinder failed for user %s: %s", uid, exc)
                feed_queues[uid] = []

        # --- Cache feed queues in Redis ---
        pipe = redis.pipeline()
        for uid, queue in feed_queues.items():
            key = f"feed_queue:{uid}"
            pipe.set(key, json.dumps(queue), ex=FEED_QUEUE_TTL)
        await pipe.execute()
        log.info("run_daily_compatible: cached %d feed queues", len(feed_queues))

        # --- Stable marriage on users who opted for it (looking_for != figuring_out) ---
        marriage_users = [
            u for u in user_list if u.get("looking_for") != "figuring_out"
        ]

        if len(marriage_users) >= 2:
            try:
                engine = StableMarriageEngine()
                proposals = engine.compute(marriage_users, feed_queues)

                if proposals:
                    # Write proposals to DB
                    await conn.executemany(
                        """
                        INSERT INTO daily_proposals (user_a_id, user_b_id, score)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_a_id, user_b_id) DO UPDATE
                            SET score = EXCLUDED.score, proposed_at = NOW()
                        """,
                        [(p["user_a"], p["user_b"], p["score"]) for p in proposals],
                    )
                    log.info("run_daily_compatible: wrote %d proposals", len(proposals))
            except Exception as exc:
                log.error("StableMarriageEngine failed: %s", exc, exc_info=True)

        log.info("run_daily_compatible: complete")
    finally:
        await conn.close()
        await redis.aclose()
