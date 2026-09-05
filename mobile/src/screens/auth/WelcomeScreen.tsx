/**
 * Welcome Slides — 3 value prop slides, horizontal swipe + dot indicators
 * DEVPLAN.md Steps 2–4
 */

import React, { useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Dimensions,
  StatusBar,
  Animated,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { colors, spacing, typography, radii, gradients } from "../../theme/tokens";
import { PrimaryButton } from "../../components/core";
import type { AuthStackParams } from "../../navigation/AppNavigator";

const { width } = Dimensions.get("window");

const SLIDES = [
  {
    id: "1",
    headline: "Finally.\nAn app that gets it.",
    sub: "Built for Jains, by people who understand what actually matters in a life partner.",
    bg: colors.bg,
    accent: colors.saffron,
  },
  {
    id: "2",
    headline: "Real people.\nShared world.",
    sub: "Community values, dietary boundaries, family traditions — all matched with intention.",
    bg: colors.pinkLight,
    accent: colors.pinkMid,
  },
  {
    id: "3",
    headline: "Your community.\nYour terms.",
    sub: "No pressure. No algorithms hiding your likes. Transparent, dignified, and built on trust.",
    bg: colors.saffronLight,
    accent: colors.saffron,
  },
];

type Nav = NativeStackNavigationProp<AuthStackParams, "Welcome">;

export default function WelcomeScreen() {
  const navigation = useNavigation<Nav>();
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatRef = useRef<FlatList>(null);

  const isLast = currentIndex === SLIDES.length - 1;

  const handleNext = () => {
    if (isLast) {
      navigation.navigate("AuthMethod");
    } else {
      flatRef.current?.scrollToIndex({ index: currentIndex + 1, animated: true });
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

      {/* Skip */}
      <TouchableOpacity
        style={styles.skip}
        onPress={() => navigation.navigate("AuthMethod")}
      >
        <Text style={styles.skipText}>Skip</Text>
      </TouchableOpacity>

      <FlatList
        ref={flatRef}
        data={SLIDES}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        keyExtractor={(item) => item.id}
        onMomentumScrollEnd={(e) => {
          const idx = Math.round(e.nativeEvent.contentOffset.x / width);
          setCurrentIndex(idx);
        }}
        renderItem={({ item }) => (
          <View style={[styles.slide, { backgroundColor: item.bg }]}>
            <View style={styles.slideContent}>
              <Text style={[styles.headline, { color: item.accent }]}>{item.headline}</Text>
              <Text style={styles.sub}>{item.sub}</Text>
            </View>
          </View>
        )}
      />

      {/* Dot indicators */}
      <View style={styles.dots}>
        {SLIDES.map((_, i) => (
          <View
            key={i}
            style={[
              styles.dot,
              i === currentIndex ? styles.dotActive : styles.dotInactive,
            ]}
          />
        ))}
      </View>

      {/* CTA */}
      <View style={styles.cta}>
        <PrimaryButton
          label={isLast ? "Get Started" : "Next"}
          onPress={handleNext}
          style={{ marginHorizontal: spacing.base }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  skip: {
    position: "absolute",
    top: 56,
    right: spacing.base,
    zIndex: 10,
    padding: spacing.sm,
  },
  skipText: { ...typography.body, color: colors.mid },
  slide: {
    width,
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xxl,
    paddingTop: 80,
  },
  slideContent: { alignItems: "flex-start", width: "100%" },
  headline: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 36,
    lineHeight: 44,
    marginBottom: spacing.lg,
  },
  sub: { ...typography.body, color: colors.mid, lineHeight: 24 },
  dots: {
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.sm,
    marginBottom: spacing.xl,
  },
  dot: { height: 6, borderRadius: 3 },
  dotActive: { width: 24, backgroundColor: colors.saffron },
  dotInactive: { width: 6, backgroundColor: colors.border },
  cta: {
    paddingHorizontal: spacing.base,
    paddingBottom: spacing.xxl,
  },
});
