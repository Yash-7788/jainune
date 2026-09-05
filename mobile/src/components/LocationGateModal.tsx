import React from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  SafeAreaView,
  StatusBar,
} from "react-native";
import { openDeviceLocationSettings, LocationGateState } from "../security/locationPermissionGuard";

interface Props {
  gateState: LocationGateState;
  onRetry?: () => void;
}

export const LocationGateModal: React.FC<Props> = ({ gateState, onRetry }) => {
  if (gateState.status === "ALLOWED" || gateState.status === "CHECKING") {
    return null;
  }

  // Gate 1: Permission Denied
  if (gateState.status === "GATE1_PERMISSION_DENIED") {
    return (
      <Modal visible={true} transparent={false} animationType="fade">
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="light-content" backgroundColor="#0D0F14" />
          <View style={styles.contentCard}>
            <View style={styles.iconCircle}>
              <Text style={styles.iconText}>📍</Text>
            </View>
            <Text style={styles.title}>Location Permission Required</Text>
            <Text style={styles.subtitle}>
              Jainune needs your device location to verify you are within our active operational launch zones and match you with nearby Jain singles.
            </Text>
            <Text style={styles.warningText}>
              Access cannot be granted without location permission.
            </Text>

            <TouchableOpacity
              style={styles.primaryButton}
              activeOpacity={0.8}
              onPress={openDeviceLocationSettings}
            >
              <Text style={styles.primaryButtonText}>Open Device Settings</Text>
            </TouchableOpacity>

            {onRetry && (
              <TouchableOpacity
                style={styles.secondaryButton}
                activeOpacity={0.7}
                onPress={onRetry}
              >
                <Text style={styles.secondaryButtonText}>I Have Granted Permission</Text>
              </TouchableOpacity>
            )}
          </View>
        </SafeAreaView>
      </Modal>
    );
  }

  // Security Gate: Spoofing / Mock Location Detected
  if (gateState.status === "SPOOFING_DETECTED") {
    return (
      <Modal visible={true} transparent={false} animationType="fade">
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="light-content" backgroundColor="#0D0F14" />
          <View style={styles.contentCard}>
            <View style={[styles.iconCircle, styles.alertCircle]}>
              <Text style={styles.iconText}>⚠️</Text>
            </View>
            <Text style={styles.title}>Location Manipulation Detected</Text>
            <Text style={styles.subtitle}>
              {gateState.reason}
            </Text>
            <Text style={styles.warningText}>
              Simulated GPS coordinates, mock location apps, and developer location spoofing are strictly prohibited to ensure the safety and authenticity of our community.
            </Text>

            {onRetry && (
              <TouchableOpacity
                style={styles.primaryButton}
                activeOpacity={0.8}
                onPress={onRetry}
              >
                <Text style={styles.primaryButtonText}>Retry With Real GPS</Text>
              </TouchableOpacity>
            )}
          </View>
        </SafeAreaView>
      </Modal>
    );
  }

  // Gate 2: Location Outside Launch Zones -> Waitlist Screen
  if (gateState.status === "GATE2_OUTSIDE_ZONES") {
    return (
      <Modal visible={true} transparent={false} animationType="slide">
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="light-content" backgroundColor="#0D0F14" />
          <View style={styles.contentCard}>
            <View style={styles.iconCircle}>
              <Text style={styles.iconText}>🚀</Text>
            </View>
            <Text style={styles.title}>We'll Be In Your City Soon!</Text>
            <Text style={styles.subtitle}>
              Jainune is currently live in Mumbai MMR (100km), Pune & PCMC (100km), and Bengaluru (100km).
            </Text>
            <View style={styles.badgeContainer}>
              <Text style={styles.badgeText}>✓ You're On The Priority Waitlist</Text>
            </View>
            <Text style={styles.infoText}>
              We track location demand to determine which cities launch next. We'll notify you via SMS as soon as Jainune goes live in your area!
            </Text>
          </View>
        </SafeAreaView>
      </Modal>
    );
  }

  return null;
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0D0F14",
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 24,
  },
  contentCard: {
    width: "100%",
    maxWidth: 400,
    alignItems: "center",
    padding: 24,
    borderRadius: 20,
    backgroundColor: "#161922",
    borderWidth: 1,
    borderColor: "#252B3B",
  },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: "rgba(217, 119, 6, 0.15)",
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 20,
  },
  alertCircle: {
    backgroundColor: "rgba(239, 68, 68, 0.15)",
  },
  iconText: {
    fontSize: 32,
  },
  title: {
    fontSize: 22,
    fontWeight: "700",
    color: "#FFFFFF",
    textAlign: "center",
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 15,
    lineHeight: 22,
    color: "#9CA3AF",
    textAlign: "center",
    marginBottom: 16,
  },
  warningText: {
    fontSize: 13,
    lineHeight: 18,
    color: "#F59E0B",
    textAlign: "center",
    marginBottom: 24,
  },
  infoText: {
    fontSize: 13,
    lineHeight: 19,
    color: "#6B7280",
    textAlign: "center",
    marginTop: 16,
  },
  badgeContainer: {
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "rgba(16, 185, 129, 0.3)",
    marginBottom: 8,
  },
  badgeText: {
    color: "#10B981",
    fontSize: 14,
    fontWeight: "600",
  },
  primaryButton: {
    width: "100%",
    backgroundColor: "#D97706",
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: "center",
    marginBottom: 12,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "600",
  },
  secondaryButton: {
    width: "100%",
    paddingVertical: 12,
    alignItems: "center",
  },
  secondaryButtonText: {
    color: "#9CA3AF",
    fontSize: 14,
    fontWeight: "500",
  },
});
