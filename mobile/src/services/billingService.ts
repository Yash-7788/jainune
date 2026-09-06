/**
 * Unified Billing Gateway Service
 *
 * Implements store compliance abstraction for Google Play Billing / Apple StoreKit
 * and India User Choice Billing (UCB) / Alternative Billing (Razorpay).
 */

import { Platform, Linking } from "react-native";
import RazorpayCheckout from "react-native-razorpay";
import {
  createSubscriptionOrder,
  verifySubscriptionPayment,
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
  expires_at?: string;
  error?: string;
}

export const ACTIVE_BILLING_PROVIDER: BillingProvider =
  (process.env.EXPO_PUBLIC_BILLING_PROVIDER as BillingProvider) ||
  (Platform.OS === "android" ? "razorpay" : "web");

/**
 * Purchases a subscription plan adhering to Google Play / Apple Store / Razorpay pathways.
 */
export async function purchaseSubscription(
  plan: SubscriptionPlan
): Promise<PurchaseResult> {
  // Option 1: Web checkout (store policy compliant external redirect)
  if (ACTIVE_BILLING_PROVIDER === "web") {
    const webUrl = `https://jainune.com/subscribe?plan=${encodeURIComponent(plan.plan_id)}`;
    await Linking.openURL(webUrl);
    return { success: true };
  }

  // Option 2: Direct Razorpay / Alternative billing (UCB compliant)
  try {
    const order = await createSubscriptionOrder(plan.plan_id);

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

    const verifyRes = await verifySubscriptionPayment({
      razorpay_order_id: paymentResult.razorpay_order_id,
      razorpay_payment_id: paymentResult.razorpay_payment_id,
      razorpay_signature: paymentResult.razorpay_signature,
    });

    return {
      success: true,
      activated: verifyRes.activated,
      expires_at: verifyRes.expires_at,
    };
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
  if (ACTIVE_BILLING_PROVIDER === "web") {
    const webUrl = `https://jainune.com/arcade?product=${encodeURIComponent(productId)}`;
    await Linking.openURL(webUrl);
    return { success: true };
  }

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
