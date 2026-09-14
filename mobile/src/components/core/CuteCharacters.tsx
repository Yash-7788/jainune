/**
 * Cute Characters & Motifs — Jainune
 *
 * Whimsical, minimalist SVG characters for intro and welcome slides:
 * - BlueBoyHeart: Cute blue stickman holding a radiant red heart
 * - PinkGirlHeart: Cute pink girl character holding a radiant red heart
 */

import React, { useEffect, useRef } from "react";
import { View, StyleSheet, Animated } from "react-native";
import Svg, { Path, Circle, Rect, G } from "react-native-svg";

interface CharacterProps {
  size?: number;
  angle?: number;
  floating?: boolean;
  style?: object;
}

// ── Cute Blue Boy Holding a Red Heart ─────────────────────────────────────────

export function BlueBoyHeart({
  size = 64,
  angle = -8,
  floating = true,
  style,
}: CharacterProps) {
  const floatAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!floating) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, {
          toValue: -5,
          duration: 1700,
          useNativeDriver: true,
        }),
        Animated.timing(floatAnim, {
          toValue: 0,
          duration: 1700,
          useNativeDriver: true,
        }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [floating, floatAnim]);

  return (
    <Animated.View
      style={[
        styles.wrap,
        {
          width: size,
          height: size,
          transform: [{ translateY: floatAnim }, { rotate: `${angle}deg` }],
        },
        style,
      ]}
      pointerEvents="none"
    >
      <Svg width={size} height={size} viewBox="0 0 80 80" fill="none">
        {/* Head */}
        <Circle cx={36} cy={22} r={12} fill="#3B82F6" stroke="#1D4ED8" strokeWidth={2.5} />
        {/* Cute Face details */}
        {/* Eyes */}
        <Circle cx={33} cy={21} r={1.8} fill="#FFFFFF" />
        <Circle cx={41} cy={21} r={1.8} fill="#FFFFFF" />
        {/* Smile */}
        <Path d="M34 26c1.2 1.2 3.8 1.2 5 0" stroke="#FFFFFF" strokeWidth={1.8} strokeLinecap="round" />
        {/* Cheeks */}
        <Circle cx={30} cy={23} r={1.8} fill="#93C5FD" opacity={0.8} />
        <Circle cx={44} cy={23} r={1.8} fill="#93C5FD" opacity={0.8} />

        {/* Body (Torso) */}
        <Path d="M36 34v22" stroke="#1D4ED8" strokeWidth={3.5} strokeLinecap="round" />

        {/* Legs */}
        <Path d="M36 56l-9 17" stroke="#1D4ED8" strokeWidth={3.5} strokeLinecap="round" />
        <Path d="M36 56l10 17" stroke="#1D4ED8" strokeWidth={3.5} strokeLinecap="round" />

        {/* Left Arm holding the heart */}
        <Path d="M36 40l14-4" stroke="#1D4ED8" strokeWidth={3.5} strokeLinecap="round" />
        {/* Right Arm wrapping around heart */}
        <Path d="M36 40l18 8" stroke="#1D4ED8" strokeWidth={3.5} strokeLinecap="round" />

        {/* The Vibrant Red Heart being held */}
        <G transform="translate(48, 30) scale(0.9)">
          {/* Pixel / Smooth Heart Silhouette */}
          <Path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill="#E53935"
            stroke="#B71C1C"
            strokeWidth={1.5}
          />
          {/* Heart Highlight */}
          <Circle cx={7} cy={7} r={1.5} fill="#FF8A80" />
        </G>
      </Svg>
    </Animated.View>
  );
}

// ── Cute Pink Girl Holding a Red Heart ────────────────────────────────────────

export function PinkGirlHeart({
  size = 64,
  angle = 12,
  floating = true,
  style,
}: CharacterProps) {
  const floatAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!floating) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, {
          toValue: -5.5,
          duration: 1900,
          useNativeDriver: true,
        }),
        Animated.timing(floatAnim, {
          toValue: 0,
          duration: 1900,
          useNativeDriver: true,
        }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [floating, floatAnim]);

  return (
    <Animated.View
      style={[
        styles.wrap,
        {
          width: size,
          height: size,
          transform: [{ translateY: floatAnim }, { rotate: `${angle}deg` }],
        },
        style,
      ]}
      pointerEvents="none"
    >
      <Svg width={size} height={size} viewBox="0 0 80 80" fill="none">
        {/* Pigtails / Hair ribbons */}
        <Path d="M22 18c-4-4-8-1-6 6 2 4 8 2 8 2" fill="#DB2777" />
        <Path d="M58 18c4-4 8-1 6 6-2 4-8 2-8 2" fill="#DB2777" />

        {/* Head */}
        <Circle cx={40} cy={22} r={12} fill="#EC4899" stroke="#DB2777" strokeWidth={2.5} />

        {/* Cute Face details */}
        {/* Eyes (Happy arcs) */}
        <Path d="M34 20c1-1.5 3-1.5 4 0" stroke="#FFFFFF" strokeWidth={1.8} strokeLinecap="round" />
        <Path d="M42 20c1-1.5 3-1.5 4 0" stroke="#FFFFFF" strokeWidth={1.8} strokeLinecap="round" />
        {/* Smile */}
        <Path d="M37 26c1.5 1 4.5 1 6 0" stroke="#FFFFFF" strokeWidth={1.8} strokeLinecap="round" />
        {/* Rosy Cheeks */}
        <Circle cx={32} cy={23} r={2} fill="#FBCFE8" opacity={0.8} />
        <Circle cx={48} cy={23} r={2} fill="#FBCFE8" opacity={0.8} />

        {/* Cute A-Line Dress / Body */}
        <Path d="M40 34L28 54h24L40 34z" fill="#F472B6" stroke="#DB2777" strokeWidth={2} strokeLinejoin="round" />

        {/* Legs */}
        <Path d="M35 54v18" stroke="#DB2777" strokeWidth={3} strokeLinecap="round" />
        <Path d="M45 54v18" stroke="#DB2777" strokeWidth={3} strokeLinecap="round" />

        {/* Arms holding heart in front */}
        <Path d="M33 39l-11-2" stroke="#DB2777" strokeWidth={3} strokeLinecap="round" />
        <Path d="M47 39l-11 5" stroke="#DB2777" strokeWidth={3} strokeLinecap="round" />

        {/* The Radiant Red Heart held in hands */}
        <G transform="translate(14, 28) scale(0.9)">
          <Path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill="#E53935"
            stroke="#B71C1C"
            strokeWidth={1.5}
          />
          <Circle cx={7} cy={7} r={1.5} fill="#FF8A80" />
        </G>
      </Svg>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: "center",
    justifyContent: "center",
  },
});
