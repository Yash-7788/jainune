/**
 * Step 22 — Onboarding complete
 * Calls PATCH /v1/onboarding/step/22 to finalize, then sets auth state to authenticated.
 */
import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Animated } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { colors, spacing, typography, gradients } from "../../../theme/tokens";
import { PrimaryButton } from "../../../components/core";
import { CheckIcon } from "../../../components/core/Icons";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { useAuthStore } from "../../../store/authStore";
import { submitStep22 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";

export default function Step22Screen() {
  const { reset } = useOnboardingStore();
  const { setOnboardingCompleted } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const checkScale = useState(new Animated.Value(0))[0];
  const opacity = useState(new Animated.Value(0))[0];

  useEffect(() => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    Animated.parallel([
      Animated.spring(checkScale, { toValue: 1, tension: 60, friction: 7, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 1, duration: 600, useNativeDriver: true }),
    ]).start();
  }, []);

  const handleEnter = async () => {
    setLoading(true);
    try {
      await submitStep22();
      reset();
      setOnboardingCompleted();
      // AppNavigator reacts to authStore state → navigates to MainNavigator
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <LinearGradient
      colors={gradients.primary}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={styles.container}
    >
      <Animated.View style={[styles.content, { opacity }]}>
        {/* Animated checkmark */}
        <Animated.View style={[styles.checkCircle, { transform: [{ scale: checkScale }] }]}>
          <CheckIcon color={colors.saffron} size={48} />
        </Animated.View>

        <Text style={styles.title}>You're all set!</Text>
        <Text style={styles.sub}>
          Your profile is ready. Time to discover your Jain community.
        </Text>

        {error && (
          <Text style={styles.errorText}>{error.message}</Text>
        )}

        <PrimaryButton
          label="Enter Jainune"
          onPress={handleEnter}
          loading={loading}
          style={styles.btn}
        />
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center" },
  content: { alignItems: "center", paddingHorizontal: spacing.xxl },
  checkCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xxl,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.15,
    shadowRadius: 20,
    elevation: 12,
  },
  title: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 36,
    color: colors.white,
    textAlign: "center",
    marginBottom: spacing.base,
  },
  sub: {
    ...typography.body,
    color: "rgba(255,255,255,0.8)",
    textAlign: "center",
    lineHeight: 24,
    marginBottom: spacing.xxl,
  },
  errorText: {
    ...typography.bodySmall,
    color: "rgba(255,255,255,0.9)",
    textAlign: "center",
    marginBottom: spacing.base,
  },
  btn: { width: "100%" },
});
