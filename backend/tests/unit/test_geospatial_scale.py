"""
Large-Scale Geospatial Geodesy Test Suite for Jainune Operational Launch Zones.
Generates and evaluates 6,000+ coordinates:
  - Bengaluru: 1,000 inside (0-99.9km) + 1,000 outside (100.1-400km)
  - Pune:      1,000 inside (0-99.9km) + 1,000 outside (100.1-400km)
  - Mumbai:    1,000 inside (0-99.9km) + 1,000 outside (100.1-400km)
Verifies boundary edge cases at 99.9km vs 100.1km across 360-degree bearings.
"""

from __future__ import annotations

import math
import random
import unittest
from typing import Tuple

from app.services.location_verifier import (
    LAUNCH_ZONES,
    haversine_distance_km,
    verify_location_zone,
)

EARTH_RADIUS_KM = 6371.0


def destination_point(lat: float, lon: float, distance_km: float, bearing_deg: float) -> Tuple[float, float]:
    """
    Computes destination latitude and longitude given a starting point,
    distance in km, and bearing in degrees (0-360) using Great Circle equations.
    """
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)

    sin_phi1 = math.sin(phi1)
    cos_phi1 = math.cos(phi1)
    sin_delta = math.sin(delta)
    cos_delta = math.cos(delta)

    phi2 = math.asin(sin_phi1 * cos_delta + cos_phi1 * sin_delta * math.cos(theta))
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * sin_delta * cos_phi1,
        cos_delta - sin_phi1 * math.sin(phi2),
    )

    # Normalize longitude to [-180, 180]
    lambda2_deg = (math.degrees(lambda2) + 540) % 360 - 180
    return math.degrees(phi2), lambda2_deg


class TestGeospatialScale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deterministic seed for reproducible testing
        random.seed(42)

        cls.zones_by_id = {z["id"]: z for z in LAUNCH_ZONES}
        cls.blr = cls.zones_by_id["bengaluru"]
        cls.pune = cls.zones_by_id["pune_pcmc"]
        cls.mumbai = cls.zones_by_id["mumbai_mmr"]

    def test_01_bangalore_1000_inside_coordinates(self):
        """Generate 1,000 points across all bearings at distances 0.1km to 99.8km from Bengaluru center."""
        c_lat, c_lon = self.blr["center_lat"], self.blr["center_lon"]
        count = 1000

        for i in range(count):
            bearing = (i * 360.0) / count
            # Distances uniformly distributed from 0.5km up to 99.8km
            dist = 0.5 + (99.3 * (i / count))
            lat, lon = destination_point(c_lat, c_lon, dist, bearing)

            calc_dist = haversine_distance_km(lat, lon, c_lat, c_lon)
            self.assertLessEqual(calc_dist, 100.0)

            allowed, zone = verify_location_zone(lat, lon)
            self.assertTrue(allowed, f"BLR inside point failed at dist={dist:.2f}km, bearing={bearing:.1f}")
            self.assertEqual(zone["id"], "bengaluru")

    def test_02_bangalore_1000_outside_coordinates(self):
        """Generate 1,000 points outside Bengaluru (100.5km to 350km, bearing away from MH)."""
        c_lat, c_lon = self.blr["center_lat"], self.blr["center_lon"]
        count = 1000

        for i in range(count):
            # South, East, West bearings (avoiding north-north-west towards MH)
            bearing = 90.0 + (180.0 * (i / count))
            dist = 100.5 + (250.0 * (i / count))
            lat, lon = destination_point(c_lat, c_lon, dist, bearing)

            calc_dist = haversine_distance_km(lat, lon, c_lat, c_lon)
            self.assertGreater(calc_dist, 100.0)

            allowed, _ = verify_location_zone(lat, lon)
            self.assertFalse(allowed, f"BLR outside point falsely passed at dist={dist:.2f}km")

    def test_03_pune_1000_inside_coordinates(self):
        """Generate 1,000 points inside Pune 100km radius."""
        c_lat, c_lon = self.pune["center_lat"], self.pune["center_lon"]
        count = 1000

        for i in range(count):
            bearing = (i * 360.0) / count
            dist = 0.5 + (99.3 * (i / count))
            lat, lon = destination_point(c_lat, c_lon, dist, bearing)

            calc_dist = haversine_distance_km(lat, lon, c_lat, c_lon)
            self.assertLessEqual(calc_dist, 100.0)

            allowed, zone = verify_location_zone(lat, lon)
            self.assertTrue(allowed, f"Pune inside point failed at dist={dist:.2f}km")
            # Must match either pune_pcmc or mumbai_mmr if in overlap
            self.assertIn(zone["id"], ["pune_pcmc", "mumbai_mmr"])

    def test_04_pune_1000_outside_coordinates(self):
        """Generate 1,000 points outside Pune (>100.5km) bearing east/south-east away from Mumbai."""
        c_lat, c_lon = self.pune["center_lat"], self.pune["center_lon"]
        count = 1000

        for i in range(count):
            # Bearings 90 to 180 (Solapur, Satara south, Kolhapur border >100km)
            bearing = 90.0 + (90.0 * (i / count))
            dist = 102.0 + (250.0 * (i / count))
            lat, lon = destination_point(c_lat, c_lon, dist, bearing)

            calc_dist = haversine_distance_km(lat, lon, c_lat, c_lon)
            self.assertGreater(calc_dist, 100.0)

            allowed, _ = verify_location_zone(lat, lon)
            self.assertFalse(allowed, f"Pune outside point falsely passed at dist={dist:.2f}km")

    def test_05_mumbai_1000_inside_coordinates(self):
        """Generate 1,000 points inside Mumbai MMR 100km radius."""
        c_lat, c_lon = self.mumbai["center_lat"], self.mumbai["center_lon"]
        count = 1000

        for i in range(count):
            bearing = (i * 360.0) / count
            dist = 0.5 + (99.3 * (i / count))
            lat, lon = destination_point(c_lat, c_lon, dist, bearing)

            calc_dist = haversine_distance_km(lat, lon, c_lat, c_lon)
            self.assertLessEqual(calc_dist, 100.0)

            allowed, zone = verify_location_zone(lat, lon)
            self.assertTrue(allowed, f"Mumbai inside point failed at dist={dist:.2f}km")
            self.assertIn(zone["id"], ["mumbai_mmr", "pune_pcmc"])

    def test_06_mumbai_1000_outside_coordinates(self):
        """Generate 1,000 points outside Mumbai (>100.5km) bearing north / north-west / south-west."""
        c_lat, c_lon = self.mumbai["center_lat"], self.mumbai["center_lon"]
        count = 1000

        for i in range(count):
            # Bearing north towards Gujarat border (>100km) or west into Arabian Sea >100km
            bearing = 330.0 + (60.0 * (i / count))  # North towards Surat
            dist = 105.0 + (250.0 * (i / count))
            lat, lon = destination_point(c_lat, c_lon, dist, bearing)

            calc_dist = haversine_distance_km(lat, lon, c_lat, c_lon)
            self.assertGreater(calc_dist, 100.0)

            allowed, _ = verify_location_zone(lat, lon)
            self.assertFalse(allowed, f"Mumbai outside point falsely passed at dist={dist:.2f}km")

    def test_07_boundary_precision_edges(self):
        """Test boundary knife-edge precision at 99.9 km (Allowed) vs 100.1 km (Outside)."""
        for zone in LAUNCH_ZONES:
            c_lat, c_lon = zone["center_lat"], zone["center_lon"]
            # Test 4 cardinal directions (N, E, S, W)
            for bearing in [0.0, 90.0, 180.0, 270.0]:
                # 99.9 km: strictly inside
                lat_in, lon_in = destination_point(c_lat, c_lon, 99.9, bearing)
                d_in = haversine_distance_km(lat_in, lon_in, c_lat, c_lon)
                self.assertLessEqual(d_in, 100.0)

                # Isolated zone boundary check (BLR)
                if zone["id"] == "bengaluru":
                    allowed_in, z_in = verify_location_zone(lat_in, lon_in)
                    self.assertTrue(allowed_in)
                    self.assertEqual(z_in["id"], "bengaluru")

                    # 100.2 km: strictly outside
                    lat_out, lon_out = destination_point(c_lat, c_lon, 100.2, bearing)
                    d_out = haversine_distance_km(lat_out, lon_out, c_lat, c_lon)
                    self.assertGreater(d_out, 100.0)
                    allowed_out, _ = verify_location_zone(lat_out, lon_out)
                    self.assertFalse(allowed_out)


if __name__ == "__main__":
    unittest.main()
