"""
Admin moderation router — Phase 6.

All endpoints require admin role verified against admin_users table.
No public access; deployed behind an internal network rule in production.

Endpoints:
  GET  /v1/admin/users                → list users with filters
  GET  /v1/admin/users/{id}           → full user detail
  POST /v1/admin/users/{id}/ban       → permanent ban
  POST /v1/admin/users/{id}/suspend   → temporary suspend
  POST /v1/admin/users/{id}/reinstate → lift suspension / ban
  GET  /v1/admin/reports              → list unresolved reports
  POST /v1/admin/reports/{id}/resolve → mark report resolved
  GET  /v1/admin/media/pending        → list media awaiting manual review
  POST /v1/admin/media/{id}/approve   → approve media
  POST /v1/admin/media/{id}/reject    → reject media
  GET  /v1/admin/stats                → dashboard metrics
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

import asyncpg

from app.core.database import get_pool
from app.core.redis import get_redis
from app.core.security import sliding_window_rate_limit
from app.dependencies import get_current_user, require_admin, require_superadmin
from app.services.messaging_service import _mask_phone
from app.services.dignity_engine import recompute_trust_score

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class BanBody(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class SuspendBody(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)
    suspend_until_days: int = Field(default=7, ge=1, le=365)


class ResolveReportBody(BaseModel):
    action_taken: str = Field(
        ...,
        pattern="^(no_action|warned|suspended|banned)$",
        description="Action taken against reported user",
    )
    notes: Optional[str] = Field(None, max_length=1000)


class RejectMediaBody(BaseModel):
    reason: str = Field(..., pattern="^(nudity|violence|spam|fake|other)$")


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_users(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|suspended|banned|pending_review)$"),
    search: Optional[str] = Query(None, max_length=64, description="Search by phone or name"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List users with optional status filter and name/phone search."""
    conditions = ["account_status != 'deleted'"]
    params: list = []

    status_filter_val = status_filter if isinstance(status_filter, str) else None
    search_val = search if isinstance(search, str) else None
    limit_val = limit if isinstance(limit, int) else getattr(limit, "default", 25)
    offset_val = offset if isinstance(offset, int) else getattr(offset, "default", 0)

    if status_filter_val:
        params.append(status_filter_val)
        conditions.append(f"account_status = ${len(params)}")

    if search_val:
        escaped = search_val.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
        n = len(params)
        conditions.append(f"(first_name ILIKE ${n} OR phone_number ILIKE ${n})")

    where = " AND ".join(conditions)
    params.extend([limit_val, offset_val])

    query = f"""
        SELECT id, phone_number, first_name, account_status,
               subscription_tier, trust_score, created_at
        FROM users
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM users WHERE {where}",
            *params[:-2],
        )

    users_list = []
    is_superadmin = admin.get("admin_role") == "superadmin"
    for r in rows:
        d = dict(r)
        if not is_superadmin and d.get("phone_number"):
            d["phone_number"] = _mask_phone(d["phone_number"])
        users_list.append(d)

    return {
        "users": users_list,
        "total": total,
        "limit": limit_val,
        "offset": offset_val,
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: UUID,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Full user record including PII — for moderator review with role-based redaction."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.*,
                (SELECT COUNT(*) FROM reports WHERE reported_id = u.id) AS report_count,
                (SELECT COUNT(*) FROM dignity_badges WHERE to_user_id = u.id) AS badge_count,
                (SELECT COUNT(*) FROM user_media WHERE user_id = u.id AND status = 'approved') AS media_count
            FROM users u
            WHERE u.id = $1
            """,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    res = dict(row)
    if admin.get("admin_role") != "superadmin":
        from app.services.messaging_service import _mask_phone, _mask_email
        if res.get("phone_number"):
            res["phone_number"] = _mask_phone(res["phone_number"])
        if res.get("email"):
            res["email"] = _mask_email(res["email"])
        for sensitive_col in (
            "revealed_preference_vector",
            "behavior_vector",
            "income",
            "income_range",
            "annual_income",
        ):
            res.pop(sensitive_col, None)
    return res


@router.post("/users/{user_id}/ban", status_code=status.HTTP_200_OK)
async def ban_user(
    user_id: UUID,
    body: BanBody,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Permanently ban a user. Logs the action in admin_audit_log and revokes active sessions."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                """
                UPDATE users
                   SET account_status = 'banned', updated_at = NOW()
                 WHERE id = $1
                """,
                user_id,
            )
            if res == "UPDATE 0":
                raise HTTPException(status_code=404, detail="User not found")

            await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)

            await conn.execute(
                """
                INSERT INTO admin_audit_log
                    (admin_user_id, target_user_id, action, reason)
                VALUES ($1, $2, 'ban', $3)
                """,
                admin["user_id"],
                user_id,
                body.reason,
            )

    try:
        r = get_redis()
        await r.delete(f"user:session:{user_id}", f"feed:cache:{user_id}")
    except Exception:
        pass

    return {"banned": True, "user_id": user_id}


@router.post("/users/{user_id}/suspend", status_code=status.HTTP_200_OK)
async def suspend_user(
    user_id: UUID,
    body: SuspendBody,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Temporarily suspend a user for N days."""
    from datetime import datetime, timedelta, timezone

    suspend_until = datetime.now(tz=timezone.utc) + timedelta(days=body.suspend_until_days)

    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                """
                UPDATE users
                   SET account_status   = 'suspended',
                       suspend_until    = $1,
                       updated_at       = NOW()
                 WHERE id = $2
                """,
                suspend_until,
                user_id,
            )
            if res == "UPDATE 0":
                raise HTTPException(status_code=404, detail="User not found")

            await conn.execute(
                """
                INSERT INTO admin_audit_log
                    (admin_user_id, target_user_id, action, reason)
                VALUES ($1, $2, 'suspend', $3)
                """,
                admin["user_id"],
                user_id,
                body.reason,
            )

    try:
        r = get_redis()
        await r.delete(f"user:session:{user_id}")
    except Exception:
        pass

    return {"suspended": True, "user_id": user_id, "until": suspend_until}


@router.post("/users/{user_id}/reinstate", status_code=status.HTTP_200_OK)
async def reinstate_user(
    user_id: UUID,
    admin: dict = Depends(require_superadmin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Lift a suspension or ban. Superadmin only."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                """
                UPDATE users
                   SET account_status = 'active',
                       suspend_until  = NULL,
                       updated_at     = NOW()
                 WHERE id = $1
                """,
                user_id,
            )
            if res == "UPDATE 0":
                raise HTTPException(status_code=404, detail="User not found")

            await conn.execute(
                """
                INSERT INTO admin_audit_log
                    (admin_user_id, target_user_id, action, reason)
                VALUES ($1, $2, 'reinstate', 'Manual reinstate by superadmin')
                """,
                admin["user_id"],
                user_id,
            )
    return {"reinstated": True, "user_id": user_id}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/reports")
async def list_reports(
    resolved: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List reports, defaulting to unresolved."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                r.id, r.reporter_id, r.reported_id, r.reason,
                r.detail, r.resolved, r.created_at,
                u.first_name AS reported_name,
                u.phone_number AS reported_phone
            FROM reports r
            JOIN users u ON u.id = r.reported_id
            WHERE r.resolved = $1
            ORDER BY r.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            resolved,
            limit,
            offset,
        )
    return {"reports": [dict(r) for r in rows]}


@router.post("/reports/{report_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_report(
    report_id: UUID,
    body: ResolveReportBody,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Mark a report as resolved and log the action taken."""
    async with pool.acquire() as conn:
        report = await conn.fetchrow(
            "SELECT reported_id FROM reports WHERE id = $1",
            report_id,
        )
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE reports
                   SET resolved         = TRUE,
                       resolved_by      = $1,
                       resolved_at      = NOW(),
                       resolution_notes = $2,
                       action_taken     = $3
                  WHERE id = $4
                """,
                admin["user_id"],
                body.notes,
                body.action_taken,
                report_id,
            )

            # Apply account action if suspension or ban decided
            if body.action_taken == "banned":
                await conn.execute(
                    "UPDATE users SET account_status = 'banned', updated_at = NOW() WHERE id = $1",
                    report["reported_id"],
                )
            elif body.action_taken == "suspended":
                from datetime import datetime, timedelta, timezone
                suspend_until = datetime.now(tz=timezone.utc) + timedelta(days=7)
                await conn.execute(
                    "UPDATE users SET account_status = 'suspended', suspend_until = $1, updated_at = NOW() WHERE id = $2",
                    suspend_until,
                    report["reported_id"],
                )

            await conn.execute(
                """
                INSERT INTO admin_audit_log
                    (admin_user_id, target_user_id, action, reason)
                VALUES ($1, $2, $3, $4)
                """,
                admin["user_id"],
                report["reported_id"],
                f"report_resolved:{body.action_taken}",
                body.notes or "",
            )

            # Recompute trust score for reported user inside the same transaction
            await recompute_trust_score(report["reported_id"], conn)

    return {"resolved": True, "report_id": report_id}


# ---------------------------------------------------------------------------
# Media moderation
# ---------------------------------------------------------------------------


@router.get("/media/pending")
async def list_pending_media(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List media items with status='pending' for manual review."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                m.id, m.user_id, m.media_type, m.cdn_url,
                m.status, m.created_at,
                u.first_name, u.phone_number
            FROM user_media m
            JOIN users u ON u.id = m.user_id
            WHERE m.status = 'pending'
            ORDER BY m.created_at ASC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return {"media": [dict(r) for r in rows]}


@router.post("/media/{media_id}/approve", status_code=status.HTTP_200_OK)
async def approve_media(
    media_id: UUID,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Manually approve a media item."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE user_media
               SET status      = 'approved',
                   reviewed_by = $1,
                   reviewed_at = NOW()
             WHERE id = $2 AND status = 'pending'
            """,
            admin["user_id"],
            media_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Media not found or not pending")
    return {"approved": True, "media_id": media_id}


@router.post("/media/{media_id}/reject", status_code=status.HTTP_200_OK)
async def reject_media(
    media_id: UUID,
    body: RejectMediaBody,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Manually reject a media item with a reason."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM user_media WHERE id = $1",
            media_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Media not found")

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE user_media
                   SET status           = 'rejected',
                       rejection_reason = $1,
                       reviewed_by      = $2,
                       reviewed_at      = NOW()
                 WHERE id = $3
                """,
                body.reason,
                admin["user_id"],
                media_id,
            )
            # Recompute trust score atomically with the rejection
            await recompute_trust_score(row["user_id"], conn)

    return {"rejected": True, "media_id": media_id, "reason": body.reason}


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_dashboard_stats(
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Key operational metrics for the admin dashboard."""
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE account_status = 'active')  AS active_users,
                (SELECT COUNT(*) FROM users WHERE account_status = 'suspended') AS suspended_users,
                (SELECT COUNT(*) FROM users WHERE account_status = 'banned')   AS banned_users,
                (SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24h') AS new_users_24h,
                (SELECT COUNT(*) FROM users WHERE subscription_tier = 'jainune_plus') AS jainune_plus_subscribers,
                (SELECT COUNT(*) FROM users WHERE subscription_tier = 'gold')  AS gold_subscribers,
                (SELECT COUNT(*) FROM users WHERE subscription_tier = 'platinum') AS platinum_subscribers,
                (SELECT COUNT(*) FROM users WHERE subscription_tier != 'free' AND subscription_valid_until > NOW()) AS active_paid_subscribers,
                (SELECT COUNT(*) FROM reports WHERE resolved = FALSE)          AS open_reports,
                (SELECT COUNT(*) FROM user_media WHERE status = 'pending')     AS pending_media,
                (SELECT COUNT(*) FROM matches WHERE created_at > NOW() - INTERVAL '24h') AS matches_24h
            """
        )
    return dict(stats)


# ---------------------------------------------------------------------------
# Promotional & Marketing Campaign Broadcast
# ---------------------------------------------------------------------------


class BroadcastCampaignBody(BaseModel):
    campaign_name: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(..., min_length=3, max_length=120)
    message: str = Field(..., min_length=5, max_length=1000)
    channels: list[str] = Field(default=["email"], description="List containing email, whatsapp, and/or sms")
    target_segment: str = Field(default="free", pattern="^(free|plus|all)$")
    offer_badge: Optional[str] = Field(None, max_length=40)
    cta_url: Optional[str] = Field(None, max_length=500, pattern=r"^https?://[a-zA-Z0-9.-]+.*$")
    limit: int = Field(default=500, ge=1, le=5000)


@router.post("/campaigns/broadcast", status_code=status.HTTP_200_OK)
async def trigger_campaign_broadcast(
    body: BroadcastCampaignBody,
    admin: dict = Depends(require_superadmin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Superadmin-only broadcast of promotional or festival campaign across channels with rate limiting."""
    try:
        r = get_redis()
        await sliding_window_rate_limit(f"ratelimit:admin:broadcast:{admin['user_id']}", 5, 3600, r)
    except Exception:
        pass

    from app.services.messaging_service import broadcast_promotional_campaign
    res = await broadcast_promotional_campaign(
        pool=pool,
        campaign_name=body.campaign_name,
        title=body.title,
        message=body.message,
        channels=body.channels,
        target_segment=body.target_segment,
        offer_badge=body.offer_badge,
        cta_url=body.cta_url,
        limit=body.limit,
    )
    log.info("Campaign %s triggered by superadmin %s: %s", body.campaign_name, admin["user_id"], res)
    return {"success": True, "results": res}


# ---------------------------------------------------------------------------
# Admin Refund Action (Last resort dispute resolution)
# ---------------------------------------------------------------------------


class AdminRefundBody(BaseModel):
    razorpay_payment_id: str = Field(..., pattern=r"^(pay|order)_[a-zA-Z0-9_-]+$", min_length=5, max_length=64)
    reason: str = Field(..., min_length=3, max_length=256)
    amount_paise: Optional[int] = Field(None, ge=100)


@router.post("/subscriptions/refund", status_code=status.HTTP_200_OK)
async def admin_refund_subscription(
    body: AdminRefundBody,
    admin: dict = Depends(require_superadmin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Superadmin-authorized refund. Initiates gateway refund and immediately revokes
    the user's subscription access back to free tier.
    """
    try:
        r = get_redis()
        await sliding_window_rate_limit(f"ratelimit:admin:refund:{admin['user_id']}", 20, 3600, r)
    except Exception:
        pass

    from app.services import payment_service
    res = await payment_service.initiate_refund(
        payment_id=body.razorpay_payment_id,
        amount_paise=body.amount_paise,
        reason=f"admin_action: {body.reason}",
        pool=pool,
    )
    log.info("Superadmin %s initiated refund for payment %s", admin["user_id"], body.razorpay_payment_id)
    return res


