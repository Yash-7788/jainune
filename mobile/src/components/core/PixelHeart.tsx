/**
 * PixelHeart Component — Jainune
 *
 * Retro pixelated red heart SVG with white "Jain" typography in center.
 * Features discrete angle rotation, balanced proportions, and subtle floating idle animation.
 */

import React, { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "../../theme/tokens";

interface PixelHeartProps {
  size?: number;
  angle?: number;
  floating?: boolean;
  style?: object;
}

export default function PixelHeart({
  size = 58,
  angle = -10,
  floating = true,
  style,
}: PixelHeartProps) {
  const floatAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!floating) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, {
          toValue: -6,
          duration: 1800,
          useNativeDriver: true,
        }),
        Animated.timing(floatAnim, {
          toValue: 0,
          duration: 1800,
          useNativeDriver: true,
        }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [floating, floatAnim]);

  const fontSize = Math.max(10, Math.round(size * 0.22));

  return (
    <Animated.View
      style={[
        styles.wrapper,
        {
          width: size,
          height: size,
          transform: [
            { translateY: floatAnim },
            { rotate: `${angle}deg` },
          ],
        },
        style,
      ]}
      pointerEvents="none"
    >
      <Svg width={size} height={size} viewBox="0 0 32 30" fill="none">
        {/* Pixel Heart Outer Silhouette (Dark Ruby Red Outline) */}
        <Path
          d="M6 2h6v2h2v2h4V4h2V2h6v2h2v4h2v6h-2v4h-2v4h-2v2h-2v2h-2v2h-2v2h-4v-2h-2v-2h-2v-2h-2v-2H8v-4H6v-4H4V8h2V4h2V2z"
          fill="#B71C1C"
        />
        {/* Pixel Heart Body (Vibrant Crimson Red) */}
        <Path
          d="M7 4h4v2h2v4h6V6h2V4h4v4h2v6h-2v4h-2v4h-2v2h-2v2h-2v2h-2v-2h-2v-2h-2v-2H9v-4H7v-4H5V8h2V4z"
          fill="#E53935"
        />
        {/* Pixel Heart Highlights (Soft Coral Glint) */}
        <Path
          d="M8 5h2v2H8V5zm-1 3h2v2H7V8zm14 0h2v2h-2V8z"
          fill="#FF8A80"
        />
      </Svg>

      {/* Centered White "Jain" Text */}
      <View style={styles.textContainer}>
        <Text
          style={[
            styles.jainText,
            {
              fontSize,
              lineHeight: fontSize + 2,
            },
          ]}
          numberOfLines={1}
        >
          Jain
        </Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  textContainer: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    paddingTop: 1,
  },
  jainText: {
    fontFamily: "Outfit_800ExtraBold",
    color: colors.white,
    letterSpacing: 0.2,
    textShadowColor: "rgba(0, 0, 0, 0.45)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
    textAlign: "center",
  },
});
