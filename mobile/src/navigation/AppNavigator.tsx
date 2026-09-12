/**
 * App Navigator — React Navigation 6
 * Routes based on auth state: loading → unauthenticated → onboarding → authenticated
 * 4 bottom tabs: Feed, Likes, Chats, Profile
 */

import React, { useEffect, useRef, useCallback } from "react";
import { View, ActivityIndicator, StyleSheet, Linking as RNLinking } from "react-native";
import { NavigationContainer, createNavigationContainerRef } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import * as Linking from "expo-linking";
import { colors } from "../theme/tokens";
import { useAuthStore } from "../store/authStore";
import {
  registerForPushNotificationsAsync,
  setupNotificationListeners,
  checkInitialNotificationResponse,
} from "../services/notifications";

// Auth screens
import SplashScreen from "../screens/auth/SplashScreen";
import WelcomeScreen from "../screens/auth/WelcomeScreen";
import PhoneScreen from "../screens/auth/PhoneScreen";
import OTPVerifyScreen from "../screens/auth/OTPVerifyScreen";
import EmailScreen from "../screens/auth/EmailScreen";
import AuthMethodScreen from "../screens/auth/AuthMethodScreen";

// Onboarding screens
import OnboardingNavigator from "../screens/onboarding/OnboardingNavigator";

// Main app screens
import FeedScreen from "../screens/main/FeedScreen";
import LikesScreen from "../screens/main/LikesScreen";
import ChatsScreen from "../screens/main/ChatsScreen";
import ProfileScreen from "../screens/main/ProfileScreen";
import ChatScreen from "../screens/main/ChatScreen";
import SettingsScreen from "../screens/main/SettingsScreen";
import SubscriptionsScreen from "../screens/main/SubscriptionsScreen";
import DeleteAccountScreen from "../screens/main/DeleteAccountScreen";
import EditProfileScreen from "../screens/main/EditProfileScreen";

// Icons (SVG inline — no external icon lib)
import { OrbitIcon, HeartIcon, ChatIcon, PersonIcon } from "../components/core/Icons";

// ── Stack param types ─────────────────────────────────────────────────────────

export type AuthStackParams = {
  Splash: undefined;
  Welcome: undefined;
  AuthMethod: undefined;
  Phone: undefined;
  OTPVerify: { phoneNumber: string; masked: string; mode?: "phone" | "email" };
  Email: undefined;
  EmailOTPVerify: { email: string; masked: string };
};

export type OnboardingStackParams = {
  Onboarding: undefined;
};

export type MainTabParams = {
  Feed: undefined;
  Likes: undefined;
  Chats: undefined;
  Profile: undefined;
};

export type MainStackParams = {
  MainTabs: undefined;
  Chat: { matchId: string; otherUser: { id: string; first_name: string; photo_url?: string | null; is_online?: boolean } };
  Subscriptions: undefined;
  Settings: undefined;
  DeleteAccount: undefined;
  EditProfile: undefined;
};

const AuthStack = createNativeStackNavigator<AuthStackParams>();
const MainTab = createBottomTabNavigator<MainTabParams>();
const MainStack = createNativeStackNavigator<MainStackParams>();

// ── Auth navigator ────────────────────────────────────────────────────────────

function AuthNavigator() {
  return (
    <AuthStack.Navigator
      screenOptions={{ headerShown: false, animation: "fade" }}
      initialRouteName="Splash"
    >
      <AuthStack.Screen name="Splash" component={SplashScreen} />
      <AuthStack.Screen name="Welcome" component={WelcomeScreen} />
      <AuthStack.Screen name="AuthMethod" component={AuthMethodScreen} />
      <AuthStack.Screen name="Phone" component={PhoneScreen} />
      <AuthStack.Screen name="OTPVerify" component={OTPVerifyScreen} />
      <AuthStack.Screen name="Email" component={EmailScreen} />
      <AuthStack.Screen
        name="EmailOTPVerify"
        component={OTPVerifyScreen}
        initialParams={{ email: "", masked: "" }}
      />
    </AuthStack.Navigator>
  );
}

// ── Main tab navigator ────────────────────────────────────────────────────────

function MainNavigator() {
  return (
    <MainTab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.white,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          height: 64,
          paddingBottom: 8,
          paddingTop: 8,
        },
        tabBarActiveTintColor: colors.saffron,
        tabBarInactiveTintColor: colors.mid,
        tabBarLabelStyle: {
          fontFamily: "Inter_400Regular",
          fontSize: 11,
          marginTop: 2,
        },
      }}
    >
      <MainTab.Screen
        name="Feed"
        component={FeedScreen}
        options={{
          tabBarLabel: "Discover",
          tabBarIcon: ({ color }) => <OrbitIcon color={color} />,
        }}
      />
      <MainTab.Screen
        name="Likes"
        component={LikesScreen}
        options={{
          tabBarLabel: "Likes",
          tabBarIcon: ({ color }) => <HeartIcon color={color} />,
        }}
      />
      <MainTab.Screen
        name="Chats"
        component={ChatsScreen}
        options={{
          tabBarLabel: "Chats",
          tabBarIcon: ({ color }) => <ChatIcon color={color} />,
        }}
      />
      <MainTab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          tabBarLabel: "Profile",
          tabBarIcon: ({ color }) => <PersonIcon color={color} />,
        }}
      />
    </MainTab.Navigator>
  );
}

// ── Main stack — wraps tab nav + modal screens ───────────────────────────────

function MainStackNavigator() {
  return (
    <MainStack.Navigator screenOptions={{ headerShown: false }}>
      <MainStack.Screen name="MainTabs" component={MainNavigator} />
      <MainStack.Screen
        name="Chat"
        component={ChatScreen}
        options={{ animation: "slide_from_right" }}
      />
      <MainStack.Screen
        name="Subscriptions"
        component={SubscriptionsScreen}
        options={{ animation: "slide_from_bottom" }}
      />
      <MainStack.Screen
        name="Settings"
        component={SettingsScreen}
        options={{ animation: "slide_from_right" }}
      />
      <MainStack.Screen
        name="DeleteAccount"
        component={DeleteAccountScreen}
        options={{ animation: "slide_from_right" }}
      />
      <MainStack.Screen
        name="EditProfile"
        component={EditProfileScreen}
        options={{ animation: "slide_from_right" }}
      />
    </MainStack.Navigator>
  );
}

// ── Root navigator — routes by auth state ─────────────────────────────────────

function LoadingScreen() {
  return (
    <View style={styles.loading}>
      <ActivityIndicator size="large" color={colors.saffron} />
    </View>
  );
}

const linking = {
  prefixes: [Linking.createURL("/"), "jainune://", "https://jainune.com", "https://*.jainune.com"],
  config: {
    screens: {
      Chat: "chat/:matchId",
      Subscriptions: "subscriptions",
      Settings: "settings",
      EditProfile: "profile/edit",
      MainTabs: {
        screens: {
          Feed: "feed",
          Likes: "likes",
          Chats: "chats",
          Profile: "profile",
        },
      },
    },
  },
};

export const navigationRef = createNavigationContainerRef();

export default function AppNavigator() {
  const authState = useAuthStore((s) => s.state);
  const pendingIntentRef = useRef<{ name: string; params: any } | null>(null);

  const routeOrQueue = useCallback(
    (name: string, params: any) => {
      if (authState === "authenticated" && navigationRef.isReady()) {
        (navigationRef as any).navigate(name, params);
        pendingIntentRef.current = null;
      } else {
        // Queue intent until authenticated navigation stack mounts (SECOND-014)
        pendingIntentRef.current = { name, params };
      }
    },
    [authState]
  );

  useEffect(() => {
    if (authState === "authenticated") {
      registerForPushNotificationsAsync();
      if (navigationRef.isReady() && pendingIntentRef.current) {
        const { name, params } = pendingIntentRef.current;
        pendingIntentRef.current = null;
        (navigationRef as any).navigate(name, params);
      }
    }
  }, [authState]);

  const handleDeepLinkUrl = useCallback(
    (url: string) => {
      try {
        const parsed = Linking.parse(url);
        const path = (parsed.path ?? "").replace(/^\/+/, "");
        if (!path) return;
        if (path.startsWith("chat/")) {
          const matchId = path.split("/")[1];
          if (matchId) {
            routeOrQueue("Chat", { matchId, otherUser: { id: "", first_name: "Match" } });
          }
        } else if (path === "subscriptions") {
          routeOrQueue("Subscriptions", undefined);
        } else if (path === "settings") {
          routeOrQueue("Settings", undefined);
        } else if (path === "profile/edit") {
          routeOrQueue("EditProfile", undefined);
        } else if (path === "likes") {
          routeOrQueue("MainTabs", { screen: "Likes" });
        } else if (path === "chats") {
          routeOrQueue("MainTabs", { screen: "Chats" });
        } else if (path === "profile") {
          routeOrQueue("MainTabs", { screen: "Profile" });
        } else if (path === "feed") {
          routeOrQueue("MainTabs", { screen: "Feed" });
        }
      } catch {}
    },
    [routeOrQueue]
  );

  useEffect(() => {
    // Intercept cold-boot deep link
    RNLinking.getInitialURL()
      .then((url: string | null) => {
        if (url) handleDeepLinkUrl(url);
      })
      .catch(() => {});

    const sub = RNLinking.addEventListener("url", (event: { url: string }) => {
      if (event.url) handleDeepLinkUrl(event.url);
    });

    return () => {
      sub.remove();
    };
  }, [handleDeepLinkUrl]);

  useEffect(() => {
    const cleanup = setupNotificationListeners((name, params) => {
      routeOrQueue(name, params);
    });

    // Check cold-boot notification response
    checkInitialNotificationResponse((name, params) => {
      routeOrQueue(name, params);
    });

    return cleanup;
  }, [routeOrQueue]);

  return (
    <NavigationContainer
      ref={navigationRef}
      linking={linking}
      onReady={() => {
        checkInitialNotificationResponse((name, params) => {
          routeOrQueue(name, params);
        });
        if (authState === "authenticated" && pendingIntentRef.current) {
          const { name, params } = pendingIntentRef.current;
          pendingIntentRef.current = null;
          (navigationRef as any).navigate(name, params);
        }
      }}
    >
      {authState === "loading" && <LoadingScreen />}
      {authState === "unauthenticated" && <AuthNavigator />}
      {authState === "onboarding" && <OnboardingNavigator />}
      {authState === "authenticated" && <MainStackNavigator />}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
  },
});
