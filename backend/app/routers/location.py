"""
Location router — operational geofence verification and waitlist registration.

Active Launch Zones:
  1. Mumbai Metropolitan Region (MMR)
  2. Pune & Pimpri-Chinchwad (PCMC)
  3. Bengaluru Metropolitan Area
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.database import get_pool
from app.core.security import get_trusted_client_ip, sliding_window_rate_limit
from app.dependencies import get_current_user, RedisDep
import asyncpg

from app.core.responses import ok
from app.services.location_verifier import (
    LAUNCH_ZONES,
    save_city_waitlist,
    verify_location_anti_spoofing,
    verify_location_zone,
)

router = APIRouter(prefix="/v1/location", tags=["Location"])


class VerifyLocationRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    phone_number: Optional[str] = Field(None, max_length=16)
    city_hint: Optional[str] = Field(None, max_length=128)
    is_mocked: bool = Field(False, description="Device mock location or developer option flag")
    accuracy_meters: Optional[float] = Field(None, description="GPS horizontal accuracy in meters")


class LocationZoneResponse(BaseModel):
    allowed: bool
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    state: Optional[str] = None
    distance_to_center_km: Optional[float] = None
    message: str


@router.post("/verify", summary="Verify GPS coordinates against active operational zones")
async def verify_location(
    body: VerifyLocationRequest,
    request: Request,
    redis: RedisDep,
    current_user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """
    Called by mobile app after location permission is granted:
    - Verifies anti-spoofing (mock provider, coordinate anomalies).
    - If coordinates are inside Mumbai MMR, Pune PCMC, or Bengaluru: returns allowed=True.
    - If outside: returns allowed=False and automatically logs entry to location_waitlist.
    """
    user_id = current_user.get("id") or current_user.get("user_id")
    await sliding_window_rate_limit(f"ratelimit:loc_verify:{user_id}", 15, 60, redis)

    # 1. Anti-spoofing & integrity gate
    client_ip = get_trusted_client_ip(request)
    valid_gps, spoof_error = verify_location_anti_spoofing(
        lat=body.latitude,
        lon=body.longitude,
        is_mocked=body.is_mocked,
        accuracy_meters=body.accuracy_meters,
        client_ip=client_ip,
        headers=dict(request.headers),
    )
    if not valid_gps:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=spoof_error or "GPS location verification failed.",
        )

    is_allowed, zone = verify_location_zone(body.latitude, body.longitude)

    if is_allowed and zone:
        import uuid
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE users
                    SET location = ST_SetSRID(ST_MakePoint($1, $2), 4326),
                        location_zone = $3,
                        updated_at = NOW()
                    WHERE id = $4
                    """,
                    body.longitude,
                    body.latitude,
                    zone["id"],
                    uuid.UUID(str(user_id)),
                )
        except Exception:
            pass

        try:
            await redis.delete(f"feed:cache:{user_id}")
        except Exception:
            pass

        return ok({
            "allowed": True,
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "state": zone["state"],
            "distance_to_center_km": zone["distance_to_center_km"],
            "message": f"Welcome to Jainune! Active in {zone['name']}.",
        })

    # Out of coverage: register on waitlist
    try:
        phone = body.phone_number or current_user.get("phone_number")
        await save_city_waitlist(
            phone_number=phone,
            lat=body.latitude,
            lon=body.longitude,
            city_hint=body.city_hint,
            pool=pool,
        )
    except Exception:
        pass  # Graceful fallback if waitlist logging fails

    return ok({
        "allowed": False,
        "zone_id": None,
        "zone_name": None,
        "state": None,
        "distance_to_center_km": None,
        "message": "Jainune is currently live in Mumbai MMR, Pune, and Bengaluru. We'll be in your city soon! 🚀",
        "waitlist_registered": True,
    })


@router.get("/zones", summary="List currently active operational zones")
async def get_active_zones() -> dict:
    """Returns list of active launch zones with bounding descriptions."""
    return ok({"zones": LAUNCH_ZONES})
