/**
 * Phase 7 — ProfileScreen (Full)
 * Own profile view: hero photos, prompts, basics strip, subscription badge,
 * Paryushan toggle, Profile Health Coach, Edit / Settings / Subscription CTAs.
 *
 * Security: FLAG_SECURE enabled on mount (profile data is private).
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  Switch,
  RefreshControl,
  Platform,
  Alert,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { getMyProfile, updateProfile, MyProfile } from "../../api/profileApi";
import { useAuthStore } from "../../store/authStore";
import { extractError } from "../../api/client";
import {
  enableScreenCaptureProtection,
  disableScreenCaptureProtection,
} from "../../security/antiReversing";

function calcAge(dob: string): number {
  const birth = new Date(dob);
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  if (
    now.getMonth() < birth.getMonth() ||
    (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())
  ) {
    age--;
  }
  return age;
}

export default function ProfileScreen() {
  const navigation = useNavigation<any>();
  const logout = useAuthStore((s) => s.logout);
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [paryushanLoading, setParyushanLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Block screenshots on private screen
  useEffect(() => {
    enableScreenCaptureProtection();
    return () => disableScreenCaptureProtection();
  }, []);

  const load = useCallback(async (isRefresh = false) => {
    if (!isRefresh) setLoading(true);
    setError(null);
    try {
      const data = await getMyProfile();
      setProfile(data);
    } catch (err) {
      setError(extractError(err).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  const toggleParyushan = async (val: boolean) => {
    if (!profile) return;
    setParyushanLoading(true);
    try {
      const updated = await updateProfile({ paryushan_mode: val });
      setProfile(updated);
    } catch {
      Alert.alert("Error", "Could not update Paryushan mode.");
    } finally {
      setParyushanLoading(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.saffron} />
      </View>
    );
  }

  if (error || !profile) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error ?? "Profile unavailable"}</Text>
        <TouchableOpacity onPress={() => load()}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const age = calcAge(profile.date_of_birth);
  const heroPhoto = profile.photos?.[0]?.url;
  const isSubscriber = profile.subscription_tier === "plus";

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingBottom: 80 }}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => { setRefreshing(true); load(true); }}
          tintColor={colors.saffron}
        />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>My Profile</Text>
        <TouchableOpacity
          style={styles.settingsBtn}
          onPress={() => navigation.navigate("Settings")}
        >
          <Text style={styles.settingsBtnText}>Settings</Text>
        </TouchableOpacity>
      </View>

      {/* Hero Photo */}
      <View style={styles.heroWrap}>
        {heroPhoto ? (
          <Image source={{ uri: heroPhoto }} style={styles.hero} />
        ) : (
          <View style={[styles.hero, styles.heroFallback]}>
            <Text style={styles.heroInitial}>{profile.first_name?.[0]}</Text>
          </View>
        )}

        {/* Subscription badge overlay */}
        {isSubscriber && (
          <View style={styles.subscriptionBadge}>
            <Text style={styles.subscriptionBadgeText}>Jainune+ ✦</Text>
          </View>
        )}

        {/* Verified badge */}
        {profile.is_verified && (
          <View style={styles.verifiedBadge}>
            <Text style={styles.verifiedBadgeText}>Verified</Text>
          </View>
        )}
      </View>

      <View style={styles.body}>
        {/* Name & City */}
        <Text style={styles.name}>{profile.first_name}, {age}</Text>
        {profile.city ? <Text style={styles.city}>{profile.city}</Text> : null}

        {/* Basics strip */}
        <View style={styles.basicsStrip}>
          {profile.profession ? (
            <View style={styles.basicPill}>
              <Text style={styles.basicPillText}>{profile.profession}</Text>
            </View>
          ) : null}
          {profile.community_sect ? (
            <View style={styles.basicPill}>
              <Text style={styles.basicPillText}>{profile.community_sect}</Text>
            </View>
          ) : null}
          {profile.dietary_strictness ? (
            <View style={styles.basicPill}>
              <Text style={styles.basicPillText}>{profile.dietary_strictness}</Text>
            </View>
          ) : null}
          {profile.eats_root_vegetables === false && (
            <View style={[styles.basicPill, styles.basicPillGreen]}>
              <Text style={[styles.basicPillText, styles.basicPillTextGreen]}>No Root Veg</Text>
            </View>
          )}
          {profile.eats_onion_garlic === false && (
            <View style={[styles.basicPill, styles.basicPillGreen]}>
              <Text style={[styles.basicPillText, styles.basicPillTextGreen]}>No Onion/Garlic</Text>
            </View>
          )}
        </View>

        {/* Paryushan Mode */}
        <View style={styles.paryushanRow}>
          <View style={styles.paryushanInfo}>
            <Text style={styles.paryushanLabel}>Paryushan Mode</Text>
            <Text style={styles.paryushanHint}>
              Pauses discovery & notifications during Paryushan
            </Text>
          </View>
          <Switch
            value={profile.paryushan_mode}
            onValueChange={toggleParyushan}
            disabled={paryushanLoading}
            trackColor={{ false: colors.border, true: colors.saffron }}
            thumbColor={colors.white}
          />
        </View>

        {/* Profile Health Coach — shown if health score is low */}
        {profile.profile_health_score < 0.5 && (
          <View style={styles.healthCard}>
            <Text style={styles.healthCardTitle}>
              Let's optimize your profile's genuine warmth.
            </Text>
            {profile.photos.length < 3 && (
              <Text style={styles.healthCardTip}>
                — Add at least 3 photos. Natural daylight photos increase connections by 42%.
              </Text>
            )}
            {profile.prompts.length < 3 && (
              <Text style={styles.healthCardTip}>
                — Add 3 prompts with detailed responses to give matches a conversation hook.
              </Text>
            )}
            {!profile.voice_snapshot_url && (
              <Text style={styles.healthCardTip}>
                — Record a 7-second voice snapshot. Voice profiles get 3x more matches.
              </Text>
            )}
          </View>
        )}

        {/* Prompts preview */}
        {profile.prompts.map((p) => (
          <View key={p.prompt_id} style={styles.promptCard}>
            <Text style={styles.promptLabel}>{p.prompt_text}</Text>
            <Text style={styles.promptResponse}>{p.response}</Text>
          </View>
        ))}

        {/* Photo count indicator */}
        <Text style={styles.photoCount}>
          {profile.photos.length} / 6 photos
        </Text>

        {/* Action Buttons */}
        <TouchableOpacity
          style={styles.primaryBtn}
          onPress={() => navigation.navigate("EditProfile")}
        >
          <Text style={styles.primaryBtnText}>Edit Profile</Text>
        </TouchableOpacity>

        {!isSubscriber && (
          <TouchableOpacity
            style={styles.upgradeBtn}
            onPress={() => navigation.navigate("Subscriptions")}
          >
            <Text style={styles.upgradeBtnText}>Upgrade to Jainune+ ✦</Text>
          </TouchableOpacity>
        )}

        {isSubscriber && profile.subscription_expires_at && (
          <View style={styles.subscriptionInfo}>
            <Text style={styles.subscriptionInfoText}>
              Jainune+ active until{" "}
              {new Date(profile.subscription_expires_at).toLocaleDateString("en-IN", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </Text>
          </View>
        )}

        {/* Danger zone */}
        <View style={styles.dangerSection}>
          <TouchableOpacity
            style={styles.dangerBtn}
            onPress={() => {
              Alert.alert(
                "Sign Out",
                "Are you sure you want to sign out?",
                [
                  { text: "Cancel", style: "cancel" },
                  { text: "Sign Out", style: "destructive", onPress: logout },
                ]
              );
            }}
          >
            <Text style={styles.dangerBtnText}>Sign Out</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.deleteLinkWrap}
            onPress={() => navigation.navigate("DeleteAccount")}
          >
            <Text style={styles.deleteLink}>Delete Account</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg, padding: spacing.xxl },
  errorText: { ...typography.body, color: colors.red, textAlign: "center", marginBottom: spacing.sm },
  retryText: { fontFamily: "Outfit_600SemiBold", color: colors.saffron },
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
  headerTitle: { fontFamily: "Outfit_700Bold", fontSize: 22, color: colors.dark },
  settingsBtn: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  settingsBtnText: { fontFamily: "Outfit_600SemiBold", color: colors.saffron, fontSize: 15 },
  heroWrap: { position: "relative" },
  hero: { width: "100%", height: 340, resizeMode: "cover" },
  heroFallback: {
    backgroundColor: colors.saffronLight,
    alignItems: "center",
    justifyContent: "center",
  },
  heroInitial: { fontFamily: "Outfit_800ExtraBold", fontSize: 100, color: colors.saffron },
  subscriptionBadge: {
    position: "absolute",
    top: spacing.base,
    right: spacing.base,
    backgroundColor: "rgba(255,156,74,0.92)",
    borderRadius: radii.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  subscriptionBadgeText: { fontFamily: "Outfit_700Bold", fontSize: 12, color: colors.white },
  verifiedBadge: {
    position: "absolute",
    top: spacing.base,
    left: spacing.base,
    backgroundColor: colors.green,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  verifiedBadgeText: { fontFamily: "Outfit_700Bold", fontSize: 11, color: colors.white },
  body: { padding: spacing.base },
  name: { fontFamily: "Outfit_800ExtraBold", fontSize: 28, color: colors.dark, marginTop: spacing.base },
  city: { ...typography.body, color: colors.mid, marginBottom: spacing.base },
  basicsStrip: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginBottom: spacing.xl,
  },
  basicPill: {
    borderRadius: radii.full,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: colors.white,
  },
  basicPillText: { ...typography.caption, color: colors.mid },
  basicPillGreen: { borderColor: colors.green, backgroundColor: colors.greenLight },
  basicPillTextGreen: { color: colors.green },
  paryushanRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: radii.lg,
    padding: spacing.base,
    marginBottom: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
  },
  paryushanInfo: { flex: 1 },
  paryushanLabel: { fontFamily: "Outfit_600SemiBold", fontSize: 15, color: colors.dark },
  paryushanHint: { ...typography.caption, color: colors.muted, marginTop: 2 },
  healthCard: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.lg,
    padding: spacing.base,
    marginBottom: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  healthCardTitle: { fontFamily: "Outfit_600SemiBold", fontSize: 14, color: colors.dark, marginBottom: spacing.sm },
  healthCardTip: { ...typography.bodySmall, color: colors.mid, lineHeight: 20, marginBottom: spacing.xs },
  promptCard: {
    backgroundColor: colors.white,
    borderRadius: radii.lg,
    padding: spacing.base,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  promptLabel: { fontFamily: "Outfit_700Bold", fontSize: 13, color: colors.saffron, marginBottom: spacing.xs },
  promptResponse: { ...typography.body, color: colors.dark, lineHeight: 22 },
  photoCount: { ...typography.caption, color: colors.muted, textAlign: "center", marginVertical: spacing.md },
  primaryBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  primaryBtnText: { fontFamily: "Outfit_700Bold", fontSize: 16, color: colors.white },
  upgradeBtn: {
    backgroundColor: colors.pinkMid,
    borderRadius: radii.full,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  upgradeBtnText: { fontFamily: "Outfit_700Bold", fontSize: 16, color: colors.white },
  subscriptionInfo: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
    alignItems: "center",
  },
  subscriptionInfoText: { ...typography.bodySmall, color: colors.saffron },
  dangerSection: { marginTop: spacing.xxl, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.xl },
  dangerBtn: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.full,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  dangerBtnText: { fontFamily: "Outfit_600SemiBold", fontSize: 15, color: colors.dark },
  deleteLinkWrap: { alignItems: "center", paddingVertical: spacing.sm },
  deleteLink: { ...typography.bodySmall, color: colors.red },
});
