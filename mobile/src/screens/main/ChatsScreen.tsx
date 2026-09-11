/**
 * Phase 5 — ChatsScreen: conversation thread list
 * GET /v1/chats — ChatThread[]
 * Unread badge, momentum expiry countdown, online dot, pull-to-refresh.
 * 5 UI states: loading | populated | empty | error | offline
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
import { getChats, ChatThread } from "../../api/chatApi";
import { extractError } from "../../api/client";

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffHrs = diffMs / 3600000;
  if (diffHrs < 1) return `${Math.floor(diffMs / 60000)}m`;
  if (diffHrs < 24) return `${Math.floor(diffHrs)}h`;
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

function getMomentumLabel(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const msLeft = new Date(expiresAt).getTime() - Date.now();
  if (msLeft <= 0) return null;
  const hLeft = Math.ceil(msLeft / 3600000);
  return `⚡ ${hLeft}h left`;
}

export default function ChatsScreen() {
  const navigation = useNavigation<any>();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (!isRefresh) setLoading(true);
    setError(null);
    try {
      const data = await getChats();
      // Sort: unread first, then by last message time
      const sorted = [...data].sort((a, b) => {
        if (a.unread_count > 0 && b.unread_count === 0) return -1;
        if (b.unread_count > 0 && a.unread_count === 0) return 1;
        const aTime = a.last_message?.created_at ?? "";
        const bTime = b.last_message?.created_at ?? "";
        return bTime.localeCompare(aTime);
      });
      setThreads(sorted);
    } catch (err: any) {
      setError(extractError(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

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

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyTitle}>Our Servers Need a Chai Break ☕</Text>
        <Text style={styles.emptyDesc}>{error.message}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={() => load()}>
          <Text style={styles.retryBtnText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const renderItem = useCallback(
    ({ item }: { item: ChatThread }) => {
      const momentum = getMomentumLabel(item.momentum_expires_at);
      const lastMsg = item.last_message;

      return (
        <TouchableOpacity
          style={[styles.thread, item.unread_count > 0 && styles.threadUnread]}
          onPress={() =>
            navigation.navigate("Chat", {
              matchId: item.match_id,
              otherUser: {
                id: item.other_user.id,
                first_name: item.other_user.first_name,
                photo_url: item.other_user.photo_url,
                is_online: item.other_user.is_online,
              },
            })
          }
          activeOpacity={0.7}
        >
          {/* Avatar */}
          <View style={styles.avatarWrap}>
            {item.other_user.photo_url ? (
              <Image source={{ uri: item.other_user.photo_url }} style={styles.avatar} />
            ) : (
              <View style={[styles.avatar, styles.avatarFallback]}>
                <Text style={styles.avatarInitial}>{item.other_user.first_name?.[0]}</Text>
              </View>
            )}
            {item.other_user.is_online && <View style={styles.onlineDot} />}
          </View>

          {/* Content */}
          <View style={styles.threadContent}>
            <View style={styles.threadTop}>
              <Text style={[styles.threadName, item.unread_count > 0 && styles.threadNameBold]}>
                {item.other_user.first_name}
              </Text>
              <View style={styles.threadTopRight}>
                {momentum && (
                  <View style={styles.momentumPill}>
                    <Text style={styles.momentumText}>{momentum}</Text>
                  </View>
                )}
                {lastMsg && (
                  <Text style={styles.threadTime}>{formatTime(lastMsg.created_at)}</Text>
                )}
              </View>
            </View>

            <View style={styles.threadBottom}>
              <Text
                style={[styles.lastMsg, item.unread_count > 0 && styles.lastMsgBold]}
                numberOfLines={1}
              >
                {lastMsg?.content ?? "Tap to start chatting!"}
              </Text>
              {item.unread_count > 0 && (
                <View style={styles.unreadBadge}>
                  <Text style={styles.unreadBadgeText}>
                    {item.unread_count > 99 ? "99+" : item.unread_count}
                  </Text>
                </View>
              )}
            </View>
          </View>
        </TouchableOpacity>
      );
    },
    [navigation]
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Chats</Text>
      </View>

      <FlatList
        data={threads}
        keyExtractor={(item) => item.match_id}
        maxToRenderPerBatch={10}
        windowSize={5}
        initialNumToRender={10}
        getItemLayout={(_, index) => ({ length: 77, offset: 77 * index, index })}
        removeClippedSubviews={Platform.OS === "android"}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); load(true); }}
            tintColor={colors.saffron}
          />
        }
        contentContainerStyle={threads.length === 0 ? styles.emptyContainer : { paddingBottom: spacing.xxl }}
        ListEmptyComponent={
          <View style={styles.emptyInner}>
            <Text style={styles.emptyEmoji}>💌</Text>
            <Text style={styles.emptyTitle}>No Conversations Yet</Text>
            <Text style={styles.emptyDesc}>
              Start liking profiles! When it's a match, you can chat here.
            </Text>
          </View>
        }
        renderItem={renderItem}
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
  header: {
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 56 : 24,
    paddingBottom: spacing.base,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 22,
    color: colors.dark,
  },
  emptyContainer: { flex: 1 },
  emptyInner: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xxl,
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
    marginBottom: spacing.xl,
  },
  retryBtn: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.full,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  retryBtnText: { fontFamily: "Outfit_600SemiBold", color: colors.saffron },
  thread: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    gap: spacing.md,
  },
  threadUnread: { backgroundColor: colors.saffronLight + "33" },
  avatarWrap: { position: "relative" },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  avatarFallback: {
    backgroundColor: colors.saffronLight,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarInitial: { fontFamily: "Outfit_700Bold", fontSize: 20, color: colors.saffron },
  onlineDot: {
    position: "absolute",
    bottom: 1,
    right: 1,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.green,
    borderWidth: 2,
    borderColor: colors.white,
  },
  threadContent: { flex: 1 },
  threadTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  threadName: { fontFamily: "Inter_400Regular", fontSize: 15, color: colors.dark },
  threadNameBold: { fontFamily: "Inter_700Bold" },
  threadTopRight: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  momentumPill: {
    backgroundColor: colors.blueLight,
    borderRadius: radii.full,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
  },
  momentumText: { ...typography.caption, color: colors.blue, fontSize: 10 },
  threadTime: { ...typography.caption, color: colors.muted, fontSize: 11 },
  threadBottom: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  lastMsg: { ...typography.bodySmall, color: colors.muted, flex: 1 },
  lastMsgBold: { fontFamily: "Inter_700Bold", color: colors.dark },
  unreadBadge: {
    backgroundColor: colors.pinkMid,
    borderRadius: radii.full,
    minWidth: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 5,
  },
  unreadBadgeText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 11,
    color: colors.white,
  },
});
