import React, { useEffect, useRef } from "react";
import { View, StyleSheet, Animated } from "react-native";
import Svg, { Path, Rect, Circle } from "react-native-svg";

interface PeekingHeartMascotProps {
  isFocused: boolean;
  textLength: number;
  maxLength?: number;
}

/**
 * PeekingHeartMascot — Interactive mascot that muscles up over input boxes on focus.
 *
 * Features:
 * - Wider balanced proportion (70px width, 52px height)
 * - True 3-finger paws with 1.5px black outline physically gripping the top edge
 * - Physically clamped eyes (overflow: "hidden" scleras) so pupils never pop out
 * - Real-time gaze tracking (looks forward/down toward typing cursor, tracks backspacing)
 */
export default function PeekingHeartMascot({
  isFocused,
  textLength,
  maxLength = 10,
}: PeekingHeartMascotProps) {
  // Muscle-up transition (entry / exit)
  const muscleAnim = useRef(new Animated.Value(0)).current;

  // Real-time tracking animation for eyes and body
  const trackAnim = useRef(new Animated.Value(0)).current;

  // Muscle up / down on focus state changes
  useEffect(() => {
    Animated.spring(muscleAnim, {
      toValue: isFocused ? 1 : 0,
      tension: 70,
      friction: 8,
      useNativeDriver: true,
    }).start();
  }, [isFocused, muscleAnim]);

  // Smoothly track character progress forward & backward (backspacing)
  useEffect(() => {
    const clampedLength = Math.max(0, Math.min(textLength, maxLength));
    const normalized = maxLength > 0 ? clampedLength / maxLength : 0;

    Animated.spring(trackAnim, {
      toValue: normalized,
      tension: 110,
      friction: 12,
      useNativeDriver: true,
    }).start();
  }, [textLength, maxLength, trackAnim]);

  // Interpolations for mascot body
  const translateY = muscleAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [36, 0],
  });

  const scale = muscleAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.8, 1],
  });

  const opacity = muscleAnim.interpolate({
    inputRange: [0, 0.35, 1],
    outputRange: [0, 0.7, 1],
  });

  // Body tilt as cursor moves across input
  const bodyRotate = trackAnim.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: ["-5deg", "0deg", "6deg"],
  });

  // Horizontal pupil gaze tracking cursor (strictly bounded inside 14px sclera)
  const pupilTranslateX = trackAnim.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [-2.5, 0, 2.5],
  });

  // Vertical pupil gaze focusing down toward the typing text
  const pupilTranslateY = trackAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.5, 2.0],
  });

  return (
    <View style={styles.container} pointerEvents="none">
      <Animated.View
        style={[
          styles.mascotWrap,
          {
            opacity,
            transform: [
              { translateY },
              { scale },
              { rotate: bodyRotate },
            ],
          },
        ]}
      >
        {/* Heart Body SVG (Wider, balanced pixel/rounded shape) */}
        <Svg width={70} height={48} viewBox="0 0 70 48" fill="none">
          {/* Thick Dark Outer Border Silhouette */}
          <Path
            d="M20 2h10v4h5v-4h10v4h9v6h5v8h2v8h-2v6h-5v5h-6v5h-8v4h-5v-4h-8v-5h-6v-5H6v-6H4v-8h2v-8h5V6h9V2z"
            fill="#1A0507"
          />

          {/* Rich Red Heart Inner Body */}
          <Path
            d="M21 4h8v4h6v-4h8v4h8v6h4v8h-2v6h-4v5h-6v5h-7v4h-4v-4h-7v-5h-6v-5H9v-6H7v-8h4V8h10V4z"
            fill="#EF4444"
          />

          {/* Highlights on top left lobe */}
          <Rect x={13} y={8} width={6} height={3} rx={1} fill="#FCA5A5" />
          <Rect x={11} y={11} width={3} height={3} rx={1} fill="#FCA5A5" />

          {/* Rosy Cheeks */}
          <Circle cx={15} cy={29} r={3.5} fill="#F87171" opacity={0.8} />
          <Circle cx={55} cy={29} r={3.5} fill="#F87171" opacity={0.8} />

          {/* Cute Little Smile */}
          <Path
            d="M32 30c1 1.5 5 1.5 6 0"
            stroke="#1A0507"
            strokeWidth={1.8}
            strokeLinecap="round"
          />
        </Svg>

        {/* Physical Eye Scleras (overflow: hidden ensures pupil NEVER escapes) */}
        <View style={styles.leftEyeSclera}>
          <Animated.View
            style={[
              styles.pupil,
              {
                transform: [
                  { translateX: pupilTranslateX },
                  { translateY: pupilTranslateY },
                ],
              },
            ]}
          >
            <View style={styles.pupilIris} />
            <View style={styles.pupilGlint} />
          </Animated.View>
        </View>

        <View style={styles.rightEyeSclera}>
          <Animated.View
            style={[
              styles.pupil,
              {
                transform: [
                  { translateX: pupilTranslateX },
                  { translateY: pupilTranslateY },
                ],
              },
            ]}
          >
            <View style={styles.pupilIris} />
            <View style={styles.pupilGlint} />
          </Animated.View>
        </View>

        {/* Left Paw — 3 Distinct Rounded Fingers gripping over the border */}
        <View style={styles.leftPaw}>
          <View style={styles.finger} />
          <View style={[styles.finger, styles.fingerMiddle]} />
          <View style={styles.finger} />
        </View>

        {/* Right Paw — 3 Distinct Rounded Fingers gripping over the border */}
        <View style={styles.rightPaw}>
          <View style={styles.finger} />
          <View style={[styles.finger, styles.fingerMiddle]} />
          <View style={styles.finger} />
        </View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    top: -42,
    left: "50%",
    marginLeft: -35,
    width: 70,
    height: 48,
    zIndex: 20,
    alignItems: "center",
    justifyContent: "flex-end",
  },
  mascotWrap: {
    width: 70,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  leftEyeSclera: {
    position: "absolute",
    top: 17,
    left: 20,
    width: 13,
    height: 13,
    borderRadius: 6.5,
    backgroundColor: "#FFFFFF",
    borderWidth: 1.5,
    borderColor: "#1A0507",
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  rightEyeSclera: {
    position: "absolute",
    top: 17,
    right: 20,
    width: 13,
    height: 13,
    borderRadius: 6.5,
    backgroundColor: "#FFFFFF",
    borderWidth: 1.5,
    borderColor: "#1A0507",
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  pupil: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: "#1A0507",
    alignItems: "flex-start",
    justifyContent: "flex-start",
  },
  pupilIris: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: "#1A0507",
  },
  pupilGlint: {
    position: "absolute",
    top: 1,
    left: 1,
    width: 2.2,
    height: 2.2,
    borderRadius: 1.1,
    backgroundColor: "#FFFFFF",
  },
  // ── 3-Finger Paws Gripping the Container Rim ─────────────────────────────────
  leftPaw: {
    position: "absolute",
    bottom: -4,
    left: 11,
    flexDirection: "row",
    alignItems: "flex-start",
    zIndex: 25,
  },
  rightPaw: {
    position: "absolute",
    bottom: -4,
    right: 11,
    flexDirection: "row",
    alignItems: "flex-start",
    zIndex: 25,
  },
  finger: {
    width: 4.8,
    height: 9,
    borderRadius: 2.4,
    backgroundColor: "#EF4444",
    borderWidth: 1.4,
    borderColor: "#1A0507",
    marginHorizontal: 0.4,
  },
  fingerMiddle: {
    height: 11,
    marginTop: -2,
  },
});
