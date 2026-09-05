from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class InteractionActionRequest(BaseModel):
    target_id: UUID
    action: str  # "like" | "pass" | "super_connect"
    prompt_id: Optional[str] = None   # which prompt they reacted to (for vector update)
    reaction_emoji: Optional[str] = None  # super_connect flavour emoji

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"like", "pass", "super_connect"}
        if v not in allowed:
            raise ValueError(f"action must be one of {allowed}")
        return v


class InteractionActionResponse(BaseModel):
    success: bool
    match_created: bool = False
    chat_id: Optional[UUID] = None
    message: str = ""
