"""
Onboarding router - 22-step sequential profile construction.

Each step is an idempotent PATCH. The client may re-submit any step to
correct a previous value. The current step is tracked in the `onboarding_step`
column (added in migration 0002 via ALTER TABLE users). Completing step 22
sets `onboarding_completed = TRUE` and marks the account as active.

Step gate: every step past step 1 requires the user to be authenticated
(CurrentUser dependency). Step 1 is gated by the auth flow (OTP verify
already ran and created the user row).

Rate limit: 60 onboarding mutations per hour per user (generous to allow
corrections) enforced via sliding-window Redis key.
"""
from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import sliding_window_rate_limit
from app.dependencies import CurrentUser, DBDep, RedisDep
from app.models.schemas.user import (
    OnboardingStatusResponse,
    Step02BasicInfoBody,
    Step03GenderBody,
    Step04ShowMeBody,
    Step05LookingForBody,
    Step06DietaryStrictnessBody,
    Step07DietaryDetailsBody,
    Step08CommunitySectBody,
    Step09ParyushanBody,
    Step10CityBody,
    Step11LocationBody,
    Step12DistanceBody,
    Step13RelocationBody,
    Step14HeightBody,
    Step15CareerBody,
    Step16EducationBody,
    Step17BioBody,
    Step18PromptsBody,
    Step19PhotosBody,
    Step20VoiceSnapshotBody,
    Step21ConsentBody,
    Step22CompleteBody,
)
from app.services.location_verifier import (
    verify_location_anti_spoofing,
    verify_location_zone,
)

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

TOTAL_STEPS = 22

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _status(step: int, completed: bool, hint: str | None = None) -> dict:
    return {
        "success": True,
        "data": {
            "current_step": step,
            "total_steps": TOTAL_STEPS,
            "completed": completed,
            "next_step_hint": hint,
        },
        "error": None,
    }


async def _update_user(
    conn,
    user_id: uuid.UUID,
    step: int,
    fields: dict,
) -> None:
    """Build and execute a parameterized UPDATE for the given fields + step."""
    if not fields:
        return
    set_clauses = ", ".join(
        f"{col} = ${i + 1}" for i, col in enumerate(fields.keys())
    )
    values = list(fields.values())
    # Append step number and user_id
    set_clauses += f", onboarding_step = ${len(values) + 1}"
    values.append(step)
    values.append(user_id)
    await conn.execute(
        f"UPDATE users SET {set_clauses}, updated_at = NOW() WHERE id = ${len(values)}",
        *values,
    )


async def _guard_rate_limit(user_id: uuid.UUID, redis) -> None:
    key = f"rl:onboarding:{user_id}"
    await sliding_window_rate_limit(key, limit=60, window_seconds=3600, redis=redis)


async def _require_onboarding_not_completed(user_id: uuid.UUID, db) -> None:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT onboarding_completed FROM users WHERE id = $1", user_id
        )
    if row and row["onboarding_completed"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding already completed. Use profile update endpoints.",
        )


# ---------------------------------------------------------------------------
# Step 2 - Basic Info
# ---------------------------------------------------------------------------


@router.patch("/step/2", response_model=None)
async def step2_basic_info(
    body: Step02BasicInfoBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn,
            current_user.id,
            step=2,
            fields={
                "first_name": body.first_name,
                "date_of_birth": body.date_of_birth,
            },
        )
    return _status(2, False, "Select your gender on step 3.")


# ---------------------------------------------------------------------------
# Step 3 - Gender
# ---------------------------------------------------------------------------


@router.patch("/step/3", response_model=None)
async def step3_gender(
    body: Step03GenderBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(conn, current_user.id, 3, {"gender": body.gender})
    return _status(3, False, "Select who you want to see on step 4.")


# ---------------------------------------------------------------------------
# Step 4 - Show Me
# ---------------------------------------------------------------------------


@router.patch("/step/4", response_model=None)
async def step4_show_me(
    body: Step04ShowMeBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(conn, current_user.id, 4, {"show_me": body.show_me})
    return _status(4, False, "Tell us what you are looking for on step 5.")


# ---------------------------------------------------------------------------
# Step 5 - Looking For
# ---------------------------------------------------------------------------


@router.patch("/step/5", response_model=None)
async def step5_looking_for(
    body: Step05LookingForBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 5, {"looking_for": body.looking_for}
        )
    return _status(5, False, "Select your dietary strictness on step 6.")


# ---------------------------------------------------------------------------
# Step 6 - Dietary Strictness
# ---------------------------------------------------------------------------


@router.patch("/step/6", response_model=None)
async def step6_dietary_strictness(
    body: Step06DietaryStrictnessBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn,
            current_user.id,
            6,
            {"dietary_strictness": body.dietary_strictness},
        )
    return _status(6, False, "Specify dietary details on step 7.")


# ---------------------------------------------------------------------------
# Step 7 - Dietary Details
# ---------------------------------------------------------------------------


@router.patch("/step/7", response_model=None)
async def step7_dietary_details(
    body: Step07DietaryDetailsBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn,
            current_user.id,
            7,
            {
                "eats_root_vegetables": body.eats_root_vegetables,
                "eats_onion_garlic": body.eats_onion_garlic,
            },
        )
    return _status(7, False, "Select your community sect on step 8.")


# ---------------------------------------------------------------------------
# Step 8 - Community Sect
# ---------------------------------------------------------------------------


@router.patch("/step/8", response_model=None)
async def step8_community_sect(
    body: Step08CommunitySectBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 8, {"community_sect": body.community_sect}
        )
    return _status(8, False, "Paryushan observance on step 9.")


# ---------------------------------------------------------------------------
# Step 9 - Paryushan Mode
# ---------------------------------------------------------------------------


@router.patch("/step/9", response_model=None)
async def step9_paryushan(
    body: Step09ParyushanBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 9, {"paryushan_mode": body.paryushan_mode}
        )
    return _status(9, False, "Select your city on step 10.")


# ---------------------------------------------------------------------------
# Step 10 - City / State
# ---------------------------------------------------------------------------


@router.patch("/step/10", response_model=None)
async def step10_city(
    body: Step10CityBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 10, {"city": body.city, "state": body.state}
        )
    return _status(10, False, "Share GPS location for proximity matching on step 11.")


# ---------------------------------------------------------------------------
# Step 11 - GPS Location
# ---------------------------------------------------------------------------


@router.patch("/step/11", response_model=None)
async def step11_location(
    body: Step11LocationBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    """
    Stores raw GPS as a PostGIS geometry point. The trg_snap_user_location
    trigger immediately snaps it to the Geohash-6 centroid before commit.
    The application never stores or returns raw coordinates.
    Gated to active operational launch zones (Mumbai MMR, Pune, Bengaluru).
    """
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)

    valid_gps, spoof_error = verify_location_anti_spoofing(
        lat=body.latitude,
        lon=body.longitude,
        is_mocked=body.is_mocked,
        accuracy_meters=body.accuracy_meters,
    )
    if not valid_gps:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=spoof_error or "GPS location verification failed.",
        )

    is_allowed, zone = verify_location_zone(body.latitude, body.longitude)
    if not is_allowed or not zone:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jainune is currently active in Mumbai MMR, Pune, and Bengaluru. We'll be in your city soon! 🚀",
        )

    async with db.acquire() as conn:
        # ST_MakePoint(lon, lat) per PostGIS convention; SRID 4326
        await conn.execute(
            """
            UPDATE users
            SET location = ST_SetSRID(ST_MakePoint($1, $2), 4326),
                location_zone = $3,
                onboarding_step = 11,
                updated_at = NOW()
            WHERE id = $4
            """,
            body.longitude,
            body.latitude,
            zone["id"],
            current_user.id,
        )
    return _status(11, False, "Set local discovery radius on step 12.")


# ---------------------------------------------------------------------------
# Step 12 - Max Distance
# ---------------------------------------------------------------------------


@router.patch("/step/12", response_model=None)
async def step12_distance(
    body: Step12DistanceBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 12, {"max_distance_km": body.max_distance_km}
        )
    return _status(12, False, "Set relocation preference on step 13.")


# ---------------------------------------------------------------------------
# Step 13 - Relocation
# ---------------------------------------------------------------------------


@router.patch("/step/13", response_model=None)
async def step13_relocation(
    body: Step13RelocationBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn,
            current_user.id,
            13,
            {"open_to_relocation": body.open_to_relocation},
        )
    return _status(13, False, "Enter height on step 14.")


# ---------------------------------------------------------------------------
# Step 14 - Height
# ---------------------------------------------------------------------------


@router.patch("/step/14", response_model=None)
async def step14_height(
    body: Step14HeightBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 14, {"height_cm": body.height_cm}
        )
    return _status(14, False, "Enter career details on step 15.")


# ---------------------------------------------------------------------------
# Step 15 - Career
# ---------------------------------------------------------------------------


@router.patch("/step/15", response_model=None)
async def step15_career(
    body: Step15CareerBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn,
            current_user.id,
            15,
            {"job_title": body.job_title, "company": body.company},
        )
    return _status(15, False, "Enter education on step 16.")


# ---------------------------------------------------------------------------
# Step 16 - Education
# ---------------------------------------------------------------------------


@router.patch("/step/16", response_model=None)
async def step16_education(
    body: Step16EducationBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(
            conn, current_user.id, 16, {"education": body.education}
        )
    return _status(16, False, "Write your bio on step 17.")


# ---------------------------------------------------------------------------
# Step 17 - Bio
# ---------------------------------------------------------------------------


@router.patch("/step/17", response_model=None)
async def step17_bio(
    body: Step17BioBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        await _update_user(conn, current_user.id, 17, {"bio": body.bio})
    return _status(17, False, "Add your prompts on step 18.")


# ---------------------------------------------------------------------------
# Step 18 - Prompts (1-3 question/answer pairs)
# ---------------------------------------------------------------------------


@router.patch("/step/18", response_model=None)
async def step18_prompts(
    body: Step18PromptsBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        async with conn.transaction():
            # Delete existing prompts before upsert to handle re-submissions
            await conn.execute(
                "DELETE FROM user_prompts WHERE user_id = $1", current_user.id
            )
            for p in body.prompts:
                await conn.execute(
                    """
                    INSERT INTO user_prompts (user_id, prompt_key, response_text, position)
                    VALUES ($1, $2, $3, $4)
                    """,
                    current_user.id,
                    p.prompt_key,
                    p.response_text,
                    p.position,
                )
            await conn.execute(
                "UPDATE users SET onboarding_step = 18, updated_at = NOW() WHERE id = $1",
                current_user.id,
            )
    return _status(18, False, "Upload your photos on step 19.")


# ---------------------------------------------------------------------------
# Step 19 - Photos confirmation
# ---------------------------------------------------------------------------


@router.patch("/step/19", response_model=None)
async def step19_photos(
    body: Step19PhotosBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    """
    Confirms that the user has uploaded photos via presigned URL flow.
    Verifies that each media_id exists in user_media and belongs to this user.
    """
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        # Validate ownership and existence for all provided media IDs
        rows = await conn.fetch(
            """
            SELECT id FROM user_media
            WHERE user_id = $1
              AND media_type = 'photo'
              AND id = ANY($2::uuid[])
            """,
            current_user.id,
            [str(m) for m in body.media_ids],
        )
        confirmed_ids = {str(r["id"]) for r in rows}
        requested_ids = {str(m) for m in body.media_ids}
        if not requested_ids.issubset(confirmed_ids):
            missing = requested_ids - confirmed_ids
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Media IDs not found or do not belong to this user: {missing}",
            )
        await conn.execute(
            "UPDATE users SET onboarding_step = 19, updated_at = NOW() WHERE id = $1",
            current_user.id,
        )
    return _status(19, False, "Upload your 7-second voice snapshot on step 20.")


# ---------------------------------------------------------------------------
# Step 20 - Voice Snapshot confirmation
# ---------------------------------------------------------------------------


@router.patch("/step/20", response_model=None)
async def step20_voice_snapshot(
    body: Step20VoiceSnapshotBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM user_media
            WHERE user_id = $1 AND media_type = 'voice' AND id = $2
            """,
            current_user.id,
            body.media_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Voice snapshot not found or does not belong to this user.",
            )
        await conn.execute(
            "UPDATE users SET onboarding_step = 20, updated_at = NOW() WHERE id = $1",
            current_user.id,
        )
    return _status(20, False, "Review and accept consent terms on step 21.")


# ---------------------------------------------------------------------------
# Step 21 - Consent (DPDP Act 2023)
# ---------------------------------------------------------------------------


@router.patch("/step/21", response_model=None)
async def step21_consent(
    body: Step21ConsentBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    await _guard_rate_limit(current_user.id, redis)
    await _require_onboarding_not_completed(current_user.id, db)
    consents = [
        ("core_matchmaking", body.core_matchmaking),
        ("family_contact_gotra", body.family_contact_gotra),
        ("relocation_intercity", body.relocation_intercity),
    ]
    async with db.acquire() as conn:
        async with conn.transaction():
            for consent_type, granted in consents:
                await conn.execute(
                    """
                    INSERT INTO consent_records (user_id, consent_type, granted, consent_version)
                    VALUES ($1, $2, $3, '1.0.0')
                    ON CONFLICT DO NOTHING
                    """,
                    current_user.id,
                    consent_type,
                    granted,
                )
            await conn.execute(
                "UPDATE users SET onboarding_step = 21, updated_at = NOW() WHERE id = $1",
                current_user.id,
            )
    return _status(21, False, "Confirm completion on step 22.")


# ---------------------------------------------------------------------------
# Step 22 - Complete Onboarding
# ---------------------------------------------------------------------------


@router.patch("/step/22", response_model=None)
async def step22_complete(
    body: Step22CompleteBody,
    current_user: CurrentUser,
    db: DBDep,
    redis: RedisDep,
) -> dict:
    """
    Final onboarding step. Validates that all mandatory fields are present
    before marking onboarding_completed = TRUE and account_status = 'active'.
    Also initializes the user_behavior_vectors row with a zero-vector.
    """
    await _guard_rate_limit(current_user.id, redis)

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                first_name, date_of_birth, gender, show_me, looking_for,
                dietary_strictness, community_sect, city, state, location,
                onboarding_completed
            FROM users WHERE id = $1
            """,
            current_user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        if row["onboarding_completed"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Onboarding already completed.",
            )

        # Check mandatory fields
        required = [
            "first_name", "date_of_birth", "gender", "show_me", "looking_for",
            "dietary_strictness", "community_sect", "city", "state",
        ]
        missing = [f for f in required if not row[f]]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Mandatory fields not completed: {missing}",
            )
        if not row["location"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Location (step 11) is required to complete onboarding.",
            )

        async with conn.transaction():
            # Mark onboarding complete and activate account
            await conn.execute(
                """
                UPDATE users
                SET onboarding_completed = TRUE,
                    account_status = 'active',
                    onboarding_step = 22,
                    updated_at = NOW()
                WHERE id = $1
                """,
                current_user.id,
            )
            # Initialize behavior vector row with uniform zero-vector (128d)
            # The vector is represented as a list of 128 zeros in pgvector format
            zero_vec = "[" + ",".join(["0"] * 128) + "]"
            await conn.execute(
                """
                INSERT INTO user_behavior_vectors (user_id, revealed_preference_vector)
                VALUES ($1, $2::vector)
                ON CONFLICT (user_id) DO NOTHING
                """,
                current_user.id,
                zero_vec,
            )

    # Purge any onboarding-step cache keys from Redis
    await redis.delete(f"user:onboarding:{current_user.id}")

    return _status(22, True, None)


# ---------------------------------------------------------------------------
# GET current onboarding status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=None)
async def get_onboarding_status(
    current_user: CurrentUser,
    db: DBDep,
) -> dict:
    """Returns the user's current onboarding step and completion state."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT onboarding_step, onboarding_completed FROM users WHERE id = $1",
            current_user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    step = row["onboarding_step"] or 1
    completed = row["onboarding_completed"] or False
    return _status(step, completed)
