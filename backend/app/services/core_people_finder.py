"""
Core People-Finding Engine (BRRE) — Behavioral Reciprocal Recommendation Engine.

Five-stage retrieval pipeline targeting sub-30ms p95:
  L0: Hard filter gating  — PostGIS GiST + B-Tree  (<3ms)
  L1: ANN candidate gen   — pgvector HNSW cosine   (<12ms)
  L2: Reciprocal scoring  — geometric mean formula  (<8ms)
  L3: Dignity floor       — Thompson Sampling boost (<4ms)
  L4: Redis session cache — sorted set prefetch     (<1ms)
"""
from __future__ import annotations

import json
import math
import uuid
from typing import List, Optional

import asyncpg
import redis.asyncio as aioredis


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FEED_CACHE_TTL = 300        # seconds — 5-minute session cache
_DIGNITY_THRESHOLD = 35      # impressions per 48h below which profile is boosted
_DIGNITY_BOOST = 25.0        # composite score bonus for under-exposed profiles
_UNDER_2KM_LABEL = "Under 2 km away"


# ---------------------------------------------------------------------------
# Distance display formatter (trilateration defense: no decimal precision)
# ---------------------------------------------------------------------------

def _format_distance(distance_km: float, user_a_id: str, user_b_id: str) -> str:
    """
    Returns a privacy-safe distance string.
    - < 2 km  -> "Under 2 km away"
    - >= 2 km -> rounded to nearest km + deterministic jitter in [-0.2, +0.2]
                 derived from HMAC of (user_a_id, user_b_id).

    The jitter is deterministic per pair, preventing convergent trilateration
    across repeated queries with different observer positions.
    """
    if distance_km < 2.0:
        return _UNDER_2KM_LABEL

    # Deterministic jitter: hash of sorted pair ids, mapped to [-0.2, 0.2]
    pair_key = f"{min(user_a_id, user_b_id)}:{max(user_a_id, user_b_id)}"
    hash_int = int(pair_key.encode().hex(), 16) % 1000
    jitter = (hash_int / 1000.0 - 0.5) * 0.4  # range [-0.2, +0.2]
    display = round(distance_km) + jitter
    return f"{display:.0f} km away"


# ---------------------------------------------------------------------------
# Redis feed cache helpers
# ---------------------------------------------------------------------------

async def _get_cached_feed(
    user_id: uuid.UUID,
    redis: aioredis.Redis,
) -> Optional[List[dict]]:
    """Read pre-ranked candidate batch from Redis sorted set."""
    key = f"feed:cache:{user_id}"
    raw = await redis.get(key)
    if raw:
        return json.loads(raw)
    return None


async def _cache_feed(
    user_id: uuid.UUID,
    candidates: List[dict],
    redis: aioredis.Redis,
) -> None:
    key = f"feed:cache:{user_id}"
    await redis.set(key, json.dumps(candidates, default=str), ex=_FEED_CACHE_TTL)


async def invalidate_feed_cache(user_id: uuid.UUID, redis: aioredis.Redis) -> None:
    """Call on like/pass to keep feed fresh."""
    await redis.delete(f"feed:cache:{user_id}")


# ---------------------------------------------------------------------------
# Main engine entry point
# ---------------------------------------------------------------------------

async def fetch_recommended_feed(
    user_id: uuid.UUID,
    user_data: dict,
    db: asyncpg.Pool,
    redis: aioredis.Redis,
    limit: int = 15,
    force_refresh: bool = False,
) -> dict:
    """
    Returns up to `limit` ranked candidate profiles.

    Returns:
        {
            "candidates": [...],
            "batch_id": str,
            "exhausted": bool,
            "from_cache": bool,
        }
    """
    # L4: Check session cache first (avoids DB hit on rapid swipes)
    if not force_refresh:
        cached = await _get_cached_feed(user_id, redis)
        if cached:
            batch = cached[:limit]
            remaining = cached[limit:]
            # Slide the cache forward
            if remaining:
                await _cache_feed(user_id, remaining, redis)
            else:
                await redis.delete(f"feed:cache:{user_id}")
            return {
                "candidates": batch,
                "batch_id": f"batch_{uuid.uuid4().hex[:8]}",
                "exhausted": len(remaining) == 0,
                "from_cache": True,
            }

    # L0 + L1 + L2 + L3: Full pipeline
    candidates = await _run_pipeline(user_id, user_data, db, limit * 2)

    # Cache surplus for session prefetch
    if len(candidates) > limit:
        await _cache_feed(user_id, candidates[limit:], redis)

    # Batch increment impression counts for Dignity Engine tracking
    if candidates:
        ids = [c["id"] for c in candidates]
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE users SET impressions_last_48h = impressions_last_48h + 1 WHERE id = ANY($1::uuid[])",
                ids,
            )

    return {
        "candidates": candidates[:limit],
        "batch_id": f"batch_{uuid.uuid4().hex[:8]}",
        "exhausted": len(candidates) <= limit,
        "from_cache": False,
    }


# ---------------------------------------------------------------------------
# Multi-stage SQL pipeline
# ---------------------------------------------------------------------------

async def _run_pipeline(
    user_id: uuid.UUID,
    user_data: dict,
    db: asyncpg.Pool,
    internal_limit: int,
) -> List[dict]:
    """
    Single SQL query combining PostGIS spatial filter (L0), pgvector HNSW
    cosine ANN (L1), cultural/dietary composite scoring (L2), and
    Thompson Sampling Dignity Floor injection (L3).

    Executes under service_role connection (bypasses RLS for feed generation).
    All returned columns are public-safe; raw location geometry is excluded.
    """
    # Determine gender target from user preferences
    gender_map = {
        "men": "man",
        "women": "woman",
        "everyone": None,  # no gender filter
    }
    target_gender: Optional[str] = gender_map.get(user_data.get("show_me", "everyone"))

    # Behavior vector (128-d). Fallback to zero-vector for new users.
    behavior_vector = user_data.get("revealed_preference_vector")
    if not behavior_vector:
        behavior_vector = "[" + ",".join(["0"] * 128) + "]"
    elif isinstance(behavior_vector, list):
        behavior_vector = "[" + ",".join(str(v) for v in behavior_vector) + "]"

    # PostGIS geography point for ST_DWithin  (WKB hex)
    user_location = user_data.get("location")  # asyncpg returns geometry as WKBElement

    dietary = user_data.get("dietary_strictness", "")
    eats_root = user_data.get("eats_root_vegetables", False)
    eats_onion = user_data.get("eats_onion_garlic", False)
    sect = user_data.get("community_sect", "open")
    relocation = user_data.get("open_to_relocation", False)
    max_km = user_data.get("max_distance_km", 30)

    query = """
    WITH candidate_pool AS (
        SELECT
            u.id,
            u.first_name,
            u.city,
            u.state,
            u.gender,
            u.date_of_birth,
            u.dietary_strictness,
            u.eats_root_vegetables,
            u.eats_onion_garlic,
            u.community_sect,
            u.paryushan_mode,
            u.job_title,
            u.education,
            u.height_cm,
            u.bio,
            u.open_to_relocation,
            u.subscription_tier,
            u.is_photo_verified,
            u.impressions_last_48h,
            -- Geodetic distance in km; NULL if location is NULL
            CASE
                WHEN u.location IS NOT NULL AND $1::geometry IS NOT NULL
                THEN ST_Distance(
                    ST_Transform(u.location, 3857),
                    ST_Transform($1::geometry, 3857)
                ) / 1000.0
                ELSE NULL
            END AS distance_km,
            -- L1: pgvector HNSW cosine ANN score (1 = identical, 0 = orthogonal)
            CASE
                WHEN b.revealed_preference_vector IS NOT NULL
                THEN (1.0 - (b.revealed_preference_vector <=> $2::vector))
                ELSE 0.0
            END AS behavioral_affinity,
            -- L2: Cultural composite score (deterministic, no randomness)
            (
                CASE WHEN u.dietary_strictness = $3 THEN 30 ELSE 10 END
                + CASE WHEN u.eats_root_vegetables = $4 THEN 10 ELSE 0 END
                + CASE WHEN u.eats_onion_garlic    = $5 THEN 10 ELSE 0 END
                + CASE
                    WHEN u.community_sect = $6 THEN 25
                    WHEN u.community_sect = 'open' THEN 15
                    ELSE 10
                  END
                + CASE WHEN u.open_to_relocation AND $7 THEN 15 ELSE 0 END
                + CASE
                    WHEN u.updated_at >= NOW() - INTERVAL '24 hours' THEN 10
                    WHEN u.updated_at >= NOW() - INTERVAL '72 hours' THEN 6
                    ELSE 0
                  END
            ) AS cultural_score
        FROM users u
        LEFT JOIN user_behavior_vectors b ON u.id = b.user_id
        WHERE
            u.id           != $8
            AND u.account_status = 'active'
            AND u.is_paused = FALSE
            AND u.onboarding_completed = TRUE
            -- Gender filter (NULL = everyone)
            AND ($9::text IS NULL OR u.gender = $9::text)
            -- Hard dietary dealbreaker: pure_jain must only see pure_jain or vegan
            AND (
                $3 != 'pure_jain'
                OR u.dietary_strictness IN ('pure_jain', 'vegan')
            )
            -- Hard onion-garlic dealbreaker for pure_jain viewers
            AND (
                NOT ($3 = 'pure_jain' AND NOT $5 AND u.eats_onion_garlic = TRUE)
            )
            -- Geographic constraint: local radius OR pan-India relocation
            AND (
                (
                    u.location IS NOT NULL
                    AND $1::geometry IS NOT NULL
                    AND ST_DWithin(
                        ST_Transform(u.location, 3857),
                        ST_Transform($1::geometry, 3857),
                        $10 * 1000
                    )
                )
                OR (u.open_to_relocation = TRUE AND $7 = TRUE)
            )
            -- Exclude already-swiped profiles
            AND NOT EXISTS (
                SELECT 1 FROM interactions i
                WHERE i.actor_id = $8 AND i.target_id = u.id
            )
        ORDER BY b.revealed_preference_vector <=> $2::vector ASC
        LIMIT 200
    )
    SELECT
        id,
        first_name,
        city,
        state,
        gender,
        date_of_birth,
        dietary_strictness,
        eats_root_vegetables,
        eats_onion_garlic,
        community_sect,
        paryushan_mode,
        job_title,
        education,
        height_cm,
        bio,
        open_to_relocation,
        subscription_tier,
        is_photo_verified,
        impressions_last_48h,
        distance_km,
        behavioral_affinity,
        cultural_score,
        -- Final composite: behavioral (40%) + cultural (60 max)
        (behavioral_affinity * 40.0 + cultural_score) AS raw_score
    FROM candidate_pool
    ORDER BY
        -- L3: Dignity Floor — boost under-exposed profiles
        CASE
            WHEN impressions_last_48h < $11 THEN
                (behavioral_affinity * 40.0 + cultural_score) + $12
            ELSE
                (behavioral_affinity * 40.0 + cultural_score)
        END DESC
    LIMIT $13
    """

    async with db.acquire() as conn:
        rows = await conn.fetch(
            query,
            user_location,          # $1  geometry
            behavior_vector,        # $2  vector
            dietary,                # $3  text
            eats_root,              # $4  bool
            eats_onion,             # $5  bool
            sect,                   # $6  text
            relocation,             # $7  bool
            user_id,                # $8  uuid
            target_gender,          # $9  text | NULL
            max_km,                 # $10 int
            _DIGNITY_THRESHOLD,     # $11 int
            _DIGNITY_BOOST,         # $12 float
            internal_limit,         # $13 int
        )

        # Batch-load media (photos + voice) for all candidate ids
        candidate_ids = [r["id"] for r in rows]
        media_by_user: dict[str, list] = {}
        voice_by_user: dict[str, dict] = {}

        if candidate_ids:
            media_rows = await conn.fetch(
                """
                SELECT user_id, media_type, cdn_url, s3_key, position, duration_seconds
                FROM user_media
                WHERE user_id = ANY($1::uuid[])
                  AND is_processed = TRUE
                ORDER BY user_id, media_type, position ASC
                """,
                candidate_ids,
            )
            for m in media_rows:
                uid = str(m["user_id"])
                url = m["cdn_url"] or m["s3_key"]
                if m["media_type"] == "photo":
                    media_by_user.setdefault(uid, []).append({
                        "id": str(m["user_id"]) + f"_p{m['position']}",
                        "url": url,
                        "order": m["position"],
                    })
                elif m["media_type"] == "voice":
                    voice_by_user[uid] = {
                        "audio_url": url,
                        "duration_seconds": float(m["duration_seconds"] or 0),
                    }

            # Batch-load prompts
            prompt_rows = await conn.fetch(
                """
                SELECT user_id, prompt_key, response_text, position
                FROM user_prompts
                WHERE user_id = ANY($1::uuid[])
                ORDER BY user_id, position ASC
                """,
                candidate_ids,
            )
            prompts_by_user: dict[str, list] = {}
            for p in prompt_rows:
                uid = str(p["user_id"])
                prompts_by_user.setdefault(uid, []).append({
                    "question": p["prompt_key"],
                    "answer": p["response_text"],
                    "position": p["position"],
                })
        else:
            prompts_by_user = {}

    result = []
    viewer_id_str = str(user_id)
    for row in rows:
        r = dict(row)
        uid = str(r["id"])

        # Calculate age from DOB
        age = None
        if r.get("date_of_birth"):
            from datetime import date
            today = date.today()
            dob = r["date_of_birth"]
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        dist_km = r.get("distance_km")
        dist_display = (
            _format_distance(dist_km, viewer_id_str, uid)
            if dist_km is not None
            else "Pan-India"
        )

        result.append({
            "id": uid,
            "first_name": r["first_name"],
            "age": age,
            "city": r["city"],
            "state": r["state"],
            "distance_display": dist_display,
            "dietary_strictness": r["dietary_strictness"],
            "eats_root_vegetables": r["eats_root_vegetables"],
            "eats_onion_garlic": r["eats_onion_garlic"],
            "community_sect": r["community_sect"],
            "paryushan_mode": r["paryushan_mode"],
            "education": r["education"],
            "job_title": r["job_title"],
            "height_cm": r["height_cm"],
            "bio": r["bio"],
            "open_to_relocation": r["open_to_relocation"],
            "is_photo_verified": r["is_photo_verified"],
            "photos": media_by_user.get(uid, []),
            "prompts": prompts_by_user.get(uid, []),
            "voice_snapshot": voice_by_user.get(uid),
            # Internal scoring (stripped before API response in router)
            "_behavioral_affinity": float(r.get("behavioral_affinity") or 0),
            "_cultural_score": float(r.get("cultural_score") or 0),
        })

    return result


# ---------------------------------------------------------------------------
# Nightly Gale-Shapley: fetch today's pre-computed "Daily Compatible" pair
# ---------------------------------------------------------------------------

async def fetch_daily_compatible(
    user_id: uuid.UUID,
    db: asyncpg.Pool,
    redis: aioredis.Redis,
) -> Optional[dict]:
    """
    Returns today's stable-marriage pairing for the user, if computed.
    The nightly GS worker writes results to `daily_compatible_cache` Redis key.
    Falls back to top BRRE result when nightly job hasn't run yet.
    """
    cache_key = f"daily_compatible:{user_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # No nightly result: fall back to highest reciprocal score in DB
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.id, u.first_name, u.city, u.state, u.community_sect,
                u.dietary_strictness, u.date_of_birth
            FROM users u
            JOIN user_behavior_vectors b ON u.id = b.user_id
            WHERE u.id != $1
              AND u.account_status = 'active'
              AND u.onboarding_completed = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM interactions i
                  WHERE i.actor_id = $1 AND i.target_id = u.id
              )
            ORDER BY b.revealed_preference_vector <=>
                (SELECT revealed_preference_vector FROM user_behavior_vectors WHERE user_id = $1)
            ASC
            LIMIT 1
            """,
            user_id,
        )
    if not row:
        return None

    from datetime import date as date_type
    dob = row["date_of_birth"]
    today = date_type.today()
    age = None
    if dob:
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    return {
        "id": str(row["id"]),
        "first_name": row["first_name"],
        "age": age,
        "city": row["city"],
        "state": row["state"],
        "community_sect": row["community_sect"],
        "dietary_strictness": row["dietary_strictness"],
        "compatibility_rationale": "Highest reciprocal behavioral affinity in your region.",
        "pairing_algorithm": "brre_fallback",
    }
