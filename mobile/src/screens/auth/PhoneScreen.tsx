/**
 * Phone Screen — +91 phone number entry
 * Validates +91[6-9]XXXXXXXXX exactly. Anti-enumeration: no "already registered" feedback.
 * Matches backend OTPRequestBody validator byte-for-byte.
 */

import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  TextInput,
  TouchableOpacity,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as Haptics from "expo-haptics";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import { PrimaryButton, ErrorToast } from "../../components/core";
import { BackIcon } from "../../components/core/Icons";
import { requestPhoneOTP } from "../../api/authApi";
import { validatePhone } from "../../security/inputValidation";
import { extractError } from "../../api/client";
import type { AuthStackParams } from "../../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<AuthStackParams, "Phone">;

export default function PhoneScreen() {
  const navigation = useNavigation<Nav>();
  const [digits, setDigits] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const phoneValidation = validatePhone(digits);
  const isValid = phoneValidation.valid;

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
      // res.phone_number is masked: +91*****1210 — no account enumeration
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
        <Text style={styles.title}>Your phone number</Text>
        <Text style={styles.sub}>
          We'll send a 6-digit verification code via SMS or WhatsApp.
        </Text>
      </View>

      {/* Phone input */}
      <View style={styles.inputRow}>
        <View style={styles.countryCode}>
          <Text style={styles.countryCodeText}>+91</Text>
        </View>
        <TextInput
          style={styles.phoneInput}
          value={digits}
          onChangeText={handleChange}
          placeholder="9820098200"
          placeholderTextColor={colors.mid}
          keyboardType="phone-pad"
          autoFocus
          maxLength={10}
        />
      </View>

      {/* Send OTP */}
      <View style={styles.cta}>
        <PrimaryButton
          label="Send Code via SMS"
          onPress={() => handleSend("sms")}
          loading={loading}
          disabled={!isValid || loading}
        />
        <TouchableOpacity
          style={styles.whatsappBtn}
          onPress={() => handleSend("whatsapp")}
          disabled={!isValid || loading}
        >
          <Text style={styles.whatsappBtnText}>💬 Send Code via WhatsApp</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  whatsappBtn: {
    marginTop: spacing.md,
    alignItems: "center",
    paddingVertical: spacing.sm,
  },
  whatsappBtnText: {
    fontFamily: "Outfit_600SemiBold",
    color: "#25D366",
    fontSize: 14,
  },
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
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: 2,
    borderBottomColor: colors.saffron,
    paddingBottom: spacing.sm,
    marginBottom: spacing.xxl,
  },
  countryCode: {
    paddingRight: spacing.sm,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    marginRight: spacing.sm,
  },
  countryCodeText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 20,
    color: colors.dark,
  },
  phoneInput: {
    flex: 1,
    fontFamily: "Outfit_700Bold",
    fontSize: 24,
    color: colors.dark,
    letterSpacing: 2,
  },
  cta: { paddingBottom: spacing.xxl },
});
