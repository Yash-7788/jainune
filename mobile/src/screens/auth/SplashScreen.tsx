/**
 * Splash Screen — 2s auto-advance, Jainune wordmark fade on saffron-pink gradient
 * DEVPLAN.md Step 1
 */

import React, { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View, StatusBar } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { colors, typography, gradients } from "../../theme/tokens";
import { useAuthStore } from "../../store/authStore";
import { performDeviceIntegrityCheck, terminateCompromisedSession } from "../../security/deviceIntegrity";
import type { AuthStackParams } from "../../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<AuthStackParams, "Splash">;

export default function SplashScreen() {
  const navigation = useNavigation<Nav>();
  const { initSession, state } = useAuthStore();
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.9)).current;

  useEffect(() => {
    // 1. Run device integrity check FIRST before any app logic
    (async () => {
      const result = await performDeviceIntegrityCheck();
      if (!result.isSecure) {
        terminateCompromisedSession(result.violations);
        return; // Halt
      }

      // 2. Animate wordmark in
      Animated.parallel([
        Animated.timing(opacity, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.spring(scale, { toValue: 1, tension: 60, friction: 8, useNativeDriver: true }),
      ]).start();

      // 3. Init session from SecureStore
      await initSession();

      // 4. After 2s, route based on auth state
      setTimeout(() => {
        // Auth state is reactive — navigation happens via AppNavigator
        // Just need to leave splash
        if (state === "unauthenticated" || state === "loading") {
          navigation.replace("Welcome");
        }
        // If authenticated or onboarding, AppNavigator handles routing
      }, 2000);
    })();
  }, []);

  return (
    <LinearGradient
      colors={gradients.primary}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={styles.container}
    >
      <StatusBar barStyle="light-content" />
      <Animated.View style={[styles.wordmark, { opacity, transform: [{ scale }] }]}>
        <Text style={styles.logo}>jainune</Text>
        <Text style={styles.tagline}>Your community. Your terms.</Text>
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center" },
  wordmark: { alignItems: "center" },
  logo: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 48,
    color: colors.white,
    letterSpacing: -1,
  },
  tagline: {
    ...typography.body,
    color: "rgba(255,255,255,0.75)",
    marginTop: 8,
  },
});
