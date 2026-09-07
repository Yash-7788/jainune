/**
 * Unified Billing Gateway Service
 *
 * Implements store compliance abstraction for Google Play Billing / Apple StoreKit
 * and India User Choice Billing (UCB) / Alternative Billing (Razorpay).
 */

import { Platform, Linking } from "react-native";
let RazorpayCheckout: any = null;
try {
  const rnrp = require("react-native-razorpay");
  RazorpayCheckout = rnrp?.default || rnrp;
} catch {
  // Native module unavailable in Expo Go
}

import * as SecureStore from "expo-secure-store";
import {
  createSubscriptionOrder,
  verifySubscriptionPayment,
  syncSubscriptionOrder,
  createArcadeOrder,
  verifyArcadePayment,
  SubscriptionPlan,
} from "../api/profileApi";
import { validatePaymentResponse } from "../security/inputValidation";
import { colors } from "../theme/tokens";

export type BillingProvider = "play_billing" | "app_store" | "razorpay" | "web";

export interface PurchaseResult {
  success: boolean;
  activated?: boolean;
  pending_verification?: boolean;
  message?: string;
  expires_at?: string;
  error?: string;
}

const PENDING_PAYMENT_KEY = "jainune_pending_payment";

export interface PendingPayment {
  order_id: string;
  payment_id: string;
  signature: string;
  plan_id?: string;
  timestamp: number;
}

export async function savePendingPayment(payment: PendingPayment): Promise<void> {
  try {
    await SecureStore.setItemAsync(PENDING_PAYMENT_KEY, JSON.stringify(payment));
  } catch {}
}

export async function getPendingPayment(): Promise<PendingPayment | null> {
  try {
    const raw = await SecureStore.getItemAsync(PENDING_PAYMENT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export async function clearPendingPayment(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(PENDING_PAYMENT_KEY);
  } catch {}
}

export async function syncPendingPayment(): Promise<PurchaseResult> {
  const pending = await getPendingPayment();
  if (pending) {
    if (pending.payment_id && pending.signature) {
      try {
        const verifyRes = await verifySubscriptionPayment({
          razorpay_order_id: pending.order_id,
          razorpay_payment_id: pending.payment_id,
          razorpay_signature: pending.signature,
        });
        await clearPendingPayment();
        return {
          success: true,
          activated: verifyRes.activated,
          expires_at: verifyRes.expires_at,
        };
      } catch {}
    }

    try {
      const syncRes = await syncSubscriptionOrder(pending.order_id);
      if (syncRes.activated) {
        await clearPendingPayment();
        return {
          success: true,
          activated: true,
          expires_at: syncRes.expires_at,
        };
      }
    } catch {}

    // Expire stale pending payment records older than 24 hours
    if (Date.now() - (pending.timestamp || 0) > 86400000) {
      await clearPendingPayment();
    }
  }

  return { success: false };
}

export const ACTIVE_BILLING_PROVIDER: BillingProvider =
  (process.env.EXPO_PUBLIC_BILLING_PROVIDER as BillingProvider) ||
  (Platform.OS === "ios" ? "app_store" : "play_billing");

/**
 * Purchases a subscription plan adhering to Google Play / Apple StoreKit / User Choice Billing pathways.
 */
export async function purchaseSubscription(
  plan: SubscriptionPlan
): Promise<PurchaseResult> {
  // Pathway 1: Apple StoreKit IAP (Strictly required on iOS per Apple Guideline 3.1.1)
  if (Platform.OS === "ios" || ACTIVE_BILLING_PROVIDER === "app_store") {
    try {
      // If native IAP bridge is available, initiate StoreKit transaction
      const NativeIap = (global as any).RNIap || null;
      if (NativeIap && typeof NativeIap.requestSubscription === "function") {
        const purchase = await NativeIap.requestSubscription({ sku: plan.plan_id });
        return {
          success: true,
          activated: true,
          expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
        };
      }
      // StoreKit sandbox fallback allowed strictly in __DEV__ (Expo Go)
      if (__DEV__) {
        await createSubscriptionOrder(plan.plan_id);
        return {
          success: true,
          activated: true,
          expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
        };
      }
      throw new Error("STOREKIT_MODULE_UNAVAILABLE");
    } catch (err: any) {
      if (err?.code === "E_USER_CANCELLED") {
        return { success: false, error: "CANCELLED" };
      }
      throw err;
    }
  }

  // Pathway 2: Android (Google Play Billing / User Choice Billing / Razorpay alternative)
  try {
    const order = await createSubscriptionOrder(plan.plan_id);

    // Persist pending order ID before launching native UPI / webview
    await savePendingPayment({
      order_id: order.order_id,
      payment_id: "",
      signature: "",
      plan_id: plan.plan_id,
      timestamp: Date.now(),
    });

    if (!RazorpayCheckout || typeof RazorpayCheckout.open !== "function") {
      throw new Error("BILLING_MODULE_UNAVAILABLE");
    }

    const paymentResult = await RazorpayCheckout.open({
      key: order.razorpay_key,
      order_id: order.order_id,
      amount: order.amount_paisa,
      currency: order.currency,
      name: "Jainune+",
      description: `${plan.label} Subscription`,
      prefill: {},
      theme: { color: colors.saffron },
      modal: { backdropclose: false },
    });

    if (!validatePaymentResponse(paymentResult)) {
      throw new Error("INVALID_PAYMENT_RESPONSE");
    }

    // Persist receipt in SecureStore immediately before network verification
    await savePendingPayment({
      order_id: paymentResult.razorpay_order_id,
      payment_id: paymentResult.razorpay_payment_id,
      signature: paymentResult.razorpay_signature,
      plan_id: plan.plan_id,
      timestamp: Date.now(),
    });

    try {
      const verifyRes = await verifySubscriptionPayment({
        razorpay_order_id: paymentResult.razorpay_order_id,
        razorpay_payment_id: paymentResult.razorpay_payment_id,
        razorpay_signature: paymentResult.razorpay_signature,
      });

      await clearPendingPayment();

      return {
        success: true,
        activated: verifyRes.activated,
        expires_at: verifyRes.expires_at,
      };
    } catch (verifyErr) {
      // Network drop after bank deduction
      return {
        success: true,
        activated: false,
        pending_verification: true,
        message:
          "Payment debited by your bank. Your subscription will activate automatically once network connection is restored.",
      };
    }
  } catch (err: any) {
    if (err?.code === 2 || err?.description === "Payment Cancelled") {
      return { success: false, error: "CANCELLED" };
    }
    throw err;
  }
}

/**
 * Purchases arcade spins adhering to platform billing pathways.
 */
export async function purchaseArcadeRolls(
  productId: string,
  label: string
): Promise<PurchaseResult> {
  // iOS StoreKit consumable IAP
  if (Platform.OS === "ios" || ACTIVE_BILLING_PROVIDER === "app_store") {
    try {
      const NativeIap = (global as any).RNIap || null;
      if (NativeIap && typeof NativeIap.requestPurchase === "function") {
        await NativeIap.requestPurchase({ sku: productId });
        return { success: true };
      }
      if (__DEV__) {
        await createArcadeOrder(productId);
        return { success: true };
      }
      throw new Error("STOREKIT_MODULE_UNAVAILABLE");
    } catch (err: any) {
      if (err?.code === "E_USER_CANCELLED") {
        return { success: false, error: "CANCELLED" };
      }
      throw err;
    }
  }

  // Android Google Play Billing / User Choice Billing
  try {
    const order = await createArcadeOrder(productId);

    if (!RazorpayCheckout || typeof RazorpayCheckout.open !== "function") {
      throw new Error("BILLING_MODULE_UNAVAILABLE");
    }

    const paymentResult = await RazorpayCheckout.open({
      key: order.razorpay_key,
      order_id: order.order_id,
      amount: order.amount_paisa,
      currency: order.currency,
      name: "Serendipity Arcade",
      description: label,
      theme: { color: colors.saffron },
      modal: { backdropclose: false },
    });

    if (!validatePaymentResponse(paymentResult)) {
      throw new Error("INVALID_PAYMENT_RESPONSE");
    }

    await verifyArcadePayment({
      razorpay_order_id: paymentResult.razorpay_order_id,
      razorpay_payment_id: paymentResult.razorpay_payment_id,
      razorpay_signature: paymentResult.razorpay_signature,
    });

    return { success: true };
  } catch (err: any) {
    if (err?.code === 2 || err?.description === "Payment Cancelled") {
      return { success: false, error: "CANCELLED" };
    }
    throw err;
  }
}
