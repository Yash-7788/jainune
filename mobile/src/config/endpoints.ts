import { Platform } from "react-native";

const localApi = Platform.OS === "android"
  ? "http://10.0.2.2:8000/v1"
  : "http://localhost:8000/v1";

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_URL ||
  (__DEV__ ? localApi : "https://api.jainune.com/v1")
).replace(/\/+$/, "");

// Keep chat on the same environment as REST unless explicitly configured.
export const WS_BASE_URL = (
  process.env.EXPO_PUBLIC_WS_URL ||
  `${API_BASE_URL.replace(/^http/, "ws")}/ws/chat`
).replace(/\/+$/, "");
