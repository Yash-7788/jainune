/**
 * Phase 5 — ChatScreen
 * Full real-time chat using WebSocket via single-use ticket.
 * - POST /v1/ws/ticket → wss://api.jainune.com/v1/ws/chat/{match_id}?ticket={ticket}
 * - Cursor-paginated message history (GET /v1/chats/:match_id/messages)
 * - Auto mark-read on focus (PUT /v1/chats/:match_id/read)
 * - Read receipts: incoming WS events update message.is_read
 * - Client-side PII moderation (ContentModerationSheet)
 * - Report / Block via bottom action sheet
 * - Momentum countdown banner
 * - Blocked chat: disabled input bar with banner
 * - 5 UI states: loading | populated | empty (no msgs) | error | chat_not_allowed
 */

import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from "react";
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Image,
  Alert,
  ActionSheetIOS,
} from "react-native";
import { useNavigation, useRoute } from "@react-navigation/native";
import * as SecureStore from "expo-secure-store";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  getMessages,
  sendMessage,
  sendMediaMessage,
  markRead,
  getWsTicket,
  reportMessage,
  blockUser,
  Message,
} from "../../api/chatApi";
import { getSubscriptionStatus } from "../../api/profileApi";
import { extractError } from "../../api/client";
import { MAX_MESSAGE_LENGTH } from "../../security/inputValidation";
import ContentModerationSheet, {
  scanMessage,
  DetectedType,
} from "../../components/chat/ContentModerationSheet";

const WS_BASE = "wss://api.jainune.com/v1/ws/chat";

interface RouteParams {
  matchId: string;
  otherUser: {
    id: string;
    first_name: string;
    photo_url?: string | null;
    is_online?: boolean;
    momentum_expires_at?: string | null;
  };
  momentumExpiresAt?: string | null;
}

export default function ChatScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute();
  const { matchId, otherUser } = route.params as RouteParams;

  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [chatBlocked, setChatBlocked] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [isOnline, setIsOnline] = useState(otherUser.is_online ?? false);

  // Moderation
  const [pendingContent, setPendingContent] = useState<string | null>(null);
  const [detectedType, setDetectedType] = useState<DetectedType>(null);
  const [isSubscriber, setIsSubscriber] = useState(false);

  // WebSocket connection & resilience
  const ws = useRef<WebSocket | null>(null);
  const pingInterval = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const lastMarkReadTime = useRef(0);

  // Cursor pagination
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const listRef = useRef<FlatList>(null);
  const myUserId = useRef<string | null>(null);

  // Momentum countdown
  const momentumExpiry = route.params.momentumExpiresAt || route.params.otherUser.momentum_expires_at;
  const [hoursLeft, setHoursLeft] = useState<number | null>(null);

  useEffect(() => {
    if (!momentumExpiry) return;
    const calculateTime = () => {
      const diff = new Date(momentumExpiry).getTime() - Date.now();
      if (diff > 0) {
        setHoursLeft(Math.max(1, Math.ceil(diff / (1000 * 60 * 60))));
      } else {
        setHoursLeft(0);
      }
    };
    calculateTime();
    const interval = setInterval(calculateTime, 60000);
    return () => clearInterval(interval);
  }, [momentumExpiry]);

  // Load my user ID and subscription status
  useEffect(() => {
    SecureStore.getItemAsync("jainune_user_id").then((id) => {
      myUserId.current = id;
    });
    getSubscriptionStatus()
      .then((sub) => {
        setIsSubscriber(sub.tier === "plus" && sub.status === "active");
      })
      .catch(() => {});
  }, []);

  // Throttled mark-as-read to avoid hammering server on rapid incoming messages
  const triggerMarkRead = useCallback(() => {
    const now = Date.now();
    if (now - lastMarkReadTime.current > 4000) {
      lastMarkReadTime.current = now;
      markRead(matchId).catch(() => {});
    }
  }, [matchId]);

  // Load message history
  const loadMessages = useCallback(async (cursorParam?: string) => {
    try {
      const msgs = await getMessages(matchId, cursorParam);
      if (msgs.length < 30) setHasMore(false);
      if (cursorParam) {
        setMessages((prev) => [...msgs, ...prev]);
      } else {
        setMessages(msgs);
        setTimeout(() => listRef.current?.scrollToEnd({ animated: false }), 100);
      }
      if (msgs.length > 0) {
        setCursor(msgs[0].id);
      }
    } catch (err: any) {
      const e = err?._apiError;
      if (e?.code === "CHAT_NOT_ALLOWED") {
        setChatBlocked(true);
      } else {
        setError(extractError(err));
      }
    } finally {
      setLoading(false);
    }
  }, [matchId]);

  // WebSocket connection with clean teardown, exponential backoff, and max 5 attempts
  const connectWebSocket = useCallback(async () => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    if (ws.current) {
      ws.current.onopen = null;
      ws.current.onmessage = null;
      ws.current.onerror = null;
      ws.current.onclose = null;
      try {
        ws.current.close();
      } catch {}
      ws.current = null;
    }

    try {
      const ticket = await getWsTicket();
      const url = `${WS_BASE}/${matchId}?ticket=${ticket}`;
      const socket = new WebSocket(url);

      socket.onopen = () => {
        reconnectAttempts.current = 0;
        setWsConnected(true);
        if (pingInterval.current) clearInterval(pingInterval.current);
        pingInterval.current = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            try {
              socket.send(JSON.stringify({ type: "ping" }));
            } catch {}
          }
        }, 25000);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleWsEvent(data);
        } catch {}
      };

      const handleDisconnect = () => {
        if (pingInterval.current) {
          clearInterval(pingInterval.current);
          pingInterval.current = null;
        }
        setWsConnected(false);
        if (reconnectAttempts.current < 5) {
          const delay = Math.min(20000, 2000 * Math.pow(1.5, reconnectAttempts.current));
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(connectWebSocket, delay);
        }
      };

      socket.onerror = handleDisconnect;
      socket.onclose = (e) => {
        if (pingInterval.current) {
          clearInterval(pingInterval.current);
          pingInterval.current = null;
        }
        if (e.code !== 1000) {
          handleDisconnect();
        } else {
          setWsConnected(false);
        }
      };

      ws.current = socket;
    } catch {
      setWsConnected(false);
      if (reconnectAttempts.current < 5) {
        const delay = Math.min(20000, 2000 * Math.pow(1.5, reconnectAttempts.current));
        reconnectAttempts.current += 1;
        reconnectTimer.current = setTimeout(connectWebSocket, delay);
      }
    }
  }, [matchId]);

  useEffect(() => {
    loadMessages();
    triggerMarkRead();
    connectWebSocket();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (pingInterval.current) {
        clearInterval(pingInterval.current);
        pingInterval.current = null;
      }
      if (ws.current) {
        ws.current.onopen = null;
        ws.current.onmessage = null;
        ws.current.onerror = null;
        ws.current.onclose = null;
        try {
          ws.current.close();
        } catch {}
        ws.current = null;
      }
    };
  }, []);

  const handleWsEvent = (data: {
    type: string;
    message?: any;
    payload?: any;
    message_id?: string;
    user_id?: string;
  }) => {
    switch (data.type) {
      case "message":
      case "new_message": {
        const p = data.payload || data.message;
        if (p) {
          const incoming: Message = {
            id: String(p.id),
            match_id: String(p.chat_id || matchId),
            sender_id: String(p.sender_id),
            type: (p.message_type === "photo" || p.type === "photo") ? "photo" : (p.message_type === "voice" || p.type === "voice") ? "voice" : "text",
            content: p.content || null,
            media_url: p.media_url || null,
            is_read: Boolean(p.is_read),
            created_at: p.created_at || new Date().toISOString(),
          };
          setMessages((prev) => {
            const withoutTemp = prev.filter(
              (m) => !(m.id.startsWith("temp_") && m.content === incoming.content && m.sender_id === incoming.sender_id)
            );
            if (withoutTemp.some((m) => m.id === incoming.id)) return prev;
            return [...withoutTemp, incoming];
          });
          triggerMarkRead();
          setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
        }
        break;
      }
      case "read_receipt":
      case "message_read": {
        const targetId = data.payload?.message_id || data.message_id;
        if (targetId) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === targetId ? { ...m, is_read: true } : m
            )
          );
        } else {
          setMessages((prev) => prev.map((m) => ({ ...m, is_read: true })));
        }
        break;
      }
      case "user_online": {
        const uid = data.payload?.user_id || data.user_id;
        if (uid === otherUser.id) setIsOnline(true);
        break;
      }
      case "user_offline": {
        const uid = data.payload?.user_id || data.user_id;
        if (uid === otherUser.id) setIsOnline(false);
        break;
      }
    }
  };

  const sendDraft = useCallback(async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || trimmed.length > MAX_MESSAGE_LENGTH) return;

    // Client-side moderation check using canonical patterns
    const detected = scanMessage(trimmed);
    if (detected) {
      setPendingContent(trimmed);
      setDetectedType(detected);
      return;
    }

    await dispatchSend(trimmed);
  }, []);

  const dispatchSend = useCallback(async (content: string) => {
    setSending(true);
    setDraft("");
    setPendingContent(null);
    setDetectedType(null);

    // Optimistic: add a local pending message
    const tempId = `temp_${Date.now()}`;
    const tempMsg: Message = {
      id: tempId,
      match_id: matchId,
      sender_id: myUserId.current ?? "",
      type: "text",
      content,
      media_url: null,
      is_read: false,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempMsg]);
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);

    try {
      const sent = await sendMessage(matchId, content);
      setMessages((prev) => prev.map((m) => (m.id === tempId ? sent : m)));
    } catch (err: any) {
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
      const e = err?._apiError;
      if (e?.code === "CHAT_NOT_ALLOWED") {
        setChatBlocked(true);
      }
      Alert.alert("Unable to send message", extractError(err).message);
    } finally {
      setSending(false);
    }
  }, [matchId]);

  const handleReport = useCallback(() => {
    const options = ["Harassment", "Fake Profile", "Inappropriate Content", "Spam", "Cancel"];
    if (Platform.OS === "ios") {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex: 4, destructiveButtonIndex: [0, 1, 2, 3], title: "Report this conversation" },
        (idx) => {
          if (idx < 4) {
            reportMessage(otherUser.id, options[idx]).catch(() => {});
            Alert.alert("Report Submitted", "Our team will review this within 24 hours.");
          }
        }
      );
    } else {
      Alert.alert("Report User", "Choose a reason:", [
        { text: "Harassment", onPress: () => reportMessage(otherUser.id, "Harassment").catch(() => {}) },
        { text: "Fake Profile", onPress: () => reportMessage(otherUser.id, "Fake Profile").catch(() => {}) },
        { text: "Inappropriate Content", onPress: () => reportMessage(otherUser.id, "Inappropriate Content").catch(() => {}) },
        { text: "Spam", onPress: () => reportMessage(otherUser.id, "Spam").catch(() => {}) },
        { text: "Cancel", style: "cancel" },
      ]);
    }
  }, [otherUser.id]);

  const handleBlock = useCallback(() => {
    Alert.alert(
      "Block User",
      `Block ${otherUser.first_name}? They won't be able to contact you and will be removed from your matches.`,
      [
        {
          text: "Block",
          style: "destructive",
          onPress: async () => {
            try {
              await blockUser(otherUser.id);
              navigation.goBack();
            } catch {}
          },
        },
        { text: "Cancel", style: "cancel" },
      ]
    );
  }, [otherUser]);

  const loadOlderMessages = useCallback(async () => {
    if (!hasMore || loadingMore || !cursor) return;
    setLoadingMore(true);
    try {
      const msgs = await getMessages(matchId, cursor);
      if (msgs.length < 30) setHasMore(false);
      setMessages((prev) => [...msgs, ...prev]);
      if (msgs.length > 0) setCursor(msgs[0].id);
    } catch {}
    setLoadingMore(false);
  }, [hasMore, loadingMore, cursor, matchId]);

  // ── Render message bubble ───────────────────────────────────────────────────

  const renderMessage = useCallback(
    ({ item }: { item: Message }) => {
      const isMe = item.sender_id === myUserId.current;
      const isTemp = item.id.startsWith("temp_");

      return (
        <View style={[styles.msgRow, isMe ? styles.msgRowMe : styles.msgRowOther]}>
          {!isMe && otherUser.photo_url && (
            <Image source={{ uri: otherUser.photo_url }} style={styles.msgAvatar} />
          )}
          <View style={[styles.bubble, isMe ? styles.bubbleMe : styles.bubbleOther]}>
            <Text style={[styles.bubbleText, isMe ? styles.bubbleTextMe : styles.bubbleTextOther]}>
              {item.content}
            </Text>
            <View style={styles.bubbleMeta}>
              <Text style={styles.bubbleTime}>
                {new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </Text>
              {isMe && (
                <Text style={styles.readReceipt}>
                  {isTemp ? "·" : item.is_read ? "✓✓" : "✓"}
                </Text>
              )}
            </View>
          </View>
        </View>
      );
    },
    [otherUser.photo_url]
  );

  // ── Loading state ────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.saffron} />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backBtnText}>‹</Text>
        </TouchableOpacity>
        {otherUser.photo_url ? (
          <Image source={{ uri: otherUser.photo_url }} style={styles.headerAvatar} />
        ) : (
          <View style={[styles.headerAvatar, styles.headerAvatarFallback]}>
            <Text style={styles.headerAvatarInitial}>{otherUser.first_name?.[0]}</Text>
          </View>
        )}
        <View style={styles.headerInfo}>
          <Text style={styles.headerName}>{otherUser.first_name}</Text>
          <View style={styles.onlineRow}>
            <View style={[styles.onlineDot, { backgroundColor: isOnline ? colors.green : colors.border }]} />
            <Text style={styles.onlineText}>{isOnline ? "Online" : "Offline"}</Text>
          </View>
        </View>
        <TouchableOpacity
          style={styles.moreBtn}
          onPress={() => {
            Alert.alert(otherUser.first_name, undefined, [
              { text: "Report", onPress: handleReport },
              { text: "Block", style: "destructive", onPress: handleBlock },
              { text: "Cancel", style: "cancel" },
            ]);
          }}
        >
          <Text style={styles.moreBtnText}>⋯</Text>
        </TouchableOpacity>
      </View>

      {/* Momentum countdown banner */}
      {hoursLeft !== null && hoursLeft > 0 && !chatBlocked && (
        <View style={styles.momentumBanner}>
          <Text style={styles.momentumText}>
            ⚡ Momentum: {hoursLeft}h remaining to keep this spark active!
          </Text>
        </View>
      )}

      {/* Disconnected banner with manual reconnect */}
      {!wsConnected && !chatBlocked && (
        <TouchableOpacity
          style={styles.reconnectBanner}
          onPress={() => {
            reconnectAttempts.current = 0;
            connectWebSocket();
          }}
        >
          <Text style={styles.reconnectText}>
            Chat disconnected. Tap to reconnect 🔄
          </Text>
        </TouchableOpacity>
      )}

      {/* Chat blocked banner */}
      {chatBlocked && (
        <View style={styles.blockedBanner}>
          <Text style={styles.blockedText}>
            Silence is Golden 🤫 — This conversation is taking a pause or is no longer active.
          </Text>
        </View>
      )}

      {/* Error state */}
      {error && !chatBlocked && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error.message}</Text>
        </View>
      )}

      {/* Message list */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={renderMessage}
        maxToRenderPerBatch={10}
        windowSize={5}
        initialNumToRender={15}
        removeClippedSubviews={Platform.OS === "android"}
        contentContainerStyle={styles.list}
        onEndReached={loadOlderMessages}
        onEndReachedThreshold={0.1}
        ListHeaderComponent={
          loadingMore ? <ActivityIndicator size="small" color={colors.saffron} style={{ margin: spacing.base }} /> : null
        }
        ListEmptyComponent={
          !loading ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyEmoji}>💬</Text>
              <Text style={styles.emptyTitle}>Start the Conversation!</Text>
              <Text style={styles.emptyDesc}>
                Say something warm to {otherUser.first_name}. Authentic openings get the best responses!
              </Text>
            </View>
          ) : null
        }
        inverted={false}
      />

      {/* Input bar */}
      <View style={[styles.inputBar, chatBlocked && styles.inputBarDisabled]}>
        {!chatBlocked && (
          <TouchableOpacity
            style={styles.mediaBtn}
            onPress={() => {
              Alert.alert("Send Media", "Choose attachment type:", [
                {
                  text: "Voice Spark (60s) 🎙️",
                  onPress: () => {
                    if (!isSubscriber) {
                      Alert.alert(
                        "Jainune+ Feature",
                        "Voice Sparks are exclusive to Jainune+ members.",
                        [
                          { text: "Cancel", style: "cancel" },
                          { text: "Upgrade", onPress: () => navigation.navigate("Subscriptions") },
                        ]
                      );
                      return;
                    }
                    Alert.alert("Voice Spark", "Recording feature initialized.");
                  },
                },
                {
                  text: "Photo 📷",
                  onPress: () => {
                    Alert.alert("Photo Sharing", "Select photo from library.");
                  },
                },
                { text: "Cancel", style: "cancel" },
              ]);
            }}
          >
            <Text style={styles.mediaBtnText}>＋</Text>
          </TouchableOpacity>
        )}
        <TextInput
          style={styles.input}
          value={draft}
          onChangeText={(t) => t.length <= MAX_MESSAGE_LENGTH && setDraft(t)}
          placeholder={chatBlocked ? "This conversation is no longer active" : "Type a message..."}
          placeholderTextColor={colors.muted}
          multiline
          maxLength={MAX_MESSAGE_LENGTH}
          editable={!chatBlocked && !sending}
          returnKeyType="default"
        />
        {!chatBlocked && (
          <TouchableOpacity
            style={[styles.sendBtn, (!draft.trim() || sending) && styles.sendBtnDisabled]}
            onPress={() => sendDraft(draft)}
            disabled={!draft.trim() || sending}
          >
            {sending ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <Text style={styles.sendBtnText}>↑</Text>
            )}
          </TouchableOpacity>
        )}
      </View>

      {/* Content moderation sheet */}
      <ContentModerationSheet
        visible={!!detectedType}
        detectedType={detectedType}
        isSubscriber={isSubscriber}
        onProceed={() => pendingContent && dispatchSend(pendingContent)}
        onCancel={() => {
          setDetectedType(null);
          setPendingContent(null);
        }}
        onUpgrade={() => {
          setDetectedType(null);
          setPendingContent(null);
          navigation.navigate("Subscriptions");
        }}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 52 : 20,
    paddingBottom: spacing.base,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    gap: spacing.sm,
  },
  backBtn: { padding: spacing.xs },
  backBtnText: { fontSize: 28, color: colors.dark, lineHeight: 32 },
  headerAvatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  headerAvatarFallback: {
    backgroundColor: colors.saffronLight,
    alignItems: "center",
    justifyContent: "center",
  },
  headerAvatarInitial: { fontFamily: "Outfit_700Bold", color: colors.saffron, fontSize: 16 },
  headerInfo: { flex: 1 },
  headerName: { fontFamily: "Outfit_700Bold", fontSize: 16, color: colors.dark },
  onlineRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  onlineDot: { width: 6, height: 6, borderRadius: 3 },
  onlineText: { ...typography.caption, color: colors.muted },
  moreBtn: { padding: spacing.sm },
  moreBtnText: { fontSize: 22, color: colors.mid, letterSpacing: 1 },
  blockedBanner: {
    backgroundColor: colors.light,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  blockedText: { ...typography.bodySmall, color: colors.muted, textAlign: "center" },
  errorBanner: {
    backgroundColor: colors.redLight,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
  },
  errorText: { ...typography.bodySmall, color: colors.red, textAlign: "center" },
  list: {
    padding: spacing.base,
    paddingBottom: spacing.xl,
  },
  msgRow: {
    flexDirection: "row",
    marginBottom: spacing.sm,
    alignItems: "flex-end",
    gap: spacing.xs,
  },
  msgRowMe: { justifyContent: "flex-end" },
  msgRowOther: { justifyContent: "flex-start" },
  msgAvatar: { width: 28, height: 28, borderRadius: 14 },
  bubble: {
    maxWidth: "72%",
    borderRadius: radii.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  bubbleMe: {
    backgroundColor: colors.pinkMid,
    borderBottomRightRadius: radii.xs,
  },
  bubbleOther: {
    backgroundColor: colors.white,
    borderBottomLeftRadius: radii.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  bubbleText: { fontSize: 15, lineHeight: 21 },
  bubbleTextMe: { color: colors.white, fontFamily: "Inter_400Regular" },
  bubbleTextOther: { color: colors.dark, fontFamily: "Inter_400Regular" },
  bubbleMeta: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 4,
    marginTop: 2,
  },
  bubbleTime: {
    fontSize: 10,
    color: "rgba(255,255,255,0.7)",
    fontFamily: "Inter_400Regular",
  },
  readReceipt: { fontSize: 10, color: "rgba(255,255,255,0.7)" },
  emptyState: {
    alignItems: "center",
    paddingTop: 80,
    paddingHorizontal: spacing.xxl,
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
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    padding: spacing.sm,
    backgroundColor: colors.white,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.sm,
    paddingBottom: Platform.OS === "ios" ? spacing.xl : spacing.sm,
  },
  inputBarDisabled: { opacity: 0.5 },
  input: {
    flex: 1,
    backgroundColor: colors.light,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    fontSize: 15,
    fontFamily: "Inter_400Regular",
    color: colors.dark,
    maxHeight: 100,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.pinkMid,
    alignItems: "center",
    justifyContent: "center",
  },
  sendBtnDisabled: { backgroundColor: colors.border },
  sendBtnText: { fontSize: 18, color: colors.white, fontWeight: "700" },
  mediaBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.light,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  mediaBtnText: { fontSize: 20, color: colors.mid, fontWeight: "600" },
  momentumBanner: {
    backgroundColor: "rgba(255, 156, 74, 0.15)",
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 156, 74, 0.3)",
    alignItems: "center",
  },
  momentumText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 12,
    color: colors.saffron,
  },
  reconnectBanner: {
    backgroundColor: "rgba(239, 68, 68, 0.15)",
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(239, 68, 68, 0.3)",
    alignItems: "center",
  },
  reconnectText: {
    fontFamily: "Inter_700Bold",
    fontSize: 12,
    color: colors.red,
  },
});
