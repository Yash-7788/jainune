/**
 * Email Screen — email entry with allowed domain allowlist validation
 * frontend_integration_contracts.md §4.2: only approved domains accepted
 * Anti-enumeration: same OTP screen regardless of whether email is registered
 */

import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  TouchableOpacity,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as Haptics from "expo-haptics";
import { colors, spacing, typography } from "../../theme/tokens";
import { JainuneInput, PrimaryButton, ErrorToast } from "../../components/core";
import { BackIcon } from "../../components/core/Icons";
import {
  sanitizeEmail,
  isEmailDomainAllowed,
  requestEmailOTP,
} from "../../api/authApi";
import { extractError } from "../../api/client";
import type { AuthStackParams } from "../../navigation/AppNavigator";

const EMAIL_REGEX = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;

type Nav = NativeStackNavigationProp<AuthStackParams, "Email">;

export default function EmailScreen() {
  const navigation = useNavigation<Nav>();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [inlineError, setInlineError] = useState<string | undefined>();
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleChange = (text: string) => {
    setEmail(text.slice(0, 254));
    if (inlineError) setInlineError(undefined);
    if (error) setError(null);
  };

  const handleSend = async () => {
    const clean = sanitizeEmail(email);
    if (!EMAIL_REGEX.test(clean)) {
      setInlineError("Please enter a valid email address.");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      return;
    }
    if (!isEmailDomainAllowed(clean)) {
      setInlineError(
        "Please use a supported email provider (Gmail, Outlook, Yahoo, iCloud, Proton, Zoho, or Rediffmail)."
      );
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await requestEmailOTP(clean);
      // Navigate to OTPVerify: use email as phoneNumber field, masked email as masked
      navigation.navigate("OTPVerify", {
        phoneNumber: clean, // stored here for verifyEmailOTP call
        masked: res.email, // masked: u****@gmail.com
        mode: "email",
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

      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}>
          <BackIcon color={colors.dark} />
        </TouchableOpacity>
        <Text style={styles.title}>Your email address</Text>
        <Text style={styles.sub}>We'll send a 6-digit code to verify it's you.</Text>
      </View>

      <JainuneInput
        label="Email address"
        value={email}
        onChangeText={handleChange}
        placeholder="you@gmail.com"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoFocus
        error={inlineError}
      />

      <Text style={styles.domains}>
        Supported: Gmail, Outlook, Yahoo, iCloud, Proton, Zoho, Rediffmail
      </Text>

      <View style={styles.cta}>
        <PrimaryButton
          label="Send Code"
          onPress={handleSend}
          loading={loading}
          disabled={loading}
        />
      </View>
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
  domains: {
    ...typography.bodySmall,
    color: colors.mid,
    marginTop: spacing.xs,
    marginBottom: spacing.xxl,
  },
  cta: { paddingBottom: spacing.xxl },
});
