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
from app.core.security import get_current_user
from app.services.dignity_engine import recompute_trust_score

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Admin auth dependency
# ---------------------------------------------------------------------------


async def require_admin(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Verify caller has an admin_users row with role in (superadmin, moderator)."""
    async with pool.acquire() as conn:
        role = await conn.fetchval(
            "SELECT role FROM admin_users WHERE user_id = $1",
            current_user["user_id"],
        )
    if role not in ("superadmin", "moderator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    current_user["admin_role"] = role
    return current_user


def require_superadmin(admin: dict = Depends(require_admin)) -> dict:
    if admin.get("admin_role") != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return admin


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
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, description="Search by phone or name"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List users with optional status filter and name/phone search."""
    conditions = ["account_status != 'deleted'"]
    params: list = []

    if status_filter:
        params.append(status_filter)
        conditions.append(f"account_status = ${len(params)}")

    if search:
        params.append(f"%{search}%")
        n = len(params)
        conditions.append(f"(first_name ILIKE ${n} OR phone_number ILIKE ${n})")

    where = " AND ".join(conditions)
    params.extend([limit, offset])

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

    return {
        "users": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: UUID,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Full user record including PII — for moderator review."""
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
    return dict(row)


@router.post("/users/{user_id}/ban", status_code=status.HTTP_200_OK)
async def ban_user(
    user_id: UUID,
    body: BanBody,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Permanently ban a user. Logs the action in admin_audit_log."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE users
                   SET account_status = 'banned', updated_at = NOW()
                 WHERE id = $1
                """,
                user_id,
            )
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
            await conn.execute(
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
            await conn.execute(
                """
                UPDATE users
                   SET account_status = 'active',
                       suspend_until  = NULL,
                       updated_at     = NOW()
                 WHERE id = $1
                """,
                user_id,
            )
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
                       resolution_notes = $2
                 WHERE id = $3
                """,
                admin["user_id"],
                body.notes,
                report_id,
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

        # Recompute trust score for reported user
        async with conn.transaction():
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

        await conn.execute(
            """
            UPDATE user_media
               SET status         = 'rejected',
                   rejection_reason = $1,
                   reviewed_by    = $2,
                   reviewed_at    = NOW()
             WHERE id = $3
            """,
            body.reason,
            admin["user_id"],
            media_id,
        )

        # Recompute trust score (rejected photo = lower score)
        async with conn.transaction():
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
                (SELECT COUNT(*) FROM users WHERE subscription_tier = 'gold')  AS gold_subscribers,
                (SELECT COUNT(*) FROM users WHERE subscription_tier = 'platinum') AS platinum_subscribers,
                (SELECT COUNT(*) FROM reports WHERE resolved = FALSE)          AS open_reports,
                (SELECT COUNT(*) FROM user_media WHERE status = 'pending')          AS pending_media,
                (SELECT COUNT(*) FROM matches WHERE created_at > NOW() - INTERVAL '24h') AS matches_24h
            """
        )
    return dict(stats)
