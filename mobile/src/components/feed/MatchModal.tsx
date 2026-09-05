/**
 * MatchModal — shown immediately on mutual match
 * Animated entrance: scale + fade in.
 * Shows both users' photos, first name, CTA to open chat.
 */

import React, { useEffect, useRef } from "react";
import {
  Modal,
  View,
  Text,
  Image,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Dimensions,
} from "react-native";
import { colors, spacing, radii, typography, shadows } from "../../theme/tokens";
import { InteractionResult, FeedCandidate } from "../../api/feedApi";

interface MatchModalProps {
  visible: boolean;
  match: InteractionResult | null;
  candidate: FeedCandidate | null;
  myPhotoUrl?: string;
  onOpenChat: (chatId: string) => void;
  onDismiss: () => void;
}

const { width } = Dimensions.get("window");

export default function MatchModal({
  visible,
  match,
  candidate,
  myPhotoUrl,
  onOpenChat,
  onDismiss,
}: MatchModalProps) {
  const scale = useRef(new Animated.Value(0.4)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(scale, {
          toValue: 1,
          friction: 6,
          tension: 60,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 250,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      scale.setValue(0.4);
      opacity.setValue(0);
    }
  }, [visible]);

  if (!match || !candidate) return null;

  const momentumHours = match.momentum_window_hours ?? 24;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      statusBarTranslucent
      onRequestClose={onDismiss}
    >
      <View style={styles.backdrop}>
        <Animated.View style={[styles.card, { transform: [{ scale }], opacity }]}>
          {/* Confetti-like decorative line */}
          <View style={styles.topAccent} />

          <Text style={styles.headline}>It's a Match! 🎉</Text>
          <Text style={styles.sub}>
            You and {candidate.first_name} both said yes!
          </Text>

          {/* Avatar pair */}
          <View style={styles.avatarRow}>
            <View style={styles.avatarWrap}>
              {myPhotoUrl ? (
                <Image source={{ uri: myPhotoUrl }} style={styles.avatar} />
              ) : (
                <View style={[styles.avatar, styles.avatarFallback]}>
                  <Text style={styles.avatarInitial}>Me</Text>
                </View>
              )}
            </View>

            <View style={styles.heartBadge}>
              <Text style={styles.heartBadgeText}>♥</Text>
            </View>

            <View style={styles.avatarWrap}>
              {candidate.photos?.[0] ? (
                <Image source={{ uri: candidate.photos[0].url }} style={styles.avatar} />
              ) : (
                <View style={[styles.avatar, styles.avatarFallbackOther]}>
                  <Text style={styles.avatarInitial}>{candidate.first_name?.[0]}</Text>
                </View>
              )}
            </View>
          </View>

          {/* Momentum window reminder */}
          <View style={styles.momentumBanner}>
            <Text style={styles.momentumText}>
              ⚡ Send a message within {momentumHours}h to keep the spark alive!
            </Text>
          </View>

          <TouchableOpacity
            style={styles.chatBtn}
            onPress={() => match.chat_id && onOpenChat(match.chat_id)}
          >
            <Text style={styles.chatBtnText}>Start the Conversation 💬</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.dismissBtn} onPress={onDismiss}>
            <Text style={styles.dismissBtnText}>Keep browsing</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.65)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xxl,
  },
  card: {
    width: "100%",
    backgroundColor: colors.white,
    borderRadius: radii.xl,
    overflow: "hidden",
    alignItems: "center",
    ...shadows.card,
    paddingBottom: spacing.xxl,
  },
  topAccent: {
    width: "100%",
    height: 6,
    backgroundColor: colors.pinkMid,
    marginBottom: spacing.xl,
  },
  headline: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 28,
    color: colors.dark,
    textAlign: "center",
    marginBottom: spacing.xs,
  },
  sub: {
    ...typography.body,
    color: colors.mid,
    textAlign: "center",
    marginBottom: spacing.xxl,
    paddingHorizontal: spacing.base,
  },
  avatarRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xl,
  },
  avatarWrap: {
    ...shadows.heart,
  },
  avatar: {
    width: 100,
    height: 100,
    borderRadius: 50,
    borderWidth: 3,
    borderColor: colors.pinkMid,
  },
  avatarFallback: {
    backgroundColor: colors.saffronLight,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarFallbackOther: {
    backgroundColor: colors.pinkLight,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarInitial: {
    fontFamily: "Outfit_700Bold",
    fontSize: 32,
    color: colors.saffron,
  },
  heartBadge: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.pinkMid,
    alignItems: "center",
    justifyContent: "center",
    marginHorizontal: -8,
    zIndex: 10,
    ...shadows.heart,
  },
  heartBadgeText: { fontSize: 18, color: colors.white },
  momentumBanner: {
    backgroundColor: colors.blueLight,
    borderRadius: radii.md,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    marginHorizontal: spacing.base,
    marginBottom: spacing.xl,
  },
  momentumText: {
    ...typography.bodySmall,
    color: colors.blue,
    textAlign: "center",
    fontFamily: "Inter_400Regular",
  },
  chatBtn: {
    backgroundColor: colors.pinkMid,
    borderRadius: radii.full,
    paddingHorizontal: spacing.xxl,
    paddingVertical: spacing.md,
    marginHorizontal: spacing.base,
    width: "85%",
    alignItems: "center",
    ...shadows.button,
    marginBottom: spacing.md,
  },
  chatBtnText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    color: colors.white,
  },
  dismissBtn: {
    paddingVertical: spacing.sm,
  },
  dismissBtnText: {
    ...typography.bodySmall,
    color: colors.muted,
    textDecorationLine: "underline",
  },
});
