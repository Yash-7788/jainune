/**
 * Auth Method Screen — Choose login method
 * Phone OTP, Email OTP, Google Sign-In, Apple Sign-In (iOS mandatory per App Store 4.8)
 * Security: all inputs sanitized, no account enumeration, friendly errors
 */

import React from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Platform,
  StatusBar,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { GoogleSignin } from "@react-native-google-signin/google-signin";
import * as AppleAuthentication from "expo-apple-authentication";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import { PrimaryButton, GhostButton, ErrorToast } from "../../components/core";
import { googleSignIn, appleSignIn } from "../../api/authApi";
import { useAuthStore } from "../../store/authStore";
import { extractError } from "../../api/client";
import type { AuthStackParams } from "../../navigation/AppNavigator";

// Configure Google Sign-In at module level
GoogleSignin.configure({
  webClientId:
    process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ||
    "YOUR_WEB_CLIENT_ID.apps.googleusercontent.com",
  offlineAccess: false,
});

type Nav = NativeStackNavigationProp<AuthStackParams, "AuthMethod">;

export default function AuthMethodScreen() {
  const navigation = useNavigation<Nav>();
  const setAuthenticated = useAuthStore((s) => s.setAuthenticated);
  const [loading, setLoading] = React.useState<"google" | "apple" | null>(null);
  const [error, setError] = React.useState<{ title: string; message: string } | null>(null);

  const handleGoogle = async () => {
    setLoading("google");
    setError(null);
    try {
      await GoogleSignin.hasPlayServices();
      const userInfo: any = await GoogleSignin.signIn();
      const idToken = userInfo?.data?.idToken || userInfo?.idToken;
      if (!idToken) throw new Error("No ID token from Google");

      const data = await googleSignIn(idToken);
      setAuthenticated(data.user_id, data.is_new_user, data.onboarding_completed);
    } catch (err: any) {
      if (err?.code === "12501" || err?.code === "SIGN_IN_CANCELLED") {
        return; // User cancelled
      }
      setError(extractError(err));
    } finally {
      setLoading(null);
    }
  };

  const handleApple = async () => {
    setLoading("apple");
    setError(null);
    try {
      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      const idToken = credential.identityToken;
      if (!idToken) throw new Error("No identity token from Apple");

      const firstName = credential.fullName?.givenName ?? null;
      const data = await appleSignIn(idToken, firstName);
      setAuthenticated(data.user_id, data.is_new_user, data.onboarding_completed);
    } catch (err: unknown) {
      if ((err as { code?: string }).code === "ERR_CANCELED") {
        setLoading(null);
        return; // User cancelled — not an error
      }
      setError(extractError(err));
    } finally {
      setLoading(null);
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

      {error && (
        <ErrorToast title={error.title} message={error.message} visible={!!error} />
      )}

      <View style={styles.header}>
        <Text style={styles.title}>Sign in or create{"\n"}your account</Text>
        <Text style={styles.sub}>Choose how you'd like to continue</Text>
      </View>

      <View style={styles.methods}>
        {/* Phone — primary */}
        <PrimaryButton
          label="Continue with Phone"
          onPress={() => navigation.navigate("Phone")}
        />

        {/* Email */}
        <GhostButton
          label="Continue with Email"
          onPress={() => navigation.navigate("Email")}
          style={{ marginTop: spacing.md }}
        />

        {/* Divider */}
        <View style={styles.divider}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>or</Text>
          <View style={styles.dividerLine} />
        </View>

        {/* Google */}
        <SocialButton
          label="Continue with Google"
          onPress={handleGoogle}
          loading={loading === "google"}
          icon="G"
          iconColor="#4285F4"
        />

        {/* Apple — iOS only (App Store guideline 4.8) */}
        {Platform.OS === "ios" && (
          <AppleAuthentication.AppleAuthenticationButton
            buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
            buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
            cornerRadius={radii.full}
            style={styles.appleBtn}
            onPress={handleApple}
          />
        )}
        {/* Show Apple on Android too via social button for cross-platform users */}
        {Platform.OS === "android" && (
          <SocialButton
            label="Continue with Apple"
            onPress={handleApple}
            loading={loading === "apple"}
            icon=""
            iconColor={colors.dark}
          />
        )}
      </View>

      <Text style={styles.legal}>
        By continuing, you agree to our{" "}
        <Text style={styles.link}>Terms of Service</Text> and{" "}
        <Text style={styles.link}>Privacy Policy</Text>.
      </Text>
    </View>
  );
}

function SocialButton({
  label,
  onPress,
  loading,
  icon,
  iconColor,
}: {
  label: string;
  onPress: () => void;
  loading: boolean;
  icon: string;
  iconColor: string;
}) {
  return (
    <TouchableOpacity
      style={styles.socialBtn}
      onPress={onPress}
      disabled={loading}
      activeOpacity={0.8}
    >
      <Text style={[styles.socialIcon, { color: iconColor }]}>{icon}</Text>
      <Text style={styles.socialLabel}>{loading ? "Signing in..." : label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.base,
    paddingTop: 80,
  },
  header: { marginBottom: spacing.xxl },
  title: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 30,
    lineHeight: 38,
    color: colors.dark,
    marginBottom: spacing.sm,
  },
  sub: { ...typography.body, color: colors.mid },
  methods: { flex: 1 },
  divider: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: spacing.xl,
    gap: spacing.sm,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: colors.border },
  dividerText: { ...typography.bodySmall, color: colors.mid },
  socialBtn: {
    height: 52,
    borderRadius: radii.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.white,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    marginBottom: spacing.md,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  socialIcon: { fontFamily: "Outfit_700Bold", fontSize: 18 },
  socialLabel: { ...typography.body, color: colors.dark, fontFamily: "Outfit_600SemiBold" },
  appleBtn: {
    height: 52,
    marginBottom: spacing.md,
  },
  legal: {
    ...typography.bodySmall,
    color: colors.mid,
    textAlign: "center",
    paddingBottom: spacing.xxl,
    lineHeight: 18,
  },
  link: { color: colors.saffron },
});
