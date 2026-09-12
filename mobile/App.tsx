/**
 * Jainune App Entry Point — Phase 8 Security-Hardened
 *
 * Boot sequence:
 * 1. Load fonts (required before any UI renders)
 * 2. runSecurityBoot() — integrity checks (root, Frida, debugger, APK tamper)
 * 3. If violation: render SecurityBlockScreen (non-dismissible)
 * 4. If clean: wire session-expired callback, call initSession(), render AppNavigator
 *
 * Session expiry: client.ts fires _onSessionExpired → authStore.logout() → navigator
 * auto-routes to auth stack. No manual handling needed in screens.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import {
  useFonts,
  Outfit_800ExtraBold,
  Outfit_700Bold,
  Outfit_600SemiBold,
} from "@expo-google-fonts/outfit";
import { Inter_400Regular, Inter_700Bold } from "@expo-google-fonts/inter";
import * as SplashScreenExpo from "expo-splash-screen";
import AppNavigator from "./src/navigation/AppNavigator";
import SecurityBlockScreen from "./src/screens/security/SecurityBlockScreen";
import ErrorBoundary from "./src/components/core/ErrorBoundary";
import { runSecurityBoot } from "./src/security/securityBoot";
import { setSessionExpiredCallback } from "./src/api/client";
import { useAuthStore } from "./src/store/authStore";
import { syncPendingPayment } from "./src/services/billingService";

SplashScreenExpo.preventAutoHideAsync();

type BootState =
  | { status: "pending" }
  | { status: "passed" }
  | { status: "blocked"; reason: string };

export default function App() {
  const [fontsLoaded] = useFonts({
    Outfit_800ExtraBold,
    Outfit_700Bold,
    Outfit_600SemiBold,
    Inter_400Regular,
    Inter_700Bold,
  });

  const [boot, setBoot] = useState<BootState>({ status: "pending" });
  const sessionCallbackSet = useRef(false);

  // Run security checks once fonts are loaded
  useEffect(() => {
    if (!fontsLoaded) return;

    runSecurityBoot().then((result) => {
      if (result.passed) {
        setBoot({ status: "passed" });
      } else {
        setBoot({ status: "blocked", reason: result.reason });
      }
    });
  }, [fontsLoaded]);

  // Wire session-expired callback and initialize session (once, after boot passes)
  useEffect(() => {
    if (boot.status !== "passed" || sessionCallbackSet.current) return;
    sessionCallbackSet.current = true;

    // When refresh token is exhausted, client calls this → authStore routes to login
    setSessionExpiredCallback(() => {
      useAuthStore.getState().logout();
    });

    // Restore existing session from SecureStore
    useAuthStore.getState().initSession();

    // Reconcile interrupted pending payments across app boots
    syncPendingPayment().catch(() => {});
  }, [boot.status]);

  const onLayoutRootView = useCallback(async () => {
    if (fontsLoaded && boot.status !== "pending") {
      await SplashScreenExpo.hideAsync();
    }
  }, [fontsLoaded, boot.status]);

  // Keep splash visible until fonts AND security boot are done
  if (!fontsLoaded || boot.status === "pending") return null;

  if (boot.status === "blocked") {
    return (
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <View style={{ flex: 1 }} onLayout={onLayoutRootView}>
            <SecurityBlockScreen reason={boot.reason} />
          </View>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    );
  }

  return (
    <ErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <View style={{ flex: 1 }} onLayout={onLayoutRootView}>
            <AppNavigator />
          </View>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}
