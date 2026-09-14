/**
 * Welcome Slides — Jainune
 *
 * 3 value proposition slides with diverse SVG characters:
 * - Slide 1: Blue stickman holding a red heart with subtle discrete Jain pixel heart accent
 * - Slide 2: Pink girl holding a red heart with subtle discrete Jain pixel heart accent
 * - Slide 3: Blue boy & Pink girl holding hearts together with the Jain heart in the center
 * - Tactile thick 2px black-bordered buttons with micro-animations & spring clicks
 */

import React, { useRef, useState, useEffect } from "react";
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
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import {
  PrimaryButton,
  GhostButton,
  PixelHeart,
  BlueBoyHeart,
  PinkGirlHeart,
} from "../../components/core";
import type { AuthStackParams } from "../../navigation/AppNavigator";

const { width } = Dimensions.get("window");

const SLIDES = [
  {
    id: "1",
    tag: "INTENTIONAL CONNECTIONS",
    headline: "Finally.\nAn app that gets it.",
    sub: "Built for the Jain community — honoring cultural values, dietary boundaries, and genuine compatibility.",
  },
  {
    id: "2",
    tag: "SHARED VALUES",
    headline: "Real people.\nShared world.",
    sub: "Community traditions, Ahimsa principles, and family roots — paired with complete transparency and trust.",
  },
  {
    id: "3",
    tag: "DIGNIFIED DISCOVERY",
    headline: "Your community.\nYour terms.",
    sub: "No spam. Zero fake accounts. 100% verified authentic profiles with dignity floor matching.",
  },
];

type Nav = NativeStackNavigationProp<AuthStackParams, "Welcome">;

export default function WelcomeScreen() {
  const navigation = useNavigation<Nav>();
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatRef = useRef<FlatList>(null);

  // Staggered entrance animation
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
      Animated.spring(slideAnim, {
        toValue: 0,
        tension: 80,
        friction: 10,
        useNativeDriver: true,
      }),
    ]).start();
  }, [fadeAnim, slideAnim]);

  const handleNext = () => {
    if (currentIndex < SLIDES.length - 1) {
      flatRef.current?.scrollToIndex({ index: currentIndex + 1, animated: true });
    } else {
      navigation.navigate("AuthMethod");
    }
  };

  const isLast = currentIndex === SLIDES.length - 1;

  // Render hero visual character composition per slide
  const renderSlideHero = (slideId: string) => {
    if (slideId === "1") {
      return (
        <View style={styles.heroScene}>
          {/* Subtle floating Jain heart in discrete corner */}
          <View style={styles.floatingAccentTopRight}>
            <PixelHeart size={34} angle={16} floating={true} />
          </View>
          {/* Blue stickman holding radiant red heart */}
          <BlueBoyHeart size={100} angle={-10} floating={true} />
        </View>
      );
    }

    if (slideId === "2") {
      return (
        <View style={styles.heroScene}>
          {/* Subtle floating Jain heart in discrete corner */}
          <View style={styles.floatingAccentTopLeft}>
            <PixelHeart size={34} angle={-15} floating={true} />
          </View>
          {/* Pink girl holding radiant red heart */}
          <PinkGirlHeart size={100} angle={12} floating={true} />
        </View>
      );
    }

    // Slide 3: Both meeting with Jain heart in center
    return (
      <View style={styles.heroSceneDuo}>
        <View style={styles.duoBoy}>
          <BlueBoyHeart size={82} angle={-8} floating={true} />
        </View>
        <View style={styles.duoCenterHeart}>
          <PixelHeart size={50} angle={-2} floating={true} />
        </View>
        <View style={styles.duoGirl}>
          <PinkGirlHeart size={82} angle={8} floating={true} />
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

      {/* Top Skip button */}
      <View style={styles.topBar}>
        {!isLast ? (
          <TouchableOpacity
            style={styles.skipBtn}
            onPress={() => navigation.navigate("AuthMethod")}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
          >
            <Text style={styles.skipText}>Skip</Text>
          </TouchableOpacity>
        ) : (
          <View style={{ height: 28 }} />
        )}
      </View>

      {/* Slides FlatList */}
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
          <View style={styles.slide}>
            {/* Visual Hero Area */}
            <View style={styles.heroArea}>
              <View style={styles.sparklePill}>
                <Text style={styles.sparkleIcon}>✦</Text>
                <Text style={styles.tagText}>{item.tag}</Text>
              </View>

              <View style={styles.characterStage}>
                {renderSlideHero(item.id)}
              </View>
            </View>

            {/* Typography Content */}
            <Animated.View
              style={[
                styles.slideContent,
                {
                  opacity: fadeAnim,
                  transform: [{ translateY: slideAnim }],
                },
              ]}
            >
              <Text style={styles.headline}>{item.headline}</Text>
              <Text style={styles.sub}>{item.sub}</Text>
            </Animated.View>
          </View>
        )}
      />

      {/* Pagination Dots */}
      <View style={styles.dotsRow}>
        {SLIDES.map((_, i) => (
          <View
            key={i}
            style={[
              styles.dot,
              currentIndex === i ? styles.dotActive : styles.dotInactive,
            ]}
          />
        ))}
      </View>

      {/* Bottom Actions with Thick Black Borders & Click Animations */}
      <View style={styles.cta}>
        <PrimaryButton
          label={isLast ? "Get Started" : "Continue"}
          onPress={handleNext}
        />

        <GhostButton
          label="Already have an account? Sign In"
          onPress={() => navigation.navigate("AuthMethod")}
          style={{ marginTop: spacing.md }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  topBar: {
    paddingHorizontal: spacing.base,
    paddingTop: 54,
    paddingBottom: spacing.xs,
    flexDirection: "row",
    justifyContent: "flex-end",
  },
  skipBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  skipText: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 14,
    color: colors.mid,
  },
  slide: {
    width,
    flex: 1,
    paddingHorizontal: spacing.base,
    justifyContent: "center",
  },
  heroArea: {
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xxl,
  },
  sparklePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radii.full,
    borderWidth: 1.5,
    borderColor: "#1C1C1E",
    backgroundColor: colors.white,
    marginBottom: spacing.lg,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    elevation: 2,
  },
  sparkleIcon: {
    color: colors.saffron,
    fontSize: 12,
  },
  tagText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 11,
    color: colors.dark,
    letterSpacing: 1.2,
  },
  characterStage: {
    height: 120,
    width: "100%",
    alignItems: "center",
    justifyContent: "center",
  },
  heroScene: {
    width: "100%",
    height: 120,
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  heroSceneDuo: {
    width: "100%",
    height: 120,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  duoBoy: {
    zIndex: 10,
  },
  duoCenterHeart: {
    marginBottom: 16,
    zIndex: 15,
  },
  duoGirl: {
    zIndex: 10,
  },
  floatingAccentTopRight: {
    position: "absolute",
    top: -10,
    right: 36,
    opacity: 0.85,
  },
  floatingAccentTopLeft: {
    position: "absolute",
    top: -10,
    left: 36,
    opacity: 0.85,
  },
  slideContent: {
    paddingHorizontal: spacing.sm,
  },
  headline: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 34,
    lineHeight: 42,
    color: colors.dark,
    marginBottom: spacing.md,
  },
  sub: {
    ...typography.body,
    fontSize: 16,
    lineHeight: 24,
    color: colors.mid,
  },
  dotsRow: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 8,
    marginBottom: spacing.xl,
  },
  dot: {
    height: 8,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: "#1C1C1E",
  },
  dotActive: {
    width: 28,
    backgroundColor: colors.saffron,
  },
  dotInactive: {
    width: 8,
    backgroundColor: colors.white,
  },
  cta: {
    paddingHorizontal: spacing.base,
    paddingBottom: 40,
  },
});
