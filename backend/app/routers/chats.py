"""
Chat REST router.

GET  /v1/chats                       → list all chat threads for current user
GET  /v1/chats/{chat_id}/messages    → paginated message history (cursor-based)
POST /v1/chats/{chat_id}/messages    → send a message (text / media)
POST /v1/chats/{chat_id}/read        → mark all messages as read
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DBDep, RedisDep
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
    """Fetch chat row and verify the requesting user is a participant."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, match_id, participant_1_id, participant_2_id,
                   is_ephemeral, expires_at
            FROM chats
            WHERE id = $1
              AND (participant_1_id = $2 OR participant_2_id = $2)
            """,
            chat_id, user_id,
        )
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
) -> ChatListResponse:
    """
    Returns all active chat threads for the current user, ordered by most
    recent message. Includes other participant's name, photo, and last message.
    """
    user_id = uuid.UUID(str(current_user["id"]))

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
                -- Last message
                lm.content   AS last_message_text,
                lm.created_at AS last_message_at,
                -- Unread count
                (
                    SELECT COUNT(*) FROM messages m2
                    WHERE m2.chat_id = c.id
                      AND m2.sender_id != $1
                      AND m2.is_read = FALSE
                ) AS unread_count
            FROM chats c
            LEFT JOIN LATERAL (
                SELECT content, created_at FROM messages
                WHERE chat_id = c.id
                ORDER BY created_at DESC
                LIMIT 1
            ) lm ON TRUE
            WHERE c.participant_1_id = $1 OR c.participant_2_id = $1
            ORDER BY lm.created_at DESC NULLS LAST
            """,
            user_id,
        )

        # Batch-fetch other participants' names + primary photo
        other_ids = [r["other_user_id"] for r in rows]
        user_meta: dict[str, dict] = {}
        if other_ids:
            u_rows = await conn.fetch(
                """
                SELECT u.id, u.first_name,
                       (SELECT cdn_url FROM user_media
                        WHERE user_id = u.id AND media_type = 'photo'
                          AND is_processed = TRUE
                        ORDER BY position ASC LIMIT 1) AS photo_url
                FROM users u
                WHERE u.id = ANY($1::uuid[])
                """,
                other_ids,
            )
            for u in u_rows:
                user_meta[str(u["id"])] = {
                    "first_name": u["first_name"],
                    "photo_url": u["photo_url"],
                }

    threads = []
    for r in rows:
        other_id = str(r["other_user_id"])
        meta = user_meta.get(other_id, {})
        threads.append(ChatThread(
            id=r["id"],
            match_id=r["match_id"],
            other_user_id=r["other_user_id"],
            other_user_first_name=meta.get("first_name", ""),
            other_user_photo_url=meta.get("photo_url"),
            last_message_text=r["last_message_text"],
            last_message_at=r["last_message_at"],
            unread_count=r["unread_count"],
            is_ephemeral=r["is_ephemeral"],
            expires_at=r["expires_at"],
        ))

    return ChatListResponse(threads=threads)


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
) -> ChatHistoryResponse:
    user_id = uuid.UUID(str(current_user["id"]))
    await _assert_participant(chat_id, user_id, db)

    async with db.acquire() as conn:
        if before:
            # Cursor-based: fetch messages older than `before` message id
            try:
                before_uuid = uuid.UUID(before)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor.")
            before_ts = await conn.fetchval(
                "SELECT created_at FROM messages WHERE id = $1", before_uuid
            )
            rows = await conn.fetch(
                """
                SELECT id, chat_id, sender_id, message_type, content,
                       media_url, is_read, created_at
                FROM messages
                WHERE chat_id = $1 AND created_at < $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                chat_id, before_ts, limit + 1,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, chat_id, sender_id, message_type, content,
                       media_url, is_read, created_at
                FROM messages
                WHERE chat_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                chat_id, limit + 1,
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
    """
    user_id = uuid.UUID(str(current_user["id"]))
    chat = await _assert_participant(chat_id, user_id, db)

    # Validate ephemeral expiry
    from datetime import datetime, timezone
    if chat.get("expires_at") and chat["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This chat has expired.",
        )

    body.validate_content()

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO messages (chat_id, sender_id, message_type, content, media_url)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, chat_id, sender_id, message_type, content, media_url, is_read, created_at
            """,
            chat_id,
            user_id,
            body.message_type,
            body.content,
            body.media_url,
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
    )

    # Publish to Redis pub/sub for WebSocket fan-out
    import json
    await redis.publish(
        f"chat:{chat_id}",
        json.dumps({
            "type": "message",
            "payload": {
                "id": str(msg.id),
                "sender_id": str(msg.sender_id),
                "message_type": msg.message_type,
                "content": msg.content,
                "media_url": msg.media_url,
                "created_at": msg.created_at.isoformat(),
            },
        }),
    )

    return msg


@router.post(
    "/{chat_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all messages as read",
)
async def mark_read(
    chat_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBDep,
) -> None:
    user_id = uuid.UUID(str(current_user["id"]))
    await _assert_participant(chat_id, user_id, db)

    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE messages
            SET is_read = TRUE
            WHERE chat_id = $1 AND sender_id != $2 AND is_read = FALSE
            """,
            chat_id, user_id,
        )
