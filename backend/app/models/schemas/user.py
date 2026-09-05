from __future__ import annotations

import re
from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")


def _validate_phone(v: str) -> str:
    if not _PHONE_RE.match(v):
        raise ValueError("Phone number must be in E.164 format: +91XXXXXXXXXX")
    return v


# ---------------------------------------------------------------------------
# Enumerations (typed strings to avoid enum import overhead)
# ---------------------------------------------------------------------------

GENDER_VALUES = ("man", "woman", "nonbinary")
SHOW_ME_VALUES = ("men", "women", "everyone")
LOOKING_FOR_VALUES = ("marriage", "long_term", "figuring_out")
DIET_VALUES = ("pure_jain", "vaishnav", "ovo_veg", "vegan")
SECT_VALUES = (
    "digambar",
    "shwetambar_murtipujak",
    "shwetambar_sthanakvasi",
    "terapanthi",
    "open",
)
CONSENT_TYPES = (
    "core_matchmaking",
    "family_contact_gotra",
    "relocation_intercity",
)
BADGE_VALUES = (
    "punctual",
    "respects_diet",
    "real_photos",
    "great_conversation",
    "courteous",
)


# ---------------------------------------------------------------------------
# Step bodies (22-step onboarding flow)
# ---------------------------------------------------------------------------


class Step01PhoneBody(BaseModel):
    """Step 1: phone number already verified in auth flow; included here
    to allow the onboarding router to gate later steps."""

    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)


class Step02BasicInfoBody(BaseModel):
    """Step 2: name + date of birth."""

    first_name: str = Field(..., min_length=2, max_length=64)
    date_of_birth: date

    @field_validator("date_of_birth")
    @classmethod
    def validate_age(cls, v: date) -> date:
        from datetime import date as date_type

        today = date_type.today()
        age = (
            today.year
            - v.year
            - ((today.month, today.day) < (v.month, v.day))
        )
        if age < 18:
            raise ValueError("Minimum age is 18.")
        if age > 70:
            raise ValueError("Maximum age is 70.")
        return v


class Step03GenderBody(BaseModel):
    """Step 3: gender identity."""

    gender: str

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if v not in GENDER_VALUES:
            raise ValueError(f"Gender must be one of: {GENDER_VALUES}")
        return v


class Step04ShowMeBody(BaseModel):
    """Step 4: who to show in discovery feed."""

    show_me: str

    @field_validator("show_me")
    @classmethod
    def validate_show_me(cls, v: str) -> str:
        if v not in SHOW_ME_VALUES:
            raise ValueError(f"show_me must be one of: {SHOW_ME_VALUES}")
        return v


class Step05LookingForBody(BaseModel):
    """Step 5: relationship intent."""

    looking_for: str

    @field_validator("looking_for")
    @classmethod
    def validate_looking_for(cls, v: str) -> str:
        if v not in LOOKING_FOR_VALUES:
            raise ValueError(f"looking_for must be one of: {LOOKING_FOR_VALUES}")
        return v


class Step06DietaryStrictnessBody(BaseModel):
    """Step 6: dietary classification."""

    dietary_strictness: str

    @field_validator("dietary_strictness")
    @classmethod
    def validate_diet(cls, v: str) -> str:
        if v not in DIET_VALUES:
            raise ValueError(f"dietary_strictness must be one of: {DIET_VALUES}")
        return v


class Step07DietaryDetailsBody(BaseModel):
    """Step 7: root vegetables and onion-garlic consumption.
    Only shown when dietary_strictness is 'pure_jain' or 'vaishnav'."""

    eats_root_vegetables: bool
    eats_onion_garlic: bool


class Step08CommunitySectBody(BaseModel):
    """Step 8: Jain sectarian identity."""

    community_sect: str

    @field_validator("community_sect")
    @classmethod
    def validate_sect(cls, v: str) -> str:
        if v not in SECT_VALUES:
            raise ValueError(f"community_sect must be one of: {SECT_VALUES}")
        return v


class Step09ParyushanBody(BaseModel):
    """Step 9: Paryushan observance mode."""

    paryushan_mode: bool


class Step10CityBody(BaseModel):
    """Step 10: home city and state."""

    city: str = Field(..., min_length=2, max_length=64)
    state: str = Field(..., min_length=2, max_length=64)


class Step11LocationBody(BaseModel):
    """Step 11: GPS coordinates for proximity matching.
    Raw GPS is snapped to Geohash-6 centroid at DB trigger level."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    is_mocked: bool = Field(False, description="Device mock location or developer option flag")
    accuracy_meters: Optional[float] = Field(None, description="GPS horizontal accuracy in meters")


class Step12DistanceBody(BaseModel):
    """Step 12: local radius preference."""

    max_distance_km: int = Field(default=30, ge=5, le=200)


class Step13RelocationBody(BaseModel):
    """Step 13: pan-India relocation openness."""

    open_to_relocation: bool


class Step14HeightBody(BaseModel):
    """Step 14: height in cm."""

    height_cm: Optional[int] = Field(None, ge=120, le=250)


class Step15CareerBody(BaseModel):
    """Step 15: job title and company."""

    job_title: Optional[str] = Field(None, max_length=128)
    company: Optional[str] = Field(None, max_length=128)


class Step16EducationBody(BaseModel):
    """Step 16: highest education."""

    education: Optional[str] = Field(None, max_length=128)


class Step17BioBody(BaseModel):
    """Step 17: short bio."""

    bio: Optional[str] = Field(None, max_length=500)


class PromptItem(BaseModel):
    prompt_key: str = Field(..., max_length=64)
    response_text: str = Field(..., min_length=5, max_length=200)
    position: int = Field(..., ge=1, le=3)


class Step18PromptsBody(BaseModel):
    """Step 18: up to 3 prompts (questions + answers)."""

    prompts: List[PromptItem] = Field(..., min_length=1, max_length=3)

    @field_validator("prompts")
    @classmethod
    def validate_unique_positions(cls, v: List[PromptItem]) -> List[PromptItem]:
        positions = [p.position for p in v]
        if len(positions) != len(set(positions)):
            raise ValueError("Prompt positions must be unique (1, 2, 3).")
        return v


class Step19PhotosBody(BaseModel):
    """Step 19: confirm photos uploaded.
    Actual upload is done via presigned URL (/v1/media/presign-upload).
    This step marks the media_ids as confirmed by the user."""

    media_ids: List[UUID] = Field(..., min_length=1, max_length=6)


class Step20VoiceSnapshotBody(BaseModel):
    """Step 20: confirm 7-second voice snapshot uploaded."""

    media_id: UUID


class Step21ConsentBody(BaseModel):
    """Step 21: DPDP Act 2023 consent collection."""

    # core_matchmaking is always TRUE; others are optional
    core_matchmaking: bool = True
    family_contact_gotra: bool = False
    relocation_intercity: bool = False

    @field_validator("core_matchmaking")
    @classmethod
    def core_must_be_granted(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "Core matchmaking consent is mandatory to use Jainune."
            )
        return v


class Step22CompleteBody(BaseModel):
    """Step 22: final onboarding submission - client confirms completion."""

    confirmed: bool = True


# ---------------------------------------------------------------------------
# User profile read/update DTOs
# ---------------------------------------------------------------------------


class UserProfileResponse(BaseModel):
    id: UUID
    phone_number: Optional[str] = None
    email: Optional[str] = None
    auth_provider: str = "phone"
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    show_me: Optional[str] = None
    looking_for: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    max_distance_km: int = 50
    open_to_relocation: bool = False
    dietary_strictness: Optional[str] = None
    eats_root_vegetables: bool = False
    eats_onion_garlic: bool = False
    community_sect: Optional[str] = None
    paryushan_mode: bool = False
    job_title: Optional[str] = None
    company: Optional[str] = None
    education: Optional[str] = None
    height_cm: Optional[int] = None
    bio: Optional[str] = None
    subscription_tier: str = "free"
    is_photo_verified: bool = False
    account_status: str = "active"
    onboarding_completed: bool = False
    super_connect_credits: int = 0
    photos: List[dict] = Field(default_factory=list)
    prompts: List[dict] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UpdatePromptsBody(BaseModel):
    prompts: List[PromptItem] = Field(..., min_length=1, max_length=3)


class MediaPositionItem(BaseModel):
    media_id: UUID
    position: int = Field(..., ge=1, le=6)


class ReorderMediaBody(BaseModel):
    positions: List[MediaPositionItem]


class OnboardingStatusResponse(BaseModel):
    """Returned after each step to inform the client of current progress."""

    current_step: int
    total_steps: int = 22
    completed: bool
    next_step_hint: Optional[str] = None
