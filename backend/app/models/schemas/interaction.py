from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


class InteractionActionRequest(BaseModel):
    target_id: Optional[UUID] = None
    target_user_id: Optional[UUID] = None
    action: str  # "like" | "pass" | "super_connect"
    prompt_id: Optional[str] = None   # which prompt they reacted to (for vector update)
    reaction_emoji: Optional[str] = None  # super_connect flavour emoji
    target_element_type: Optional[str] = None
    target_element_id: Optional[str] = None
    comment: Optional[str] = None
    voice_note_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values):
        if isinstance(values, dict):
            # Map target_user_id to target_id if target_id is omitted
            if not values.get("target_id") and values.get("target_user_id"):
                values["target_id"] = values["target_user_id"]
            # Normalize superlike -> super_connect
            if values.get("action") == "superlike":
                values["action"] = "super_connect"
        return values

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v == "superlike":
            return "super_connect"
        allowed = {"like", "pass", "super_connect"}
        if v not in allowed:
            raise ValueError(f"action must be one of {allowed}")
        return v


class InteractionActionResponse(BaseModel):
    success: bool
    match_created: bool = False
    is_match: bool = False
    chat_id: Optional[UUID] = None
    message: str = ""
    match_timestamp: Optional[str] = None
    momentum_window_hours: int = 48
