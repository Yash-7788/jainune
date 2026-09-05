"""
Users router — profile read and update.

GET  /v1/users/me          → fetch own full profile
PATCH /v1/users/me         → update mutable fields
GET  /v1/users/me/subscription → subscription tier + limits
DELETE /v1/users/me        → GDPR/DPDP account deletion (soft-delete)
GET  /v1/users/{user_id}/public → public card view (for open profiles)
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.database import get_pool
from app.core.security import get_current_user
from app.models.schemas.payment import SubscriptionStatusResponse, SubscriptionTier
from app.models.schemas.user import UserProfileResponse

import asyncpg

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/users", tags=["Users"])


# ---------------------------------------------------------------------------
# Update body — all fields optional
# ---------------------------------------------------------------------------


class UpdateProfileBody(BaseModel):
    first_name: Optional[str] = Field(None, min_length=2, max_length=64)
    bio: Optional[str] = Field(None, max_length=500)
    job_title: Optional[str] = Field(None, max_length=128)
    company: Optional[str] = Field(None, max_length=128)
    education: Optional[str] = Field(None, max_length=128)
    height_cm: Optional[int] = Field(None, ge=120, le=250)
    max_distance_km: Optional[int] = Field(None, ge=5, le=200)
    open_to_relocation: Optional[bool] = None
    show_me: Optional[str] = Field(None, pattern="^(men|women|everyone)$")
    looking_for: Optional[str] = Field(
        None, pattern="^(marriage|long_term|figuring_out)$"
    )


# ---------------------------------------------------------------------------
# Subscription tier limits
# ---------------------------------------------------------------------------

_TIER_LIMITS = {
    "free": {
        "daily_likes": 10,
        "super_likes": 0,
        "can_see_who_liked": False,
    },
    "gold": {
        "daily_likes": 50,
        "super_likes": 5,
        "can_see_who_liked": True,
    },
    "platinum": {
        "daily_likes": None,  # unlimited
        "super_likes": 10,
        "can_see_who_liked": True,
    },
}


async def _get_user_row(user_id: UUID, conn: asyncpg.Connection) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT
            id, phone_number, first_name, date_of_birth, gender, show_me,
            looking_for, city, state, max_distance_km, open_to_relocation,
            dietary_strictness, eats_root_vegetables, eats_onion_garlic,
            community_sect, paryushan_mode, job_title, company, education,
            height_cm, bio, subscription_tier, is_photo_verified, account_status
        FROM users
        WHERE id = $1 AND account_status != 'deleted'
        """,
        user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return the authenticated user's full profile."""
    async with pool.acquire() as conn:
        row = await _get_user_row(current_user["user_id"], conn)
    return dict(row)


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    body: UpdateProfileBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Patch mutable profile fields.
    Only fields explicitly set (not None) are written to the DB.
    """
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    # Build dynamic SET clause
    set_clauses = [f"{col} = ${i + 2}" for i, col in enumerate(updates)]
    values = list(updates.values())
    query = f"""
        UPDATE users
           SET {', '.join(set_clauses)}, updated_at = NOW()
         WHERE id = $1
           AND account_status != 'deleted'
    """

    async with pool.acquire() as conn:
        result = await conn.execute(query, current_user["user_id"], *values)
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="User not found")
        row = await _get_user_row(current_user["user_id"], conn)

    return dict(row)


@router.get("/me/subscription", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return current subscription tier, validity, and feature limits."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, subscription_tier, subscription_valid_until
            FROM users WHERE id = $1
            """,
            current_user["user_id"],
        )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    from datetime import datetime, timezone

    tier: str = row["subscription_tier"] or "free"
    valid_until = row["subscription_valid_until"]

    # If subscription expired, fall back to free limits
    if valid_until and valid_until < datetime.now(tz=timezone.utc) and tier != "free":
        tier = "free"

    limits = _TIER_LIMITS[tier]
    return {
        "user_id": row["id"],
        "tier": SubscriptionTier(tier),
        "valid_until": valid_until,
        "daily_likes_remaining": limits["daily_likes"],
        "super_likes_remaining": limits["super_likes"],
        "can_see_who_liked": limits["can_see_who_liked"],
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Soft-delete: sets account_status='deleted', blanks PII fields.
    Hard deletion runs via a scheduled worker after 30-day retention window.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
               SET account_status   = 'deleted',
                   first_name       = 'Deleted User',
                   phone_number     = 'DELETED_' || id::text,
                   bio              = NULL,
                   job_title        = NULL,
                   company          = NULL,
                   education        = NULL,
                   deleted_at       = NOW(),
                   updated_at       = NOW()
             WHERE id = $1
            """,
            current_user["user_id"],
        )


@router.get("/{user_id}/public")
async def get_public_profile(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Public card view — only fields visible to other users.
    Used by the chat/profile deep-link flow.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.id,
                u.first_name,
                u.date_of_birth,
                u.gender,
                u.city,
                u.state,
                u.bio,
                u.job_title,
                u.company,
                u.education,
                u.height_cm,
                u.community_sect,
                u.dietary_strictness,
                u.subscription_tier,
                u.is_photo_verified,
                ARRAY(
                    SELECT m.cdn_url
                    FROM media m
                    WHERE m.user_id = u.id
                      AND m.media_type = 'photo'
                      AND m.status = 'approved'
                    ORDER BY m.position
                ) AS photos,
                ARRAY(
                    SELECT json_build_object('key', p.prompt_key, 'response', p.response_text)
                    FROM user_prompts p
                    WHERE p.user_id = u.id
                    ORDER BY p.position
                ) AS prompts
            FROM users u
            WHERE u.id = $1
              AND u.account_status = 'active'
            """,
            user_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    from datetime import date

    dob: date = row["date_of_birth"]
    age = None
    if dob:
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    return {
        "id": row["id"],
        "first_name": row["first_name"],
        "age": age,
        "gender": row["gender"],
        "city": row["city"],
        "state": row["state"],
        "bio": row["bio"],
        "job_title": row["job_title"],
        "company": row["company"],
        "education": row["education"],
        "height_cm": row["height_cm"],
        "community_sect": row["community_sect"],
        "dietary_strictness": row["dietary_strictness"],
        "subscription_tier": row["subscription_tier"],
        "is_photo_verified": row["is_photo_verified"],
        "photos": row["photos"] or [],
        "prompts": [dict(p) for p in (row["prompts"] or [])],
    }


# ---------------------------------------------------------------------------
# Report a user
# ---------------------------------------------------------------------------


class ReportUserBody(BaseModel):
    reason: str = Field(
        ...,
        pattern="^(harassment|fake_profile|inappropriate_content|hate_speech|spam|underage|scam|other)$",
    )
    detail: Optional[str] = Field(None, max_length=500)


@router.post("/{user_id}/report", status_code=status.HTTP_201_CREATED)
async def report_user(
    user_id: UUID,
    body: ReportUserBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """File a report against another user."""
    from app.services.dignity_engine import file_report

    try:
        result = await file_report(
            reporter_id=current_user["user_id"],
            reported_id=user_id,
            reason=body.reason,
            detail=body.detail,
            pool=pool,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result


# ---------------------------------------------------------------------------
# Award dignity badge
# ---------------------------------------------------------------------------


class AwardBadgeBody(BaseModel):
    badge: str = Field(
        ...,
        pattern="^(punctual|respects_diet|real_photos|great_conversation|courteous)$",
    )


@router.post("/{user_id}/badge", status_code=status.HTTP_201_CREATED)
async def award_badge(
    user_id: UUID,
    body: AwardBadgeBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Award a dignity badge to a user you were matched with."""
    from app.services.dignity_engine import award_badge as _award_badge

    try:
        result = await _award_badge(
            from_user_id=current_user["user_id"],
            to_user_id=user_id,
            badge=body.badge,
            pool=pool,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result
