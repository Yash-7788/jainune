/**
 * Phase 7 — SettingsScreen
 * Privacy controls, notification preferences, account management.
 * All settings persist via PUT /v1/users/me/settings.
 * FLAG_SECURE active on this screen.
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Switch,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
  Linking,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { updateSettings, getSettings } from "../../api/profileApi";
import { useAuthStore } from "../../store/authStore";
import {
  enableScreenCaptureProtection,
  disableScreenCaptureProtection,
} from "../../security/antiReversing";
import LegalModal, { LegalDocType } from "../../components/legal/LegalModal";

interface SettingState {
  notifications_enabled: boolean;
  marketing_emails: boolean;
  show_online_status: boolean;
  discovery_paused: boolean;
}

export default function SettingsScreen() {
  const navigation = useNavigation<any>();
  const logout = useAuthStore((s) => s.logout);
  const [legalDoc, setLegalDoc] = useState<LegalDocType | null>(null);
  const [settings, setSettings] = useState<SettingState>({
    notifications_enabled: true,
    marketing_emails: false,
    show_online_status: true,
    discovery_paused: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<keyof SettingState | null>(null);

  useEffect(() => {
    enableScreenCaptureProtection();
    getSettings()
      .then((data) => {
        if (data) {
          setSettings({
            notifications_enabled: !!data.notifications_enabled,
            marketing_emails: !!data.marketing_emails,
            show_online_status: !!data.show_online_status,
            discovery_paused: !!data.discovery_paused,
          });
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    return () => disableScreenCaptureProtection();
  }, []);

  const toggle = useCallback(async (key: keyof SettingState, val: boolean) => {
    setSettings((prev) => ({ ...prev, [key]: val }));
    setSaving(key);
    try {
      await updateSettings({ [key]: val });
    } catch {
      // Revert on error
      setSettings((prev) => ({ ...prev, [key]: !val }));
      Alert.alert("Error", "Could not save setting. Try again.");
    } finally {
      setSaving(null);
    }
  }, []);

  const rows: { key: keyof SettingState; label: string; hint: string }[] = [
    {
      key: "notifications_enabled",
      label: "Push Notifications",
      hint: "Match alerts, messages, Momentum warnings",
    },
    {
      key: "marketing_emails",
      label: "Marketing Emails",
      hint: "Jainune features, offers & Sunday Drops newsletter",
    },
    {
      key: "show_online_status",
      label: "Show Online Status",
      hint: "Others can see when you're active",
    },
    {
      key: "discovery_paused",
      label: "Pause Discovery",
      hint: "Your profile won't appear in anyone's feed",
    },
  ];

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 80 }}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Text style={styles.backBtnText}>Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings & Privacy</Text>
        <View style={{ width: 48 }} />
      </View>

      {/* Notifications & Privacy */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>NOTIFICATIONS & PRIVACY</Text>
        {rows.map((row) => (
          <View key={row.key} style={styles.row}>
            <View style={styles.rowInfo}>
              <Text style={styles.rowLabel}>{row.label}</Text>
              <Text style={styles.rowHint}>{row.hint}</Text>
            </View>
            {saving === row.key ? (
              <ActivityIndicator size="small" color={colors.saffron} />
            ) : (
              <Switch
                value={settings[row.key]}
                onValueChange={(v) => toggle(row.key, v)}
                trackColor={{ false: colors.border, true: colors.saffron }}
                thumbColor={colors.white}
              />
            )}
          </View>
        ))}
      </View>

      {/* Legal & Safety */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>LEGAL & SAFETY</Text>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => setLegalDoc("privacy")}
        >
          <Text style={styles.linkRowText}>Privacy Policy</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => setLegalDoc("terms")}
        >
          <Text style={styles.linkRowText}>Terms of Service</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => setLegalDoc("child_safety")}
        >
          <Text style={styles.linkRowText}>Child Safety & CSAE Standards</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => setLegalDoc("community")}
        >
          <Text style={styles.linkRowText}>Community Guidelines</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => setLegalDoc("deletion")}
        >
          <Text style={styles.linkRowText}>External Data Erasure Portal</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* Account */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>ACCOUNT</Text>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => navigation.navigate("Subscriptions")}
        >
          <Text style={styles.linkRowText}>Manage Subscription</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => {
            Alert.alert("Sign Out", "Are you sure?", [
              { text: "Cancel", style: "cancel" },
              { text: "Sign Out", style: "destructive", onPress: logout },
            ]);
          }}
        >
          <Text style={[styles.linkRowText, { color: colors.red }]}>Sign Out</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.linkRow}
          onPress={() => navigation.navigate("DeleteAccount")}
        >
          <Text style={[styles.linkRowText, { color: colors.red }]}>Delete Account</Text>
          <Text style={styles.linkChevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* App info */}
      <Text style={styles.appVersion}>Jainune v1.0.0 — Made with care in Bangalore</Text>

      <LegalModal
        visible={legalDoc !== null}
        initialDoc={legalDoc ?? "privacy"}
        onClose={() => setLegalDoc(null)}
      />
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
  backBtn: { width: 48, paddingVertical: spacing.xs },
  backBtnText: { fontFamily: "Outfit_600SemiBold", color: colors.saffron, fontSize: 15 },
  headerTitle: { fontFamily: "Outfit_700Bold", fontSize: 17, color: colors.dark },
  section: {
    marginTop: spacing.xl,
    backgroundColor: colors.white,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.border,
  },
  sectionTitle: {
    fontFamily: "Inter_700Bold",
    fontSize: 11,
    color: colors.muted,
    letterSpacing: 1.2,
    paddingHorizontal: spacing.base,
    paddingTop: spacing.base,
    paddingBottom: spacing.sm,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.sm,
  },
  rowInfo: { flex: 1 },
  rowLabel: { fontFamily: "Inter_400Regular", fontSize: 15, color: colors.dark },
  rowHint: { ...typography.caption, color: colors.muted, marginTop: 2 },
  linkRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  linkRowText: { fontFamily: "Inter_400Regular", fontSize: 15, color: colors.dark },
  linkChevron: { fontSize: 18, color: colors.muted },
  appVersion: {
    ...typography.caption,
    color: colors.muted,
    textAlign: "center",
    marginTop: spacing.xxl,
    marginBottom: spacing.base,
  },
});
