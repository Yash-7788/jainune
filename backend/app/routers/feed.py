"""
Feed router — BRRE-powered discovery feed + Daily Compatible endpoint.

GET  /v1/feed                   → paginated ranked profile batch
GET  /v1/feed/daily-compatible  → today's stable-marriage pairing
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.models.schemas.feed import DailyCompatibleResponse, FeedResponse
from app.services.core_people_finder import (
    fetch_daily_compatible,
    fetch_recommended_feed,
    _filter_current_feed_candidates,
)

router = APIRouter(prefix="/v1/feed", tags=["feed"])


class CachedFeedValidationRequest(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


@router.post("/validate-candidates", summary="Revalidate locally cached feed cards")
async def validate_cached_feed_candidates(
    body: CachedFeedValidationRequest,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    """Return cached candidate IDs that remain visible and actionable for this user."""
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    await sliding_window_rate_limit(f"ratelimit:feed:validate:{user_id}", 20, 60, redis)
    candidates = [{"id": str(candidate_id)} for candidate_id in body.candidate_ids]
    eligible = await _filter_current_feed_candidates(user_id, candidates, db)
    return {"eligible_ids": [candidate["id"] for candidate in eligible]}


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
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))

    if current_user.get("onboarding_completed") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding must be completed before accessing discovery feed.",
        )

    # Rate limit: 20 feed requests per minute per user (SECURITY.md 10.1)
    await sliding_window_rate_limit(f"ratelimit:feed:{user_id}", 20, 60, redis)

    # Single-roundtrip feed architecture: delegate Redis pop + lazy DB fallback to fetch_recommended_feed
    result = await fetch_recommended_feed(
        user_id=user_id,
        user_data=dict(current_user),
        db=db,
        redis=redis,
        limit=limit,
        force_refresh=refresh,
    )

    # Strip internal scoring fields before returning
    for c in result.get("candidates", []):
        if isinstance(c, dict):
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

    - Reads from `daily_compatible:{user_id}` Redis cache (TTL aligned with midnight IST)
    - Falls back to top BRRE reciprocal result when nightly job hasn't run
    - Lock resets at midnight IST; users cannot skip their Daily Compatible
    """
    user_id = uuid.UUID(str(current_user.get("user_id") or current_user.get("id")))
    await sliding_window_rate_limit(f"ratelimit:feed:daily:{user_id}", 30, 60, redis)
    candidate = await fetch_daily_compatible(user_id=user_id, db=db, redis=redis)

    # Compute lock_until = next midnight IST as ISO string
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    midnight_ist = (now_ist + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    locked_until = midnight_ist.isoformat()

    if candidate and isinstance(candidate, dict):
        candidate.pop("_behavioral_affinity", None)
        candidate.pop("_cultural_score", None)

    return DailyCompatibleResponse(
        candidate=candidate,
        pairing_algorithm=candidate.get("pairing_algorithm", "brre_fallback") if candidate else "none",
        locked_until=locked_until,
    )
