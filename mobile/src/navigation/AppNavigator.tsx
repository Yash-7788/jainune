/**
 * App Navigator — React Navigation 6
 * Routes based on auth state: loading → unauthenticated → onboarding → authenticated
 * 4 bottom tabs: Feed, Likes, Chats, Profile
 */

import React, { useEffect } from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { NavigationContainer, createNavigationContainerRef } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import * as Linking from "expo-linking";
import { colors } from "../theme/tokens";
import { useAuthStore } from "../store/authStore";
import { registerForPushNotificationsAsync, setupNotificationListeners } from "../services/notifications";

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
        initialParams={{ phoneNumber: "", masked: "" }}
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

  useEffect(() => {
    if (authState === "authenticated") {
      registerForPushNotificationsAsync();
    }
  }, [authState]);

  useEffect(() => {
    const cleanup = setupNotificationListeners((name, params) => {
      if (navigationRef.isReady()) {
        (navigationRef as any).navigate(name, params);
      }
    });
    return cleanup;
  }, []);

  return (
    <NavigationContainer ref={navigationRef} linking={linking}>
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
