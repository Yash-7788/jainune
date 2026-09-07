/**
 * Phase 6 — LikesScreen: Mutual Matches + Incoming Likes
 * Two tabs: "Matches" (mutual) | "Liked You" (incoming, blurred for free users)
 * GET /v1/interactions/matches → mutual matches
 * GET /v1/interactions/liked-me → incoming likes (blurred for free tier)
 * Tapping a match opens ChatScreen.
 * Tapping a blurred "liked you" card prompts upgrade.
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  RefreshControl,
  Platform,
} from "react-native";
import { useNavigation, useFocusEffect } from "@react-navigation/native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import { getLikes, getLikedMe, FeedCandidate } from "../../api/feedApi";
import { getSubscriptionStatus } from "../../api/profileApi";
import { extractError } from "../../api/client";

type Tab = "matches" | "liked_you";

interface MatchCard {
  id: string;
  first_name: string;
  age: number;
  city: string;
  photo_url?: string;
  chat_id?: string;
  matched_at?: string;
}

export default function LikesScreen() {
  const navigation = useNavigation<any>();
  const [tab, setTab] = useState<Tab>("matches");
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [likedMe, setLikedMe] = useState<MatchCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [isSubscriber, setIsSubscriber] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (!isRefresh) setLoading(true);
    setError(null);
    try {
      const [matchRes, likedRes, subRes] = await Promise.allSettled([
        getLikes(),
        getLikedMe(),
        getSubscriptionStatus(),
      ]);

      if (subRes.status === "fulfilled") {
        const s = subRes.value;
        setIsSubscriber(
          s.can_see_who_liked === true ||
            s.tier === "jainune_plus" ||
            s.tier === "plus" ||
            s.tier === "gold" ||
            s.tier === "platinum" ||
            s.is_active === true
        );
      }

      if (matchRes.status === "fulfilled") {
        const profiles = matchRes.value.profiles ?? [];
        setMatches(
          profiles.map((c: any) => ({
            id: c.id,
            first_name: c.first_name,
            age: c.age,
            city: c.city,
            photo_url: c.photos?.[0]?.url,
            chat_id: c.chat_id || c.id,
            matched_at: c.matched_at,
          }))
        );
      }

      if (likedRes.status === "fulfilled") {
        const likes = likedRes.value.likes ?? [];
        setLikedMe(
          likes.map((c: any) => ({
            id: c.id,
            first_name: c.first_name,
            age: c.age,
            city: c.city,
            photo_url: c.photos?.[0]?.url,
            matched_at: c.liked_at,
          }))
        );
      }
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load(true);
    }, [load])
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.saffron} />
      </View>
    );
  }

  const activeData = tab === "matches" ? matches : likedMe;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Likes & Matches</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        <TouchableOpacity
          style={[styles.tab, tab === "matches" && styles.tabActive]}
          onPress={() => setTab("matches")}
        >
          <Text style={[styles.tabText, tab === "matches" && styles.tabTextActive]}>
            Matches {matches.length > 0 && `(${matches.length})`}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, tab === "liked_you" && styles.tabActive]}
          onPress={() => setTab("liked_you")}
        >
          <Text style={[styles.tabText, tab === "liked_you" && styles.tabTextActive]}>
            Liked You {likedMe.length > 0 && `(${likedMe.length})`}
          </Text>
          {likedMe.length > 0 && !isSubscriber && <View style={styles.tabLockDot} />}
        </TouchableOpacity>
      </View>

      {/* Subscriber upgrade banner for liked-you tab */}
      {tab === "liked_you" && !isSubscriber && likedMe.length > 0 && (
        <View style={styles.upgradeBanner}>
          <Text style={styles.upgradeBannerText}>
            🔒 {likedMe.length} profile{likedMe.length > 1 ? "s" : ""} liked you! Upgrade to Gold to see who.
          </Text>
          <TouchableOpacity
            style={styles.upgradeBannerBtn}
            onPress={() => navigation.navigate("Subscriptions")}
          >
            <Text style={styles.upgradeBannerBtnText}>Upgrade</Text>
          </TouchableOpacity>
        </View>
      )}

      {error && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error.message}</Text>
          <TouchableOpacity onPress={() => load()}>
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

      <FlatList
        data={activeData}
        keyExtractor={(item) => item.id}
        numColumns={2}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); load(true); }}
            tintColor={colors.saffron}
          />
        }
        contentContainerStyle={
          activeData.length === 0 ? styles.emptyContainer : styles.grid
        }
        ListEmptyComponent={
          <View style={styles.emptyInner}>
            {tab === "matches" ? (
              <>
                <Text style={styles.emptyEmoji}>💑</Text>
                <Text style={styles.emptyTitle}>No Matches Yet</Text>
                <Text style={styles.emptyDesc}>
                  Keep swiping! When both of you like each other, you'll appear here.
                </Text>
              </>
            ) : (
              <>
                <Text style={styles.emptyEmoji}>👀</Text>
                <Text style={styles.emptyTitle}>No Likes Yet</Text>
                <Text style={styles.emptyDesc}>
                  Profiles that like you will appear here. Make sure your profile is complete!
                </Text>
              </>
            )}
          </View>
        }
        renderItem={({ item }) => {
          const isBlurred = tab === "liked_you" && !isSubscriber;

          return (
            <TouchableOpacity
              style={styles.card}
              onPress={() => {
                if (isBlurred) {
                  navigation.navigate("Subscriptions");
                  return;
                }
                if (tab === "matches") {
                  const targetChatId = item.chat_id || item.id;
                  navigation.navigate("Chat", {
                    matchId: targetChatId,
                    otherUser: {
                      id: item.id,
                      first_name: item.first_name,
                      photo_url: item.photo_url,
                    },
                  });
                }
              }}
              activeOpacity={0.8}
            >
              <View style={styles.cardImageWrap}>
                {item.photo_url ? (
                  <Image
                    source={{ uri: item.photo_url }}
                    style={[styles.cardImage, isBlurred && styles.cardImageBlurred]}
                    blurRadius={isBlurred ? 20 : 0}
                  />
                ) : (
                  <View style={[styles.cardImage, styles.cardImageFallback]}>
                    <Text style={styles.cardImageInitial}>
                      {isBlurred ? "?" : item.first_name?.[0]}
                    </Text>
                  </View>
                )}

                {isBlurred && (
                  <View style={styles.lockOverlay}>
                    <Text style={styles.lockIcon}>🔒</Text>
                  </View>
                )}

                {tab === "matches" && (
                  <View style={styles.matchBadge}>
                    <Text style={styles.matchBadgeText}>Match ❤️</Text>
                  </View>
                )}
              </View>

              <View style={styles.cardBody}>
                <Text style={styles.cardName} numberOfLines={1}>
                  {isBlurred ? "Someone" : `${item.first_name}, ${item.age}`}
                </Text>
                <Text style={styles.cardCity} numberOfLines={1}>
                  {isBlurred ? "···" : item.city}
                </Text>
              </View>
            </TouchableOpacity>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 56 : 24,
    paddingBottom: spacing.base,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { fontFamily: "Outfit_700Bold", fontSize: 22, color: colors.dark },
  tabs: {
    flexDirection: "row",
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  tab: {
    flex: 1,
    paddingVertical: spacing.md,
    alignItems: "center",
    position: "relative",
    flexDirection: "row",
    justifyContent: "center",
    gap: 4,
  },
  tabActive: {
    borderBottomWidth: 2.5,
    borderBottomColor: colors.pinkMid,
  },
  tabText: { fontFamily: "Inter_400Regular", fontSize: 14, color: colors.muted },
  tabTextActive: { fontFamily: "Outfit_700Bold", color: colors.dark },
  tabLockDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.pinkMid,
  },
  upgradeBanner: {
    backgroundColor: colors.pinkLight,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    gap: spacing.sm,
  },
  upgradeBannerText: { ...typography.bodySmall, color: colors.dark, flex: 1 },
  upgradeBannerBtn: {
    backgroundColor: colors.pinkMid,
    borderRadius: radii.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  upgradeBannerBtnText: { fontFamily: "Outfit_700Bold", fontSize: 13, color: colors.white },
  errorBanner: {
    backgroundColor: colors.redLight,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.base,
  },
  errorText: { ...typography.bodySmall, color: colors.red, flex: 1 },
  retryText: { fontFamily: "Outfit_700Bold", color: colors.red },
  grid: {
    padding: spacing.sm,
    paddingBottom: spacing.xxl,
  },
  emptyContainer: { flex: 1 },
  emptyInner: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xxl,
    paddingTop: 80,
  },
  emptyEmoji: { fontSize: 48, marginBottom: spacing.base },
  emptyTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 20,
    color: colors.dark,
    textAlign: "center",
    marginBottom: spacing.sm,
  },
  emptyDesc: {
    ...typography.body,
    color: colors.mid,
    textAlign: "center",
    lineHeight: 22,
  },
  card: {
    flex: 1,
    margin: spacing.xs,
    backgroundColor: colors.white,
    borderRadius: radii.lg,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 8,
    elevation: 3,
  },
  cardImageWrap: { position: "relative" },
  cardImage: {
    width: "100%",
    aspectRatio: 0.85,
    resizeMode: "cover",
    backgroundColor: colors.light,
  },
  cardImageBlurred: {},
  cardImageFallback: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.saffronLight,
  },
  cardImageInitial: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 40,
    color: colors.saffron,
  },
  lockOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.35)",
  },
  lockIcon: { fontSize: 32 },
  matchBadge: {
    position: "absolute",
    top: spacing.sm,
    left: spacing.sm,
    backgroundColor: colors.pinkMid,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  matchBadgeText: { fontFamily: "Outfit_700Bold", fontSize: 10, color: colors.white },
  cardBody: { padding: spacing.sm },
  cardName: { fontFamily: "Outfit_700Bold", fontSize: 14, color: colors.dark },
  cardCity: { ...typography.caption, color: colors.muted, marginTop: 2 },
});
