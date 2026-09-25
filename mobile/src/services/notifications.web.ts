import * as SecureStore from "../utils/secureStorage";
import { apiGet, apiPost } from "../api/client";

export type WebPushStatus = "checking" | "unsupported" | "install_required" | "unconfigured" | "disabled" | "denied" | "enabled";

let publicKey: string | null = null;
const isStandalone = () =>
  (window.navigator as Navigator & { standalone?: boolean }).standalone === true ||
  window.matchMedia("(display-mode: standalone)").matches;

function supportsWebPush(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function loadPublicKey(): Promise<string> {
  if (publicKey) return publicKey;
  const response = await apiGet<{ public_key: string }>("/users/me/web-push/config");
  if (!response.success || !response.data?.public_key) throw new Error("Web Push is not configured.");
  publicKey = response.data.public_key;
  return publicKey;
}

function decodePublicKey(key: string): Uint8Array<ArrayBuffer> {
  const base64 = key.replace(/-/g, "+").replace(/_/g, "/");
  const binary = window.atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function getRegistration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/push-sw.js", { scope: "/" });
}

export async function getOrCreateDeviceId(): Promise<string> {
  let id = await SecureStore.getItemAsync("jainune_device_id");
  if (!id) {
    id = `web_${crypto.randomUUID()}`;
    await SecureStore.setItemAsync("jainune_device_id", id);
  }
  return id;
}

async function subscribeAndRegister(): Promise<string> {
  const key = await loadPublicKey();
  const registration = await getRegistration();
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodePublicKey(key),
    });
  }
  const serialized = subscription.toJSON();
  if (!serialized.endpoint || !serialized.keys?.p256dh || !serialized.keys?.auth) {
    throw new Error("The browser did not return a usable push subscription.");
  }
  const response = await apiPost("/users/me/web-push/subscriptions", {
    endpoint: serialized.endpoint,
    keys: serialized.keys,
    device_id: await getOrCreateDeviceId(),
  });
  if (!response.success) throw new Error("Could not register notifications with Jainune.");
  return serialized.endpoint;
}

export async function getWebPushStatus(): Promise<WebPushStatus> {
  if (/iPhone|iPad|iPod/i.test(navigator.userAgent) && !isStandalone()) return "install_required";
  if (!supportsWebPush()) return "unsupported";
  try {
    await loadPublicKey();
  } catch {
    return "unconfigured";
  }
  if (Notification.permission === "denied") return "denied";
  if (Notification.permission !== "granted") return "disabled";
  const registration = await navigator.serviceWorker.getRegistration("/");
  return (await registration?.pushManager.getSubscription()) ? "enabled" : "disabled";
}

/** Call directly from a tap handler; iOS requires user activation for permission. */
export async function enableWebPushFromGesture(): Promise<void> {
  if (!supportsWebPush()) throw new Error("This browser does not support notifications.");
  if (/iPhone|iPad|iPod/i.test(navigator.userAgent) && !isStandalone()) {
    throw new Error("Add Jainune to your Home Screen, open it there, then enable notifications.");
  }
  if (!publicKey) throw new Error("Notifications are not configured yet. Please try again later.");
  const permission = Notification.permission === "granted"
    ? Promise.resolve("granted")
    : Notification.requestPermission();
  if ((await permission) !== "granted") throw new Error("Notification permission was not granted.");
  await subscribeAndRegister();
}

export async function registerForPushNotificationsAsync(): Promise<string | null> {
  if (!supportsWebPush() || Notification.permission !== "granted") return null;
  try { return await subscribeAndRegister(); } catch { return null; }
}

export async function disableWebPush(): Promise<void> {
  if (!supportsWebPush()) return;
  const registration = await navigator.serviceWorker.getRegistration("/");
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return;
  try {
    await apiPost("/users/me/web-push/unsubscribe", { endpoint: subscription.endpoint });
  } finally {
    await subscription.unsubscribe();
  }
}

export function setupNotificationListeners(_navigate: (name: string, params?: any) => void) {
  return () => {};
}

export async function checkInitialNotificationResponse(
  _navigate: (name: string, params?: any) => void
): Promise<void> {
  // The service worker opens a URL; React Navigation handles the deep link.
}
