"""
Chat REST router.

GET  /v1/chats                       → list all chat threads for current user
GET  /v1/chats/{chat_id}/messages    → paginated message history (cursor-based)
POST /v1/chats/{chat_id}/messages    → send a message (text / media)
POST /v1/chats/{chat_id}/read        → mark all messages as read
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.services.payment_service import get_effective_user_tier
from app.models.schemas.chat import (
    ChatHistoryResponse,
    ChatListResponse,
    ChatMessage,
    ChatThread,
    SendMessageRequest,
)

router = APIRouter(prefix="/v1/chats", tags=["chats"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_participant(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    db,
) -> dict:
    """Fetch chat row and verify the requesting user is a participant. Accepts chat_id or match_id."""
    sql = """
        SELECT id, match_id, participant_1_id, participant_2_id,
               is_ephemeral, expires_at, is_unmatched,
               (expires_at IS NOT NULL AND expires_at < NOW()) AS is_expired
        FROM chats
        WHERE (id = $1 OR match_id = $1)
          AND (participant_1_id = $2 OR participant_2_id = $2)
    """
    if hasattr(db, "acquire"):
        async with db.acquire() as conn:
            row = await conn.fetchrow(sql, chat_id, user_id)
    else:
        row = await db.fetchrow(sql, chat_id, user_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or you are not a participant.",
        )
    return dict(row)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ChatListResponse, summary="List chat threads")
async def list_chats(
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep = None,
) -> ChatListResponse:
    """
    Returns all active chat threads for the current user, ordered by most
    recent message. Includes other participant's name, photo, and last message.
    """
    user_id = uuid.UUID(str(current_user["id"]))
    if redis is not None:
        await sliding_window_rate_limit(f"ratelimit:chats:list:{user_id}", 60, 60, redis)

    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.match_id,
                c.is_ephemeral,
                c.expires_at,
                -- Other participant
                CASE
                    WHEN c.participant_1_id = $1 THEN c.participant_2_id
                    ELSE c.participant_1_id
                END AS other_user_id,
                other_u.first_name AS other_user_first_name,
                CASE
                    WHEN other_u.account_status = 'suspended' THEN NULL
                    ELSE photo.cdn_url
                END AS other_user_photo_url,
                -- Last message
                lm.content   AS last_message_text,
                lm.created_at AS last_message_at,
                -- Unread count
                COALESCE(unread.unread_count, 0) AS unread_count
            FROM chats c
            JOIN users other_u ON other_u.id = (
                CASE
                    WHEN c.participant_1_id = $1 THEN c.participant_2_id
                    ELSE c.participant_1_id
                END
            )
            LEFT JOIN LATERAL (
                SELECT cdn_url FROM user_media
                WHERE user_id = other_u.id
                  AND media_type = 'photo'
                  AND is_processed = TRUE
                  AND status = 'approved'
                ORDER BY position ASC
                LIMIT 1
            ) photo ON TRUE
            LEFT JOIN LATERAL (
                SELECT content, created_at FROM messages
                WHERE chat_id = c.id
                ORDER BY created_at DESC
                LIMIT 1
            ) lm ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS unread_count
                FROM messages m2
                WHERE m2.chat_id = c.id
                  AND m2.sender_id != $1
                  AND m2.is_read = FALSE
            ) unread ON TRUE
            WHERE (c.participant_1_id = $1 OR c.participant_2_id = $1)
              AND c.is_unmatched = FALSE
              AND other_u.account_status NOT IN ('banned', 'deleted', 'suspended')
              AND NOT EXISTS (
                  SELECT 1 FROM user_blocks ub
                  WHERE (ub.blocker_id = $1 AND ub.blocked_id = (CASE WHEN c.participant_1_id = $1 THEN c.participant_2_id ELSE c.participant_1_id END))
                     OR (ub.blocked_id = $1 AND ub.blocker_id = (CASE WHEN c.participant_1_id = $1 THEN c.participant_2_id ELSE c.participant_1_id END))
              )
            ORDER BY lm.created_at DESC NULLS LAST
            """,
            user_id,
        )

    threads = [
        ChatThread(
            id=r["id"],
            match_id=r["match_id"],
            other_user_id=r["other_user_id"],
            other_user_first_name=r["other_user_first_name"] or "",
            other_user_photo_url=r["other_user_photo_url"],
            last_message_text=r["last_message_text"],
            last_message_at=r["last_message_at"],
            unread_count=r["unread_count"],
            is_ephemeral=r["is_ephemeral"],
            expires_at=r["expires_at"],
        )
        for r in rows
    ]

    return ChatListResponse(threads=threads)


WEEKLY_QUESTIONS = [
    "How do you incorporate Jain principles like Ahimsa and Anekantavada into your daily life?",
    "What is your family's favorite Paryushan or festival tradition?",
    "What does balance between traditional Jain values and modern ambitions look like to you?",
    "Which Jain pilgrimage or temple holds the most special memory for you?",
    "How important is strict dietary practice in your lifestyle and future home?",
    "What is one value passed down from your elders that you cherish the most?",
    "If you could volunteer for any community or social initiative, what would it be?",
    "How do you practice mindful living and compassion in a high-speed world?",
]


@router.get(
    "/weekly-question",
    summary="Get weekly Jain icebreaker question",
)
async def get_weekly_question(
    current_user: CurrentUser,
) -> dict:
    """Returns rotating Jain cultural & philosophical question for chat icebreakers."""
    from datetime import datetime, timezone
    week_num = datetime.now(timezone.utc).isocalendar().week
    selected = WEEKLY_QUESTIONS[week_num % len(WEEKLY_QUESTIONS)]
    return {"question": selected}


@router.get(
    "/{chat_id}/messages",
    response_model=ChatHistoryResponse,
    summary="Paginated message history",
)
async def get_messages(
    chat_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
    limit: int = Query(default=30, ge=1, le=100),
    before: Optional[str] = Query(default=None, description="Cursor: message UUID for pagination"),
    cursor: Optional[str] = Query(default=None, description="Cursor alias for pagination"),
    redis: RedisDep = None,
) -> ChatHistoryResponse:
    user_id = uuid.UUID(str(current_user["id"]))
    if redis is not None:
        await sliding_window_rate_limit(f"ratelimit:chats:get:{user_id}", 60, 60, redis)
    chat = await _assert_participant(chat_id, user_id, db)
    if chat.get("is_unmatched"):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Chat thread is closed due to unmatch.",
        )
    if chat.get("is_expired"):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This chat has expired.",
        )
    actual_chat_id = chat["id"]
    cursor_val = before or cursor

    async with db.acquire() as conn:
        if cursor_val:
            # Cursor-based: fetch messages older than cursor message id
            try:
                before_uuid = uuid.UUID(cursor_val)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor.")
            before_row = await conn.fetchrow(
                "SELECT created_at, id FROM messages WHERE id = $1 AND chat_id = $2",
                before_uuid, actual_chat_id,
            )
            if not before_row:
                rows = []
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, chat_id, sender_id, message_type, content,
                           media_url, is_read, created_at,
                           is_moderated, moderation_type, moderation_disclaimer
                    FROM messages
                    WHERE chat_id = $1 AND (created_at, id) < ($2, $3)
                    ORDER BY created_at DESC, id DESC
                    LIMIT $4
                    """,
                    actual_chat_id, before_row["created_at"], before_row["id"], limit + 1,
                )
        else:
            rows = await conn.fetch(
                """
                SELECT id, chat_id, sender_id, message_type, content,
                       media_url, is_read, created_at,
                       is_moderated, moderation_type, moderation_disclaimer
                FROM messages
                WHERE chat_id = $1
                ORDER BY created_at DESC, id DESC
                LIMIT $2
                """,
                actual_chat_id, limit + 1,
            )

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = str(rows[-1]["id"]) if has_more and rows else None

    messages = [
        ChatMessage(
            id=r["id"],
            chat_id=r["chat_id"],
            sender_id=r["sender_id"],
            message_type=r["message_type"],
            content=r["content"],
            media_url=r["media_url"],
            is_read=r["is_read"],
            created_at=r["created_at"],
            is_moderated=r.get("is_moderated", False),
            moderation_type=r.get("moderation_type"),
            moderation_disclaimer=r.get("moderation_disclaimer"),
        )
        for r in rows
    ]

    return ChatHistoryResponse(
        messages=messages,
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.post(
    "/{chat_id}/messages",
    response_model=ChatMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
)
async def send_message(
    chat_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> ChatMessage:
    """
    Inserts message into DB, then publishes to Redis pub/sub channel
    `chat:{chat_id}` so the WebSocket handler fans it out to both participants.
    Applies Roblox-style chat safety filters and moderation.
    """
    user_id = uuid.UUID(str(current_user["id"]))
    await sliding_window_rate_limit(f"ratelimit:chats:msg:{user_id}", 60, 60, redis)

    async with db.acquire() as conn:
        async with conn.transaction():
            chat = await _assert_participant(chat_id, user_id, conn)
            actual_chat_id = chat["id"]

            if chat.get("is_unmatched"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Chat thread is closed due to unmatch.",
                )

            # Validate ephemeral expiry atomically via DB NOW() (BUG-070)
            if chat.get("is_expired"):
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="This chat has expired.",
                )
            elif chat.get("expires_at"):
                is_expired = await conn.fetchval(
                    "SELECT (expires_at < NOW()) FROM chats WHERE id = $1",
                    actual_chat_id,
                )
                if is_expired:
                    raise HTTPException(
                        status_code=status.HTTP_410_GONE,
                        detail="This chat has expired.",
                    )

            try:
                body.validate_content()
            except ValueError as err:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

            other_id = chat["participant_2_id"] if chat["participant_1_id"] == user_id else chat["participant_1_id"]

            # Check user blocks atomically in the same transaction (BUG-063)
            blocked = await conn.fetchval(
                """
                SELECT 1 FROM user_blocks
                WHERE (blocker_id = $1 AND blocked_id = $2)
                   OR (blocker_id = $2 AND blocked_id = $1)
                LIMIT 1
                """,
                user_id, other_id,
            )
            if blocked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Communication is blocked.",
                )

            # Check recipient status including suspended (BUG-066)
            recipient_status = await conn.fetchval(
                "SELECT account_status FROM users WHERE id = $1",
                other_id,
            )
            if recipient_status in ("deleted", "banned", "suspended"):
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Recipient account is no longer active.",
                )

            effective_tier = await get_effective_user_tier(user_id, conn)
            is_subscribed = effective_tier in ("jainune_plus", "gold", "platinum")

            # Filter content if text message
            final_content = body.content
            is_moderated = False
            mod_type = None
            mod_disclaimer = None

            if body.message_type == "text" and body.content:
                from app.services.chat_safety_filter import filter_chat_content
                mod_result = await filter_chat_content(
                    content=body.content,
                    chat_id=actual_chat_id,
                    user_id=user_id,
                    redis=redis,
                    is_subscribed=is_subscribed,
                    user_disclaimer_approved=body.user_disclaimer_approved,
                )
                final_content = mod_result.content
                is_moderated = mod_result.is_moderated
                mod_type = mod_result.moderation_type
                mod_disclaimer = mod_result.moderation_disclaimer

            # Validate media attachment provenance and approval (NEW-003)
            final_media_url = body.media_url
            if body.message_type in ("photo", "voice"):
                target_media_id = None
                if body.media_id:
                    try:
                        target_media_id = uuid.UUID(str(body.media_id))
                    except (ValueError, AttributeError):
                        target_media_id = None

                if target_media_id:
                    media_row = await conn.fetchrow(
                        """
                        SELECT id, user_id, media_type, status, cdn_url
                        FROM user_media
                        WHERE id = $1 AND user_id = $2
                        """,
                        target_media_id, user_id,
                    )
                elif body.media_url:
                    media_row = await conn.fetchrow(
                        """
                        SELECT id, user_id, media_type, status, cdn_url
                        FROM user_media
                        WHERE cdn_url = $1 AND user_id = $2
                        """,
                        body.media_url, user_id,
                    )
                else:
                    media_row = None

                if not media_row:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Media attachment not found or not owned by user.",
                    )
                if media_row["status"] != "approved":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Media is not approved (status: {media_row['status']}).",
                    )
                if media_row["media_type"] != body.message_type:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Media type mismatch.",
                    )
                final_media_url = media_row["cdn_url"] or body.media_url
            elif body.message_type == "gif":
                final_media_url = body.media_url

            row = await conn.fetchrow(
                """
                INSERT INTO messages (
                    chat_id, sender_id, message_type, content, media_url,
                    is_moderated, moderation_type, moderation_disclaimer
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, chat_id, sender_id, message_type, content, media_url, is_read, created_at,
                          is_moderated, moderation_type, moderation_disclaimer
                """,
                actual_chat_id,
                user_id,
                body.message_type,
                final_content,
                final_media_url,
                is_moderated,
                mod_type,
                mod_disclaimer,
            )
            await conn.execute(
                "UPDATE chats SET updated_at = NOW() WHERE id = $1",
                actual_chat_id,
            )
            if chat.get("match_id"):
                await conn.execute(
                    """
                    UPDATE matches
                    SET last_message_at = NOW(),
                        expiry_warned = FALSE,
                        status = CASE WHEN status = 'expired' THEN 'active' ELSE status END,
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    chat["match_id"],
                )

    msg = ChatMessage(
        id=row["id"],
        chat_id=row["chat_id"],
        sender_id=row["sender_id"],
        message_type=row["message_type"],
        content=row["content"],
        media_url=row["media_url"],
        is_read=row["is_read"],
        created_at=row["created_at"],
        is_moderated=row["is_moderated"],
        moderation_type=row["moderation_type"],
        moderation_disclaimer=row["moderation_disclaimer"],
    )

    # Publish to Redis pub/sub for WebSocket fan-out (both chat_id and match_id if distinct)
    payload_str = json.dumps({
        "type": "message",
        "payload": {
            "id": str(msg.id),
            "chat_id": str(msg.chat_id),
            "sender_id": str(msg.sender_id),
            "message_type": msg.message_type,
            "content": msg.content,
            "media_url": msg.media_url,
            "created_at": msg.created_at.isoformat(),
            "is_moderated": msg.is_moderated,
            "moderation_type": msg.moderation_type,
            "moderation_disclaimer": msg.moderation_disclaimer,
        },
    })
    channels = {f"chat:{actual_chat_id}"}
    if chat.get("match_id"):
        channels.add(f"chat:{chat['match_id']}")
    channels.add(f"chat:{chat_id}")
    for ch in channels:
        await redis.publish(ch, payload_str)

    # Dispatch FCM push notification to recipient only if not actively in this chat
    try:
        recipient_active = await redis.get(f"presence:chat:{actual_chat_id}:{other_id}")
        if not recipient_active:
            from app.workers.notification_worker import notify_new_message
            preview_text = msg.content[:80] if msg.content else "Sent a media attachment"
            notify_new_message.delay(str(actual_chat_id), str(user_id), preview_text)
    except Exception:
        pass

    return msg


@router.post(
    "/{chat_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Mark all messages as read",
)
async def mark_read(
    chat_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep = None,
) -> Response:
    user_id = uuid.UUID(str(current_user["id"]))
    if redis is not None:
        await sliding_window_rate_limit(f"ratelimit:chats:read:{user_id}", 60, 60, redis)
    chat = await _assert_participant(chat_id, user_id, db)
    actual_chat_id = chat["id"]

    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE messages
            SET is_read = TRUE
            WHERE chat_id = $1 AND sender_id != $2 AND is_read = FALSE
            """,
            actual_chat_id, user_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.post(
    "/{chat_id}/unmatch",
    status_code=status.HTTP_200_OK,
    summary="Unmatch connection and permanently close chat thread",
)
async def unmatch_chat(
    chat_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    """
    Unmatch protocol per SECURITY.md Section 4.2 Layer 3:
    1. Sets chats.is_unmatched = TRUE and matches.status = 'unmatched'.
    2. Purges both users' feed session caches in Redis.
    3. Blocks future messaging attempts with 403 Forbidden.
    """
    user_id = uuid.UUID(str(current_user["id"]))
    await sliding_window_rate_limit(f"ratelimit:chats:unmatch:{user_id}", 15, 60, redis)
    chat = await _assert_participant(chat_id, user_id, db)
    actual_chat_id = chat["id"]
    p1 = chat["participant_1_id"]
    p2 = chat["participant_2_id"]
    other_id = p2 if p1 == user_id else p1

    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE chats SET is_unmatched = TRUE, updated_at = NOW() WHERE id = $1",
                actual_chat_id,
            )
            if chat.get("match_id"):
                await conn.execute(
                    "UPDATE matches SET status = 'unmatched', updated_at = NOW() WHERE id = $1",
                    chat["match_id"],
                )

    # Invalidate feed caches immediately
    await redis.delete(f"feed:cache:{user_id}")
    await redis.delete(f"feed:cache:{other_id}")

    # Evict active WebSocket sessions over Redis
    try:
        eviction_payload = json.dumps({"type": "chat_closed", "reason": "unmatched"})
        channels = {f"chat:{actual_chat_id}", f"chat:{chat_id}"}
        if chat.get("match_id"):
            channels.add(f"chat:{chat['match_id']}")
        for ch in channels:
            await redis.publish(ch, eviction_payload)
    except Exception:
        pass

    return {"success": True, "message": "Successfully unmatched. Chat thread locked."}
