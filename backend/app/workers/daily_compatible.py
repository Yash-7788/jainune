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
import uuid

import asyncpg
import redis.asyncio as aioredis

from app.celery_app import celery_app
from app.core.config import settings
from app.services.core_people_finder import CorePeopleFinder
from app.services.stable_marriage import StableMarriageEngine
from app.workers.worker_pool import get_worker_conn, run_worker_task

log = logging.getLogger(__name__)

FEED_QUEUE_TTL = 26 * 3600   # 26 hours — covers the day + buffer
TOP_K = 50                    # candidates per user stored in Redis queue
BATCH_SIZE = 500              # users fetched per DB batch


async def _get_conn() -> asyncpg.Connection:
    return await get_worker_conn()


async def _get_redis() -> aioredis.Redis:
    return await aioredis.from_url(settings.redis_url, decode_responses=True)


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


@celery_app.task(name="app.workers.daily_compatible.run_daily_compatible")
def run_daily_compatible() -> None:
    """Beat-scheduled task: pre-compute feed queues and stable proposals."""
    run_worker_task(_run_async())


async def _run_async() -> None:
    conn = await _get_conn()
    redis = await _get_redis()

    try:
        log.info("run_daily_compatible: start")

        # --- Fetch all eligible users via keyset pagination (NEW-013) ---
        user_list = []
        last_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        BATCH_FETCH_SIZE = 1000
        while True:
            batch = await conn.fetch(
                """
                SELECT
                    id, gender, show_me, looking_for,
                    dietary_strictness, community_sect, city,
                    ST_X(location::geometry) AS longitude,
                    ST_Y(location::geometry) AS latitude,
                    max_distance_km, open_to_relocation,
                    subscription_tier, trust_score,
                    paryushan_mode, eats_root_vegetables, eats_onion_garlic
                FROM users
                WHERE account_status = 'active'
                  AND onboarding_completed = TRUE
                  AND location IS NOT NULL
                  AND id > $1
                ORDER BY id ASC
                LIMIT $2
                """,
                last_id, BATCH_FETCH_SIZE,
            )
            if not batch:
                break
            user_list.extend([dict(u) for u in batch])
            last_id = batch[-1]["id"]
            if len(batch) < BATCH_FETCH_SIZE:
                break

        if not user_list:
            log.info("run_daily_compatible: no eligible users")
            return

        log.info("run_daily_compatible: processing %d users", len(user_list))

        # --- Per-user candidate ranking via CorePeopleFinder ---
        finder = CorePeopleFinder()
        feed_queues: dict[str, list[str]] = {}
        CHECKPOINT_BATCH_SIZE = 100

        # Pre-partition pool by gender for O(1) candidate narrowing
        pool_by_gender = {
            "men": [u for u in user_list if u.get("gender") in ("men", "man")],
            "women": [u for u in user_list if u.get("gender") in ("women", "woman")],
        }

        pipe = redis.pipeline()
        for idx, user in enumerate(user_list, start=1):
            uid = str(user["id"])
            req_gender = user.get("show_me", "everyone")
            scoped_pool = pool_by_gender.get(req_gender, user_list)

            # Bound pool candidates to top 500 by coarse geo/city match or slice to avoid O(N^2) quadratic stall (NEW-014)
            MAX_CANDIDATE_POOL = 500
            if len(scoped_pool) > MAX_CANDIDATE_POOL:
                u_city = str(user.get("city") or "").strip().lower()
                same_city = [c for c in scoped_pool if str(c.get("city") or "").strip().lower() == u_city]
                other_city = [c for c in scoped_pool if str(c.get("city") or "").strip().lower() != u_city]
                scoped_pool = (same_city + other_city)[:MAX_CANDIDATE_POOL]

            try:
                candidates = await finder.rank_candidates(
                    requester=user,
                    pool_users=scoped_pool,
                    top_k=TOP_K,
                    conn=conn,
                )
                queue = [str(c["id"]) for c in candidates]
                feed_queues[uid] = queue
            except Exception as exc:
                log.warning("CorePeopleFinder failed for user %s: %s", uid, exc)
                queue = []
                feed_queues[uid] = []

            # Checkpointed Redis persistence: flush every 100 users
            key = f"feed_queue:{uid}"
            pipe.set(key, json.dumps(queue), ex=FEED_QUEUE_TTL)

            if idx % CHECKPOINT_BATCH_SIZE == 0:
                await pipe.execute()
                pipe = redis.pipeline()
                await asyncio.sleep(0)  # Yield to event loop to keep worker responsive

        # Flush any remaining queued keys
        try:
            await pipe.execute()
        except Exception as exc:
            log.warning("Final feed_queue pipeline flush error: %s", exc)

        log.info("run_daily_compatible: checkpointed %d feed queues", len(feed_queues))

        # --- Stable marriage on users who opted for it (looking_for != figuring_out) ---
        marriage_users = [
            u for u in user_list if u.get("looking_for") != "figuring_out"
        ]

        if len(marriage_users) >= 2:
            try:
                engine = StableMarriageEngine()
                proposals = []
                if len(marriage_users) > 200:
                    clusters: dict[str, list[dict]] = {}
                    for u in marriage_users:
                        loc_key = str(u.get("city") or "general").strip().lower()
                        clusters.setdefault(loc_key, []).append(u)
                    for cluster_users in clusters.values():
                        if len(cluster_users) >= 2:
                            proposals.extend(engine.compute(cluster_users, feed_queues))
                else:
                    proposals = engine.compute(marriage_users, feed_queues)

                if proposals:
                    # Write proposals to DB with canonical pair ordering (min, max)
                    proposal_rows = []
                    for p in proposals:
                        u_a = uuid.UUID(str(p["user_a"]))
                        u_b = uuid.UUID(str(p["user_b"]))
                        u1, u2 = min(u_a, u_b), max(u_a, u_b)
                        proposal_rows.append((u1, u2, float(p["score"])))

                    await conn.executemany(
                        """
                        INSERT INTO daily_proposals (user_a_id, user_b_id, score)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_a_id, user_b_id) DO UPDATE
                            SET score = EXCLUDED.score, proposed_at = NOW()
                        """,
                        proposal_rows,
                    )
                    log.info("run_daily_compatible: wrote %d proposals", len(proposals))
            except Exception as exc:
                log.error("StableMarriageEngine failed: %s", exc, exc_info=True)

        log.info("run_daily_compatible: complete")
    finally:
        await conn.close()
        await redis.aclose()
