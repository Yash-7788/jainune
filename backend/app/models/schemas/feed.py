from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FeedCandidate(BaseModel):
    id: UUID
    first_name: str
    age: Optional[int] = None
    city: Optional[str] = None
    state: Optional[str] = None
    distance_display: str = "Pan-India"
    dietary_strictness: Optional[str] = None
    eats_root_vegetables: bool = False
    eats_onion_garlic: bool = False
    community_sect: Optional[str] = None
    paryushan_mode: bool = False
    education: Optional[str] = None
    job_title: Optional[str] = None
    height_cm: Optional[int] = None
    bio: Optional[str] = None
    open_to_relocation: bool = True
    is_photo_verified: bool = False
    photos: list = []
    prompts: list = []
    voice_snapshot: Optional[dict] = None


class FeedResponse(BaseModel):
    candidates: list
    batch_id: str
    exhausted: bool
    from_cache: bool = False


class DailyCompatibleResponse(BaseModel):
    candidate: Optional[dict]
    pairing_algorithm: str
    locked_until: Optional[str] = None
