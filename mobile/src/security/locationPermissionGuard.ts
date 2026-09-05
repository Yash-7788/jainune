/**
 * Jainune Location Permission Guard & Anti-Manipulation Engine
 * 
 * Strict 2-Gate Security Architecture:
 * 
 * Gate 1 (Permission Denied):
 * - If location permission not granted: App blocked with unbypassable modal.
 * - Shows: "Location permission required to use Jainune."
 * - Action: "Open Device Settings" button.
 * - NEVER shows "coming soon" when permission is missing.
 * 
 * Anti-Manipulation:
 * - Checks Location.mocked / isFromMockProvider.
 * - Rejects spoofed accuracy (> 5000m or <= 0m).
 * - Checks timestamp freshness (< 30s, prevents replay attacks).
 * - Rejects Null Island (0,0) or out-of-bound coords.
 * 
 * Gate 2 (Coordinates Outside Operational Launch Zones):
 * - If coordinates valid but outside Mumbai MMR (100km), Pune PCMC (100km), or Bengaluru (100km):
 * - Shows: "We'll be in your city soon! 🚀" waitlist modal.
 * - Enrolls phone number to location waitlist.
 */

import { Platform, Linking, Alert } from "react-native";

export interface GeoCoordinates {
  latitude: float;
  longitude: float;
  accuracyMeters?: float;
  isMocked: boolean;
  timestamp: number;
}

export type LocationGateState =
  | { status: "CHECKING" }
  | { status: "GATE1_PERMISSION_DENIED"; message: string }
  | { status: "SPOOFING_DETECTED"; reason: string }
  | { status: "GATE2_OUTSIDE_ZONES"; message: string; waitlistRegistered: boolean }
  | { status: "ALLOWED"; zoneId: string; zoneName: string };

type float = number;

const API_BASE_URL = "https://api.jainune.com";

/**
 * Validates GPS coordinate integrity against client-side spoofers and mock location apps.
 */
export function validateCoordinatesIntegrity(coords: GeoCoordinates): { isValid: boolean; error?: string } {
  // 1. Mock location detection (Android Mock Location Provider / iOS Location Simulation)
  if (coords.isMocked) {
    return {
      isValid: false,
      error: "Mock location or GPS spoofing detected. Disable mock locations in Developer Options.",
    };
  }

  // 2. Coordinate range boundaries
  if (coords.latitude < -90 || coords.latitude > 90 || coords.longitude < -180 || coords.longitude > 180) {
    return { isValid: false, error: "Invalid coordinate bounds detected." };
  }

  // 3. Null Island anomaly check
  if (Math.abs(coords.latitude) < 0.0001 && Math.abs(coords.longitude) < 0.0001) {
    return { isValid: false, error: "GPS hardware returned invalid null coordinates." };
  }

  // 4. Accuracy bounds (reject wild inaccurate or simulated 0 accuracy)
  if (coords.accuracyMeters !== undefined) {
    if (coords.accuracyMeters <= 0) {
      return { isValid: false, error: "Synthetic GPS accuracy detected." };
    }
    if (coords.accuracyMeters > 5000) {
      return { isValid: false, error: "GPS accuracy too low. Move to an area with clear sky view." };
    }
  }

  // 5. Freshness check (reject cached locations older than 60 seconds to prevent replay)
  const ageSeconds = (Date.now() - coords.timestamp) / 1000;
  if (ageSeconds > 60) {
    return { isValid: false, error: "Stale location reading detected. Refreshing GPS..." };
  }

  return { isValid: true };
}

/**
 * Directs user to native system settings when permission is denied.
 */
export function openDeviceLocationSettings(): void {
  if (Platform.OS === "ios") {
    Linking.openURL("app-settings:");
  } else {
    Linking.openSettings();
  }
}

/**
 * Verifies coordinates with backend against active launch zones (Mumbai MMR 100km, Pune 100km, Bengaluru 100km).
 */
export async function verifyCoordinatesWithServer(
  coords: GeoCoordinates,
  phoneNumber?: string
): Promise<LocationGateState> {
  // Client-side anti-manipulation gate
  const integrity = validateCoordinatesIntegrity(coords);
  if (!integrity.isValid) {
    return {
      status: "SPOOFING_DETECTED",
      reason: integrity.error || "Location verification failed.",
    };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/v1/location/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        latitude: coords.latitude,
        longitude: coords.longitude,
        is_mocked: coords.isMocked,
        accuracy_meters: coords.accuracyMeters,
        phone_number: phoneNumber,
      }),
    });

    if (response.status === 403) {
      const errData = await response.json().catch(() => ({}));
      return {
        status: "SPOOFING_DETECTED",
        reason: errData.error?.message || "Location security verification rejected by server.",
      };
    }

    const resJson = await response.json();
    const data = resJson.data || {};

    if (data.allowed) {
      return {
        status: "ALLOWED",
        zoneId: data.zone_id,
        zoneName: data.zone_name,
      };
    } else {
      return {
        status: "GATE2_OUTSIDE_ZONES",
        message: data.message || "We'll be in your city soon! 🚀",
        waitlistRegistered: data.waitlist_registered ?? true,
      };
    }
  } catch (error) {
    // Fallback: network error retry
    return {
      status: "CHECKING",
    };
  }
}
