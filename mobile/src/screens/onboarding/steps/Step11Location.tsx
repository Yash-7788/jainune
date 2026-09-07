/**
 * Step 11 — GPS location capture
 * Anti-spoofing: validates is_mocked=false, accuracy ≤ 5000m, not Null Island (0,0)
 * Opens device settings if permission denied — never shows "coming soon" screen.
 * Then calls /v1/location/verify to check 100km geofence. Waitlist if outside.
 */
import React, { useState, useEffect, useCallback } from "react";
import { View, Text, StyleSheet, Alert, AppState, AppStateStatus } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as Location from "expo-location";
import * as Linking from "expo-linking";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep11 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import {
  verifyCoordinatesWithServer,
  openDeviceLocationSettings,
} from "../../../security/locationPermissionGuard";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step11">;

export default function Step11Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [permStatus, setPermStatus] = useState<"idle" | "denied" | "granted">("idle");
  const [locStatus, setLocStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [insideZone, setInsideZone] = useState<boolean | null>(null);
  const [coords, setCoords] = useState<{
    latitude: number;
    longitude: number;
    isMocked: boolean;
    accuracyMeters: number | null;
  } | null>(null);

  const checkPermissionAndLocation = useCallback(async () => {
    try {
      const { status } = await Location.getForegroundPermissionsAsync();
      if (status === "granted") {
        setPermStatus("granted");
        fetchPosition();
      } else if (status === "denied") {
        setPermStatus("denied");
      }
    } catch {
      // Non-fatal
    }
  }, []);

  useEffect(() => {
    checkPermissionAndLocation();

    // Re-check permissions when returning from device settings
    const sub = AppState.addEventListener("change", (nextState: AppStateStatus) => {
      if (nextState === "active") {
        checkPermissionAndLocation();
      }
    });

    return () => sub.remove();
  }, [checkPermissionAndLocation]);

  const requestLocation = async () => {
    setLocStatus("loading");
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== "granted") {
      setPermStatus("denied");
      setLocStatus("idle");
      return;
    }
    setPermStatus("granted");
    await fetchPosition();
  };

  const fetchPosition = async () => {
    setLocStatus("loading");
    try {
      const loc = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      const lat = loc.coords.latitude;
      const lon = loc.coords.longitude;
      const accuracy = loc.coords.accuracy;
      const isMocked = (loc as unknown as { mocked?: boolean }).mocked === true;

      // Client-side anti-spoofing
      if (isMocked) {
        setError({ title: "Location Issue", message: "Mock location detected. Please disable mock location." });
        setLocStatus("error");
        return;
      }
      if (lat === 0 && lon === 0) {
        setError({ title: "Location Issue", message: "GPS fix unavailable. Please move outdoors and retry." });
        setLocStatus("error");
        return;
      }
      if (accuracy !== null && accuracy > 5000) {
        setError({ title: "Low Accuracy", message: "GPS accuracy too low. Please enable high-accuracy location." });
        setLocStatus("error");
        return;
      }

      setCoords({ latitude: lat, longitude: lon, isMocked, accuracyMeters: accuracy });
      setLocStatus("done");

      // Verify geofence with anti-manipulation checks
      const gateResult = await verifyCoordinatesWithServer({
        latitude: lat,
        longitude: lon,
        accuracyMeters: accuracy ?? undefined,
        isMocked,
        timestamp: loc.timestamp || Date.now(),
      });

      if (gateResult.status === "ALLOWED") {
        setInsideZone(true);
      } else if (gateResult.status === "GATE2_OUTSIDE_ZONES") {
        setInsideZone(false);
      } else if (gateResult.status === "SPOOFING_DETECTED") {
        setError({ title: "Location Security Warning", message: gateResult.reason });
        setLocStatus("error");
      }
    } catch (err) {
      setError(extractError(err));
      setLocStatus("error");
    }
  };

  const handleNext = async () => {
    if (!coords) return;
    setLoading(true);
    try {
      await submitStep11(coords.latitude, coords.longitude, coords.isMocked, coords.accuracyMeters);
      updateData({
        latitude: coords.latitude,
        longitude: coords.longitude,
        isMocked: coords.isMocked,
        accuracyMeters: coords.accuracyMeters,
      });
      setStep(12);
      navigation.navigate("Step12");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  const openSettings = () => {
    openDeviceLocationSettings();
  };

  return (
    <OnboardingStep
      title="Share your location"
      subtitle="Used to find verified Jain singles nearby. Exact coordinates are never shown to anyone."
      onNext={
        permStatus === "denied"
          ? openSettings
          : locStatus === "done"
          ? handleNext
          : requestLocation
      }
      nextLabel={
        locStatus === "done"
          ? "Continue"
          : permStatus === "denied"
          ? "Open Device Settings"
          : "Enable Location Access"
      }
      loading={loading || locStatus === "loading"}
      disabled={locStatus === "loading"}
      error={error}
    >
      <View style={styles.statusCard}>
        {permStatus === "idle" && locStatus === "idle" && (
          <View>
            <Text style={styles.disclosureHeading}>Prominent Location Disclosure</Text>
            <Text style={styles.disclosureText}>
              Jainune accesses your device location to:{"\n"}
              • Connect you with nearby verified Jain singles{"\n"}
              • Calculate distance in kilometers on match cards{"\n"}
              • Verify supported matchmaking regions
            </Text>
            <Text style={styles.disclosureSubtext}>
              Your exact GPS coordinates are NEVER shared with other members. Location is only accessed while the app is active in the foreground.
            </Text>
          </View>
        )}
        {locStatus === "loading" && (
          <Text style={styles.statusText}>Getting your location...</Text>
        )}
        {locStatus === "done" && insideZone === true && (
          <Text style={[styles.statusText, { color: colors.green }]}>
            Location verified! You're in a supported city.
          </Text>
        )}
        {locStatus === "done" && insideZone === false && (
          <Text style={[styles.statusText, { color: colors.saffron }]}>
            We'll be in your city soon! You'll be added to our waitlist.
          </Text>
        )}
        {permStatus === "denied" && (
          <Text style={styles.statusText}>
            Location permission is required to use Jainune.{"\n"}Please open settings and grant location access.
          </Text>
        )}
      </View>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  statusCard: {
    backgroundColor: colors.light,
    borderRadius: 12,
    padding: spacing.base,
    marginBottom: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  disclosureHeading: {
    fontFamily: "Outfit_700Bold",
    fontSize: 15,
    color: colors.dark,
    marginBottom: spacing.xs,
  },
  disclosureText: {
    ...typography.bodySmall,
    color: colors.dark,
    lineHeight: 20,
    marginBottom: spacing.sm,
  },
  disclosureSubtext: {
    ...typography.caption,
    color: colors.mid,
    lineHeight: 16,
  },
  statusText: { ...typography.body, color: colors.mid, lineHeight: 22 },
});
