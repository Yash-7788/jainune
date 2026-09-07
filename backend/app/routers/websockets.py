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

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

import secrets
from app.core.database import get_pool
from app.core.redis import get_redis
from app.core.security import validate_access_token_raw, sliding_window_rate_limit
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
    user_id = str(current_user.get("user_id") or current_user.get("id"))
    await sliding_window_rate_limit(f"ratelimit:ws_ticket:{user_id}", 30, 60, redis)
    ticket = f"wst_{secrets.token_urlsafe(32)}"
    ticket_key = f"ws:ticket:{ticket}"
    await redis.set(ticket_key, user_id, ex=30)
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
    from urllib.parse import urlparse
    from app.core.config import settings
    origin = websocket.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        host = (parsed.netloc or parsed.path).split(":")[0].lower()
        allowed_hosts = {
            (urlparse(a).netloc or a).split(":")[0].lower()
            for a in settings.allowed_origins
        }
        allowed_hosts.update({"localhost", "127.0.0.1"})
        if host not in allowed_hosts and not origin.startswith("jainune://"):
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

    # Sliding window connection rate limit: 30 connects per 60s per user to prevent DoS
    try:
        await sliding_window_rate_limit(f"ratelimit:ws_connect:{user_id}", 30, 60, redis)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Rate limit exceeded.")
        return
    except Exception:
        pass

    # ── 3. Participant and account status check ──────────────────────────────
    async with db.acquire() as conn:
        caller_row = await conn.fetchrow(
            "SELECT account_status, suspend_until, deleted_at FROM users WHERE id = $1",
            user_id,
        )
        from datetime import datetime, timezone
        if not caller_row or caller_row.get("account_status") in ("banned", "deleted") or caller_row.get("deleted_at") is not None:
            await websocket.close(code=4003, reason="Account is banned or deleted.")
            return

        suspend_until = caller_row.get("suspend_until")
        if caller_row.get("account_status") == "suspended" or (suspend_until and suspend_until > datetime.now(timezone.utc)):
            await websocket.close(code=4003, reason="Account is suspended.")
            return

        row = await conn.fetchrow(
            """
            SELECT c.id, c.match_id, c.is_unmatched,
                   CASE WHEN c.participant_1_id = $2 THEN c.participant_2_id ELSE c.participant_1_id END AS other_id
            FROM chats c
            WHERE (c.id = $1 OR c.match_id = $1)
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

        other_row = await conn.fetchrow(
            "SELECT account_status, deleted_at FROM users WHERE id = $1",
            row["other_id"],
        )
        if not other_row or other_row.get("account_status") in ("banned", "deleted") or other_row.get("deleted_at") is not None:
            await websocket.close(code=4003, reason="Recipient account is no longer active.")
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
    real_chat_id = row["id"]
    sub_channels = {f"chat:{real_chat_id}", f"chat:{chat_id}"}
    if row.get("match_id"):
        sub_channels.add(f"chat:{row['match_id']}")
    await pubsub.subscribe(*sub_channels)

    # ── 5. Concurrent tasks ──────────────────────────────────────────────────

    async def _producer() -> None:
        """Relay Redis channel messages → WebSocket client with slow-consumer protection."""
        try:
            async for raw_msg in pubsub.listen():
                if raw_msg["type"] != "message":
                    continue
                try:
                    data = json.loads(raw_msg["data"])
                    await asyncio.wait_for(websocket.send_json(data), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    break
        except asyncio.CancelledError:
            pass

    async def _consumer() -> None:
        """Relay WebSocket frames → Redis channel with 60s zombie heartbeat timeout."""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    break
                except Exception:
                    continue

                if not isinstance(data, dict):
                    continue

                msg_type = data.get("type", "")
                if msg_type == "ping":
                    try:
                        await asyncio.wait_for(websocket.send_json({"type": "pong"}), timeout=5.0)
                    except Exception:
                        break
                    continue

                if msg_type in ("typing", "read_receipt"):
                    # Fan out to other participant via the same Redis channel
                    try:
                        await redis.publish(
                            f"chat:{real_chat_id}",
                            json.dumps({
                                "type": msg_type,
                                "payload": {
                                    "sender_id": str(user_id),
                                    **data.get("payload", {}),
                                },
                            }),
                        )
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    try:
        producer_task = asyncio.create_task(_producer())
        consumer_task = asyncio.create_task(_consumer())
        done, pending = await asyncio.wait(
            [producer_task, consumer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        # ── 6. Cleanup ───────────────────────────────────────────────────────
        try:
            await pubsub.unsubscribe(*sub_channels)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
