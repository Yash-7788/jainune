"""
Location verification service — geofencing for initial operational launch zones:
  1. Mumbai Metropolitan Region (MMR) — 75 km radius
  2. Pune & Pimpri-Chinchwad (PCMC)   — 50 km radius
  3. Bengaluru Metropolitan Area       — 60 km radius
"""

from __future__ import annotations

import math
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

# Active launch zones
LAUNCH_ZONES: list[dict[str, Any]] = [
    {
        "id": "mumbai_mmr",
        "name": "Mumbai Metropolitan Region",
        "state": "Maharashtra",
        "center_lat": 19.0760,
        "center_lon": 72.8777,
        "radius_km": 75.0,
        "description": "Mumbai City, Suburbs, Thane, Navi Mumbai, Mira-Bhayandar, Kalyan-Dombivli, Vasai-Virar, Panvel",
    },
    {
        "id": "pune_pcmc",
        "name": "Pune & Pimpri-Chinchwad",
        "state": "Maharashtra",
        "center_lat": 18.5204,
        "center_lon": 73.8567,
        "radius_km": 50.0,
        "description": "Pune City, Pimpri, Chinchwad, Hinjewadi, Kothrud, Camp, Haveli",
    },
    {
        "id": "bengaluru",
        "name": "Bengaluru Metropolitan Area",
        "state": "Karnataka",
        "center_lat": 12.9716,
        "center_lon": 77.5946,
        "radius_km": 60.0,
        "description": "All Bengaluru Urban & Rural, Central, VV Puram, Jayanagar, Malleshwaram, Whitefield, Electronic City, Yelahanka",
    },
]


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in kilometers."""
    r = 6371.0  # Earth radius in km

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def verify_location_zone(lat: float, lon: float) -> tuple[bool, dict[str, Any] | None]:
    """
    Checks if given coordinates fall within any active operational zone.
    Returns (True, matched_zone_dict) or (False, None).
    """
    for zone in LAUNCH_ZONES:
        dist = haversine_distance_km(lat, lon, zone["center_lat"], zone["center_lon"])
        if dist <= zone["radius_km"]:
            result = dict(zone)
            result["distance_to_center_km"] = round(dist, 2)
            return True, result
    return False, None


async def save_city_waitlist(
    phone_number: Optional[str],
    lat: float,
    lon: float,
    city_hint: Optional[str],
    pool: asyncpg.Pool,
) -> None:
    """Records out-of-coverage user coordinates to city waitlist for launch demand tracking."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO location_waitlist (phone_number, latitude, longitude, city_hint)
            VALUES ($1, $2, $3, $4)
            """,
            phone_number,
            lat,
            lon,
            city_hint,
        )
