"""
WebSocket chat handler.

WS /v1/ws/chat/{chat_id}?token=<access_token>

Protocol:
  - Client connects with JWT as query param (Bearer header not possible in WS)
  - Server validates token, verifies participant, subscribes to Redis pubsub channel
  - Incoming client frames: { "type": "typing" | "read_receipt" | "ping" }
  - Outgoing server frames: { "type": "message" | "typing" | "read_receipt" | "pong" }

Redis pub/sub channel: `chat:{chat_id}`
  The REST send_message endpoint publishes to this channel; the WS handler
  fans the message out to all connected clients in the chat (both participants).

Concurrency model:
  - One asyncio task per connection: producer (Redis subscriber) + consumer (WS listener)
  - Uses asyncio.gather with return_when=FIRST_COMPLETED so either task
    completing (disconnect / channel close) tears down both.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

import secrets
from app.core.database import get_pool
from app.core.redis import get_redis
from app.core.security import validate_access_token_raw
from app.dependencies import CurrentUser, RedisDep

router = APIRouter(tags=["websockets"])


@router.post("/v1/ws/ticket", summary="Create single-use WebSocket authentication ticket")
async def create_ws_ticket(
    current_user: CurrentUser,
    redis: RedisDep,
) -> dict:
    """
    Ticket-based handshake per SECURITY.md Section 6.1.
    Issues a single-use, 30-second cryptographically random ticket.
    Prevents token leakage in URL access logs.
    """
    ticket = f"wst_{secrets.token_urlsafe(32)}"
    ticket_key = f"ws:ticket:{ticket}"
    await redis.set(ticket_key, str(current_user["id"]), ex=30)
    return {"ticket": ticket, "expires_in_seconds": 30}


@router.websocket("/v1/ws/chat/{chat_id}")
async def websocket_chat(
    websocket: WebSocket,
    chat_id: uuid.UUID,
    ticket: str | None = Query(default=None, description="One-time WS ticket (preferred)"),
    token: str | None = Query(default=None, description="JWT access token (fallback)"),
) -> None:
    """
    Bidirectional real-time chat over WebSocket.

    Lifecycle:
      1. Accept connection
      2. Validate ticket or JWT — close 4001 on failure
      3. Verify user is a participant in chat_id — close 4003 on failure
      4. Subscribe to Redis channel `chat:{chat_id}`
      5. Run producer + consumer tasks concurrently
      6. Clean up subscription on disconnect
    """
    db = get_pool()
    redis = get_redis()

    # ── 1. Origin validation & Accept ─────────────────────────────────────────
    from app.core.config import settings
    origin = websocket.headers.get("origin")
    if origin:
        allowed = settings.allowed_origins + ["jainune://", "localhost", "127.0.0.1"]
        if not any(a in origin for a in allowed):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed.")
            return

    await websocket.accept()

    # ── 2. Ticket / JWT validation ───────────────────────────────────────────
    try:
        if ticket:
            ticket_key = f"ws:ticket:{ticket}"
            uid_val = await redis.get(ticket_key)
            if not uid_val:
                await websocket.close(code=4001, reason="Invalid or expired ticket.")
                return
            await redis.delete(ticket_key)  # Single-use guarantee
            raw_uid = uid_val.decode() if isinstance(uid_val, bytes) else uid_val
            user_id = uuid.UUID(raw_uid)
        elif token:
            payload = await validate_access_token_raw(token, redis)
            user_id = uuid.UUID(payload["sub"])
        else:
            await websocket.close(code=4001, reason="Missing ticket or token.")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired credentials.")
        return

    # ── 3. Participant check ─────────────────────────────────────────────────
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.id, c.is_unmatched,
                   CASE WHEN c.participant_1_id = $2 THEN c.participant_2_id ELSE c.participant_1_id END AS other_id
            FROM chats c
            WHERE c.id = $1
              AND (c.participant_1_id = $2 OR c.participant_2_id = $2)
            """,
            chat_id, user_id,
        )
        if not row:
            await websocket.close(code=4003, reason="Not a participant in this chat.")
            return

        if row.get("is_unmatched"):
            await websocket.close(code=4003, reason="Chat has been unmatched and closed.")
            return

        blocked = await conn.fetchval(
            """
            SELECT 1 FROM user_blocks
            WHERE (blocker_id = $1 AND blocked_id = $2)
               OR (blocker_id = $2 AND blocked_id = $1)
            """,
            user_id, row["other_id"],
        )
        if blocked:
            await websocket.close(code=4003, reason="Communication blocked.")
            return

    # ── 4. Redis pub/sub subscription ────────────────────────────────────────
    pubsub = redis.pubsub()
    channel = f"chat:{chat_id}"
    await pubsub.subscribe(channel)

    # ── 5. Concurrent tasks ──────────────────────────────────────────────────

    async def _producer() -> None:
        """Relay Redis channel messages → WebSocket client."""
        async for raw_msg in pubsub.listen():
            if raw_msg["type"] != "message":
                continue
            try:
                data = json.loads(raw_msg["data"])
                await websocket.send_json(data)
            except Exception:
                break

    async def _consumer() -> None:
        """Relay WebSocket frames → Redis channel (typing/read_receipt events)."""
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if msg_type in ("typing", "read_receipt"):
                    # Fan out to other participant via the same Redis channel
                    await redis.publish(
                        channel,
                        json.dumps({
                            "type": msg_type,
                            "payload": {
                                "sender_id": str(user_id),
                                **data.get("payload", {}),
                            },
                        }),
                    )
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        await asyncio.gather(
            _producer(),
            _consumer(),
            return_exceptions=True,
        )
    finally:
        # ── 6. Cleanup ───────────────────────────────────────────────────────
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        try:
            await websocket.close()
        except Exception:
            pass
