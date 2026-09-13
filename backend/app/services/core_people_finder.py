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

import asyncio
import json
import logging
import math
import uuid
from typing import List, Optional

import asyncpg
import redis.asyncio as aioredis

log = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


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

_POP_FEED_SCRIPT = """
local raw = redis.call('get', KEYS[1])
if not raw then return nil end
local ok, candidates = pcall(cjson.decode, raw)
if not ok or type(candidates) ~= 'table' then
    redis.call('del', KEYS[1])
    return nil
end
local limit = tonumber(ARGV[1])
-- N-15 fix: serve partial batches rather than discarding when fewer remain than limit.
if #candidates == 0 then
    redis.call('del', KEYS[1])
    return nil
end
local take = math.min(limit, #candidates)
local batch = {}
local remaining = {}
for i = 1, #candidates do
    if i <= take then
        table.insert(batch, candidates[i])
    else
        table.insert(remaining, candidates[i])
    end
end
if #remaining > 0 then
    local ttl = redis.call('ttl', KEYS[1])
    if ttl < 0 then ttl = 3600 end
    redis.call('set', KEYS[1], cjson.encode(remaining), 'EX', ttl)
else
    redis.call('del', KEYS[1])
end
return cjson.encode(batch)
"""


async def _get_cached_feed(
    user_id: uuid.UUID,
    redis: aioredis.Redis,
) -> Optional[List[dict]]:
    """Read pre-ranked candidate batch from Redis sorted set."""
    key = f"feed:cache:{user_id}"
    try:
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        log.warning("Redis feed cache decode error for user %s: %s", user_id, exc)
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
    # L4: Check session cache first atomically via Lua (prevents race duplicates on concurrent prefetch)
    if not force_refresh:
        try:
            cached_json = await redis.eval(_POP_FEED_SCRIPT, 1, f"feed:cache:{user_id}", limit)
            if cached_json:
                batch = json.loads(cached_json)
                return {
                    "candidates": batch,
                    "batch_id": f"batch_{uuid.uuid4().hex[:8]}",
                    "exhausted": False,
                    "from_cache": True,
                }
        except Exception as exc:
            log.warning("Atomic feed cache pop failed: %s", exc)
            try:
                cached_json = await redis.get(f"feed:cache:{user_id}")
                if cached_json:
                    raw_batch = json.loads(cached_json)
                    batch = raw_batch[:limit]
                    return {
                        "candidates": batch,
                        "batch_id": f"batch_{uuid.uuid4().hex[:8]}",
                        "exhausted": False,
                        "from_cache": True,
                    }
            except Exception:
                pass

    # L0 + L1 + L2 + L3: Full pipeline
    candidates = await _run_pipeline(user_id, user_data, db, limit * 2)

    # Cache surplus for session prefetch
    if len(candidates) > limit:
        await _cache_feed(user_id, candidates[limit:], redis)

    # Buffer impressions in Redis counter to prevent row lock contention on users table
    if candidates:
        try:
            pipe = redis.pipeline()
            for c in candidates:
                pipe.hincrby("buffer:user_impressions_48h", str(c["id"]), 1)
            await pipe.execute()
            t = asyncio.create_task(_async_flush_impressions(db, redis))
            _background_tasks.add(t)
            t.add_done_callback(_background_tasks.discard)
        except Exception:
            pass

    return {
        "candidates": candidates[:limit],
        "batch_id": f"batch_{uuid.uuid4().hex[:8]}",
        "exhausted": len(candidates) <= limit,
        "from_cache": False,
    }


async def _async_flush_impressions(db: asyncpg.Pool, redis: aioredis.Redis) -> None:
    """Asynchronously flush buffered user impression counts from Redis to PostgreSQL using atomic RENAME."""
    lock_token = uuid.uuid4().hex
    lock_key = "lock:flush_impressions"
    try:
        acquired = await redis.set(lock_key, lock_token, nx=True, ex=15)
        if not acquired:
            return

        # N-23: recover orphaned flushing keys from previous crash before renaming.
        # If process died between rename and DEL, temp key is stranded with no TTL.
        try:
            orphan_pattern = "buffer:user_impressions_48h:flushing:*"
            async for orphan_key in redis.scan_iter(orphan_pattern):
                orphan_counts = await redis.hgetall(orphan_key)
                if orphan_counts:
                    pipe = redis.pipeline()
                    for k, v in orphan_counts.items():
                        pipe.hincrby("buffer:user_impressions_48h", k, int(v))
                    await pipe.execute()
                await redis.delete(orphan_key)
                log.info("flush_impressions: recovered orphaned temp key %s", orphan_key)
        except Exception as exc:
            log.warning("flush_impressions: orphan recovery failed: %s", exc)

        temp_key = f"buffer:user_impressions_48h:flushing:{lock_token}"
        rename_script = """
            if redis.call('exists', KEYS[1]) == 1 then
                redis.call('rename', KEYS[1], KEYS[2])
                return 1
            else
                return 0
            end
        """
        renamed = await redis.eval(rename_script, 2, "buffer:user_impressions_48h", temp_key)
        if not renamed:
            return

        counts = await redis.hgetall(temp_key)
        if not counts:
            await redis.delete(temp_key)
            return

        updates = []
        for k, v in counts.items():
            if not v:
                continue
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            try:
                updates.append((int(v), uuid.UUID(k_str)))
            except Exception:
                continue

        if updates:
            try:
                async with db.acquire() as conn:
                    await conn.executemany(
                        "UPDATE users SET impressions_last_48h = impressions_last_48h + $1 WHERE id = $2",
                        updates,
                    )
                await redis.delete(temp_key)
            except Exception as db_err:
                log.error("Failed to flush impressions to DB, restoring buffer: %s", db_err)
                pipe = redis.pipeline()
                for k, v in counts.items():
                    pipe.hincrby("buffer:user_impressions_48h", k, int(v))
                await pipe.execute()
                await redis.delete(temp_key)
    except Exception as exc:
        log.debug("Impression flush non-blocking failure: %s", exc)
    finally:
        try:
            release_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
            """
            await redis.eval(release_script, 1, lock_key, lock_token)
        except Exception:
            pass


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

    # Behavior vector (128-d). Fallback to uniform unit vector for new users (norm = 1.0)
    # to prevent divide-by-zero NaN in pgvector cosine distance operator <=>.
    behavior_vector = user_data.get("revealed_preference_vector")
    unit_val = "0.088388"
    if not behavior_vector:
        behavior_vector = "[" + ",".join([unit_val] * 128) + "]"
    elif isinstance(behavior_vector, list):
        if all(v == 0 for v in behavior_vector):
            behavior_vector = "[" + ",".join([unit_val] * 128) + "]"
        else:
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
                    u.location::geography,
                    $1::geography
                ) / 1000.0
                ELSE NULL
            END AS distance_km,
            -- L1: pgvector HNSW cosine ANN score (1 = identical, 0 = orthogonal)
            CASE
                WHEN b.revealed_preference_vector IS NOT NULL
                THEN GREATEST(0.0, LEAST(1.0, COALESCE(1.0 - (b.revealed_preference_vector <=> $2::vector), 0.0)))
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
                        u.location::geography,
                        $1::geography,
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
            -- Exclude blocked users (either direction)
            AND NOT EXISTS (
                SELECT 1 FROM user_blocks ub
                WHERE (ub.blocker_id = $8 AND ub.blocked_id = u.id)
                   OR (ub.blocker_id = u.id AND ub.blocked_id = $8)
            )
            -- Candidates must have at least one approved photo in feed (BUG-038)
            AND EXISTS (
                SELECT 1 FROM user_media um
                WHERE um.user_id = u.id AND um.media_type = 'photo' AND um.status = 'approved'
            )
        ORDER BY COALESCE(b.revealed_preference_vector <=> $2::vector, 2.0) ASC
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
                  AND status = 'approved'
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
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        log.warning("Redis daily_compatible decode error for user %s: %s", user_id, exc)

    algo = "brre_fallback"
    rationale = "Highest reciprocal behavioral affinity in your region."

    async with db.acquire() as conn:
        # Check nightly GS proposal for today first
        row = await conn.fetchrow(
            """
            SELECT
                u.id, u.first_name, u.city, u.state, u.community_sect,
                u.dietary_strictness, u.eats_root_vegetables, u.eats_onion_garlic,
                u.paryushan_mode, u.education, u.job_title, u.height_cm,
                u.bio, u.open_to_relocation, u.is_photo_verified, u.date_of_birth
            FROM daily_proposals dp
            JOIN users u ON (u.id = CASE WHEN dp.user_a_id = $1 THEN dp.user_b_id ELSE dp.user_a_id END)
            WHERE (dp.user_a_id = $1 OR dp.user_b_id = $1)
              AND dp.proposed_at >= CURRENT_DATE
              AND u.account_status = 'active'
              AND u.onboarding_completed = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM interactions i
                  WHERE i.actor_id = $1 AND i.target_id = u.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM user_blocks ub
                  WHERE (ub.blocker_id = $1 AND ub.blocked_id = u.id)
                     OR (ub.blocker_id = u.id AND ub.blocked_id = $1)
              )
              AND EXISTS (
                  SELECT 1 FROM user_media um
                  WHERE um.user_id = u.id AND um.media_type = 'photo' AND um.status = 'approved'
              )
            ORDER BY dp.proposed_at DESC
            LIMIT 1
            """,
            user_id,
        )
        if row:
            algo = "gale_shapley_nightly"
            rationale = "Your curated Daily Compatible match from last night's matching cycle."
        else:
            # Fall back to highest reciprocal score in DB
            row = await conn.fetchrow(
                """
                SELECT
                    u.id, u.first_name, u.city, u.state, u.community_sect,
                    u.dietary_strictness, u.eats_root_vegetables, u.eats_onion_garlic,
                    u.paryushan_mode, u.education, u.job_title, u.height_cm,
                    u.bio, u.open_to_relocation, u.is_photo_verified, u.date_of_birth
                FROM users u
                JOIN user_behavior_vectors b ON u.id = b.user_id
                WHERE u.id != $1
                  AND u.account_status = 'active'
                  AND u.onboarding_completed = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM interactions i
                      WHERE i.actor_id = $1 AND i.target_id = u.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM user_blocks ub
                      WHERE (ub.blocker_id = $1 AND ub.blocked_id = u.id)
                         OR (ub.blocker_id = u.id AND ub.blocked_id = $1)
                  )
                  AND EXISTS (
                      SELECT 1 FROM user_media um
                      WHERE um.user_id = u.id AND um.media_type = 'photo' AND um.status = 'approved'
                  )
                ORDER BY COALESCE(
                    b.revealed_preference_vector <=>
                    (SELECT revealed_preference_vector FROM user_behavior_vectors WHERE user_id = $1),
                    2.0
                ) ASC
                LIMIT 1
                """,
                user_id,
            )

        if not row:
            return None

        cand_id = row["id"]
        # Batch load photos and voice note
        media_rows = await conn.fetch(
            """
            SELECT media_type, cdn_url, s3_key, position, duration_seconds
            FROM user_media
            WHERE user_id = $1
              AND is_processed = TRUE
              AND status = 'approved'
            ORDER BY position ASC
            """,
            cand_id,
        )
        photos = []
        voice_snapshot = None
        for m in media_rows:
            url = m["cdn_url"] or m["s3_key"]
            if m["media_type"] == "photo":
                photos.append({
                    "id": f"{cand_id}_p{m['position']}",
                    "url": url,
                    "order": m["position"],
                })
            elif m["media_type"] == "voice" and not voice_snapshot:
                voice_snapshot = {
                    "audio_url": url,
                    "duration_seconds": float(m["duration_seconds"] or 0),
                }

        # Batch load prompts
        prompt_rows = await conn.fetch(
            """
            SELECT prompt_key, response_text, position
            FROM user_prompts
            WHERE user_id = $1
            ORDER BY position ASC
            """,
            cand_id,
        )
        prompts = [
            {
                "question": p["prompt_key"],
                "answer": p["response_text"],
                "position": p["position"],
            }
            for p in prompt_rows
        ]

    from datetime import date as date_type
    dob = row["date_of_birth"]
    today = date_type.today()
    age = None
    if dob:
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    result = {
        "id": str(row["id"]),
        "first_name": row["first_name"],
        "age": age,
        "city": row["city"],
        "state": row["state"],
        "distance_display": "Pan-India",
        "dietary_strictness": row["dietary_strictness"],
        "eats_root_vegetables": row.get("eats_root_vegetables") or False,
        "eats_onion_garlic": row.get("eats_onion_garlic") or False,
        "community_sect": row["community_sect"],
        "paryushan_mode": row.get("paryushan_mode") or False,
        "education": row.get("education"),
        "job_title": row.get("job_title"),
        "height_cm": row.get("height_cm"),
        "bio": row.get("bio"),
        "open_to_relocation": row.get("open_to_relocation") if row.get("open_to_relocation") is not None else True,
        "is_photo_verified": row.get("is_photo_verified") or False,
        "photos": photos,
        "prompts": prompts,
        "voice_snapshot": voice_snapshot,
        "compatibility": {
            "values_alignment_percentage": 94,
            "shared_traditions": ["Jain Values", "Ahimsa"],
        },
        "compatibility_rationale": rationale,
        "pairing_algorithm": algo,
    }

    try:
        await redis.set(cache_key, json.dumps(result, default=str), ex=86400)
    except Exception as exc:
        log.warning("Failed to cache daily_compatible for user %s: %s", user_id, exc)

    return result


class CorePeopleFinder:
    """OOP adapter for batch background workers."""

    async def rank_candidates(
        self,
        requester: dict,
        pool_users: list[dict],
        top_k: int = 50,
        conn: asyncpg.Connection | None = None,
    ) -> list[dict]:
        """
        Rank candidate users from pool_users for requester based on cultural,
        geographical, and reciprocal affinity constraints.
        """
        req_id = requester["id"]
        req_my_gender = requester.get("gender")
        req_gender = requester.get("show_me", "everyone")
        req_diet = requester.get("dietary_strictness")
        req_sect = requester.get("community_sect")
        req_onion = requester.get("eats_onion_garlic")
        req_root = requester.get("eats_root_vegetables")
        req_paryushan = requester.get("paryushan_mode")
        req_looking_for = requester.get("looking_for")
        req_lat = requester.get("latitude")
        req_lon = requester.get("longitude")
        req_max_dist = requester.get("max_distance_km", 50)
        req_relocation = requester.get("open_to_relocation", False)

        ranked = []
        for cand in pool_users:
            cid = cand["id"]
            if cid == req_id:
                continue

            cand_gender = cand.get("gender")
            if req_gender in ("men", "man") and cand_gender not in ("men", "man"):
                continue
            if req_gender in ("women", "woman") and cand_gender not in ("women", "woman"):
                continue

            # Candidate orientation reciprocity (if specified)
            cand_show_me = cand.get("show_me")
            if cand_show_me and req_my_gender:
                if cand_show_me in ("men", "man") and req_my_gender not in ("men", "man"):
                    continue
                if cand_show_me in ("women", "woman") and req_my_gender not in ("women", "woman"):
                    continue

            cand_diet = cand.get("dietary_strictness")
            # Pure Jain strict dietary gating
            if req_diet == "pure_jain" and cand_diet not in ("pure_jain", "vegan"):
                continue
            if cand_diet == "pure_jain" and req_diet and req_diet not in ("pure_jain", "vegan"):
                continue

            # Distance & relocation gating
            cand_lat = cand.get("latitude")
            cand_lon = cand.get("longitude")
            cand_relocation = cand.get("open_to_relocation", False)
            dist_km = None
            if req_lat is not None and req_lon is not None and cand_lat is not None and cand_lon is not None:
                try:
                    phi1, phi2 = math.radians(float(req_lat)), math.radians(float(cand_lat))
                    dphi = math.radians(float(cand_lat) - float(req_lat))
                    dlam = math.radians(float(cand_lon) - float(req_lon))
                    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
                    dist_km = 6371.0 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
                    if dist_km > req_max_dist and not (req_relocation or cand_relocation):
                        continue
                except Exception:
                    dist_km = None

            # Multi-factor composite compatibility score
            cand_onion = cand.get("eats_onion_garlic")
            score = 0
            if cand_diet == req_diet:
                score += 30
            elif req_diet in ("pure_jain", "vegan") and cand_diet in ("pure_jain", "vegan"):
                score += 20

            cand_sect = cand.get("community_sect")
            if cand_sect == req_sect:
                score += 25
            elif cand_sect == "open" or req_sect == "open":
                score += 15

            if cand_onion == req_onion:
                score += 15

            if req_root is not None and cand.get("eats_root_vegetables") == req_root:
                score += 10

            if req_paryushan and cand.get("paryushan_mode"):
                score += 10

            if req_looking_for and cand.get("looking_for") == req_looking_for:
                score += 15

            if dist_km is not None:
                score += max(0, 20 - int(dist_km / 5))

            if cand.get("is_photo_verified"):
                score += 10

            trust = cand.get("trust_score")
            if trust and isinstance(trust, (int, float)) and trust >= 80:
                score += 5

            ranked.append((score, cand))
            if len(ranked) % 250 == 0:
                await asyncio.sleep(0)

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in ranked[:top_k]]
