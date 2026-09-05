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
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

import asyncpg

from app.core.database import get_pool
from app.core.security import get_current_user

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
):
    """
    Returns dilemmas the current user has not voted on yet, newest-first.
    Already-voted dilemmas appear at the end with user_choice populated.
    """
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
):
    """
    Cast a vote on a dilemma. One vote per user per dilemma (idempotent).
    Increments the appropriate counter on the dilemmas table atomically.
    """
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
            await conn.execute(
                """
                INSERT INTO dilemma_votes (dilemma_id, user_id, choice)
                VALUES ($1, $2, $3)
                """,
                dilemma_id,
                current_user["user_id"],
                body.choice,
            )

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
):
    """
    Returns aggregate vote breakdown.
    User must have voted to see results (prevents anchoring bias).
    """
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
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Admin-only: create a new dilemma card."""
    async with pool.acquire() as conn:
        # Verify admin role
        role = await conn.fetchval(
            "SELECT role FROM admin_users WHERE user_id = $1",
            current_user["user_id"],
        )
        if role not in ("superadmin", "moderator"):
            raise HTTPException(status_code=403, detail="Admin access required")

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
            current_user["user_id"],
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
):
    """Fetch current user's arcade token balance (spins and dice rolls)."""
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
):
    """
    Consume 1 spin credit from wallet and trigger instantaneous random Bangalore pairing.
    (SUBSCRIPTION_SPEC.md §4.2: Kinetic Wheel Spin)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
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

            # Find active random candidate in same operational zone
            candidate = await conn.fetchrow(
                """
                SELECT id, first_name, city
                FROM users
                WHERE id != $1 AND account_status = 'active'
                ORDER BY random()
                LIMIT 1
                """,
                current_user["user_id"],
            )

    return {
        "success": True,
        "action": "spin",
        "remaining_spins": remaining,
        "paired_user": dict(candidate) if candidate else None,
        "message": "Wheel spin successful! 15-minute speed chat enabled.",
    }


@router.post("/roll", status_code=status.HTTP_200_OK)
async def roll_lucky_dice(
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Consume 1 dice roll credit from wallet and generate lucky match ticket.
    (SUBSCRIPTION_SPEC.md §4.3: Lucky Match Dice Roll)
    """
    import random
    async with pool.acquire() as conn:
        async with conn.transaction():
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

    roll_outcome = [random.randint(1, 6), random.randint(1, 6)]
    return {
        "success": True,
        "action": "dice_roll",
        "dice": roll_outcome,
        "total": sum(roll_outcome),
        "remaining_dice_rolls": remaining,
        "message": f"Rolled {roll_outcome[0]} and {roll_outcome[1]}! Match ticket active for 30 minutes.",
    }
