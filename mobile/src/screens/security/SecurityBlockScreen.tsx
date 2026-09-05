/**
 * Phase 8 — SecurityBlockScreen
 * Shown when runSecurityBoot() returns { passed: false }.
 * Blocks all app navigation. Shows clear, non-technical message.
 * No dismiss button. User must close the app.
 * FLAG_SECURE prevents screenshotting this screen itself.
 */

import React, { useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
} from "react-native";
import { enableScreenCaptureProtection } from "../../security/antiReversing";

interface Props {
  reason: string;
}

export default function SecurityBlockScreen({ reason }: Props) {
  useEffect(() => {
    enableScreenCaptureProtection();
  }, []);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0D0D0D" />

      <View style={styles.iconWrap}>
        <Text style={styles.icon}>⚠</Text>
      </View>

      <Text style={styles.title}>Security Check Failed</Text>
      <Text style={styles.message}>{reason}</Text>

      <Text style={styles.footer}>
        Install Jainune only from the official Google Play Store or Apple App Store.
        If you believe this is a mistake, contact support@jainune.com
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0D0D0D",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
  },
  iconWrap: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: "rgba(232,64,64,0.15)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 32,
  },
  icon: { fontSize: 36 },
  title: {
    fontFamily: "Outfit_700Bold",
    fontSize: 22,
    color: "#FFFFFF",
    textAlign: "center",
    marginBottom: 16,
  },
  message: {
    fontFamily: "Inter_400Regular",
    fontSize: 15,
    color: "rgba(255,255,255,0.65)",
    textAlign: "center",
    lineHeight: 24,
    marginBottom: 48,
  },
  footer: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "rgba(255,255,255,0.3)",
    textAlign: "center",
    lineHeight: 18,
    position: "absolute",
    bottom: 48,
    left: 32,
    right: 32,
  },
});
