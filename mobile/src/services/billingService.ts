/**
 * Decoupled Billing Architecture Service — Jainune
 *
 * Implements Google Play Billing (react-native-iap) for Android builds
 * and isolates Razorpay Hosted Web Checkout for iOS PWA and Web builds.
 *
 * Directives:
 * - Google Play Developer policy strictly forbids third-party payment SDKs inside Android apps for digital goods.
 * - Razorpay checkout is isolated to Web/PWA builds only.
 */

import { Platform, Linking } from "react-native";
import * as SecureStore from "../utils/secureStorage";
import { apiPost } from "../api/client";
import {
  createSubscriptionOrder,
  syncSubscriptionOrder,
  SubscriptionPlan,
} from "../api/profileApi";

// Safe dynamic loader for react-native-iap (prevents crashes in Expo Go or Web)
let RNIap: any = null;
try {
  RNIap = require("react-native-iap");
} catch {
  // Native module unavailable in Expo Go or Web environments
}

export type BillingProvider = "play_billing" | "web_razorpay";

export interface PurchaseResult {
  success: boolean;
  activated?: boolean;
  pending_verification?: boolean;
  message?: string;
  expires_at?: string;
  error?: string;
  cancelled?: boolean;
}

export const ANDROID_SKUS = [
  "jainune_base_399",
  "jainune_premium_799",
  "jainune_ultra_1499",
  "arcade_spins_3",
  "arcade_spins_10",
  "rose_single_49",
];

const PENDING_PAYMENT_KEY = "jainune_pending_payment";
const PENDING_PAYMENTS_MAP_KEY = "jainune_pending_payments_map";

export interface PendingPayment {
  order_id: string;
  payment_id: string;
  signature: string;
  plan_id?: string;
  timestamp: number;
}

export async function savePendingPayment(payment: PendingPayment): Promise<void> {
  const all = await getAllPendingPayments();
  all[payment.order_id] = payment;
  await SecureStore.setItemAsync(PENDING_PAYMENTS_MAP_KEY, JSON.stringify(all));
  await SecureStore.setItemAsync(PENDING_PAYMENT_KEY, JSON.stringify(payment));
}

export async function getAllPendingPayments(): Promise<Record<string, PendingPayment>> {
  try {
    const raw = await SecureStore.getItemAsync(PENDING_PAYMENTS_MAP_KEY);
    if (raw) return JSON.parse(raw);
    const legacy = await SecureStore.getItemAsync(PENDING_PAYMENT_KEY);
    if (legacy) {
      const parsed = JSON.parse(legacy);
      if (parsed?.order_id) return { [parsed.order_id]: parsed };
    }
  } catch {}
  return {};
}

export async function getPendingPayment(): Promise<PendingPayment | null> {
  try {
    const all = await getAllPendingPayments();
    const values = Object.values(all);
    return values.length > 0 ? values[values.length - 1] : null;
  } catch {
    return null;
  }
}

export async function clearPendingPayment(orderId?: string): Promise<void> {
  try {
    if (!orderId) {
      await SecureStore.deleteItemAsync(PENDING_PAYMENT_KEY);
      await SecureStore.deleteItemAsync(PENDING_PAYMENTS_MAP_KEY);
    } else {
      const all = await getAllPendingPayments();
      delete all[orderId];
      if (Object.keys(all).length === 0) {
        await SecureStore.deleteItemAsync(PENDING_PAYMENTS_MAP_KEY);
        await SecureStore.deleteItemAsync(PENDING_PAYMENT_KEY);
      } else {
        await SecureStore.setItemAsync(PENDING_PAYMENTS_MAP_KEY, JSON.stringify(all));
      }
    }
  } catch {}
}

let isSyncingPending = false;

export async function syncPendingPayment(targetOrderId?: string): Promise<PurchaseResult> {
  if (isSyncingPending) return { success: false };
  isSyncingPending = true;
  try {
    const all = await getAllPendingPayments();
    const pendingList = Object.values(all);
    if (pendingList.length === 0) return { success: false };

    for (const pending of pendingList) {
      if (targetOrderId && pending.order_id !== targetOrderId) continue;
      try {
        const syncRes = await syncSubscriptionOrder(pending.order_id);
        if (syncRes.activated) {
          await clearPendingPayment(pending.order_id);
          return {
            success: true,
            activated: true,
            expires_at: syncRes.expires_at,
          };
        }
      } catch {}

      if (Date.now() - (pending.timestamp || 0) > 86400000) {
        await clearPendingPayment(pending.order_id);
      }
    }
    return { success: false };
  } finally {
    isSyncingPending = false;
  }
}

/**
 * Initializes native billing bridge on Android.
 */
export async function initializeBilling(): Promise<void> {
  if (Platform.OS === "android" && RNIap && typeof RNIap.initConnection === "function") {
    try {
      await RNIap.initConnection();
      if (typeof RNIap.flushFailedPurchasesCachedAsPendingAndroid === "function") {
        await RNIap.flushFailedPurchasesCachedAsPendingAndroid();
      }
    } catch {}
  }
}

const purchasesInFlight = new Map<string, Promise<PurchaseResult>>();

async function verifyAndFinishAndroidPurchase(purchase: any, sku: string): Promise<PurchaseResult> {
  if (!purchase?.purchaseToken || !purchase?.productId) {
    throw new Error("Google Play did not return a purchase receipt.");
  }
  if (purchase.purchaseStateAndroid != null && purchase.purchaseStateAndroid !== 1) {
    return {
      success: false,
      pending_verification: true,
      message: "Google Play is still processing this purchase. It will be restored when approved.",
    };
  }
  const verification = await apiPost<{ activated: boolean; expires_at?: string }>(
    "/subscriptions/verify-google-play",
    {
      orderId: purchase.orderId || purchase.transactionId || purchase.purchaseToken,
      packageName: purchase.packageNameAndroid || "com.jainune.app",
      productId: purchase.productId || sku,
      purchaseTime: purchase.transactionDate || Date.now(),
      purchaseToken: purchase.purchaseToken,
    }
  );
  if (!verification.success || !verification.data?.activated) {
    throw new Error("Google Play purchase verification failed.");
  }
  const isConsumable = sku.startsWith("arcade_") || sku.startsWith("rose_") || sku.startsWith("slingshot_");
  if ((isConsumable || !purchase.isAcknowledgedAndroid) && typeof RNIap.finishTransaction === "function") {
    await RNIap.finishTransaction({
      purchase,
      isConsumable,
    });
  }
  return { success: true, activated: true, expires_at: verification.data.expires_at };
}

function processAndroidPurchase(purchase: any, sku: string): Promise<PurchaseResult> {
  const token = purchase?.purchaseToken;
  if (!token) return verifyAndFinishAndroidPurchase(purchase, sku);
  const existing = purchasesInFlight.get(token);
  if (existing) return existing;
  const task = verifyAndFinishAndroidPurchase(purchase, sku).finally(() => {
    purchasesInFlight.delete(token);
  });
  purchasesInFlight.set(token, task);
  return task;
}

export function setupAndroidPurchaseListener(): () => void {
  if (Platform.OS !== "android" || !RNIap?.purchaseUpdatedListener) return () => {};
  const listener = RNIap.purchaseUpdatedListener((purchase: any) => {
    if (purchase?.purchaseToken && purchase?.productId) {
      processAndroidPurchase(purchase, purchase.productId).catch(() => {});
    }
  });
  return () => listener?.remove?.();
}

/** Reconcile completed but unacknowledged purchases after an interrupted checkout. */
export async function reconcileAndroidPurchases(): Promise<void> {
  if (Platform.OS !== "android" || !RNIap?.getAvailablePurchases) return;
  await initializeBilling();
  const purchases: any[] = await RNIap.getAvailablePurchases();
  for (const purchase of purchases) {
    if (!purchase?.purchaseToken || !purchase?.productId) continue;
    try {
      await processAndroidPurchase(purchase, purchase.productId);
    } catch {
      // Retain the Play purchase for the next attempt; never acknowledge before verification.
    }
  }
}

/**
 * Executes native Google Play purchase on Android.
 */
export async function purchaseAndroidPlan(sku: string): Promise<PurchaseResult> {
  try {
    if (RNIap && (typeof RNIap.requestPurchase === "function" || typeof RNIap.requestSubscription === "function")) {
      const isSub = sku.startsWith("jainune_") || sku.startsWith("gold_") || sku.startsWith("platinum_");
      await RNIap.initConnection();
      let purchase: any;
      if (isSub && typeof RNIap.requestSubscription === "function") {
        const products: any[] = await RNIap.getSubscriptions({ skus: [sku] });
        const product = products.find((item) => item.productId === sku);
        const offers: any[] = product?.subscriptionOfferDetails || [];
        const offer = offers.find((item) => item.offerId == null && item.offerToken) ||
          offers.find((item) => item.offerToken);
        if (!offer) throw new Error("This Google Play subscription is not available yet.");
        purchase = await RNIap.requestSubscription({
          subscriptionOffers: [{ sku, offerToken: offer.offerToken }],
        });
      } else {
        const products: any[] = await RNIap.getProducts({ skus: [sku] });
        if (!products.some((item) => item.productId === sku)) {
          throw new Error("This Google Play item is not available yet.");
        }
        purchase = await RNIap.requestPurchase({ skus: [sku] });
      }

      if (Array.isArray(purchase)) {
        purchase = purchase[0];
      }

      if (!purchase) {
        return {
          success: false,
          pending_verification: true,
          message: "Google Play is processing this purchase.",
        };
      }
      return await processAndroidPurchase(purchase, sku);
    }

    throw new Error("PLAY_BILLING_UNAVAILABLE");
  } catch (err: any) {
    if (err?.code === "E_USER_CANCELLED" || err?.code === 2) {
      return { success: false, cancelled: true };
    }
    throw err;
  }
}

/**
 * Launches standalone Razorpay Web Checkout for iOS PWA and desktop web users.
 */
export async function launchWebPayment(planId: string): Promise<void> {
  const order = await createSubscriptionOrder(planId);
  await savePendingPayment({
    order_id: order.order_id,
    payment_id: "",
    signature: "",
    plan_id: planId,
    timestamp: Date.now(),
  });
  const apiBase =
    process.env.EXPO_PUBLIC_API_URL?.replace(/\/v1\/?$/, "") ||
    "https://jainune-backend-api.onrender.com";
  const returnOrigin = typeof window !== "undefined" ? window.location.origin : "";
  const checkoutUrl = `${apiBase}/v1/payments/razorpay/checkout?order_id=${encodeURIComponent(order.order_id)}&return_origin=${encodeURIComponent(returnOrigin)}`;

  if (typeof window !== "undefined" && window.location) {
    window.location.href = checkoutUrl;
  } else {
    await Linking.openURL(checkoutUrl);
  }
}

/**
 * Purchases a subscription plan adhering to decoupled platform pathways:
 * - Android: Native Google Play Billing (react-native-iap)
 * - iOS PWA / Web: Standalone Razorpay Web Checkout (zero Apple tax)
 */
export async function purchaseSubscription(
  plan: SubscriptionPlan,
  userId?: string
): Promise<PurchaseResult> {
  if (Platform.OS === "android") {
    return await purchaseAndroidPlan(plan.plan_id);
  }

  // iOS PWA or Web browser checkout
  await launchWebPayment(plan.plan_id);
  return {
    success: false,
    pending_verification: true,
    message: "Opening secure Razorpay web checkout...",
  };
}

/**
 * Purchases consumable arcade spins adhering to platform billing pathways.
 */
export async function purchaseArcadeRolls(
  productId: string,
  _label: string,
  userId?: string
): Promise<PurchaseResult> {
  if (Platform.OS === "android") {
    return await purchaseAndroidPlan(productId);
  }

  // iOS PWA or Web browser checkout
  await launchWebPayment(productId);
  return {
    success: false,
    pending_verification: true,
    message: "Opening secure Razorpay web checkout...",
  };
}
