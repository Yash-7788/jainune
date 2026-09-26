import { Platform } from "react-native";

const DEV_API_URL = Platform.OS === "android"
  ? "http://10.0.2.2:8000/v1"
  : "http://localhost:8000/v1";

function configuredApiUrl(): string {
  const raw = process.env.EXPO_PUBLIC_API_URL?.trim().replace(/\/+$/, "");
  if (!raw) {
    if (__DEV__) return DEV_API_URL;
    throw new Error("Release build requires EXPO_PUBLIC_API_URL");
  }

  const normalized = raw.endsWith("/v1") ? raw : `${raw}/v1`;
  if (!__DEV__) {
    const parsed = new URL(normalized);
    if (parsed.protocol !== "https:" || parsed.hostname.endsWith(".onrender.com")) {
      throw new Error("Release API endpoint must use HTTPS and must not expose the Render origin");
    }
  }
  return normalized;
}

export const API_V1_URL = configuredApiUrl();
export const API_ORIGIN = API_V1_URL.replace(/\/v1$/, "");

const configuredWsUrl = process.env.EXPO_PUBLIC_WS_URL?.trim().replace(/\/+$/, "");
export const WS_CHAT_URL = configuredWsUrl || `${API_ORIGIN.replace(/^http/, "ws")}/v1/ws/chat`;

if (!__DEV__) {
  const parsed = new URL(WS_CHAT_URL);
  if (parsed.protocol !== "wss:" || parsed.hostname.endsWith(".onrender.com")) {
    throw new Error("Release WebSocket endpoint must use WSS and must not expose the Render origin");
  }
}
