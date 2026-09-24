"""
In-process WebSocket Connection Manager for real-time chat, presence, and session control.
Eliminates Redis Pub/Sub dependencies and network overhead for single-instance deployments.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Set, Tuple

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSockets across chat rooms and user sessions.
    Thread-safe within the single-process asyncio event loop.
    """

    def __init__(self) -> None:
        # chat_id -> {user_id: Set[WebSocket]}
        self._chat_rooms: Dict[str, Dict[str, Set[WebSocket]]] = defaultdict(lambda: defaultdict(set))
        # user_id -> set[WebSocket] (supports multi-device/multi-tab sessions)
        self._user_sockets: Dict[str, Set[WebSocket]] = defaultdict(set)
        # (chat_id, user_id) -> expiry_timestamp
        self._presence: Dict[Tuple[str, str], float] = {}

    def register(self, chat_id: str, user_id: str, websocket: WebSocket) -> None:
        """Registers an accepted WebSocket connection into room and user registries."""
        cid = str(chat_id)
        uid = str(user_id)
        self._chat_rooms[cid][uid].add(websocket)
        self._user_sockets[uid].add(websocket)
        self.refresh_presence(cid, uid)
        log.debug("Registered WS connection for user %s in chat %s", uid, cid)

    def unregister(self, chat_id: str, user_id: str, websocket: WebSocket) -> None:
        """Removes a WebSocket connection on disconnect."""
        cid = str(chat_id)
        uid = str(user_id)

        if cid in self._chat_rooms:
            self._chat_rooms[cid][uid].discard(websocket)
            if not self._chat_rooms[cid][uid]:
                self._chat_rooms[cid].pop(uid, None)
            if not self._chat_rooms[cid]:
                self._chat_rooms.pop(cid, None)

        if uid in self._user_sockets:
            self._user_sockets[uid].discard(websocket)
            if not self._user_sockets[uid]:
                self._user_sockets.pop(uid, None)

        # Only clear presence if no sockets remain for this user in this room
        if cid not in self._chat_rooms or uid not in self._chat_rooms[cid]:
            self._presence.pop((cid, uid), None)
        log.debug("Unregistered WS connection for user %s in chat %s", uid, cid)

    async def broadcast_chat(
        self,
        chat_id: str,
        message: Dict[str, Any],
        exclude_user_id: Optional[str] = None,
    ) -> None:
        """
        Broadcasts message to all active participants in a chat room.
        Optionally excludes the sender (e.g. for typing indicators).
        """
        cid = str(chat_id)
        room = self._chat_rooms.get(cid)
        if not room:
            return

        dead_sockets: list[tuple[str, WebSocket]] = []
        for uid, ws_set in list(room.items()):
            if exclude_user_id and str(uid) == str(exclude_user_id):
                continue
            for ws in list(ws_set):
                try:
                    await asyncio.wait_for(ws.send_json(message), timeout=5.0)
                except Exception as exc:
                    log.warning("Failed to send message to user %s in chat %s: %s", uid, cid, exc)
                    dead_sockets.append((uid, ws))

        for uid, ws in dead_sockets:
            self.unregister(cid, uid, ws)

    async def close_chat(self, chat_id: str, reason: str = "unmatched") -> None:
        """Closes all active WebSockets for a chat room with 4003 policy code."""
        cid = str(chat_id)
        room = self._chat_rooms.pop(cid, None)
        if not room:
            return

        for uid, ws_set in list(room.items()):
            for ws in list(ws_set):
                if uid in self._user_sockets:
                    self._user_sockets[uid].discard(ws)
                try:
                    await ws.close(code=4003, reason=f"Chat closed: {reason}")
                except Exception:
                    pass
            if not self._user_sockets.get(uid):
                self._user_sockets.pop(uid, None)
            self._presence.pop((cid, uid), None)

    async def disconnect_user(self, user_id: str, reason: str = "Account disconnected.") -> None:
        """Forces disconnect on all active WebSocket sessions for a user (ban / session replace)."""
        uid = str(user_id)
        sockets = list(self._user_sockets.pop(uid, set()))
        if not sockets:
            return

        # Clean from all chat rooms
        for cid, room in list(self._chat_rooms.items()):
            if uid in room:
                room.pop(uid, None)
                if not room:
                    self._chat_rooms.pop(cid, None)
            self._presence.pop((cid, uid), None)

        for ws in sockets:
            try:
                await ws.close(code=4003, reason=reason)
            except Exception:
                pass
        log.info("Force-disconnected %d WebSocket(s) for user %s: %s", len(sockets), uid, reason)

    def is_present(self, chat_id: str, user_id: str) -> bool:
        """Checks if a user has sent a heartbeat/message in the last 75 seconds."""
        exp = self._presence.get((str(chat_id), str(user_id)), 0.0)
        return time.time() < exp

    def refresh_presence(self, chat_id: str, user_id: str) -> None:
        """Extends in-memory presence TTL by 75 seconds."""
        self._presence[(str(chat_id), str(user_id))] = time.time() + 75.0


# Global singleton instance
ws_manager = ConnectionManager()
