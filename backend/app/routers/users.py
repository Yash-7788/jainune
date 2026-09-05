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

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.core.database import get_pool
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.models.schemas.payment import SubscriptionStatusResponse, SubscriptionTier
from app.models.schemas.user import UserProfileResponse, UpdatePromptsBody

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
    fcm_token: Optional[str] = Field(None, max_length=256)
    model_config = {"extra": "forbid"}


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
    "jainune_plus": {
        "daily_likes": None,  # unlimited intentional likes
        "super_likes": 10,
        "can_see_who_liked": True,
    },
}


async def _get_user_row(user_id: UUID, conn: asyncpg.Connection) -> dict:
    row = await conn.fetchrow(
        """
        SELECT
            id, phone_number, email, auth_provider, first_name, date_of_birth, gender, show_me,
            looking_for, city, state, max_distance_km, open_to_relocation,
            dietary_strictness, eats_root_vegetables, eats_onion_garlic,
            community_sect, paryushan_mode, job_title, company, education,
            height_cm, bio, subscription_tier, is_photo_verified, account_status,
            onboarding_completed, super_connect_credits,
            COALESCE((
                SELECT json_agg(
                    json_build_object(
                        'id', m.id,
                        'media_type', m.media_type,
                        'cdn_url', m.cdn_url,
                        'position', m.position,
                        'status', m.status,
                        'is_processed', m.is_processed
                    ) ORDER BY m.position
                )
                FROM user_media m
                WHERE m.user_id = users.id AND m.status != 'rejected'
            ), '[]'::json) AS photos,
            COALESCE((
                SELECT json_agg(
                    json_build_object(
                        'id', p.id,
                        'prompt_key', p.prompt_key,
                        'response_text', p.response_text,
                        'position', p.position
                    ) ORDER BY p.position
                )
                FROM user_prompts p
                WHERE p.user_id = users.id
            ), '[]'::json) AS prompts
        FROM users
        WHERE id = $1 AND account_status != 'deleted'
        """,
        user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    data = dict(row)
    # Parse json_agg strings if returned as string
    import json
    if isinstance(data.get("photos"), str):
        data["photos"] = json.loads(data["photos"])
    if isinstance(data.get("prompts"), str):
        data["prompts"] = json.loads(data["prompts"])
    return data


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
        data = await _get_user_row(current_user["user_id"], conn)
    return data


@router.get("/me/prompts")
async def get_my_prompts(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Fetch user's current profile prompts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, prompt_key, response_text, position FROM user_prompts WHERE user_id = $1 ORDER BY position",
            current_user["user_id"],
        )
    return {"prompts": [dict(r) for r in rows]}


@router.put("/me/prompts")
async def update_my_prompts(
    body: UpdatePromptsBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Update profile prompts (1 to 3 items)."""
    user_id = current_user["user_id"]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM user_prompts WHERE user_id = $1", user_id)
            for p in body.prompts:
                await conn.execute(
                    "INSERT INTO user_prompts (user_id, prompt_key, response_text, position) VALUES ($1, $2, $3, $4)",
                    user_id, p.prompt_key, p.response_text, p.position,
                )
    return {"success": True, "message": "Prompts updated successfully"}


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
    """Return current subscription tier, validity, and remaining daily/super likes."""
    from app.services.payment_service import get_effective_user_tier
    from datetime import datetime, timezone
    from app.core.redis import get_redis

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, subscription_tier, subscription_valid_until, super_connect_credits
            FROM users WHERE id = $1
            """,
            current_user["user_id"],
        )
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")

        tier = await get_effective_user_tier(current_user["user_id"], conn)

    valid_until = row["subscription_valid_until"]
    limits = _TIER_LIMITS.get(tier, _TIER_LIMITS["free"])

    # Calculate remaining likes today
    daily_likes_remaining = limits["daily_likes"]
    if daily_likes_remaining is not None:
        try:
            r = get_redis()
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            used = await r.get(f"daily_likes:{current_user['user_id']}:{today_str}")
            used_int = int(used) if used else 0
            daily_likes_remaining = max(0, daily_likes_remaining - used_int)
        except Exception:
            pass

    return {
        "user_id": row["id"],
        "tier": SubscriptionTier(tier),
        "valid_until": valid_until,
        "daily_likes_remaining": daily_likes_remaining,
        "super_likes_remaining": row["super_connect_credits"] if row.get("super_connect_credits") is not None else limits["super_likes"],
        "can_see_who_liked": limits["can_see_who_liked"],
    }


class FCMTokenBody(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=256)


@router.post("/me/fcm-token", status_code=status.HTTP_200_OK)
async def set_fcm_token(
    body: FCMTokenBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Register or update device FCM push notification token."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET fcm_token = $1, updated_at = NOW() WHERE id = $2",
            body.fcm_token,
            current_user["user_id"],
        )
    return {"success": True, "message": "FCM token registered"}


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(
    hard_delete: bool = Query(True, description="When True, immediately and permanently purges all user rows, media from S3, and Redis caches to free memory and disk."),
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis = Depends(get_redis),
):
    """
    Account deletion endpoint:
    - hard_delete=True (default): Physically deletes all user records across all tables,
      deletes uploaded photos/voice notes from Amazon S3, and purges Redis feed & quota caches.
    - hard_delete=False: Anonymizes PII and marks account_status='deleted'.
    """
    from app.services.account_service import purge_user_account, soft_delete_user_account

    user_id = current_user["user_id"]
    async with pool.acquire() as conn:
        if hard_delete:
            result = await purge_user_account(user_id, conn, redis)
            return {
                "success": True,
                "data": {
                    "message": "Your account, personal data, and uploaded media have been permanently deleted.",
                    "status": "purged",
                },
                "error": None,
            }
        else:
            result = await soft_delete_user_account(user_id, conn, redis)
            return {
                "success": True,
                "data": {
                    "message": "Your account has been deactivated and scheduled for removal.",
                    "status": "deactivated",
                },
                "error": None,
            }


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
                    FROM user_media m
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
    from app.core.redis import get_redis
    from app.core.security import sliding_window_rate_limit
    from app.services.dignity_engine import file_report

    reporter_id = current_user["user_id"]

    # Rate limit: max 5 reports per 24h per reporter (Dignity Engine abuse prevention)
    try:
        redis = get_redis()
        await sliding_window_rate_limit(f"ratelimit:report:{reporter_id}", 5, 86400, redis)
    except HTTPException:
        raise
    except Exception:
        pass  # Fallback if Redis unavailable

    try:
        result = await file_report(
            reporter_id=reporter_id,
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


# ---------------------------------------------------------------------------
# User blocking & account pause
# ---------------------------------------------------------------------------


class BlockUserBody(BaseModel):
    reason: Optional[str] = Field(None, max_length=128)


@router.post("/{user_id}/block", status_code=status.HTTP_200_OK)
async def block_user(
    user_id: UUID,
    body: Optional[BlockUserBody] = None,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Block a user: terminates active matches/chats and excludes from feed."""
    blocker_id = current_user["user_id"]
    if str(blocker_id) == str(user_id):
        raise HTTPException(status_code=400, detail="Cannot block yourself")

    reason = body.reason if body else None
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO user_blocks (blocker_id, blocked_id, reason)
                VALUES ($1, $2, $3)
                ON CONFLICT (blocker_id, blocked_id) DO UPDATE
                   SET reason = EXCLUDED.reason, created_at = NOW()
                """,
                blocker_id, user_id, reason,
            )
            # Terminate mutual match if active
            await conn.execute(
                """
                UPDATE matches
                SET status = 'unmatched', updated_at = NOW()
                WHERE (user_id_1 = $1 AND user_id_2 = $2)
                   OR (user_id_1 = $2 AND user_id_2 = $1)
                """,
                blocker_id, user_id,
            )
            await conn.execute(
                """
                UPDATE chats
                SET is_unmatched = TRUE, updated_at = NOW()
                WHERE (participant_1_id = $1 AND participant_2_id = $2)
                   OR (participant_1_id = $2 AND participant_2_id = $1)
                """,
                blocker_id, user_id,
            )

    from app.core.redis import get_redis
    try:
        r = get_redis()
        await r.delete(f"feed:cache:{blocker_id}")
        await r.delete(f"feed:cache:{user_id}")
    except Exception:
        pass

    return {"success": True, "message": "User blocked and matches removed."}


@router.delete("/{user_id}/block", status_code=status.HTTP_200_OK)
async def unblock_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Unblock a user."""
    blocker_id = current_user["user_id"]
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_blocks WHERE blocker_id = $1 AND blocked_id = $2",
            blocker_id, user_id,
        )
    return {"success": True, "message": "User unblocked."}


@router.get("/me/blocks", status_code=status.HTTP_200_OK)
async def list_blocked_users(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List all blocked users."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT blocked_id, reason, created_at FROM user_blocks WHERE blocker_id = $1 ORDER BY created_at DESC",
            current_user["user_id"],
        )
    return {"blocked_users": [dict(r) for r in rows]}


@router.post("/me/pause", status_code=status.HTTP_200_OK)
async def pause_account(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Pause profile from discovery feed."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_paused = TRUE, updated_at = NOW() WHERE id = $1", current_user["user_id"])
    return {"success": True, "is_paused": True, "message": "Profile paused from discovery feed."}


@router.post("/me/unpause", status_code=status.HTTP_200_OK)
async def unpause_account(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Unpause profile to resume discovery feed."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_paused = FALSE, updated_at = NOW() WHERE id = $1", current_user["user_id"])
    return {"success": True, "is_paused": False, "message": "Profile unpaused."}
