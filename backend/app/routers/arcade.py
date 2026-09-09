"""
Arcade (Dilemma) router — community moral-dilemma voting feed.

Dilemmas are short "Would you rather…" cards that users swipe through.
They generate engagement signals used as soft compatibility features.

Endpoints:
  GET  /v1/arcade/dilemmas        → paginated dilemma feed (unseen first)
  POST /v1/arcade/dilemmas/{id}/vote  → cast a vote (A or B)
  GET  /v1/arcade/dilemmas/{id}/results → see aggregate vote breakdown
  POST /v1/arcade/dilemmas        → [admin] create a new dilemma
"""

from __future__ import annotations

import logging
import random
from typing import Optional
import uuid
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.database import get_pool
from app.core.security import sliding_window_rate_limit
from app.dependencies import get_current_user, get_redis_client, require_admin

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/arcade", tags=["Arcade"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DilemmaResponse(BaseModel):
    id: UUID
    question_text: str
    option_a: str
    option_b: str
    tags: list[str]
    # Populated only after the user votes or views results
    total_votes_a: Optional[int] = None
    total_votes_b: Optional[int] = None
    user_choice: Optional[str] = None  # "A" | "B" | None


class VoteBody(BaseModel):
    choice: str = Field(..., pattern="^(A|B)$")


class CreateDilemmaBody(BaseModel):
    question_text: str = Field(..., min_length=10, max_length=300)
    option_a: str = Field(..., min_length=2, max_length=150)
    option_b: str = Field(..., min_length=2, max_length=150)
    tags: list[str] = Field(default_factory=list, max_length=5)


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------


@router.get("/dilemmas", response_model=list[DilemmaResponse])
async def get_dilemma_feed(
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Returns dilemmas the current user has not voted on yet, newest-first.
    Already-voted dilemmas appear at the end with user_choice populated.
    """
    await sliding_window_rate_limit(f"ratelimit:arcade:feed:{current_user['user_id']}", 60, 60, redis)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                d.id,
                d.question_text,
                d.option_a,
                d.option_b,
                d.tags,
                d.total_votes_a,
                d.total_votes_b,
                dv.choice AS user_choice
            FROM dilemmas d
            LEFT JOIN dilemma_votes dv
                ON dv.dilemma_id = d.id AND dv.user_id = $1
            WHERE d.is_active = TRUE
            ORDER BY (dv.choice IS NULL) DESC, d.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            current_user["user_id"],
            limit,
            offset,
        )

    return [
        {
            "id": r["id"],
            "question_text": r["question_text"],
            "option_a": r["option_a"],
            "option_b": r["option_b"],
            "tags": r["tags"] or [],
            # Only reveal tallies for already-voted items
            "total_votes_a": r["total_votes_a"] if r["user_choice"] else None,
            "total_votes_b": r["total_votes_b"] if r["user_choice"] else None,
            "user_choice": r["user_choice"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Vote
# ---------------------------------------------------------------------------


@router.post(
    "/dilemmas/{dilemma_id}/vote",
    status_code=status.HTTP_201_CREATED,
)
async def vote_on_dilemma(
    dilemma_id: UUID,
    body: VoteBody,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Cast a vote on a dilemma. One vote per user per dilemma (idempotent).
    Increments the appropriate counter on the dilemmas table atomically.
    """
    await sliding_window_rate_limit(f"ratelimit:arcade:vote:{current_user['user_id']}", 60, 60, redis)
    async with pool.acquire() as conn:
        # Check dilemma exists
        exists = await conn.fetchval(
            "SELECT id FROM dilemmas WHERE id = $1 AND is_active = TRUE",
            dilemma_id,
        )
        if exists is None:
            raise HTTPException(status_code=404, detail="Dilemma not found")

        # Idempotent insert
        existing = await conn.fetchval(
            "SELECT choice FROM dilemma_votes WHERE dilemma_id = $1 AND user_id = $2",
            dilemma_id,
            current_user["user_id"],
        )
        if existing:
            return {"already_voted": True, "choice": existing}

        async with conn.transaction():
            inserted = await conn.fetchval(
                """
                INSERT INTO dilemma_votes (dilemma_id, user_id, choice)
                VALUES ($1, $2, $3)
                ON CONFLICT (dilemma_id, user_id) DO NOTHING
                RETURNING id
                """,
                dilemma_id,
                current_user["user_id"],
                body.choice,
            )
            if inserted is None:
                existing_choice = await conn.fetchval(
                    "SELECT choice FROM dilemma_votes WHERE dilemma_id = $1 AND user_id = $2",
                    dilemma_id,
                    current_user["user_id"],
                )
                return {"already_voted": True, "choice": existing_choice or body.choice}

            # Atomically update denormalized counter
            col = "total_votes_a" if body.choice == "A" else "total_votes_b"
            await conn.execute(
                f"UPDATE dilemmas SET {col} = {col} + 1 WHERE id = $1",
                dilemma_id,
            )

    return {"voted": True, "choice": body.choice}


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@router.get("/dilemmas/{dilemma_id}/results")
async def get_dilemma_results(
    dilemma_id: UUID,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Returns aggregate vote breakdown.
    User must have voted to see results (prevents anchoring bias).
    """
    await sliding_window_rate_limit(f"ratelimit:arcade:results:{current_user['user_id']}", 60, 60, redis)
    async with pool.acquire() as conn:
        dilemma = await conn.fetchrow(
            """
            SELECT d.*, dv.choice AS user_choice
            FROM dilemmas d
            LEFT JOIN dilemma_votes dv
                ON dv.dilemma_id = d.id AND dv.user_id = $2
            WHERE d.id = $1
            """,
            dilemma_id,
            current_user["user_id"],
        )

    if dilemma is None:
        raise HTTPException(status_code=404, detail="Dilemma not found")

    if not dilemma["user_choice"]:
        raise HTTPException(
            status_code=403,
            detail="Vote first to see results",
        )

    total = (dilemma["total_votes_a"] or 0) + (dilemma["total_votes_b"] or 0)

    def pct(n: int) -> float:
        return round((n / total * 100), 1) if total else 0.0

    return {
        "id": dilemma["id"],
        "question_text": dilemma["question_text"],
        "option_a": dilemma["option_a"],
        "option_b": dilemma["option_b"],
        "total_votes_a": dilemma["total_votes_a"] or 0,
        "total_votes_b": dilemma["total_votes_b"] or 0,
        "pct_a": pct(dilemma["total_votes_a"] or 0),
        "pct_b": pct(dilemma["total_votes_b"] or 0),
        "user_choice": dilemma["user_choice"],
        "total_votes": total,
    }


# ---------------------------------------------------------------------------
# Admin: create dilemma
# ---------------------------------------------------------------------------


@router.post("/dilemmas", status_code=status.HTTP_201_CREATED)
async def create_dilemma(
    body: CreateDilemmaBody,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Admin-only: create a new dilemma card."""
    user_id = admin.get("user_id") or admin.get("id")
    async with pool.acquire() as conn:
        dilemma_id = await conn.fetchval(
            """
            INSERT INTO dilemmas
                (question_text, option_a, option_b, tags, is_active,
                 total_votes_a, total_votes_b, created_by)
            VALUES ($1, $2, $3, $4, TRUE, 0, 0, $5)
            RETURNING id
            """,
            body.question_text,
            body.option_a,
            body.option_b,
            body.tags,
            user_id,
        )

    return {"id": dilemma_id, "created": True}


# ---------------------------------------------------------------------------
# Serendipity Arcade: Micro-Transaction Wallet & Game Actions
# ---------------------------------------------------------------------------


class ArcadeWalletResponse(BaseModel):
    user_id: UUID
    available_spins: int
    available_dice_rolls: int


@router.get("/wallet", response_model=ArcadeWalletResponse)
async def get_arcade_wallet(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """Fetch current user's arcade token balance (spins and dice rolls)."""
    await sliding_window_rate_limit(f"ratelimit:arcade:wallet:{current_user['user_id']}", 60, 60, redis)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT available_spins, available_dice_rolls
            FROM user_arcade_wallet
            WHERE user_id = $1
            """,
            current_user["user_id"],
        )
    return {
        "user_id": current_user["user_id"],
        "available_spins": row["available_spins"] if row else 0,
        "available_dice_rolls": row["available_dice_rolls"] if row else 0,
    }


@router.post("/spin", status_code=status.HTTP_200_OK)
async def spin_serendipity_wheel(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Consume 1 spin credit from wallet and trigger instantaneous random Bangalore pairing.
    (SUBSCRIPTION_SPEC.md §4.2: Kinetic Wheel Spin)
    """
    await sliding_window_rate_limit(f"ratelimit:arcade:spin:{current_user['user_id']}", 30, 60, redis)
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Concurrency lock on user arcade wallet to serialize burst requests
            await conn.execute(
                "SELECT available_spins FROM user_arcade_wallet WHERE user_id = $1 FOR UPDATE",
                current_user["user_id"],
            )
            # Atomic deduction
            remaining = await conn.fetchval(
                """
                UPDATE user_arcade_wallet
                   SET available_spins = available_spins - 1,
                       updated_at = NOW()
                 WHERE user_id = $1 AND available_spins > 0
                RETURNING available_spins
                """,
                current_user["user_id"],
            )
            if remaining is None:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="No spins remaining. Purchase an arcade pack to spin.",
                )

            # Record spend transaction
            await conn.execute(
                """
                INSERT INTO arcade_transactions
                    (user_id, action_type, spins_delta, status)
                VALUES ($1, 'spend_spin', -1, 'spent')
                """,
                current_user["user_id"],
            )

            # Find active candidate with safety, blocklist, and preference filters
            user_id = current_user.get("user_id") or current_user.get("id")
            show_me = current_user.get("show_me")
            target_gender = "man" if show_me in ("men", "man") else ("woman" if show_me in ("women", "woman") else None)

            candidate = await conn.fetchrow(
                """
                SELECT id, first_name, city
                FROM users u
                WHERE u.id != $1
                  AND u.account_status = 'active'
                  AND u.is_paused = FALSE
                  AND u.onboarding_completed = TRUE
                  AND ($2::text IS NULL OR u.gender = $2::text)
                  AND NOT EXISTS (
                      SELECT 1 FROM user_blocks ub
                      WHERE (ub.blocker_id = $1 AND ub.blocked_id = u.id)
                         OR (ub.blocked_id = $1 AND ub.blocker_id = u.id)
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM interactions i
                      WHERE i.actor_id = $1 AND i.target_id = u.id
                  )
                ORDER BY random()
                LIMIT 1
                """,
                user_id,
                target_gender,
            )

            if not candidate:
                # No eligible candidate found right now: refund spin credit and preserve wallet balance
                await conn.execute(
                    """
                    UPDATE user_arcade_wallet
                       SET available_spins = available_spins + 1,
                           updated_at = NOW()
                     WHERE user_id = $1
                    """,
                    current_user["user_id"],
                )
                await conn.execute(
                    """
                    INSERT INTO arcade_transactions
                        (user_id, action_type, spins_delta, status)
                    VALUES ($1, 'refund_spin_no_candidate', 1, 'refunded')
                    """,
                    current_user["user_id"],
                )
                return {
                    "success": False,
                    "action": "spin",
                    "remaining_spins": remaining + 1,
                    "chat_id": None,
                    "paired_user": None,
                    "message": "No new serendipity candidates available right now. Spin credit has been preserved!",
                }

            chat_id = None
            cand_id = candidate["id"]
            pair = sorted([str(user_id), str(cand_id)])
            u1 = uuid.UUID(pair[0])
            u2 = uuid.UUID(pair[1])
            match_row = await conn.fetchrow(
                """
                INSERT INTO matches
                    (user_a, user_b, user_id_1, user_id_2, user_a_id, user_b_id, match_type, status)
                VALUES ($1, $2, $1, $2, $1, $2, 'serendipity_spin', 'active')
                ON CONFLICT (user_a, user_b) DO UPDATE
                    SET match_type = EXCLUDED.match_type
                RETURNING id
                """,
                u1, u2,
            )
            from datetime import datetime, timezone, timedelta
            chat_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            chat_row = await conn.fetchrow(
                """
                INSERT INTO chats
                    (match_id, participant_1_id, participant_2_id, participant_a, participant_b, is_ephemeral, expires_at)
                VALUES ($1, $2, $3, $2, $3, TRUE, $4)
                ON CONFLICT (match_id) DO UPDATE
                    SET is_ephemeral = TRUE, expires_at = EXCLUDED.expires_at, is_unmatched = FALSE
                RETURNING id
                """,
                match_row["id"], u1, u2, chat_expires_at,
            )
            chat_id = chat_row["id"]
            await conn.execute("UPDATE matches SET chat_id = $1 WHERE id = $2", chat_id, match_row["id"])

    return {
        "success": True,
        "action": "spin",
        "remaining_spins": remaining,
        "chat_id": str(chat_id) if chat_id else None,
        "paired_user": {
            "id": str(candidate["id"]),
            "first_name": candidate["first_name"],
            "city": candidate["city"],
        },
        "message": "Wheel spin successful! 15-minute speed chat enabled.",
    }


@router.post("/roll", status_code=status.HTTP_200_OK)
async def roll_lucky_dice(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: aioredis.Redis = Depends(get_redis_client),
):
    """
    Consume 1 dice roll credit from wallet and generate lucky match ticket.
    (SUBSCRIPTION_SPEC.md §4.3: Lucky Match Dice Roll)
    """
    await sliding_window_rate_limit(f"ratelimit:arcade:roll:{current_user['user_id']}", 30, 60, redis)
    import secrets
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Concurrency lock on user arcade wallet to serialize burst requests
            await conn.execute(
                "SELECT available_dice_rolls FROM user_arcade_wallet WHERE user_id = $1 FOR UPDATE",
                current_user["user_id"],
            )
            remaining = await conn.fetchval(
                """
                UPDATE user_arcade_wallet
                   SET available_dice_rolls = available_dice_rolls - 1,
                       updated_at = NOW()
                 WHERE user_id = $1 AND available_dice_rolls > 0
                RETURNING available_dice_rolls
                """,
                current_user["user_id"],
            )
            if remaining is None:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="No dice rolls remaining. Purchase a roll to play.",
                )

            await conn.execute(
                """
                INSERT INTO arcade_transactions
                    (user_id, action_type, dice_rolls_delta, status)
                VALUES ($1, 'spend_roll', -1, 'spent')
                """,
                current_user["user_id"],
            )

    sys_rand = secrets.SystemRandom()
    roll_outcome = [sys_rand.randint(1, 6), sys_rand.randint(1, 6)]
    return {
        "success": True,
        "action": "dice_roll",
        "dice": roll_outcome,
        "total": sum(roll_outcome),
        "remaining_dice_rolls": remaining,
        "message": f"Rolled {roll_outcome[0]} and {roll_outcome[1]}! Match ticket active for 30 minutes.",
    }
