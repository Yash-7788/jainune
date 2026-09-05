/**
 * OTP Verify Screen — handles both Phone OTP and Email OTP
 * 6-box auto-advancing input, resend countdown, friendly errors
 * Anti-enumeration: never reveals if user exists or not
 * Error copy from frontend_integration_contracts.md §6
 */

import React, { useState, useCallback, useRef, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  TouchableOpacity,
  Animated,
} from "react-native";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as Haptics from "expo-haptics";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import { OTPInput, PrimaryButton, ErrorToast } from "../../components/core";
import { BackIcon } from "../../components/core/Icons";
import {
  verifyPhoneOTP,
  verifyEmailOTP,
  requestPhoneOTP,
  requestEmailOTP,
} from "../../api/authApi";
import { validateOtp } from "../../security/inputValidation";
import { useAuthStore } from "../../store/authStore";
import { extractError } from "../../api/client";
import type { AuthStackParams } from "../../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<AuthStackParams, "OTPVerify">;
type Route = RouteProp<AuthStackParams, "OTPVerify">;

const RESEND_COOLDOWN = 60;

export default function OTPVerifyScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { phoneNumber, masked, mode } = route.params;

  // email mode detection: explicit param or fallback
  const isEmail = mode === "email" || !phoneNumber || masked.includes("@");

  const setAuthenticated = useAuthStore((s) => s.setAuthenticated);
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [countdown, setCountdown] = useState(RESEND_COOLDOWN);
  const [shakeAnim] = useState(new Animated.Value(0));

  // Countdown timer
  useEffect(() => {
    if (countdown === 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const shake = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 10, duration: 50, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -10, duration: 50, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 6, duration: 50, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -6, duration: 50, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0, duration: 50, useNativeDriver: true }),
    ]).start();
  };

  const handleVerify = useCallback(async () => {
    const otpValidation = validateOtp(otp);
    if (!otpValidation.valid) {
      setError({ title: "Invalid Code", message: otpValidation.error || "Enter a 6-digit code." });
      shake();
      return;
    }
    setLoading(true);
    setError(null);
    try {
      let data;
      if (isEmail) {
        // Extract email from masked — we stored the real email in phoneNumber field for email flow
        data = await verifyEmailOTP(phoneNumber, otp);
      } else {
        data = await verifyPhoneOTP(phoneNumber, otp);
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setAuthenticated(data.user_id, data.is_new_user, data.onboarding_completed);
    } catch (err) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      shake();
      setOtp("");
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  }, [otp, phoneNumber, isEmail]);

  // Auto-verify when 6 digits entered
  useEffect(() => {
    if (otp.length === 6) {
      handleVerify();
    }
  }, [otp]);

  const handleResend = async () => {
    if (countdown > 0) return;
    setCountdown(RESEND_COOLDOWN);
    setOtp("");
    setError(null);
    try {
      if (isEmail) {
        await requestEmailOTP(phoneNumber);
      } else {
        await requestPhoneOTP(phoneNumber);
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch (err) {
      setError(extractError(err));
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

      {error && <ErrorToast title={error.title} message={error.message} visible />}

      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}>
          <BackIcon color={colors.dark} />
        </TouchableOpacity>
        <Text style={styles.title}>Enter the code</Text>
        <Text style={styles.sub}>
          We sent a 6-digit code to{"\n"}
          <Text style={styles.masked}>{masked}</Text>
        </Text>
      </View>

      {/* OTP boxes */}
      <Animated.View style={{ transform: [{ translateX: shakeAnim }] }}>
        <OTPInput
          value={otp}
          onChange={setOtp}
          error={error?.message}
        />
      </Animated.View>

      {/* Verify CTA */}
      <View style={styles.cta}>
        <PrimaryButton
          label="Verify"
          onPress={handleVerify}
          loading={loading}
          disabled={otp.length !== 6 || loading}
        />
      </View>

      {/* Resend */}
      <TouchableOpacity
        onPress={handleResend}
        disabled={countdown > 0}
        style={styles.resend}
      >
        <Text style={[styles.resendText, countdown > 0 && styles.resendDisabled]}>
          {countdown > 0
            ? `Resend code in ${countdown}s`
            : "Resend code"}
        </Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.base,
  },
  header: { paddingTop: 80, marginBottom: spacing.xxl },
  back: {
    width: 40,
    height: 40,
    justifyContent: "center",
    marginBottom: spacing.lg,
  },
  title: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 28,
    color: colors.dark,
    marginBottom: spacing.sm,
  },
  sub: { ...typography.body, color: colors.mid, lineHeight: 22 },
  masked: { fontFamily: "Outfit_700Bold", color: colors.dark },
  cta: { marginTop: spacing.xxl, marginBottom: spacing.md },
  resend: { alignItems: "center", paddingVertical: spacing.sm },
  resendText: {
    ...typography.body,
    color: colors.saffron,
    fontFamily: "Outfit_600SemiBold",
  },
  resendDisabled: { color: colors.mid },
});
