/**
 * Splash Screen — Jainune
 *
 * Visual Experience:
 * - Central rhythmic heartbeat Jain pixel heart with glowing wordmark
 * - Blue stickman holding red heart (top right, tilted -12deg)
 * - Pink girl holding red heart (bottom left, tilted +14deg)
 * - Glitch-free lifecycle management with clean timer & animation cancellation
 */

import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  Animated,
  StatusBar,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { colors } from "../../theme/tokens";
import { PixelHeart, BlueBoyHeart, PinkGirlHeart } from "../../components/core";
import { useAuthStore } from "../../store/authStore";
import {
  performDeviceIntegrityCheck,
  terminateCompromisedSession,
} from "../../security/deviceIntegrity";
import type { AuthStackParams } from "../../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<AuthStackParams, "Splash">;

export default function SplashScreen() {
  const navigation = useNavigation<Nav>();
  const initSession = useAuthStore((s) => s.initSession);

  // Intro fade & scale
  const introOpacity = useRef(new Animated.Value(0)).current;
  const introScale = useRef(new Animated.Value(0.92)).current;

  // Rhythmic heartbeat double-pulse
  const heartbeatAnim = useRef(new Animated.Value(1)).current;

  // Bottom dots pulse
  const dotsAnim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    let isMounted = true;
    let navTimer: ReturnType<typeof setTimeout> | null = null;

    // 1. Entrance animation
    Animated.parallel([
      Animated.timing(introOpacity, {
        toValue: 1,
        duration: 650,
        useNativeDriver: true,
      }),
      Animated.spring(introScale, {
        toValue: 1,
        tension: 75,
        friction: 9,
        useNativeDriver: true,
      }),
    ]).start();

    // 2. Rhythmic heartbeat loop (lub-dub pulse)
    const heartbeatLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(heartbeatAnim, {
          toValue: 1.15,
          duration: 160,
          useNativeDriver: true,
        }),
        Animated.timing(heartbeatAnim, {
          toValue: 1.04,
          duration: 120,
          useNativeDriver: true,
        }),
        Animated.timing(heartbeatAnim, {
          toValue: 1.20,
          duration: 180,
          useNativeDriver: true,
        }),
        Animated.timing(heartbeatAnim, {
          toValue: 1.0,
          duration: 350,
          useNativeDriver: true,
        }),
        Animated.delay(650),
      ])
    );
    heartbeatLoop.start();

    // 3. Dots pulsing loop
    const dotsLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(dotsAnim, {
          toValue: 1,
          duration: 600,
          useNativeDriver: true,
        }),
        Animated.timing(dotsAnim, {
          toValue: 0.35,
          duration: 600,
          useNativeDriver: true,
        }),
      ])
    );
    dotsLoop.start();

    // 4. Session restoration & smooth navigation
    (async () => {
      try {
        if (!__DEV__) {
          const result = await performDeviceIntegrityCheck();
          if (!result.isSecure) {
            terminateCompromisedSession(result.violations);
            return;
          }
        }
        await initSession();
      } catch {
        // Fallback gracefully to welcome screen
      }

      if (!isMounted) return;

      navTimer = setTimeout(() => {
        if (!isMounted) return;
        const currentState = useAuthStore.getState().state;
        if (currentState === "unauthenticated" || currentState === "loading") {
          navigation.replace("Welcome");
        }
      }, 2300);
    })();

    return () => {
      isMounted = false;
      if (navTimer) clearTimeout(navTimer);
      heartbeatLoop.stop();
      dotsLoop.stop();
    };
  }, [initSession, navigation, introOpacity, introScale, heartbeatAnim, dotsAnim]);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

      {/* Discrete floating characters in random discrete tilted angles */}
      <View style={styles.decorTopRight} pointerEvents="none">
        <BlueBoyHeart size={68} angle={-12} floating={true} />
      </View>

      <View style={styles.decorBottomLeft} pointerEvents="none">
        <PinkGirlHeart size={66} angle={14} floating={true} />
      </View>

      {/* Central Hero Intro Content */}
      <Animated.View
        style={[
          styles.centerWrap,
          {
            opacity: introOpacity,
            transform: [{ scale: introScale }],
          },
        ]}
      >
        {/* Pulsing Central Jain Pixel Heart */}
        <Animated.View
          style={[
            styles.heartBox,
            {
              transform: [{ scale: heartbeatAnim }],
            },
          ]}
        >
          <PixelHeart size={74} angle={-3} floating={false} />
        </Animated.View>

        {/* Wordmark */}
        <Text style={styles.wordmark}>Jainune</Text>
        <Text style={styles.tagline}>CULTURAL HARMONY · MODERN LOVE</Text>

        {/* Subtle Loading Aura */}
        <Animated.View style={[styles.loadingAura, { opacity: dotsAnim }]}>
          <View style={styles.auraDot} />
          <View style={[styles.auraDot, styles.auraDotCenter]} />
          <View style={styles.auraDot} />
        </Animated.View>
      </Animated.View>

      {/* Bottom Legal/Security Badge */}
      <View style={styles.bottomFooter}>
        <Text style={styles.footerText}>AHIMSA · TRUST · 18+ VERIFIED</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
  },
  decorTopRight: {
    position: "absolute",
    top: 64,
    right: 22,
    zIndex: 5,
  },
  decorBottomLeft: {
    position: "absolute",
    bottom: 90,
    left: 22,
    zIndex: 5,
  },
  centerWrap: {
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    zIndex: 10,
  },
  heartBox: {
    marginBottom: 20,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#E53935",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 16,
    elevation: 8,
  },
  wordmark: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 40,
    letterSpacing: -0.5,
    color: colors.dark,
    lineHeight: 46,
    marginBottom: 6,
  },
  tagline: {
    fontFamily: "Outfit_700Bold",
    fontSize: 11.5,
    color: colors.saffron,
    letterSpacing: 2.2,
    textAlign: "center",
    marginBottom: 26,
  },
  loadingAura: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: 8,
  },
  auraDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: colors.saffron,
  },
  auraDotCenter: {
    width: 9,
    height: 9,
    borderRadius: 4.5,
    backgroundColor: "#E53935",
  },
  bottomFooter: {
    position: "absolute",
    bottom: 36,
    alignItems: "center",
  },
  footerText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 11,
    color: colors.muted,
    letterSpacing: 1.5,
  },
});
