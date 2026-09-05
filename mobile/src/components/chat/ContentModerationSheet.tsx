/**
 * ContentModerationSheet — Phase 5
 * Real-time client-side scan of typed text for PII leakage:
 * - Phone numbers (regex)
 * - Instagram / Snapchat / WhatsApp handles
 * - Street addresses
 * - Single-character spacing evasion (e.g. "9 9 9 9")
 *
 * Shows warning bottom sheet before sending.
 * Free users: upgrade prompt. Subscribers: disclaimer + proceed.
 *
 * Backend also masks PII server-side for free users, but client-side
 * detection gives instant UX feedback.
 */

import React from "react";
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";

import {
  scanMessage as canonicalScanMessage,
  mapScanResultToDetectedType,
  DetectedSensitiveType,
} from "../../security/inputValidation";

export type DetectedType = DetectedSensitiveType;

/**
 * Scans message text using canonical security patterns.
 * Returns null if clean.
 */
export function scanMessage(text: string): DetectedType {
  const result = canonicalScanMessage(text);
  return mapScanResultToDetectedType(result);
}

const DETECTED_LABELS: Record<NonNullable<DetectedType>, string> = {
  phone: "phone number",
  social: "social media handle",
  address: "address",
  link: "external link",
};

interface ContentModerationSheetProps {
  visible: boolean;
  detectedType: DetectedType;
  isSubscriber: boolean;
  onProceed: () => void;        // subscriber only: send anyway
  onCancel: () => void;         // edit message
  onUpgrade: () => void;        // free user: go to subscriptions
}

export default function ContentModerationSheet({
  visible,
  detectedType,
  isSubscriber,
  onProceed,
  onCancel,
  onUpgrade,
}: ContentModerationSheetProps) {
  if (!detectedType) return null;

  const label = DETECTED_LABELS[detectedType];

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      statusBarTranslucent
      onRequestClose={onCancel}
    >
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.handle} />

          <Text style={styles.title}>⚠️ Sensitive Content Detected</Text>

          <Text style={styles.warning}>
            You are trying to exchange{" "}
            <Text style={styles.highlight}>[{label}]</Text>.
          </Text>

          {isSubscriber ? (
            <>
              <View style={styles.disclaimerBox}>
                <Text style={styles.disclaimerText}>
                  Exchange at your own risk and only if you trust this person.
                  Jainune is not responsible for any consequences.
                </Text>
              </View>
              <TouchableOpacity style={styles.proceedBtn} onPress={onProceed}>
                <Text style={styles.proceedBtnText}>Send Anyway — I Accept the Risk</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
                <Text style={styles.cancelBtnText}>Edit Message</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <View style={styles.maskedBox}>
                <Text style={styles.maskedText}>
                  🔒 Your {label} will be masked to{" "}
                  <Text style={{ fontFamily: "Inter_700Bold" }}>####</Text> for{" "}
                  free users. Upgrade to Jainune+ to share safely with a disclaimer.
                </Text>
              </View>
              <TouchableOpacity style={styles.upgradeBtn} onPress={onUpgrade}>
                <Text style={styles.upgradeBtnText}>Upgrade to Jainune+ ✨</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
                <Text style={styles.cancelBtnText}>Edit Message</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(0,0,0,0.45)",
  },
  sheet: {
    backgroundColor: colors.white,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    padding: spacing.xl,
    paddingBottom: spacing.xxxl,
  },
  handle: {
    width: 40,
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    alignSelf: "center",
    marginBottom: spacing.lg,
  },
  title: {
    fontFamily: "Outfit_700Bold",
    fontSize: 18,
    color: colors.dark,
    marginBottom: spacing.base,
    textAlign: "center",
  },
  warning: {
    ...typography.body,
    color: colors.mid,
    textAlign: "center",
    marginBottom: spacing.base,
  },
  highlight: { fontFamily: "Inter_700Bold", color: colors.red },
  disclaimerBox: {
    backgroundColor: colors.redLight,
    borderRadius: radii.md,
    padding: spacing.base,
    marginBottom: spacing.xl,
  },
  disclaimerText: { ...typography.bodySmall, color: colors.red, textAlign: "center" },
  maskedBox: {
    backgroundColor: colors.blueLight,
    borderRadius: radii.md,
    padding: spacing.base,
    marginBottom: spacing.xl,
  },
  maskedText: { ...typography.bodySmall, color: colors.blue, textAlign: "center" },
  proceedBtn: {
    backgroundColor: colors.red,
    borderRadius: radii.full,
    paddingVertical: spacing.md,
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  proceedBtnText: { fontFamily: "Outfit_700Bold", fontSize: 15, color: colors.white },
  upgradeBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
    paddingVertical: spacing.md,
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  upgradeBtnText: { fontFamily: "Outfit_700Bold", fontSize: 15, color: colors.white },
  cancelBtn: {
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  cancelBtnText: { ...typography.body, color: colors.muted },
});
