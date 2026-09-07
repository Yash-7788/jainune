/**
 * Push Notification Service — Phase 8 / M9-NAV-02
 * Handles push permissions, Expo push token retrieval, and routing on notification tap.
 */

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import * as Device from "expo-constants";
import { apiPost } from "../api/client";

// Foreground presentation options
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

/**
 * Registers device for push notifications and registers token with backend.
 */
export async function registerForPushNotificationsAsync(): Promise<string | null> {
  try {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== "granted") {
      return null;
    }

    // Android channel configuration
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("jainune_default", {
        name: "Jainune Notifications",
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#FF6F00",
      });
    }

    let token: string | null = null;
    try {
      const expoTokenData = await Notifications.getExpoPushTokenAsync();
      token = expoTokenData.data;
    } catch {
      try {
        const deviceTokenData = await Notifications.getDevicePushTokenAsync();
        token = deviceTokenData.data;
      } catch {
        token = null;
      }
    }

    // Send token to backend (non-blocking)
    if (token) {
      apiPost("/users/me/fcm-token", { fcm_token: token }).catch(() => {});
    }

    return token;
  } catch {
    // Non-fatal (e.g. simulator, permissions denied, offline)
    return null;
  }
}

/**
 * Routes a notification response payload to the appropriate screen.
 */
export function handleNotificationRouting(
  response: Notifications.NotificationResponse,
  navigate: (name: string, params?: any) => void
): void {
  try {
    const data = response?.notification?.request?.content?.data;
    if (!data) return;

    if ((data.type === "chat" || data.type === "new_message") && (data.match_id || data.chat_id)) {
      navigate("Chat", {
        matchId: data.match_id || data.chat_id,
        chatId: data.chat_id || data.match_id,
        otherUser: {
          id: data.sender_id || "",
          first_name: data.sender_name || "Match",
          photo_url: data.sender_photo || null,
        },
      });
    } else if (data.type === "match" || data.type === "new_match") {
      if (data.match_id) {
        navigate("Chat", {
          matchId: data.match_id,
          otherUser: {
            id: "",
            first_name: "Match",
            photo_url: null,
          },
        });
      } else {
        navigate("MainTabs", { screen: "Likes" });
      }
    } else if (data.type === "new_like" || data.type === "super_connect") {
      navigate("MainTabs", { screen: "Likes" });
    } else if (data.type === "momentum" || data.type === "match_expiring") {
      navigate("MainTabs", { screen: "Chats" });
    } else if (data.type === "subscription" || data.type === "billing") {
      navigate("Subscriptions");
    }
  } catch {}
}

/**
 * Handles cold-boot notification tap when app was completely terminated.
 */
export async function checkInitialNotificationResponse(
  navigate: (name: string, params?: any) => void
): Promise<void> {
  try {
    const response = await Notifications.getLastNotificationResponseAsync();
    if (response) {
      handleNotificationRouting(response, navigate);
    }
  } catch {}
}

/**
 * Listens for user tapping a push notification while app is running or backgrounded.
 */
export function setupNotificationListeners(navigate: (name: string, params?: any) => void) {
  const responseSubscription = Notifications.addNotificationResponseReceivedListener((response) => {
    handleNotificationRouting(response, navigate);
  });

  return () => {
    responseSubscription.remove();
  };
}
