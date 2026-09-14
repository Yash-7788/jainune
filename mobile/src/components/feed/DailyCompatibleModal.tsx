/**
 * DailyCompatibleModal — Curated Gale-Shapley Stable Marriage match of the day
 * Fetches from /feed/daily-compatible, tracks daily_compatible_view telemetry,
 * and allows the user to Like or Pass today's single curated connection.
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  Modal,
  View,
  Text,
  Image,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  Platform,
} from "react-native";
import { colors, spacing, radii, typography, shadows } from "../../theme/tokens";
import {
  getDailyCompatible,
  postInteraction,
  DailyCompatibleResponse,
  FeedCandidate,
  InteractionResult,
} from "../../api/feedApi";
import { useTelemetry } from "../../hooks/useTelemetry";

interface DailyCompatibleModalProps {
  visible: boolean;
  onClose: () => void;
  onMatch: (match: InteractionResult, candidate: FeedCandidate) => void;
}

export default function DailyCompatibleModal({
  visible,
  onClose,
  onMatch,
}: DailyCompatibleModalProps) {
  const [loading, setLoading] = useState(false);
  const [candidate, setCandidate] = useState<FeedCandidate | null>(null);
  const [lockedUntil, setLockedUntil] = useState<string | null>(null);
  const [algorithm, setAlgorithm] = useState<string>("gale_shapley_nightly");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [interacted, setInteracted] = useState(false);

  const { trackEvent } = useTelemetry();

  const loadDailyCompatible = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data: DailyCompatibleResponse = await getDailyCompatible();
      setCandidate(data.candidate);
      setLockedUntil(data.locked_until);
      setAlgorithm(data.pairing_algorithm);
      setInteracted(false);

      if (data.candidate?.id) {
        trackEvent("daily_compatible_view", data.candidate.id, null, {
          algorithm: data.pairing_algorithm,
        });
      }
    } catch (err: any) {
      setError(err?._apiError?.message || "Unable to load today's Daily Compatible.");
    } finally {
      setLoading(false);
    }
  }, [trackEvent]);

  useEffect(() => {
    if (visible) {
      loadDailyCompatible();
    }
  }, [visible, loadDailyCompatible]);

  const handleAction = async (action: "like" | "pass") => {
    if (!candidate || submitting) return;
    setSubmitting(true);
    try {
      trackEvent(`interaction_${action}`, candidate.id, null, { source: "daily_compatible" });
      const result = await postInteraction(
        candidate.id,
        action,
        candidate.photos?.[0] ? "photo" : "prompt",
        candidate.photos?.[0]?.id ?? candidate.id
      );
      setInteracted(true);
      if (result.is_match) {
        onClose();
        onMatch(result, candidate);
      }
    } catch (err: any) {
      setError(err?._apiError?.message || "Failed to submit interaction.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>Daily Compatible ✨</Text>
            <Text style={styles.headerSubtitle}>
              {algorithm === "gale_shapley_nightly"
                ? "Curated Gale-Shapley Stable Marriage"
                : "Top Mutual Behavioral Affinity"}
            </Text>
          </View>
          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={colors.saffron} />
            <Text style={styles.loadingText}>Unveiling today's curated connection...</Text>
          </View>
        ) : error ? (
          <View style={styles.center}>
            <Text style={styles.emptyTitle}>Could Not Load</Text>
            <Text style={styles.emptyDesc}>{error}</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={loadDailyCompatible}>
              <Text style={styles.retryBtnText}>Try Again</Text>
            </TouchableOpacity>
          </View>
        ) : !candidate || interacted ? (
          <View style={styles.center}>
            <Text style={styles.emptyEmoji}>🌅</Text>
            <Text style={styles.emptyTitle}>You're All Set for Today!</Text>
            <Text style={styles.emptyDesc}>
              {interacted
                ? "Your response is saved! Next curated Daily Compatible unlocks at midnight IST."
                : "No new curated profile right now. Check back at midnight IST for tomorrow's match!"}
            </Text>
            {lockedUntil && (
              <View style={styles.lockBadge}>
                <Text style={styles.lockBadgeText}>🔒 Resets at Midnight IST</Text>
              </View>
            )}
            <TouchableOpacity style={styles.doneBtn} onPress={onClose}>
              <Text style={styles.doneBtnText}>Back to Discovery Feed</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
            {/* Primary Photo Card */}
            <View style={styles.card}>
              {candidate.photos?.[0] ? (
                <Image source={{ uri: candidate.photos[0].url }} style={styles.photo} />
              ) : (
                <View style={[styles.photo, styles.photoFallback]}>
                  <Text style={styles.photoInitial}>{candidate.first_name[0]}</Text>
                </View>
              )}

              {/* Bio & Details Overlay */}
              <View style={styles.detailsContainer}>
                <Text style={styles.nameText}>
                  {candidate.first_name}, {candidate.age}
                </Text>
                <Text style={styles.locationText}>
                  📍 {candidate.city}, {candidate.state}
                </Text>

                {/* Compatibility highlights */}
                <View style={styles.pillRow}>
                  <View style={styles.pill}>
                    <Text style={styles.pillText}>✨ 94% Values Match</Text>
                  </View>
                  {candidate.community_sect ? (
                    <View style={styles.pill}>
                      <Text style={styles.pillText}>🏛️ {candidate.community_sect}</Text>
                    </View>
                  ) : null}
                  {candidate.dietary_strictness ? (
                    <View style={styles.pill}>
                      <Text style={styles.pillText}>🥗 {candidate.dietary_strictness}</Text>
                    </View>
                  ) : null}
                </View>

                {candidate.bio ? (
                  <Text style={styles.bioText}>{candidate.bio}</Text>
                ) : null}

                {/* Prompts if available */}
                {candidate.prompts && candidate.prompts.length > 0 && (
                  <View style={styles.promptWrap}>
                    <Text style={styles.promptQ}>{candidate.prompts[0].question}</Text>
                    <Text style={styles.promptA}>{candidate.prompts[0].answer}</Text>
                  </View>
                )}
              </View>
            </View>

            {/* Action Buttons */}
            <View style={styles.actionRow}>
              <TouchableOpacity
                style={[styles.actionBtn, styles.passBtn]}
                onPress={() => handleAction("pass")}
                disabled={submitting}
              >
                <Text style={styles.passBtnText}>✕ Pass</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.actionBtn, styles.likeBtn]}
                onPress={() => handleAction("like")}
                disabled={submitting}
              >
                {submitting ? (
                  <ActivityIndicator size="small" color={colors.white} />
                ) : (
                  <Text style={styles.likeBtnText}>♥ Like</Text>
                )}
              </TouchableOpacity>
            </View>

            <Text style={styles.footerNote}>
              🔒 One match per day. Gale-Shapley ensures optimal mutual preference resolution.
            </Text>
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingTop: Platform.OS === "ios" ? 20 : 16,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: {
    ...typography.h2,
    color: colors.dark,
  },
  headerSubtitle: {
    ...typography.caption,
    color: colors.saffron,
    fontWeight: "600",
    marginTop: 2,
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.light,
    alignItems: "center",
    justifyContent: "center",
  },
  closeBtnText: {
    fontSize: 16,
    color: colors.mid,
    fontWeight: "600",
  },
  scrollContent: {
    padding: spacing.md,
    alignItems: "center",
  },
  card: {
    width: "100%",
    backgroundColor: colors.white,
    borderRadius: radii.xl,
    overflow: "hidden",
    ...shadows.card,
  },
  photo: {
    width: "100%",
    height: 380,
    backgroundColor: colors.light,
  },
  photoFallback: {
    alignItems: "center",
    justifyContent: "center",
  },
  photoInitial: {
    fontSize: 72,
    color: colors.muted,
    fontWeight: "700",
  },
  detailsContainer: {
    padding: spacing.lg,
  },
  nameText: {
    ...typography.h2,
    color: colors.dark,
  },
  locationText: {
    ...typography.bodySmall,
    color: colors.mid,
    marginTop: 4,
  },
  pillRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 12,
  },
  pill: {
    backgroundColor: colors.saffronLight,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  pillText: {
    ...typography.caption,
    fontWeight: "600",
    color: colors.saffron,
  },
  bioText: {
    ...typography.body,
    color: colors.dark,
    marginTop: 12,
  },
  promptWrap: {
    marginTop: 14,
    backgroundColor: colors.light,
    padding: 12,
    borderRadius: 10,
  },
  promptQ: {
    ...typography.caption,
    color: colors.muted,
    fontWeight: "600",
  },
  promptA: {
    ...typography.body,
    color: colors.dark,
    fontWeight: "500",
    marginTop: 4,
  },
  actionRow: {
    flexDirection: "row",
    width: "100%",
    justifyContent: "space-between",
    gap: 16,
    marginTop: 20,
  },
  actionBtn: {
    flex: 1,
    height: 52,
    borderRadius: 26,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.button,
  },
  passBtn: {
    backgroundColor: colors.white,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  passBtnText: {
    ...typography.body,
    fontWeight: "700",
    color: colors.mid,
  },
  likeBtn: {
    backgroundColor: colors.saffron,
  },
  likeBtnText: {
    ...typography.body,
    fontWeight: "700",
    color: colors.white,
  },
  footerNote: {
    ...typography.caption,
    color: colors.muted,
    textAlign: "center",
    marginTop: 16,
    marginBottom: 24,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  loadingText: {
    marginTop: 12,
    ...typography.body,
    color: colors.mid,
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    ...typography.h2,
    color: colors.dark,
    textAlign: "center",
  },
  emptyDesc: {
    ...typography.body,
    color: colors.mid,
    textAlign: "center",
    marginTop: 8,
    lineHeight: 20,
  },
  lockBadge: {
    marginTop: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.light,
    borderRadius: 14,
  },
  lockBadgeText: {
    ...typography.caption,
    fontWeight: "600",
    color: colors.mid,
  },
  doneBtn: {
    marginTop: 24,
    paddingHorizontal: 24,
    paddingVertical: 12,
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
  },
  doneBtnText: {
    ...typography.body,
    fontWeight: "700",
    color: colors.white,
  },
  retryBtn: {
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
  },
  retryBtnText: {
    ...typography.bodySmall,
    fontWeight: "600",
    color: colors.white,
  },
});
