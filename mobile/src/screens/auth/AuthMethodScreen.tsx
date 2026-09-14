/**
 * Auth Method Screen — Choose login method — Jainune
 *
 * Redesigned with:
 * - Floating pixelated red heart with white "Jain" typography at discrete angle
 * - Thick 2px black borders on buttons with click micro-animations and haptics
 * - Official Google multicolor SVG and Apple SVG logos
 * - Resilient Expo Go detection and friendly notices
 * - Clean link to redesigned LegalModal
 */

import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Platform,
  StatusBar,
  NativeModules,
  Animated,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import * as AppleAuthentication from "expo-apple-authentication";
import * as Haptics from "expo-haptics";
import Svg, { Path } from "react-native-svg";
import { colors, spacing, typography, radii } from "../../theme/tokens";
import { PrimaryButton, GhostButton, ErrorToast } from "../../components/core";
import { googleSignIn, appleSignIn } from "../../api/authApi";
import { useAuthStore } from "../../store/authStore";
import { extractError } from "../../api/client";
import LegalModal, { LegalDocType } from "../../components/legal/LegalModal";
import type { AuthStackParams } from "../../navigation/AppNavigator";

// Configure Google Sign-In at module level (safeguarded for Expo Go)
let GoogleSignin: any = null;
try {
  const gModule = require("@react-native-google-signin/google-signin");
  GoogleSignin = gModule?.GoogleSignin || gModule;
  GoogleSignin?.configure?.({
    webClientId:
      process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ||
      "YOUR_WEB_CLIENT_ID.apps.googleusercontent.com",
    offlineAccess: false,
  });
} catch {
  // Native module unavailable in standard Expo Go
}

type Nav = NativeStackNavigationProp<AuthStackParams, "AuthMethod">;

// Official Google Multicolor G Logo
function GoogleLogo({ size = 20 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        fill="#4285F4"
      />
      <Path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <Path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
        fill="#FBBC05"
      />
      <Path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
        fill="#EA4335"
      />
    </Svg>
  );
}

// Official Apple Silhouette Logo
function AppleLogo({ size = 20, color = "#000000" }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 170 170">
      <Path
        d="M150.37 130.25c-2.45 5.66-5.35 10.87-8.71 15.66-4.58 6.53-8.33 11.05-11.22 13.56-4.48 4.12-9.28 6.23-14.42 6.35-3.69 0-8.14-1.05-13.32-3.18-5.19-2.12-9.97-3.17-14.34-3.17-4.58 0-9.49 1.05-14.75 3.17-5.26 2.13-9.5 3.24-12.74 3.35-4.35.13-9.16-1.9-14.42-6.08-3.69-3.08-7.7-7.94-12.04-14.58-6.19-9.52-11.03-20.4-14.54-32.63-3.5-12.23-5.26-23.75-5.26-34.56 0-14.72 3.65-27.12 10.96-37.21 7.3-10.1 16.5-15.26 27.6-15.48 4.79 0 10.15 1.25 16.08 3.75 5.92 2.5 9.94 3.79 12.05 3.87 1.63 0 5.86-1.39 12.68-4.17 6.82-2.77 12.63-3.99 17.43-3.64 13.06.75 23.36 5.66 30.9 14.73-11.53 7.08-17.15 16.92-16.86 29.5.3 9.92 4.13 18.25 11.51 25 3.48 3.16 7.42 5.56 11.83 7.21-2.5 7.4-5.32 14.56-8.47 21.49zm-38.44-106.87c0-7.39 2.65-14.28 7.95-20.67 5.3-6.4 11.75-10.3 19.34-11.71.22 1.3.33 2.55.33 3.75 0 7.39-2.78 14.41-8.34 21.05-5.56 6.64-12.19 10.42-19.89 11.33-.22-1.31-.34-2.56-.34-3.75z"
        fill={color}
      />
    </Svg>
  );
}

export default function AuthMethodScreen() {
  const navigation = useNavigation<Nav>();
  const setAuthenticated = useAuthStore((s) => s.setAuthenticated);
  const [loading, setLoading] = React.useState<"google" | "apple" | null>(null);
  const [error, setError] = React.useState<{ title: string; message: string } | null>(null);
  const [legalDoc, setLegalDoc] = React.useState<LegalDocType | null>(null);

  // Intro entry animations
  const introFade = useRef(new Animated.Value(0)).current;
  const introSlide = useRef(new Animated.Value(24)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(introFade, {
        toValue: 1,
        duration: 550,
        useNativeDriver: true,
      }),
      Animated.spring(introSlide, {
        toValue: 0,
        tension: 85,
        friction: 9,
        useNativeDriver: true,
      }),
    ]).start();
  }, [introFade, introSlide]);

  const handleGoogle = async () => {
    setLoading("google");
    setError(null);
    try {
      const isNativeGoogleLinked = Boolean(
        NativeModules?.RNGoogleSignin &&
        GoogleSignin &&
        typeof GoogleSignin.signIn === "function"
      );

      if (!isNativeGoogleLinked) {
        setError({
          title: "Expo Go Notice",
          message:
            "Google Sign-In uses native Play Services (requires an Expo Dev Client build or standalone APK). In Expo Go, please use Phone or Email login.",
        });
        return;
      }

      // Guard with timeout so unresolved native calls never freeze the UI
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Google Sign-In request timed out.")), 8000)
      );

      await Promise.race([GoogleSignin.hasPlayServices(), timeoutPromise]);
      const userInfo: any = await Promise.race([GoogleSignin.signIn(), timeoutPromise]);
      const idToken = userInfo?.data?.idToken || userInfo?.idToken;
      if (!idToken) throw new Error("No ID token returned from Google.");

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

    if (Platform.OS !== "ios") {
      setError({
        title: "Apple Sign-In",
        message:
          "Apple Sign-In is only available on Apple iOS devices. Please continue with Phone or Email login on Android.",
      });
      setLoading(null);
      return;
    }

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

      {/* Header with Title and Floating Discrete Pixel Heart */}
      <Animated.View
        style={[
          styles.header,
          {
            opacity: introFade,
            transform: [{ translateY: introSlide }],
          },
        ]}
      >
        <Text style={styles.title}>Sign in or create{"\n"}your account</Text>
        <Text style={styles.sub}>Choose how you'd like to continue</Text>
      </Animated.View>

      {/* Methods Card with 2px Black Bordered Buttons & Micro-Animations */}
      <Animated.View
        style={[
          styles.methods,
          {
            opacity: introFade,
            transform: [{ translateY: introSlide }],
          },
        ]}
      >
        {/* Phone — primary with thick black border */}
        <PrimaryButton
          label="Continue with Phone"
          onPress={() => navigation.navigate("Phone")}
        />

        {/* Email with thick black border */}
        <GhostButton
          label="Continue with Email"
          onPress={() => navigation.navigate("Email")}
          style={{ marginTop: spacing.md }}
        />

        {/* Tactile Divider */}
        <View style={styles.divider}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>or</Text>
          <View style={styles.dividerLine} />
        </View>

        {/* Google — Official Multicolor G Logo with 2px Black Border */}
        <SocialButton
          label="Continue with Google"
          onPress={handleGoogle}
          loading={loading === "google"}
          icon={<GoogleLogo size={20} />}
        />

        {/* Apple — Official Apple Logo with 2px Black Border */}
        {Platform.OS === "ios" ? (
          <AppleAuthentication.AppleAuthenticationButton
            buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
            buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
            cornerRadius={radii.full}
            style={styles.appleBtn}
            onPress={handleApple}
          />
        ) : (
          <SocialButton
            label="Continue with Apple"
            onPress={handleApple}
            loading={loading === "apple"}
            icon={<AppleLogo size={20} color="#1C1C1E" />}
          />
        )}
      </Animated.View>

      {/* Footer Legal Terms */}
      <Text style={styles.legal}>
        By continuing, you verify you are 18+ and agree to our{" "}
        <Text style={styles.link} onPress={() => setLegalDoc("terms")}>
          Terms of Service & EULA
        </Text>
        {", "}
        <Text style={styles.link} onPress={() => setLegalDoc("privacy")}>
          Privacy Policy
        </Text>
        {", and "}
        <Text style={styles.link} onPress={() => setLegalDoc("child_safety")}>
          Zero-Tolerance Safety Standards
        </Text>
        .
      </Text>

      <LegalModal
        visible={legalDoc !== null}
        initialDoc={legalDoc ?? "terms"}
        onClose={() => setLegalDoc(null)}
      />
    </View>
  );
}

// ── Tactile Thick-Bordered Social Button with Click Animation ──────────────────

function SocialButton({
  label,
  onPress,
  loading,
  icon,
}: {
  label: string;
  onPress: () => void;
  loading: boolean;
  icon: React.ReactNode;
}) {
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const translateYAnim = useRef(new Animated.Value(0)).current;

  const handlePressIn = () => {
    if (loading) return;
    Animated.parallel([
      Animated.spring(scaleAnim, { toValue: 0.965, tension: 200, friction: 10, useNativeDriver: true }),
      Animated.spring(translateYAnim, { toValue: 2, tension: 200, friction: 10, useNativeDriver: true }),
    ]).start();
  };

  const handlePressOut = () => {
    Animated.parallel([
      Animated.spring(scaleAnim, { toValue: 1, tension: 200, friction: 10, useNativeDriver: true }),
      Animated.spring(translateYAnim, { toValue: 0, tension: 200, friction: 10, useNativeDriver: true }),
    ]).start();
  };

  const handlePress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onPress();
  };

  return (
    <Animated.View style={{ transform: [{ scale: scaleAnim }, { translateY: translateYAnim }] }}>
      <TouchableOpacity
        style={styles.socialBtn}
        onPress={handlePress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={loading}
        activeOpacity={0.92}
      >
        <View style={styles.socialIconWrap}>{icon}</View>
        <Text style={styles.socialLabel}>{loading ? "Signing in..." : label}</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.base,
    paddingTop: 72,
  },
  header: {
    marginBottom: spacing.xl,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  headerTextWrap: {
    flex: 1,
    paddingRight: spacing.sm,
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
  heartBadge: {
    width: 64,
    height: 64,
    alignItems: "center",
    justifyContent: "center",
  },
  methods: {
    flex: 1,
  },
  divider: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: spacing.lg,
    gap: spacing.sm,
  },
  dividerLine: {
    flex: 1,
    height: 1.5,
    backgroundColor: "#1C1C1E",
    opacity: 0.15,
  },
  dividerText: {
    ...typography.bodySmall,
    fontFamily: "Outfit_700Bold",
    color: colors.mid,
  },
  socialBtn: {
    height: 52,
    borderRadius: radii.full,
    borderWidth: 2,
    borderColor: "#1C1C1E",
    backgroundColor: colors.white,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    marginBottom: spacing.md,
    shadowColor: "#1C1C1E",
    shadowOffset: { width: 0, height: 2.5 },
    shadowOpacity: 0.15,
    shadowRadius: 0,
    elevation: 3,
  },
  socialIconWrap: {
    width: 24,
    height: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  socialLabel: {
    fontFamily: "Outfit_700Bold",
    fontSize: 15,
    color: colors.dark,
  },
  appleBtn: {
    height: 52,
    marginBottom: spacing.md,
  },
  legal: {
    ...typography.bodySmall,
    color: colors.mid,
    textAlign: "center",
    paddingBottom: spacing.xl,
    lineHeight: 18,
  },
  link: {
    color: colors.saffron,
    fontFamily: "Outfit_600SemiBold",
  },
});
