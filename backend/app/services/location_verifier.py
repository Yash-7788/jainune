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

# Active launch zones — 100km radius for Mumbai, Pune, and Bengaluru
LAUNCH_ZONES: list[dict[str, Any]] = [
    {
        "id": "mumbai_mmr",
        "name": "Mumbai Metropolitan Region",
        "state": "Maharashtra",
        "center_lat": 19.0760,
        "center_lon": 72.8777,
        "radius_km": 100.0,
        "description": "Mumbai City, Suburbs, Thane, Navi Mumbai, Mira-Bhayandar, Kalyan-Dombivli, Vasai-Virar, Panvel, Palghar, Alibaug",
    },
    {
        "id": "pune_pcmc",
        "name": "Pune & Pimpri-Chinchwad",
        "state": "Maharashtra",
        "center_lat": 18.5204,
        "center_lon": 73.8567,
        "radius_km": 100.0,
        "description": "Pune City, Pimpri, Chinchwad, Koregaon Park, Lavale, Hinjewadi, Kothrud, Camp, Hadapsar, Haveli, Talegaon, Lonavala",
    },
    {
        "id": "bengaluru",
        "name": "Bengaluru Metropolitan Area",
        "state": "Karnataka",
        "center_lat": 12.9716,
        "center_lon": 77.5946,
        "radius_km": 100.0,
        "description": "All Bengaluru Urban & Rural, Central, VV Puram, Jayanagar, Malleshwaram, Whitefield, Electronic City, Yelahanka, Hosur border, Ramanagara",
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


def verify_location_anti_spoofing(
    lat: float,
    lon: float,
    is_mocked: bool = False,
    accuracy_meters: Optional[float] = None,
) -> tuple[bool, str | None]:
    """
    Validates GPS authenticity against client-side spoofing and coordinate anomalies:
    - Rejects mocked/simulated locations (from mock providers / developer apps).
    - Rejects impossible coordinate bounds.
    - Rejects null island coordinates (0.0, 0.0).
    - Rejects spoofed or wildly inaccurate accuracy readings (> 5000m or <= 0m).
    """
    if is_mocked:
        return False, "Mock location detected. Please disable mock location apps or developer options."

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return False, "Invalid coordinate ranges."

    if abs(lat) < 0.0001 and abs(lon) < 0.0001:
        return False, "Invalid location coordinates detected."

    if accuracy_meters is not None:
        if accuracy_meters <= 0.0:
            return False, "Invalid location accuracy reading."
        if accuracy_meters > 5000.0:
            return False, "Location accuracy is too low to verify launch zone."

    return True, None


def verify_location_zone(lat: float, lon: float) -> tuple[bool, dict[str, Any] | None]:
    """
    Checks if given coordinates fall within any active operational zone.
    Returns (True, closest_matched_zone) or (False, None).
    """
    best_zone = None
    min_dist = float("inf")
    for zone in LAUNCH_ZONES:
        dist = haversine_distance_km(lat, lon, zone["center_lat"], zone["center_lon"])
        if dist <= zone["radius_km"] and dist < min_dist:
            min_dist = dist
            best_zone = dict(zone)
            best_zone["distance_to_center_km"] = round(dist, 2)

    if best_zone:
        return True, best_zone
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
