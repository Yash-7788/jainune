"""
Unit tests for Location Verifier — Operational Geofence for Launch Zones:
Mumbai MMR (100km), Pune & PCMC (100km), Bengaluru (100km).
Verifies Koregaon Park and Lavale coverage, anti-spoofing gates, and Delhi exclusion.
"""

from __future__ import annotations

import unittest
from app.services.location_verifier import (
    LAUNCH_ZONES,
    haversine_distance_km,
    verify_location_anti_spoofing,
    verify_location_zone,
)


class TestLocationVerifier(unittest.TestCase):
    def test_launch_zones_list_excludes_delhi_and_has_100km_radius(self):
        """Verify launch zones strictly contain Mumbai, Pune, and Bengaluru with 100km radius."""
        zone_ids = [z["id"] for z in LAUNCH_ZONES]
        self.assertIn("mumbai_mmr", zone_ids)
        self.assertIn("pune_pcmc", zone_ids)
        self.assertIn("bengaluru", zone_ids)
        self.assertNotIn("delhi_ncr", zone_ids)
        self.assertEqual(len(LAUNCH_ZONES), 3)

        for zone in LAUNCH_ZONES:
            self.assertEqual(zone["radius_km"], 100.0)

    def test_mumbai_mmr_coordinates_allowed(self):
        """Test various locations inside Mumbai Metropolitan Region."""
        # Nariman Point / South Mumbai
        allowed, zone = verify_location_zone(18.9260, 72.8230)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "mumbai_mmr")

        # Borivali / Suburbs
        allowed, zone = verify_location_zone(19.2307, 72.8567)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "mumbai_mmr")

        # Thane West
        allowed, zone = verify_location_zone(19.2183, 72.9781)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "mumbai_mmr")

        # Navi Mumbai (Vashi)
        allowed, zone = verify_location_zone(19.0771, 72.9986)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "mumbai_mmr")

        # Palghar (within 100km)
        allowed, zone = verify_location_zone(19.6967, 72.7655)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "mumbai_mmr")

    def test_pune_pcmc_coordinates_allowed_including_koregaon_park_and_lavale(self):
        """Test locations inside Pune & PCMC including Koregaon Park and Lavale."""
        # Pune Central / FC Road
        allowed, zone = verify_location_zone(18.5246, 73.8415)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "pune_pcmc")

        # Koregaon Park
        allowed, zone = verify_location_zone(18.5362, 73.8940)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "pune_pcmc")

        # Lavale (near Symbiosis / Mulshi road)
        allowed, zone = verify_location_zone(18.5362, 73.7297)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "pune_pcmc")

        # Hinjewadi IT Park
        allowed, zone = verify_location_zone(18.5913, 73.7389)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "pune_pcmc")

        # Pimpri-Chinchwad
        allowed, zone = verify_location_zone(18.6279, 73.8009)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "pune_pcmc")

        # Lonavala (within 100km of Pune center)
        allowed, zone = verify_location_zone(18.7557, 73.4091)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "pune_pcmc")

    def test_bengaluru_coordinates_allowed(self):
        """Test locations inside Bengaluru."""
        # VV Puram / Central
        allowed, zone = verify_location_zone(12.9520, 77.5770)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "bengaluru")

        # Whitefield
        allowed, zone = verify_location_zone(12.9698, 77.7500)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "bengaluru")

        # Electronic City
        allowed, zone = verify_location_zone(12.8452, 77.6602)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "bengaluru")

        # Ramanagara (within 100km)
        allowed, zone = verify_location_zone(12.7159, 77.2810)
        self.assertTrue(allowed)
        self.assertEqual(zone["id"], "bengaluru")

    def test_anti_spoofing_validation(self):
        """Test client-side mock location and coordinate manipulation detection."""
        # Genuine coordinates
        valid, err = verify_location_anti_spoofing(18.5204, 73.8567, is_mocked=False, accuracy_meters=15.0)
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Mock location detected
        valid, err = verify_location_anti_spoofing(18.5204, 73.8567, is_mocked=True)
        self.assertFalse(valid)
        self.assertIn("Mock location detected", err)

        # Null Island anomaly
        valid, err = verify_location_anti_spoofing(0.0, 0.0)
        self.assertFalse(valid)

        # Out-of-bounds latitude
        valid, err = verify_location_anti_spoofing(95.0, 73.8567)
        self.assertFalse(valid)

        # Inaccurate accuracy (> 5000m)
        valid, err = verify_location_anti_spoofing(18.5204, 73.8567, accuracy_meters=8000.0)
        self.assertFalse(valid)

        # Invalid accuracy (<= 0m)
        valid, err = verify_location_anti_spoofing(18.5204, 73.8567, accuracy_meters=-5.0)
        self.assertFalse(valid)

    def test_delhi_coordinates_strictly_excluded(self):
        """Delhi coordinates must return False (waitlist gate)."""
        # Connaught Place
        allowed, zone = verify_location_zone(28.6315, 77.2167)
        self.assertFalse(allowed)
        self.assertIsNone(zone)

        # Chandni Chowk
        allowed, zone = verify_location_zone(28.6506, 77.2303)
        self.assertFalse(allowed)
        self.assertIsNone(zone)

        # South Extension
        allowed, zone = verify_location_zone(28.5684, 77.2209)
        self.assertFalse(allowed)
        self.assertIsNone(zone)

    def test_other_cities_excluded(self):
        """Other unlaunched cities must return False."""
        # Chennai
        allowed, _ = verify_location_zone(13.0827, 80.2707)
        self.assertFalse(allowed)

        # Ahmedabad
        allowed, _ = verify_location_zone(23.0225, 72.5714)
        self.assertFalse(allowed)

        # Jaipur
        allowed, _ = verify_location_zone(26.9124, 75.7873)
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
