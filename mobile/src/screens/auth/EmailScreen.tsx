/**
 * Email Screen — email entry with allowed domain validation — Jainune
 *
 * Enhanced with:
 * - PeekingHeartMascot that muscles up on focus and tracks email typing/backspacing in real time
 * - Quick-domain chips for one-tap entry
 * - Thick 2px black bordered inputs and buttons with click animations
 * - Compliant anti-enumeration behavior
 */

import React, { useState, useEffect } from "react";
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
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as Haptics from "expo-haptics";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import { PrimaryButton, ErrorToast, PeekingHeartMascot } from "../../components/core";
import { BackIcon } from "../../components/core/Icons";
import {
  sanitizeEmail,
  isEmailDomainAllowed,
  requestEmailOTP,
} from "../../api/authApi";
import { extractError } from "../../api/client";
import type { AuthStackParams } from "../../navigation/AppNavigator";

const EMAIL_REGEX = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;

const QUICK_DOMAINS = ["@gmail.com", "@yahoo.com", "@outlook.com", "@icloud.com"];

type Nav = NativeStackNavigationProp<AuthStackParams, "Email">;
type Route = RouteProp<AuthStackParams, "Email">;

export default function EmailScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const [email, setEmail] = useState("");

  useEffect(() => {
    // Phone verification is strictly required before Email step
    if (!route.params?.phoneVerified) {
      navigation.replace("Phone");
    }
  }, [route.params?.phoneVerified, navigation]);
  const [isFocused, setIsFocused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [inlineError, setInlineError] = useState<string | undefined>();
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleChange = (text: string) => {
    setEmail(text.slice(0, 254));
    if (inlineError) setInlineError(undefined);
    if (error) setError(null);
  };

  const handleQuickDomain = (domain: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (!email.includes("@")) {
      setEmail((prev) => prev.trim() + domain);
    } else {
      const prefix = email.split("@")[0];
      setEmail(prefix + domain);
    }
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
      navigation.navigate("OTPVerify", {
        phoneNumber: clean,
        masked: res.email,
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

        <Text style={styles.title}>Your email address</Text>
        <Text style={styles.sub}>We'll send a 6-digit verification code.</Text>
      </View>

      {/* Input Section with Peeking Mascot */}
      <View style={styles.inputSection}>
        <PeekingHeartMascot
          isFocused={isFocused}
          textLength={email.length}
          maxLength={24}
        />

        <View
          style={[
            styles.inputBox,
            isFocused && styles.inputBoxFocused,
            inlineError ? styles.inputBoxError : null,
          ]}
        >
          <Text style={styles.inputIcon}>✉</Text>
          <TextInput
            style={styles.textInput}
            value={email}
            onChangeText={handleChange}
            placeholder="you@gmail.com"
            placeholderTextColor={colors.muted}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoFocus
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
          />
        </View>

        {inlineError && <Text style={styles.errorText}>{inlineError}</Text>}
      </View>

      {/* Quick Domain Suggestion Pills */}
      <View style={styles.domainPillsRow}>
        {QUICK_DOMAINS.map((domain) => (
          <TouchableOpacity
            key={domain}
            style={styles.domainPill}
            onPress={() => handleQuickDomain(domain)}
            activeOpacity={0.8}
          >
            <Text style={styles.domainPillText}>{domain}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.domains}>
        Supported: Gmail, Outlook, Yahoo, iCloud, Proton, Zoho, Rediffmail
      </Text>

      {/* CTA Button with 2px Black Border & Click Animation */}
      <View style={styles.cta}>
        <PrimaryButton
          label="Send Verification Code"
          onPress={handleSend}
          loading={loading}
          disabled={loading || email.trim().length === 0}
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
  },
  inputSection: {
    position: "relative",
    marginTop: 20,
    marginBottom: spacing.md,
  },
  inputBox: {
    flexDirection: "row",
    alignItems: "center",
    height: 60,
    borderRadius: radii.full,
    borderWidth: 2,
    borderColor: "#1C1C1E",
    backgroundColor: colors.white,
    paddingHorizontal: spacing.base,
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
  inputBoxError: {
    borderColor: colors.red,
  },
  inputIcon: {
    fontSize: 18,
    color: colors.mid,
    marginRight: spacing.sm,
  },
  textInput: {
    flex: 1,
    fontFamily: "Outfit_600SemiBold",
    fontSize: 17,
    color: colors.dark,
    height: "100%",
  },
  errorText: {
    ...typography.bodySmall,
    color: colors.red,
    marginTop: spacing.xs,
    marginLeft: spacing.sm,
  },
  domainPillsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  domainPill: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radii.full,
    borderWidth: 1.5,
    borderColor: "#1C1C1E",
    backgroundColor: colors.white,
    shadowColor: "#1C1C1E",
    shadowOffset: { width: 0, height: 1.5 },
    shadowOpacity: 0.08,
    elevation: 1,
  },
  domainPillText: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 12,
    color: colors.dark,
  },
  domains: {
    ...typography.bodySmall,
    color: colors.muted,
    lineHeight: 18,
  },
  cta: {
    flex: 1,
    justifyContent: "flex-end",
    paddingBottom: 40,
  },
});
