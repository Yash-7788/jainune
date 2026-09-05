"""
Feed router — BRRE-powered discovery feed + Daily Compatible endpoint.

GET  /v1/feed                   → paginated ranked profile batch
GET  /v1/feed/daily-compatible  → today's stable-marriage pairing
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.models.schemas.feed import DailyCompatibleResponse, FeedResponse
from app.services.core_people_finder import (
    fetch_daily_compatible,
    fetch_recommended_feed,
)

router = APIRouter(prefix="/v1/feed", tags=["feed"])


@router.get("", response_model=FeedResponse, summary="Get discovery feed")
async def get_feed(
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
    limit: int = Query(default=15, ge=1, le=50),
    refresh: bool = Query(default=False, description="Force bypass of 5-min session cache"),
) -> FeedResponse:
    """
    Returns up to `limit` ranked candidate profiles via the 5-stage BRRE pipeline.

    - Reads 5-min Redis session cache when available (sub-1ms)
    - Falls back to PostGIS + pgvector SQL pipeline on cache miss (~25ms)
    - Increments `impressions_last_48h` for shown profiles (Dignity Engine)
    """
    user_id = uuid.UUID(str(current_user["id"]))

    # Rate limit: 20 feed requests per minute per user (SECURITY.md 10.1)
    await sliding_window_rate_limit(f"ratelimit:feed:{user_id}", 20, 60, redis)

    # Enrich current_user with location + behavior vector for pipeline
    async with db.acquire() as conn:
        extra = await conn.fetchrow(
            """
            SELECT u.location, b.revealed_preference_vector
            FROM users u
            LEFT JOIN user_behavior_vectors b ON u.id = b.user_id
            WHERE u.id = $1
            """,
            user_id,
        )

    if not extra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user_data = dict(current_user)
    user_data["location"] = extra["location"]
    user_data["revealed_preference_vector"] = extra["revealed_preference_vector"]

    result = await fetch_recommended_feed(
        user_id=user_id,
        user_data=user_data,
        db=db,
        redis=redis,
        limit=limit,
        force_refresh=refresh,
    )

    # Strip internal scoring fields before returning
    for c in result["candidates"]:
        c.pop("_behavioral_affinity", None)
        c.pop("_cultural_score", None)

    return FeedResponse(**result)


@router.get(
    "/daily-compatible",
    response_model=DailyCompatibleResponse,
    summary="Get today's Daily Compatible match",
)
async def get_daily_compatible(
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> DailyCompatibleResponse:
    """
    Returns today's Gale-Shapley stable-marriage pairing.

    - Reads from `daily_compatible:{user_id}` Redis key set by nightly worker
    - Falls back to top BRRE reciprocal result when nightly job hasn't run
    - Lock resets at midnight IST; users cannot skip their Daily Compatible
    """
    user_id = uuid.UUID(str(current_user["id"]))
    candidate = await fetch_daily_compatible(user_id=user_id, db=db, redis=redis)

    # Compute lock_until = next midnight IST as ISO string
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    midnight_ist = (now_ist + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    locked_until = midnight_ist.isoformat()

    return DailyCompatibleResponse(
        candidate=candidate,
        pairing_algorithm=candidate.get("pairing_algorithm", "brre_fallback") if candidate else "none",
        locked_until=locked_until,
    )
