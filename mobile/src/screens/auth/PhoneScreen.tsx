/**
 * Phone Screen — +91 phone number entry — Jainune
 *
 * Enhanced with:
 * - PeekingHeartMascot that muscles up over input on focus and tracks typing/backspacing in real time
 * - Thick 2px black bordered inputs and buttons with spring click animations
 * - Country code badge with +91 🇮🇳
 * - Anti-enumeration validation byte-for-byte compliant with backend
 */

import React, { useState, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  TextInput,
  TouchableOpacity,
  Animated,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as Haptics from "expo-haptics";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import { PrimaryButton, ErrorToast, PeekingHeartMascot } from "../../components/core";
import { BackIcon } from "../../components/core/Icons";
import { requestPhoneOTP } from "../../api/authApi";
import { validatePhone } from "../../security/inputValidation";
import { extractError } from "../../api/client";
import type { AuthStackParams } from "../../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<AuthStackParams, "Phone">;

export default function PhoneScreen() {
  const navigation = useNavigation<Nav>();
  const [digits, setDigits] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const phoneValidation = validatePhone(digits);
  const isValid = phoneValidation.valid;

  // WhatsApp button tactile animation
  const waScaleAnim = useRef(new Animated.Value(1)).current;
  const waTranslateY = useRef(new Animated.Value(0)).current;

  const handleChange = (text: string) => {
    const clean = text.replace(/\D/g, "").slice(0, 10);
    setDigits(clean);
    if (error) setError(null);
  };

  const handleSend = async (channel: "sms" | "whatsapp" = "sms") => {
    if (!isValid) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      setError({
        title: "Check Your Number",
        message: "Please enter a valid 10-digit Indian mobile number.",
      });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await requestPhoneOTP(phoneValidation.e164, channel);
      navigation.navigate("OTPVerify", {
        phoneNumber: phoneValidation.e164,
        masked: res.phone_number,
        mode: "phone",
      });
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleWaPressIn = () => {
    if (!isValid || loading) return;
    Animated.parallel([
      Animated.spring(waScaleAnim, { toValue: 0.965, tension: 200, friction: 10, useNativeDriver: true }),
      Animated.spring(waTranslateY, { toValue: 2, tension: 200, friction: 10, useNativeDriver: true }),
    ]).start();
  };

  const handleWaPressOut = () => {
    Animated.parallel([
      Animated.spring(waScaleAnim, { toValue: 1, tension: 200, friction: 10, useNativeDriver: true }),
      Animated.spring(waTranslateY, { toValue: 0, tension: 200, friction: 10, useNativeDriver: true }),
    ]).start();
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

      {error && (
        <ErrorToast
          title={error.title}
          message={error.message}
          visible
          onDismiss={() => setError(null)}
        />
      )}

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <TouchableOpacity
            onPress={() => navigation.goBack()}
            style={styles.backBtn}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
          >
            <BackIcon color={colors.dark} />
          </TouchableOpacity>
        </View>

        <Text style={styles.title}>Your phone number</Text>
        <Text style={styles.sub}>
          We'll send a 6-digit verification code via SMS or WhatsApp.
        </Text>
      </View>

      {/* Phone Input Card with Peeking Heart Mascot Mounted on Top Edge */}
      <View style={styles.inputSection}>
        {/* Interactive Peeking Mascot */}
        <PeekingHeartMascot
          isFocused={isFocused}
          textLength={digits.length}
          maxLength={10}
        />

        {/* Input Row with Thick Black Border */}
        <View
          style={[
            styles.inputBox,
            isFocused && styles.inputBoxFocused,
            isValid && styles.inputBoxValid,
          ]}
        >
          {/* Country Code Pill */}
          <View style={styles.countryBadge}>
            <Text style={styles.flag}>🇮🇳</Text>
            <Text style={styles.countryCodeText}>+91</Text>
          </View>

          {/* Number Field */}
          <TextInput
            style={styles.phoneInput}
            value={digits}
            onChangeText={handleChange}
            placeholder="98200 98200"
            placeholderTextColor={colors.muted}
            keyboardType="phone-pad"
            autoFocus
            maxLength={10}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
          />

          {/* Character count & validation status */}
          {isValid ? (
            <View style={styles.validCheck}>
              <Text style={styles.validCheckText}>✓</Text>
            </View>
          ) : digits.length > 0 ? (
            <Text style={styles.counter}>{digits.length}/10</Text>
          ) : null}
        </View>
      </View>

      {/* Action Buttons with 2px Black Borders & Click Animations */}
      <View style={styles.cta}>
        <PrimaryButton
          label="Send Code via SMS"
          onPress={() => handleSend("sms")}
          loading={loading}
          disabled={!isValid || loading}
        />

        <Animated.View
          style={{
            transform: [{ scale: waScaleAnim }, { translateY: waTranslateY }],
            marginTop: spacing.md,
          }}
        >
          <TouchableOpacity
            style={[
              styles.whatsappBtn,
              (!isValid || loading) && styles.whatsappBtnDisabled,
            ]}
            onPress={() => handleSend("whatsapp")}
            onPressIn={handleWaPressIn}
            onPressOut={handleWaPressOut}
            disabled={!isValid || loading}
            activeOpacity={0.92}
          >
            <Text style={styles.whatsappBtnText}>💬 Send Code via WhatsApp</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.base,
    paddingTop: 56,
  },
  header: {
    marginBottom: 42,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  backBtn: {
    width: 44,
    height: 44,
    borderRadius: radii.full,
    borderWidth: 2,
    borderColor: "#1C1C1E",
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    elevation: 2,
  },
  title: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 30,
    lineHeight: 38,
    color: colors.dark,
    marginBottom: spacing.xs,
  },
  sub: {
    ...typography.body,
    color: colors.mid,
    lineHeight: 22,
  },
  inputSection: {
    position: "relative",
    marginTop: 20,
    marginBottom: spacing.xxl,
  },
  inputBox: {
    flexDirection: "row",
    alignItems: "center",
    height: 60,
    borderRadius: radii.full,
    borderWidth: 2,
    borderColor: "#1C1C1E",
    backgroundColor: colors.white,
    paddingHorizontal: spacing.sm,
    shadowColor: "#1C1C1E",
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.12,
    shadowRadius: 0,
    elevation: 3,
  },
  inputBoxFocused: {
    borderColor: colors.saffron,
    shadowColor: colors.saffron,
    shadowOpacity: 0.25,
  },
  inputBoxValid: {
    borderColor: colors.green,
  },
  countryBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radii.full,
    backgroundColor: colors.light,
    marginRight: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  flag: {
    fontSize: 16,
  },
  countryCodeText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 15,
    color: colors.dark,
  },
  phoneInput: {
    flex: 1,
    fontFamily: "Outfit_700Bold",
    fontSize: 20,
    color: colors.dark,
    letterSpacing: 1.5,
    height: "100%",
  },
  validCheck: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.green,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 8,
  },
  validCheckText: {
    color: colors.white,
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 14,
  },
  counter: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 12,
    color: colors.muted,
    marginRight: 10,
  },
  cta: {
    flex: 1,
    justifyContent: "flex-end",
    paddingBottom: 40,
  },
  whatsappBtn: {
    height: 52,
    borderRadius: radii.full,
    borderWidth: 2,
    borderColor: "#1C1C1E",
    backgroundColor: "#E8F8F0",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#1C1C1E",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 0,
    elevation: 2,
  },
  whatsappBtnDisabled: {
    borderColor: "#D5CECA",
    backgroundColor: colors.light,
    opacity: 0.5,
  },
  whatsappBtnText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 15,
    color: "#1E7E45",
  },
});
