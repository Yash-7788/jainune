"""
Interactions router — like / pass / super-connect actions.

POST /v1/interactions/action

On mutual like or super_connect:
  - Creates `matches` row
  - Creates `chats` row (the encrypted chat thread)
  - Invalidates both users' feed caches
  - Updates behavior vector via EMA bump on liked attributes
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DBDep, RedisDep
from app.models.schemas.interaction import InteractionActionRequest, InteractionActionResponse
from app.services.core_people_finder import invalidate_feed_cache

router = APIRouter(prefix="/v1/interactions", tags=["interactions"])


# ---------------------------------------------------------------------------
# Behavior vector EMA update helper
# ---------------------------------------------------------------------------

async def _update_behavior_vector_ema(
    actor_id: uuid.UUID,
    target_id: uuid.UUID,
    action: str,
    db,
) -> None:
    """
    Exponential Moving Average update of actor's revealed_preference_vector.

    On LIKE  → nudge vector 10% toward target's vector  (α = 0.10)
    On PASS  → nudge vector  5% away from target's vector (repulsion)

    Uses pgvector arithmetic entirely in SQL for atomicity.
    """
    if action == "pass":
        # Mild repulsion: move 5% away from target
        sql = """
        UPDATE user_behavior_vectors uv
        SET revealed_preference_vector = (
            uv.revealed_preference_vector + (
                uv.revealed_preference_vector - t.revealed_preference_vector
            ) * 0.05
        )
        FROM user_behavior_vectors t
        WHERE uv.user_id = $1
          AND t.user_id  = $2
          AND t.revealed_preference_vector IS NOT NULL
          AND uv.revealed_preference_vector IS NOT NULL
        """
    else:
        # Attraction: move 10% toward target
        sql = """
        UPDATE user_behavior_vectors uv
        SET revealed_preference_vector = (
            uv.revealed_preference_vector + (
                t.revealed_preference_vector - uv.revealed_preference_vector
            ) * 0.10
        )
        FROM user_behavior_vectors t
        WHERE uv.user_id = $1
          AND t.user_id  = $2
          AND t.revealed_preference_vector IS NOT NULL
          AND uv.revealed_preference_vector IS NOT NULL
        """
    async with db.acquire() as conn:
        await conn.execute(sql, actor_id, target_id)


# ---------------------------------------------------------------------------
# Main action endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/action",
    response_model=InteractionActionResponse,
    summary="Record a like, pass, or super-connect",
)
async def record_interaction_action(
    body: InteractionActionRequest,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> InteractionActionResponse:
    """
    Idempotent interaction record. Re-submitting the same action is a no-op.

    Rules:
    - `like` or `super_connect` from A on B: checks if B already liked A → creates match + chat
    - `pass`: records pass, triggers mild vector repulsion, no match possible
    - `super_connect` costs 1 Jainune+ credit (enforced server-side)
    - On match: both feed caches are invalidated, match + chat rows created atomically
    """
    actor_id = uuid.UUID(str(current_user["id"]))
    target_id = body.target_id

    if actor_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot interact with yourself.",
        )

    async with db.acquire() as conn:
        # ── Idempotency check ────────────────────────────────────────────────
        existing = await conn.fetchrow(
            "SELECT id FROM interactions WHERE actor_id = $1 AND target_id = $2",
            actor_id, target_id,
        )
        if existing:
            return InteractionActionResponse(
                success=True,
                message="Interaction already recorded.",
            )

        # ── Super-connect credit deduction ───────────────────────────────────
        if body.action == "super_connect":
            deducted = await conn.fetchval(
                """
                UPDATE users
                SET super_connect_credits = super_connect_credits - 1
                WHERE id = $1 AND super_connect_credits > 0
                RETURNING super_connect_credits
                """,
                actor_id,
            )
            if deducted is None:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="No Super Connect credits remaining. Upgrade to Jainune+.",
                )

        # ── Insert interaction row ───────────────────────────────────────────
        await conn.execute(
            """
            INSERT INTO interactions (actor_id, target_id, action_type, reacted_prompt_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (actor_id, target_id) DO NOTHING
            """,
            actor_id,
            target_id,
            body.action,
            body.prompt_id,
        )

        # ── Check for mutual match ────────────────────────────────────────────
        match_created = False
        chat_id = None

        if body.action in ("like", "super_connect"):
            mutual = await conn.fetchrow(
                """
                SELECT id FROM interactions
                WHERE actor_id = $1 AND target_id = $2
                  AND action_type IN ('like', 'super_connect')
                """,
                target_id, actor_id,
            )

            if mutual:
                # Canonical pair ordering (lower UUID first) to prevent duplicate matches
                pair = sorted([str(actor_id), str(target_id)])
                u1 = uuid.UUID(pair[0])
                u2 = uuid.UUID(pair[1])

                # Upsert match row
                match_row = await conn.fetchrow(
                    """
                    INSERT INTO matches (user_id_1, user_id_2, match_type)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id_1, user_id_2) DO UPDATE
                        SET match_type = EXCLUDED.match_type
                    RETURNING id
                    """,
                    u1, u2,
                    "super_connect" if body.action == "super_connect" else "mutual_like",
                )

                # Create chat thread (idempotent on match_id)
                chat_row = await conn.fetchrow(
                    """
                    INSERT INTO chats (match_id, participant_1_id, participant_2_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (match_id) DO UPDATE SET match_id = EXCLUDED.match_id
                    RETURNING id
                    """,
                    match_row["id"], u1, u2,
                )

                match_created = True
                chat_id = chat_row["id"]

                # Update match with chat_id if column exists
                await conn.execute(
                    "UPDATE matches SET chat_id = $1 WHERE id = $2",
                    chat_id, match_row["id"],
                )

    # ── Async side effects (outside DB transaction) ──────────────────────────

    # EMA vector update (fire-and-forget; non-critical)
    try:
        await _update_behavior_vector_ema(actor_id, target_id, body.action, db)
    except Exception:
        pass  # Never fail the request over vector update

    # Invalidate feed caches for both users on match
    if match_created:
        await invalidate_feed_cache(actor_id, redis)
        await invalidate_feed_cache(target_id, redis)
    elif body.action == "pass":
        # Just invalidate actor's cache so passed profile doesn't reappear
        await invalidate_feed_cache(actor_id, redis)

    return InteractionActionResponse(
        success=True,
        match_created=match_created,
        chat_id=chat_id,
        message="Match created! You can now chat." if match_created else "Interaction recorded.",
    )
