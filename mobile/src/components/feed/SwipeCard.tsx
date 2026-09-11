/**
 * SwipeCard — Animated swipe card with dwell tracking
 * Phase 4: PanResponder-based swipe (no external dep needed).
 * Tracks per-photo dwell time for telemetry.
 * Swipe right = like, left = pass.
 */

import React, { useRef, useState, useEffect, useCallback } from "react";
import {
  Animated,
  PanResponder,
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Dimensions,
  Platform,
} from "react-native";
import { Image } from "expo-image";
import { colors, spacing, radii, typography, shadows } from "../../theme/tokens";
import { FeedCandidate } from "../../api/feedApi";

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");
const SWIPE_THRESHOLD = SCREEN_WIDTH * 0.35;
const SWIPE_OUT_DURATION = 250;
const ROTATE_DEGREE = "15deg";

interface SwipeCardProps {
  candidate: FeedCandidate;
  isTop: boolean;
  onSwipeRight: (dwellMs: number, photoDwellMs: number, promptDwellMs: number) => void;
  onSwipeLeft: (dwellMs: number, photoDwellMs: number, promptDwellMs: number) => void;
  onSuperLike?: (dwellMs: number) => void;
}

function SwipeCard({
  candidate,
  isTop,
  onSwipeRight,
  onSwipeLeft,
  onSuperLike,
}: SwipeCardProps) {
  const position = useRef(new Animated.ValueXY()).current;
  const [photoIndex, setPhotoIndex] = useState(0);
  const [swipeDirection, setSwipeDirection] = useState<"left" | "right" | "up" | null>(null);
  const swipeDirectionRef = useRef<"left" | "right" | "up" | null>(null);

  // Dwell tracking
  const cardOpenTime = useRef(Date.now());
  const photoDwellStart = useRef(Date.now());
  const photoDwellAccum = useRef(0);
  const promptDwellAccum = useRef(0);
  const promptOpenTime = useRef<number | null>(null);

  useEffect(() => {
    cardOpenTime.current = Date.now();
    photoDwellStart.current = Date.now();
  }, []);

  const flushPhotoDwell = useCallback(() => {
    photoDwellAccum.current += Date.now() - photoDwellStart.current;
    photoDwellStart.current = Date.now();
  }, []);

  const handlePhotoChange = (idx: number) => {
    flushPhotoDwell();
    setPhotoIndex(idx);
  };

  const getDwellTimes = () => {
    flushPhotoDwell();
    const total = Date.now() - cardOpenTime.current;
    const photo = photoDwellAccum.current;
    const prompt = promptDwellAccum.current;
    return { total, photo, prompt };
  };

  const forceSwipe = (direction: "right" | "left" | "up") => {
    const x = direction === "right" ? SCREEN_WIDTH * 1.5 : direction === "left" ? -SCREEN_WIDTH * 1.5 : 0;
    const y = direction === "up" ? -SCREEN_HEIGHT * 1.5 : 0;
    Animated.timing(position, {
      toValue: { x, y },
      duration: SWIPE_OUT_DURATION,
      useNativeDriver: true,
    }).start(() => onSwipeComplete(direction));
  };

  const onSwipeComplete = (direction: "right" | "left" | "up") => {
    const { total, photo, prompt } = getDwellTimes();
    if (direction === "right") onSwipeRight(total, photo, prompt);
    else if (direction === "left") onSwipeLeft(total, photo, prompt);
    else if (direction === "up") onSuperLike?.(total);
    position.setValue({ x: 0, y: 0 });
    swipeDirectionRef.current = null;
    setSwipeDirection(null);
  };

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => isTop,
      onPanResponderMove: (_, gesture) => {
        position.setValue({ x: gesture.dx, y: gesture.dy });
        const dir = gesture.dx > 20 ? "right" : gesture.dx < -20 ? "left" : gesture.dy < -40 ? "up" : null;
        if (dir !== swipeDirectionRef.current) {
          swipeDirectionRef.current = dir;
          setSwipeDirection(dir);
        }
      },
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dx > SWIPE_THRESHOLD) forceSwipe("right");
        else if (gesture.dx < -SWIPE_THRESHOLD) forceSwipe("left");
        else if (gesture.dy < -SWIPE_THRESHOLD * 0.8) forceSwipe("up");
        else {
          Animated.spring(position, {
            toValue: { x: 0, y: 0 },
            useNativeDriver: true,
            friction: 5,
          }).start();
          swipeDirectionRef.current = null;
          setSwipeDirection(null);
        }
      },
    })
  ).current;

  const rotate = position.x.interpolate({
    inputRange: [-SCREEN_WIDTH / 2, 0, SCREEN_WIDTH / 2],
    outputRange: [`-${ROTATE_DEGREE}`, "0deg", ROTATE_DEGREE],
    extrapolate: "clamp",
  });

  const cardStyle = isTop
    ? {
        transform: [{ translateX: position.x }, { translateY: position.y }, { rotate }],
      }
    : { transform: [{ scale: 0.96 }] };

  const likeOpacity = position.x.interpolate({
    inputRange: [0, SCREEN_WIDTH / 6],
    outputRange: [0, 1],
    extrapolate: "clamp",
  });
  const nopeOpacity = position.x.interpolate({
    inputRange: [-SCREEN_WIDTH / 6, 0],
    outputRange: [1, 0],
    extrapolate: "clamp",
  });

  const photos = candidate.photos ?? [];
  const currentPhoto = photos[photoIndex];

  return (
    <Animated.View
      style={[styles.card, cardStyle]}
      {...(isTop ? panResponder.panHandlers : {})}
    >
      {/* Photo area */}
      <View style={styles.photoContainer}>
        {currentPhoto ? (
          <Image
            source={{ uri: currentPhoto.url }}
            style={styles.photo}
            contentFit="cover"
            cachePolicy="memory-disk"
            transition={200}
          />
        ) : (
          <View style={[styles.photo, styles.photoPlaceholder]}>
            <Text style={styles.photoInitial}>{candidate.first_name?.[0] ?? "?"}</Text>
          </View>
        )}

        {/* Photo indicators */}
        {photos.length > 1 && (
          <View style={styles.indicators}>
            {photos.map((_, i) => (
              <TouchableOpacity
                key={i}
                style={[styles.indicator, i === photoIndex && styles.indicatorActive]}
                onPress={() => handlePhotoChange(i)}
              />
            ))}
          </View>
        )}

        {/* Swipe labels */}
        {isTop && (
          <>
            <Animated.View style={[styles.likeLabel, { opacity: likeOpacity }]}>
              <Text style={styles.likeLabelText}>INTERESTED ❤️</Text>
            </Animated.View>
            <Animated.View style={[styles.nopeLabel, { opacity: nopeOpacity }]}>
              <Text style={styles.nopeLabelText}>PASS 👋</Text>
            </Animated.View>
          </>
        )}

        {/* Gradient overlay */}
        <View style={styles.photoGradient} />

        {/* Name + basic info on photo */}
        <View style={styles.photoInfo}>
          <View style={styles.nameRow}>
            <Text style={styles.name}>{candidate.first_name}, {candidate.age}</Text>
            {candidate.is_verified && (
              <View style={styles.verifiedBadge}>
                <Text style={styles.verifiedBadgeText}>✓</Text>
              </View>
            )}
          </View>
          <Text style={styles.location}>
            {candidate.city} · {candidate.distance_display}
          </Text>
        </View>
      </View>

      {/* Card body — prompts + details */}
      <ScrollView
        style={styles.body}
        showsVerticalScrollIndicator={false}
        scrollEnabled={false}
      >
        {/* Diet badge */}
        {candidate.dietary_strictness && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>🥗 {candidate.dietary_strictness}</Text>
          </View>
        )}

        {/* Prompts */}
        {(candidate.prompts ?? []).slice(0, 2).map((prompt) => (
          <View key={prompt.id} style={styles.promptCard}>
            <Text style={styles.promptQ}>{prompt.question}</Text>
            <Text style={styles.promptA}>{prompt.answer}</Text>
          </View>
        ))}

        {/* Compatibility */}
        {candidate.compatibility && (
          <View style={styles.compatRow}>
            <Text style={styles.compatPct}>
              {candidate.compatibility.values_alignment_percentage}% values match
            </Text>
            {(candidate.compatibility.shared_traditions ?? []).slice(0, 2).map((t, i) => (
              <View key={i} style={styles.tradBadge}>
                <Text style={styles.tradBadgeText}>{t}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Action buttons */}
      {isTop && (
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.btn, styles.passBtn]}
            onPress={() => forceSwipe("left")}
          >
            <Text style={styles.passBtnText}>✕</Text>
          </TouchableOpacity>

          {onSuperLike && (
            <TouchableOpacity
              style={[styles.btn, styles.superBtn]}
              onPress={() => forceSwipe("up")}
            >
              <Text style={styles.superBtnText}>⭐</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[styles.btn, styles.likeBtn]}
            onPress={() => forceSwipe("right")}
          >
            <Text style={styles.likeBtnText}>♥</Text>
          </TouchableOpacity>
        </View>
      )}
    </Animated.View>
  );
}

const CARD_HEIGHT = SCREEN_HEIGHT * 0.72;

const styles = StyleSheet.create({
  card: {
    position: "absolute",
    width: SCREEN_WIDTH - spacing.xxl,
    height: CARD_HEIGHT,
    backgroundColor: colors.white,
    borderRadius: radii.xl,
    overflow: "hidden",
    ...shadows.card,
    alignSelf: "center",
  },
  photoContainer: {
    height: CARD_HEIGHT * 0.6,
    width: "100%",
    position: "relative",
    overflow: "hidden",
  },
  photo: { width: "100%", height: "100%" },
  photoPlaceholder: {
    backgroundColor: colors.saffronLight,
    alignItems: "center",
    justifyContent: "center",
  },
  photoInitial: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 80,
    color: colors.saffron,
  },
  indicators: {
    position: "absolute",
    top: spacing.sm,
    left: spacing.sm,
    right: spacing.sm,
    flexDirection: "row",
    gap: 4,
  },
  indicator: {
    flex: 1,
    height: 3,
    backgroundColor: "rgba(255,255,255,0.45)",
    borderRadius: 2,
  },
  indicatorActive: { backgroundColor: colors.white },
  photoGradient: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    height: 120,
    backgroundColor: "transparent",
    // Native gradient via backgroundImage not available; use a semi-dark overlay
    // Real gradient: use expo-linear-gradient if already in dep
  },
  photoInfo: {
    position: "absolute",
    bottom: spacing.base,
    left: spacing.base,
  },
  nameRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
  },
  name: {
    fontFamily: "Outfit_700Bold",
    fontSize: 22,
    color: colors.white,
    textShadowColor: "rgba(0,0,0,0.5)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  verifiedBadge: {
    backgroundColor: colors.saffron,
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: "center",
    justifyContent: "center",
  },
  verifiedBadgeText: {
    color: colors.white,
    fontSize: 11,
    fontFamily: "Outfit_700Bold",
  },
  location: {
    ...typography.bodySmall,
    color: "rgba(255,255,255,0.85)",
    marginTop: 2,
    textShadowColor: "rgba(0,0,0,0.4)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  likeLabel: {
    position: "absolute",
    top: spacing.xl,
    left: spacing.base,
    backgroundColor: colors.green,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radii.md,
    transform: [{ rotate: "-15deg" }],
  },
  likeLabelText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 18,
    color: colors.white,
  },
  nopeLabel: {
    position: "absolute",
    top: spacing.xl,
    right: spacing.base,
    backgroundColor: colors.red,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radii.md,
    transform: [{ rotate: "15deg" }],
  },
  nopeLabelText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 18,
    color: colors.white,
  },
  body: {
    flex: 1,
    padding: spacing.base,
  },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: colors.greenLight,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    marginBottom: spacing.sm,
  },
  badgeText: { ...typography.caption, color: colors.green, textTransform: "uppercase" },
  promptCard: {
    backgroundColor: colors.light,
    borderRadius: radii.md,
    padding: spacing.sm,
    marginBottom: spacing.sm,
  },
  promptQ: {
    ...typography.caption,
    color: colors.muted,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  promptA: { ...typography.body, color: colors.dark, fontSize: 14, lineHeight: 20 },
  compatRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  compatPct: { ...typography.bodySmall, color: colors.saffron, fontFamily: "Outfit_700Bold" },
  tradBadge: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  tradBadgeText: { ...typography.caption, color: colors.saffron },
  actions: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: spacing.xl,
    paddingVertical: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.white,
  },
  btn: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: "center",
    justifyContent: "center",
  },
  passBtn: {
    backgroundColor: colors.white,
    borderWidth: 2,
    borderColor: colors.border,
    ...shadows.card,
  },
  passBtnText: { fontSize: 24, color: colors.red },
  superBtn: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: colors.blueLight,
    borderWidth: 2,
    borderColor: colors.blue,
  },
  superBtnText: { fontSize: 20 },
  likeBtn: {
    backgroundColor: colors.pinkMid,
    ...shadows.heart,
  },
  likeBtnText: { fontSize: 26, color: colors.white },
});

export default React.memo(SwipeCard);
