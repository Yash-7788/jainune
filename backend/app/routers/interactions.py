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

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.models.schemas.interaction import InteractionActionRequest, InteractionActionResponse
from app.services.core_people_finder import invalidate_feed_cache

router = APIRouter(prefix="/v1/interactions", tags=["interactions"])


def _calc_compatibility(caller: dict, target_row: dict) -> dict:
    score = 72
    shared = ["Jain Values"]
    caller_sect = caller.get("community_sect")
    target_sect = target_row.get("community_sect")
    if caller_sect and target_sect and caller_sect == target_sect:
        score += 14
        shared.append("Same Sect")
    caller_diet = caller.get("dietary_strictness")
    target_diet = target_row.get("dietary_strictness")
    if caller_diet and target_diet and caller_diet == target_diet:
        score += 10
        shared.append("Shared Dietary Practice")
    if target_row.get("is_photo_verified"):
        score += 4
    return {"values_alignment_percentage": min(score, 99), "shared_traditions": shared}


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

    # Anti-bot rate limit: max 60 actions per minute per user (SECURITY.md 8.1)
    await sliding_window_rate_limit(f"ratelimit:interaction:{actor_id}", 60, 60, redis)

    if actor_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot interact with yourself.",
        )

    async with db.acquire() as conn:
        async with conn.transaction():
            # Lock user row to serialize concurrent interactions and credit deductions
            await conn.execute("SELECT id FROM users WHERE id = $1 FOR UPDATE", actor_id)

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

            # ── Daily like limit enforcement & super-connect credit deduction ────
            from app.services.payment_service import get_effective_user_tier
            tier = await get_effective_user_tier(actor_id, conn)

            if body.action == "like":
                from datetime import timedelta
                from app.core.security import get_ist_now, get_ist_today_str

                ist_now = get_ist_now()
                today_str = get_ist_today_str()
                like_key = f"daily_likes:{actor_id}:{today_str}"

                # Quotas: free=10, gold=50, platinum/jainune_plus=unlimited
                limit = 10 if tier == "free" else (50 if tier == "gold" else None)
                if limit is not None:
                    current_likes = await redis.incr(like_key)
                    if current_likes == 1:
                        # Expire strictly at upcoming IST midnight
                        tomorrow_midnight = (ist_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        ttl_seconds = int((tomorrow_midnight - ist_now).total_seconds())
                        await redis.expire(like_key, max(ttl_seconds, 60))
                    if current_likes > limit:
                        raise HTTPException(
                            status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail=f"Daily like limit of {limit} reached. Upgrade to Jainune+ for unlimited intentional likes.",
                        )
            elif body.action == "super_connect":
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
                ON CONFLICT (actor_id, target_id) DO UPDATE
                   SET action_type = EXCLUDED.action_type,
                       reacted_prompt_id = EXCLUDED.reacted_prompt_id
                """,
                actor_id,
                target_id,
                body.action,
                body.prompt_id,
            )

            # ── Check for mutual match ────────────────────────────────────────────
            match_created = False
            chat_id = None
            match_id_to_notify = None

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

                    # Upsert match row with dual column aliases for worker and router compatibility
                    match_row = await conn.fetchrow(
                        """
                        INSERT INTO matches
                            (user_a, user_b, user_id_1, user_id_2, user_a_id, user_b_id, match_type, status)
                        VALUES ($1, $2, $1, $2, $1, $2, $3, 'active')
                        ON CONFLICT (user_a, user_b) DO UPDATE
                            SET match_type = EXCLUDED.match_type
                        RETURNING id
                        """,
                        u1, u2,
                        "super_connect" if body.action == "super_connect" else "mutual_like",
                    )

                    # Create chat thread (idempotent on match_id)
                    chat_row = await conn.fetchrow(
                        """
                        INSERT INTO chats
                            (match_id, participant_1_id, participant_2_id, participant_a, participant_b)
                        VALUES ($1, $2, $3, $2, $3)
                        ON CONFLICT (match_id) DO UPDATE
                           SET match_id = EXCLUDED.match_id
                        RETURNING id
                        """,
                        match_row["id"], u1, u2,
                    )

                    match_created = True
                    chat_id = chat_row["id"]
                    match_id_to_notify = match_row["id"]

                    # Update match with chat_id
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

    # Dispatch push notifications asynchronously
    if match_created and match_id_to_notify:
        try:
            from app.workers.notification_worker import notify_new_match
            notify_new_match.delay(str(match_id_to_notify))
        except Exception:
            pass
    elif body.action in ("like", "super_connect"):
        try:
            from app.workers.notification_worker import notify_new_like
            notify_new_like.delay(str(target_id), current_user.get("first_name", "Someone"))
        except Exception:
            pass

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
        is_match=match_created,
        chat_id=chat_id,
        message="Match created! You can now chat." if match_created else "Interaction recorded.",
    )


@router.get("/matches", status_code=status.HTTP_200_OK)
async def get_my_matches(
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    """Fetch all active mutual matches for the authenticated user."""
    import json
    from datetime import date
    user_id = uuid.UUID(str(current_user["id"]))

    query = """
    SELECT
        m.id AS match_id,
        m.chat_id,
        m.created_at,
        u.id,
        u.first_name,
        u.date_of_birth,
        u.city,
        u.state,
        u.dietary_strictness,
        u.community_sect,
        COALESCE(u.profession, u.job_title) AS profession,
        u.education,
        u.is_photo_verified,
        COALESCE((
            SELECT json_agg(json_build_object('id', um.id, 'url', um.cdn_url, 'order', um.position))
            FROM user_media um WHERE um.user_id = u.id AND um.media_type = 'photo' AND um.status = 'approved'
        ), '[]'::json) AS photos
    FROM matches m
    JOIN users u ON (u.id = CASE WHEN m.user_a = $1 THEN m.user_b ELSE m.user_a END)
    WHERE (m.user_a = $1 OR m.user_b = $1 OR m.user_id_1 = $1 OR m.user_id_2 = $1)
      AND m.status = 'active'
      AND u.account_status = 'active'
      AND u.is_paused = FALSE
      AND NOT EXISTS (
          SELECT 1 FROM user_blocks ub
          WHERE (ub.blocker_id = $1 AND ub.blocked_id = u.id)
             OR (ub.blocked_id = $1 AND ub.blocker_id = u.id)
      )
    ORDER BY m.created_at DESC
    """
    async with db.acquire() as conn:
        rows = await conn.fetch(query, user_id)

    today = date.today()
    profiles = []
    for r in rows:
        dob = r["date_of_birth"]
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)) if dob else 25
        photos_val = r["photos"]
        if isinstance(photos_val, str):
            photos_val = json.loads(photos_val)
        profiles.append({
            "id": str(r["id"]),
            "first_name": r["first_name"] or "Someone",
            "age": age,
            "city": r["city"] or "Bangalore",
            "state": r["state"] or "Karnataka",
            "distance_display": "Nearby",
            "dietary_strictness": r["dietary_strictness"] or "pure_jain",
            "community_sect": r["community_sect"] or "shwetambar_murtipujak",
            "profession": r["profession"] or "Professional",
            "education": r["education"] or "Graduate",
            "photos": photos_val or [],
            "prompts": [],
            "voice_snapshot": None,
            "compatibility": _calc_compatibility(current_user, r),
            "is_verified": r.get("is_photo_verified", False),
            "chat_id": str(r["chat_id"]) if r.get("chat_id") else None,
            "matched_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return {"profiles": profiles}


@router.get("/liked-me", status_code=status.HTTP_200_OK)
async def get_users_who_liked_me(
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    """Fetch incoming likes from other users (server-side redacted for free tier)."""
    import json
    from datetime import date
    from app.services.payment_service import get_effective_user_tier
    user_id = uuid.UUID(str(current_user["id"]))

    query = """
    SELECT
        i.id AS interaction_id,
        i.created_at,
        u.id,
        u.first_name,
        u.date_of_birth,
        u.city,
        u.state,
        u.dietary_strictness,
        u.community_sect,
        COALESCE(u.profession, u.job_title) AS profession,
        u.education,
        u.is_photo_verified,
        COALESCE((
            SELECT json_agg(json_build_object('id', um.id, 'url', um.cdn_url, 'order', um.position))
            FROM user_media um WHERE um.user_id = u.id AND um.media_type = 'photo' AND um.status = 'approved'
        ), '[]'::json) AS photos
    FROM interactions i
    JOIN users u ON u.id = i.actor_id
    WHERE i.target_id = $1
      AND i.action_type IN ('like', 'super_connect')
      AND u.account_status = 'active'
      AND u.is_paused = FALSE
      AND NOT EXISTS (
          SELECT 1 FROM interactions back
          WHERE back.actor_id = $1 AND back.target_id = i.actor_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM user_blocks ub
          WHERE (ub.blocker_id = $1 AND ub.blocked_id = u.id)
             OR (ub.blocked_id = $1 AND ub.blocker_id = u.id)
      )
    ORDER BY i.created_at DESC
    LIMIT 50
    """
    async with db.acquire() as conn:
        tier = await get_effective_user_tier(user_id, conn)
        rows = await conn.fetch(query, user_id)

    is_subscriber = tier in ("jainune_plus", "gold", "platinum")
    today = date.today()
    likes = []
    for r in rows:
        dob = r["date_of_birth"]
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)) if dob else 25
        photos_val = r["photos"]
        if isinstance(photos_val, str):
            photos_val = json.loads(photos_val)

        if is_subscriber:
            likes.append({
                "id": str(r["id"]),
                "first_name": r["first_name"] or "Someone",
                "age": age,
                "city": r["city"] or "Bangalore",
                "state": r["state"] or "Karnataka",
                "distance_display": "Nearby",
                "dietary_strictness": r["dietary_strictness"] or "pure_jain",
                "community_sect": r["community_sect"] or "shwetambar_murtipujak",
                "profession": r["profession"] or "Professional",
                "education": r["education"] or "Graduate",
                "photos": photos_val or [],
                "prompts": [],
                "voice_snapshot": None,
                "compatibility": _calc_compatibility(current_user, r),
                "is_verified": r.get("is_photo_verified", False),
                "liked_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
        else:
            # Server-side redaction for free tier: prevent paywall bypass
            likes.append({
                "id": str(r["id"]),
                "first_name": "Someone",
                "age": age,
                "city": r["city"] or "Nearby",
                "state": "",
                "distance_display": "Nearby",
                "dietary_strictness": "",
                "community_sect": "",
                "profession": "",
                "education": "",
                "photos": [],
                "prompts": [],
                "voice_snapshot": None,
                "compatibility": None,
                "is_verified": False,
                "liked_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
    return {"likes": likes, "total_count": len(likes)}
