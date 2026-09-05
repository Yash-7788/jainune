from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ChatThread(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    other_user_id: uuid.UUID
    other_user_first_name: str
    other_user_photo_url: Optional[str] = None
    last_message_text: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    is_ephemeral: bool = False
    expires_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    message_type: str  # "text" | "image" | "voice" | "gif" | "dilemma_invite"
    content: Optional[str] = None
    media_url: Optional[str] = None
    is_read: bool = False
    created_at: datetime


class SendMessageRequest(BaseModel):
    message_type: str = "text"
    content: Optional[str] = None
    media_url: Optional[str] = None

    def validate_content(self) -> None:
        if self.message_type == "text" and not self.content:
            raise ValueError("content required for text messages")
        if self.message_type in ("image", "voice", "gif") and not self.media_url:
            raise ValueError("media_url required for media messages")


class ChatListResponse(BaseModel):
    threads: List[ChatThread]


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessage]
    has_more: bool
    next_cursor: Optional[str] = None


class WSMessage(BaseModel):
    """Shape of messages sent over the WebSocket channel."""
    type: str   # "message" | "typing" | "read_receipt" | "ping"
    payload: dict = {}
