/**
 * Phase 7 — DeleteAccountScreen
 * DPDP Act 2023 Right to Erasure (Section 11.2 of SECURITY.md)
 *
 * Flow:
 * 1. Show consequences clearly
 * 2. User selects reason (required, sent to backend for analytics)
 * 3. Confirm with typed word "DELETE"
 * 4. POST /v1/users/me/delete
 * 5. Backend sets account_status=deleted, schedules 72h hard purge
 * 6. Client clears tokens and signs out
 */

import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  Platform,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { requestAccountDeletion } from "../../api/profileApi";
import { useAuthStore } from "../../store/authStore";
import { extractError } from "../../api/client";

const REASONS = [
  "Found my person",
  "Taking a break",
  "App didn't meet my expectations",
  "Privacy concerns",
  "Too many notifications",
  "Other",
];

const CONSEQUENCES = [
  "Your profile will be removed from all discovery feeds immediately.",
  "All matches and conversations will be permanently deleted within 72 hours.",
  "Your photos and voice snapshots will be purged from our servers.",
  "Active Jainune+ subscriptions will not be refunded.",
  "Financial transaction logs are retained for 7 years per RBI regulations.",
  "This action cannot be undone.",
];

export default function DeleteAccountScreen() {
  const navigation = useNavigation<any>();
  const logout = useAuthStore((s) => s.logout);
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [loading, setLoading] = useState(false);

  const canDelete = selectedReason !== null && confirmText.trim() === "DELETE";

  const handleDelete = async () => {
    if (!canDelete || !selectedReason) return;
    Alert.alert(
      "This is permanent",
      "All your data will be erased. This cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete My Account",
          style: "destructive",
          onPress: async () => {
            setLoading(true);
            try {
              await requestAccountDeletion(selectedReason);
              await logout();
            } catch (err) {
              setLoading(false);
              Alert.alert("Error", extractError(err).message);
            }
          },
        },
      ]
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 80 }}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Text style={styles.backBtnText}>Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Delete Account</Text>
        <View style={{ width: 60 }} />
      </View>

      <View style={styles.body}>
        <Text style={styles.warningTitle}>Before you go</Text>
        <Text style={styles.warningSubtitle}>
          Deleting your account is permanent. Here is what will happen:
        </Text>

        {CONSEQUENCES.map((c, i) => (
          <View key={i} style={styles.consequenceRow}>
            <View style={styles.bullet} />
            <Text style={styles.consequenceText}>{c}</Text>
          </View>
        ))}

        <Text style={styles.sectionLabel}>Why are you leaving?</Text>
        {REASONS.map((r) => (
          <TouchableOpacity
            key={r}
            style={[styles.reasonRow, selectedReason === r && styles.reasonRowSelected]}
            onPress={() => setSelectedReason(r)}
          >
            <View style={[styles.radioOuter, selectedReason === r && styles.radioOuterSelected]}>
              {selectedReason === r && <View style={styles.radioInner} />}
            </View>
            <Text style={[styles.reasonText, selectedReason === r && styles.reasonTextSelected]}>
              {r}
            </Text>
          </TouchableOpacity>
        ))}

        <Text style={styles.sectionLabel}>
          Type <Text style={styles.deleteWord}>DELETE</Text> to confirm
        </Text>
        <TextInput
          style={styles.confirmInput}
          value={confirmText}
          onChangeText={setConfirmText}
          placeholder="Type DELETE here"
          placeholderTextColor={colors.muted}
          autoCapitalize="characters"
          autoCorrect={false}
          autoComplete="off"
          maxLength={6}
        />

        <TouchableOpacity
          style={[styles.deleteBtn, !canDelete && styles.deleteBtnDisabled]}
          onPress={handleDelete}
          disabled={!canDelete || loading}
        >
          {loading ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <Text style={styles.deleteBtnText}>Permanently Delete Account</Text>
          )}
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 56 : 24,
    paddingBottom: spacing.base,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  backBtn: { paddingVertical: spacing.xs },
  backBtnText: { fontFamily: "Outfit_600SemiBold", color: colors.saffron, fontSize: 15 },
  headerTitle: { fontFamily: "Outfit_700Bold", fontSize: 17, color: colors.dark },
  body: { padding: spacing.base },
  warningTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 22,
    color: colors.dark,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
  },
  warningSubtitle: { ...typography.body, color: colors.mid, marginBottom: spacing.xl, lineHeight: 22 },
  consequenceRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginBottom: spacing.sm },
  bullet: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.red, marginTop: 8, flexShrink: 0 },
  consequenceText: { ...typography.bodySmall, color: colors.mid, flex: 1, lineHeight: 20 },
  sectionLabel: {
    fontFamily: "Outfit_700Bold",
    fontSize: 15,
    color: colors.dark,
    marginTop: spacing.xxl,
    marginBottom: spacing.base,
  },
  deleteWord: { color: colors.red },
  reasonRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.base,
    borderRadius: radii.lg,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.white,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
  reasonRowSelected: { borderColor: colors.red, backgroundColor: colors.redLight },
  radioOuter: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  radioOuterSelected: { borderColor: colors.red },
  radioInner: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.red },
  reasonText: { fontFamily: "Inter_400Regular", fontSize: 15, color: colors.dark },
  reasonTextSelected: { color: colors.red, fontFamily: "Inter_700Bold" },
  confirmInput: {
    borderBottomWidth: 2,
    borderBottomColor: colors.border,
    paddingVertical: spacing.md,
    fontFamily: "Outfit_700Bold",
    fontSize: 18,
    color: colors.red,
    letterSpacing: 4,
    marginBottom: spacing.xxl,
  },
  deleteBtn: {
    backgroundColor: colors.red,
    borderRadius: radii.full,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
  },
  deleteBtnDisabled: { opacity: 0.35 },
  deleteBtnText: { fontFamily: "Outfit_700Bold", fontSize: 16, color: colors.white },
});
