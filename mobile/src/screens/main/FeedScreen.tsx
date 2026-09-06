/**
 * Phase 4 — Feed Screen: Full swipe card stack
 * - Loads batch of 15 candidates from GET /v1/feed
 * - Renders top 2 cards (stacked), PanResponder swipe on top card
 * - Like / Pass fire POST /v1/interactions/action
 * - Dwell telemetry: POST /v1/telemetry/interaction-event (fire & forget)
 * - Mutual match → MatchModal → open ChatScreen
 * - 5 UI states: loading skeleton | populated stack | empty | error | offline banner
 * - Free tier daily limit → friendly upgrade bottom sheet
 */

import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Animated,
  Platform,
  ScrollView,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as SecureStore from "expo-secure-store";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import SwipeCard from "../../components/feed/SwipeCard";
import MatchModal from "../../components/feed/MatchModal";
import { Image } from "expo-image";
import {
  getFeed,
  postInteraction,
  sendTelemetry,
  FeedCandidate,
  InteractionResult,
} from "../../api/feedApi";
import { getMyProfile } from "../../api/profileApi";
import { extractError } from "../../api/client";
import { SerendipityArcadeModal } from "../../components/arcade";

const PREFETCH_THRESHOLD = 3; // Fetch next batch when ≤3 cards left

type UIState = "loading" | "populated" | "empty" | "error" | "offline";

export default function FeedScreen() {
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();
  const [uiState, setUiState] = useState<UIState>("loading");
  const [candidates, setCandidates] = useState<FeedCandidate[]>([]);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [match, setMatch] = useState<InteractionResult | null>(null);
  const [matchCandidate, setMatchCandidate] = useState<FeedCandidate | null>(null);
  const [myPhotoUrl, setMyPhotoUrl] = useState<string | undefined>(undefined);
  const [isFetching, setIsFetching] = useState(false);
  const [dailyLimitReached, setDailyLimitReached] = useState(false);
  const [showArcade, setShowArcade] = useState(false);
  const offlineBannerAnim = useRef(new Animated.Value(0)).current;
  const isOffline = useRef(false);
  const requestTimestamps = useRef<number[]>([]);

  // Load my profile photo once
  useEffect(() => {
    getMyProfile()
      .then((p: any) => {
        const photo = p?.photos?.[0]?.cdn_url ?? p?.photos?.[0]?.url;
        if (photo) setMyPhotoUrl(photo);
      })
      .catch(() => {});
  }, []);

  // Hardware GPU prefetch for upcoming card photos (zero-flicker swipes)
  useEffect(() => {
    if (candidates.length > 0) {
      const upcoming = candidates.slice(0, 3);
      for (const cand of upcoming) {
        if (cand.photos && cand.photos.length > 0) {
          for (const p of cand.photos.slice(0, 2)) {
            if (p.url) {
              Image.prefetch(p.url).catch(() => {});
            }
          }
        }
      }
    }
  }, [candidates]);

  const fetchBatch = useCallback(async () => {
    if (isFetching) return;

    // Rate-limit guard: max 20 requests per 60 seconds (SECURITY.md §10.1)
    const now = Date.now();
    requestTimestamps.current = requestTimestamps.current.filter((t) => now - t < 60000);
    if (requestTimestamps.current.length >= 20) {
      setError({
        title: "Please Slow Down",
        message: "You have refreshed the feed frequently. Please wait a moment before trying again.",
      });
      return;
    }
    requestTimestamps.current.push(now);

    setIsFetching(true);
    try {
      const data = await getFeed(15);
      if (data.exhausted && data.candidates.length === 0) {
        setCandidates((prev) => (prev.length === 0 ? [] : prev));
        if (candidates.length === 0) setUiState("empty");
      } else {
        setCandidates((prev) => [...prev, ...data.candidates]);
        setUiState("populated");
      }
      if (isOffline.current) {
        isOffline.current = false;
        Animated.timing(offlineBannerAnim, { toValue: 0, duration: 400, useNativeDriver: true }).start();
      }
    } catch (err: any) {
      if (err?._apiError?.code === "DAILY_LIMIT_REACHED") {
        setDailyLimitReached(true);
        setUiState("populated");
        return;
      }
      if (err?._apiError?.status === 429 || err?._apiError?.code === "RATE_LIMITED") {
        setError({
          title: "Rate Limit Exceeded",
          message: "Too many feed requests. Please wait a minute before discovering more profiles.",
        });
        return;
      }
      const isNetworkErr = !err?.response;
      if (isNetworkErr) {
        isOffline.current = true;
        Animated.timing(offlineBannerAnim, { toValue: 1, duration: 400, useNativeDriver: true }).start();
        if (candidates.length === 0) setUiState("offline");
      } else {
        setError(extractError(err));
        if (candidates.length === 0) setUiState("error");
      }
    } finally {
      setIsFetching(false);
    }
  }, [isFetching, candidates.length]);

  useEffect(() => {
    fetchBatch();
  }, []);

  const handleSwipeRight = useCallback(
    async (candidate: FeedCandidate, totalMs: number, photoMs: number, promptMs: number) => {
      // Remove from stack optimistically
      setCandidates((prev) => prev.filter((c) => c.id !== candidate.id));

      // Prefetch if running low
      if (candidates.length <= PREFETCH_THRESHOLD) fetchBatch();

      try {
        const result = await postInteraction(
          candidate.id,
          "like",
          candidate.photos?.[0] ? "photo" : "prompt",
          candidate.photos?.[0]?.id ?? candidate.id
        );

        // Fire telemetry (non-blocking)
        sendTelemetry({
          target_user_id: candidate.id,
          action: "like",
          total_dwell_ms: totalMs,
          photo_dwell_ms: photoMs,
          prompt_dwell_ms: promptMs,
          voice_played_ratio: 0,
          comment_char_count: 0,
        });

        if (result.is_match) {
          setMatch(result);
          setMatchCandidate(candidate);
        }
      } catch (err: any) {
        if (err?._apiError?.code === "DAILY_LIMIT_REACHED") {
          setDailyLimitReached(true);
        }
      }
    },
    [candidates.length, fetchBatch]
  );

  const handleSwipeLeft = useCallback(
    async (candidate: FeedCandidate, totalMs: number, photoMs: number, promptMs: number) => {
      setCandidates((prev) => prev.filter((c) => c.id !== candidate.id));
      if (candidates.length <= PREFETCH_THRESHOLD) fetchBatch();

      sendTelemetry({
        target_user_id: candidate.id,
        action: "pass",
        total_dwell_ms: totalMs,
        photo_dwell_ms: photoMs,
        prompt_dwell_ms: promptMs,
        voice_played_ratio: 0,
        comment_char_count: 0,
      });

      try {
        await postInteraction(candidate.id, "pass", "photo", candidate.id);
      } catch {}
    },
    [candidates.length, fetchBatch]
  );

  const handleSuperLike = useCallback(
    async (candidate: FeedCandidate, totalMs: number) => {
      setCandidates((prev) => prev.filter((c) => c.id !== candidate.id));
      if (candidates.length <= PREFETCH_THRESHOLD) fetchBatch();

      sendTelemetry({
        target_user_id: candidate.id,
        action: "superlike",
        total_dwell_ms: totalMs,
        photo_dwell_ms: 0,
        prompt_dwell_ms: 0,
        voice_played_ratio: 0,
        comment_char_count: 0,
      });

      try {
        const result = await postInteraction(candidate.id, "superlike", "photo", candidate.id);
        if (result.is_match) {
          setMatch(result);
          setMatchCandidate(candidate);
        }
      } catch (err: any) {
        if (err?._apiError?.code === "INSUFFICIENT_CREDITS") {
          // TODO Phase 7: open arcade/coin purchase sheet
        }
      }
    },
    [candidates.length, fetchBatch]
  );

  const openChat = (chatId: string) => {
    setMatch(null);
    setMatchCandidate(null);
    navigation.navigate("Chat", { matchId: chatId, otherUser: matchCandidate });
  };

  // ── UI States ────────────────────────────────────────────────────────────────

  if (uiState === "loading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.saffron} />
        <Text style={styles.loadingText}>Finding your matches... ✨</Text>
      </View>
    );
  }

  if (uiState === "error") {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyTitle}>Our Servers Need a Chai Break ☕</Text>
        <Text style={styles.emptyDesc}>
          {error?.message ?? "Something went wrong. Hang tight!"}
        </Text>
        <TouchableOpacity style={styles.retryBtn} onPress={fetchBatch}>
          <Text style={styles.retryBtnText}>Try Again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (uiState === "offline") {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyTitle}>Lost in the Cloud Clouds? ☁️</Text>
        <Text style={styles.emptyDesc}>
          Even true love needs strong Wi-Fi! Check your connection and retry.
        </Text>
        <TouchableOpacity style={styles.retryBtn} onPress={fetchBatch}>
          <Text style={styles.retryBtnText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const visibleCards = candidates.slice(0, 2);
  const stackEmpty = candidates.length === 0;

  return (
    <View style={styles.container}>
      {/* Offline sticky banner */}
      <Animated.View
        style={[
          styles.offlineBanner,
          { opacity: offlineBannerAnim, transform: [{ translateY: offlineBannerAnim.interpolate({ inputRange: [0, 1], outputRange: [-40, 0] }) }] },
        ]}
        pointerEvents="none"
      >
        <Text style={styles.offlineBannerText}>☁️ No connection — showing cached profiles</Text>
      </Animated.View>

      {/* Header */}
      <View style={[styles.header, { paddingTop: Math.max(insets.top, Platform.OS === "ios" ? 59 : 32) }]}>
        <Text style={styles.logo}>jainune</Text>
        <View style={styles.headerRight}>
          <TouchableOpacity
            style={styles.arcadeBtn}
            onPress={() => setShowArcade(true)}
          >
            <Text style={styles.arcadeBtnText}>🎡 Arcade</Text>
          </TouchableOpacity>
          {isFetching && <ActivityIndicator size="small" color={colors.saffron} />}
        </View>
      </View>

      {/* Card stack */}
      <View style={styles.cardStack}>
        {stackEmpty || uiState === "empty" ? (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyEmoji}>✨</Text>
            <Text style={styles.emptyTitle}>You're All Caught Up!</Text>
            <Text style={styles.emptyDesc}>
              We've shown you all compatible profiles nearby. Expand your distance preference or check back later!
            </Text>
            <TouchableOpacity style={styles.retryBtn} onPress={fetchBatch}>
              <Text style={styles.retryBtnText}>Check for New Profiles</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.arcadePromoBtn}
              onPress={() => setShowArcade(true)}
            >
              <Text style={styles.arcadePromoBtnText}>🎡 Try Serendipity Arcade Wheel</Text>
            </TouchableOpacity>
          </View>
        ) : (
          // Render bottom card first (z-index), then top card
          [...visibleCards].reverse().map((candidate, i) => {
            const isTop = i === visibleCards.length - 1;
            return (
              <SwipeCard
                key={candidate.id}
                candidate={candidate}
                isTop={isTop}
                onSwipeRight={(totalMs, photoMs, promptMs) =>
                  isTop && handleSwipeRight(candidate, totalMs, photoMs, promptMs)
                }
                onSwipeLeft={(totalMs, photoMs, promptMs) =>
                  isTop && handleSwipeLeft(candidate, totalMs, photoMs, promptMs)
                }
                onSuperLike={(totalMs) => isTop && handleSuperLike(candidate, totalMs)}
              />
            );
          })
        )}
      </View>

      {/* Daily limit bottom sheet */}
      {dailyLimitReached && (
        <View style={styles.limitSheet}>
          <Text style={styles.limitTitle}>Cupid's Quiver is Empty for Today! 🏹</Text>
          <Text style={styles.limitDesc}>
            You've used all your daily complimentary connects. Recharge with Jainune+ or check back tomorrow!
          </Text>
          <View style={styles.limitBtns}>
            <TouchableOpacity
              style={[styles.limitBtn, styles.upgradeBtn]}
              onPress={() => navigation.navigate("Subscriptions")}
            >
              <Text style={styles.upgradeBtnText}>Upgrade to Jainune+</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.limitDismiss}
              onPress={() => setDailyLimitReached(false)}
            >
              <Text style={styles.limitDismissText}>Dismiss</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Match modal */}
      <MatchModal
        visible={!!match}
        match={match}
        candidate={matchCandidate}
        myPhotoUrl={myPhotoUrl}
        onOpenChat={openChat}
        onDismiss={() => { setMatch(null); setMatchCandidate(null); }}
      />

      {/* Serendipity Arcade modal */}
      <SerendipityArcadeModal
        visible={showArcade}
        onClose={() => setShowArcade(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.bg,
    padding: spacing.xxl,
  },
  loadingText: { ...typography.body, color: colors.mid, marginTop: spacing.md },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 56 : 32,
    paddingBottom: spacing.base,
  },
  logo: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 24,
    color: colors.saffron,
  },
  offlineBanner: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: colors.blueLight,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    zIndex: 100,
  },
  offlineBannerText: { ...typography.caption, color: colors.blue, textAlign: "center" },
  cardStack: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  emptyContainer: {
    alignItems: "center",
    paddingHorizontal: spacing.xxl,
  },
  emptyEmoji: { fontSize: 56, marginBottom: spacing.md },
  emptyTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 22,
    color: colors.dark,
    textAlign: "center",
    marginBottom: spacing.sm,
  },
  emptyDesc: {
    ...typography.body,
    color: colors.mid,
    textAlign: "center",
    lineHeight: 22,
    marginBottom: spacing.xl,
  },
  retryBtn: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.full,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  retryBtnText: { fontFamily: "Outfit_600SemiBold", color: colors.saffron, fontSize: 15 },
  limitSheet: {
    backgroundColor: colors.white,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    padding: spacing.xl,
    paddingBottom: spacing.xxl,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  limitTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 18,
    color: colors.dark,
    textAlign: "center",
    marginBottom: spacing.sm,
  },
  limitDesc: {
    ...typography.body,
    color: colors.mid,
    textAlign: "center",
    marginBottom: spacing.xl,
  },
  limitBtns: { flexDirection: "row", justifyContent: "center", gap: spacing.base },
  limitBtn: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xl,
    borderRadius: radii.full,
  },
  upgradeBtn: { backgroundColor: colors.saffron },
  upgradeBtnText: { fontFamily: "Outfit_700Bold", color: colors.white },
  limitDismiss: { paddingVertical: spacing.sm, paddingHorizontal: spacing.base },
  limitDismissText: { ...typography.bodySmall, color: colors.muted },
  headerRight: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  arcadeBtn: {
    backgroundColor: "rgba(255, 156, 74, 0.15)",
    paddingVertical: 5,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.full,
    borderWidth: 1,
    borderColor: "rgba(255, 156, 74, 0.3)",
  },
  arcadeBtnText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 12,
    color: colors.saffron,
  },
  arcadePromoBtn: {
    marginTop: spacing.base,
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  arcadePromoBtnText: {
    fontFamily: "Outfit_700Bold",
    color: colors.white,
    fontSize: 14,
  },
});
