/**
 * Phase 7 — SubscriptionsScreen
 * Displays all Jainune+ plans (from SUBSCRIPTION_SPEC.md):
 *   Monthly INR 499 / Quarterly INR 999 / Semi-Annual INR 1,699 / Annual INR 2,799
 *
 * Payment flow:
 * 1. User taps plan → POST /subscriptions/order → receive Razorpay order_id
 * 2. Open Razorpay checkout (via react-native-razorpay)
 * 3. On payment success → POST /subscriptions/verify (HMAC signature sent to backend)
 * 4. Backend does its own constant-time HMAC verification on webhook (SECURITY.md §7)
 * 5. UI shows activated state
 *
 * Security:
 * - Amount is NEVER sent from client. Server looks up price from plan_id.
 * - Client-side verify is defence-in-depth only; webhook is authoritative.
 * - FLAG_SECURE blocks screenshots of payment UI.
 */

import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
  Platform,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  SUBSCRIPTION_PLANS,
  SubscriptionPlan,
  getSubscriptionStatus,
  getSubscriptionPlans,
  createSubscriptionOrder,
  verifySubscriptionPayment,
  cancelSubscription,
  SubscriptionStatus,
} from "../../api/profileApi";
import { extractError } from "../../api/client";
import {
  enableScreenCaptureProtection,
  disableScreenCaptureProtection,
} from "../../security/antiReversing";

import { purchaseSubscription, syncPendingPayment } from "../../services/billingService";

const FEATURES = [
  "30 daily intentional likes (vs 10 free)",
  "Ambient Voice Canvas — hear voice before matching",
  "60-Second Ephemeral Voice Spark on every match",
  "Daily Blind Dilemma Duels at 20:00 IST",
  "In-chat Question Bounties (simultaneous reveal)",
  "Mutual Chemistry Ticker & 4-phase match moment",
  "Sunday Bangalore City Drops (curated 4-person table)",
  "Bangalore Vibe Map orbital filtering",
  "Deep Jain dietary filters (sect, root veg, Paryushan)",
  "1 Monthly Momentum Revival Pass",
  "Priority compatibility sorting in Liked You tab",
  "Jainune+ profile badge",
];

export default function SubscriptionsScreen() {
  const navigation = useNavigation<any>();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>(SUBSCRIPTION_PLANS);
  const [selectedPlan, setSelectedPlan] = useState<SubscriptionPlan>(
    SUBSCRIPTION_PLANS[1] // default to quarterly (recommended)
  );
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    enableScreenCaptureProtection();
    fetchStatus();
    syncPendingPayment().then((res) => {
      if (res.activated) fetchStatus();
    }).catch(() => {});
    return () => disableScreenCaptureProtection();
  }, []);

  const fetchStatus = async () => {
    try {
      const [s, remotePlans] = await Promise.allSettled([
        getSubscriptionStatus(),
        getSubscriptionPlans(),
      ]);
      if (s.status === "fulfilled") setStatus(s.value);
      if (remotePlans.status === "fulfilled" && remotePlans.value.length > 0) {
        setPlans(remotePlans.value);
        setSelectedPlan(
          remotePlans.value.find((p) => p.is_recommended) || remotePlans.value[0]
        );
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  };

  const handleRestorePurchases = async () => {
    setSyncing(true);
    try {
      const res = await syncPendingPayment();
      if (res.activated) {
        Alert.alert(
          "Subscription Restored",
          "Your active Jainune+ subscription was successfully verified and restored.",
          [{ text: "Great", onPress: () => fetchStatus() }]
        );
      } else {
        await fetchStatus();
        Alert.alert(
          "Purchases Synced",
          "Account status is up to date. If you were recently debited, gateway processing can take 2-3 minutes."
        );
      }
    } catch (err) {
      Alert.alert("Sync Error", extractError(err).message);
    } finally {
      setSyncing(false);
    }
  };

  const handleCancel = () => {
    Alert.alert(
      "Cancel Subscription",
      "Are you sure you want to cancel your Jainune+ subscription? You will retain benefits until the end of your billing cycle.",
      [
        { text: "Keep Subscription", style: "cancel" },
        {
          text: "Confirm Cancellation",
          style: "destructive",
          onPress: async () => {
            setCancelling(true);
            try {
              const res = await cancelSubscription();
              Alert.alert(
                "Subscription Cancelled",
                `Your benefits remain active until ${new Date(res.access_until).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}.`
              );
              fetchStatus();
            } catch (err) {
              Alert.alert("Error", extractError(err).message);
            } finally {
              setCancelling(false);
            }
          },
        },
      ]
    );
  };

  const handleSubscribe = async () => {
    setPaying(true);
    try {
      const result = await purchaseSubscription(selectedPlan);

      if (result.activated && result.expires_at) {
        Alert.alert(
          "Welcome to Jainune+",
          `Your subscription is active until ${new Date(result.expires_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}.`,
          [{ text: "Let's go", onPress: () => navigation.goBack() }]
        );
      } else if (result.pending_verification) {
        Alert.alert(
          "Payment Processing",
          result.message || "Payment debited by bank. Your subscription will activate automatically once network connection is restored.",
          [{ text: "OK", onPress: () => navigation.goBack() }]
        );
      } else if (result.success || result.activated) {
        Alert.alert(
          "Welcome to Jainune+",
          "Your subscription has been activated successfully.",
          [{ text: "Let's go", onPress: () => navigation.goBack() }]
        );
      }
      fetchStatus();
    } catch (err: any) {
      if (err?.code === 0 || err?.error === "CANCELLED") {
        return;
      }
      const friendly = extractError(err);
      Alert.alert(
        friendly.title,
        `${friendly.message}\n\nNote: If funds were debited from your account, your subscription will activate automatically once network connection is restored, or be automatically refunded to your bank within 5-7 business days.`
      );
    } finally {
      setPaying(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.saffron} />
      </View>
    );
  }

  const isActive =
    (status?.tier === "jainune_plus" ||
      status?.tier === "plus" ||
      status?.tier === "gold" ||
      status?.tier === "platinum" ||
      status?.is_active === true) &&
    status?.status !== "expired";

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 100 }}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backBtnText}>Back</Text>
        </TouchableOpacity>
      </View>

      {/* Hero */}
      <View style={styles.hero}>
        <Text style={styles.heroLabel}>JAINUNE+</Text>
        <Text style={styles.heroTitle}>
          Everything you need to{"\n"}find your person.
        </Text>
        <Text style={styles.heroSubtitle}>
          70% cheaper than Tinder Gold. 10x more meaningful.
        </Text>
      </View>

      {/* Active banner & cancellation CTA */}
      {isActive && status?.current_period_end && (
        <View style={styles.activeCard}>
          <View style={styles.activeBanner}>
            <Text style={styles.activeBannerText}>
              Jainune+ Active — renews / expires{" "}
              {new Date(status.current_period_end).toLocaleDateString("en-IN", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </Text>
          </View>
          <TouchableOpacity
            style={[styles.cancelBtn, cancelling && styles.subscribeBtnDisabled]}
            onPress={handleCancel}
            disabled={cancelling}
          >
            {cancelling ? (
              <ActivityIndicator color={colors.muted} size="small" />
            ) : (
              <Text style={styles.cancelBtnText}>Cancel Subscription</Text>
            )}
          </TouchableOpacity>
        </View>
      )}

      {/* Plan selector */}
      {!isActive && (
        <>
          <View style={styles.plansWrap}>
            {plans.map((plan) => {
              const isSelected = selectedPlan.plan_id === plan.plan_id;
              return (
                <TouchableOpacity
                  key={plan.plan_id}
                  style={[styles.planCard, isSelected && styles.planCardSelected]}
                  onPress={() => setSelectedPlan(plan)}
                  activeOpacity={0.8}
                >
                  {plan.is_recommended && (
                    <View style={styles.recommendedBadge}>
                      <Text style={styles.recommendedBadgeText}>Best Value</Text>
                    </View>
                  )}
                  <Text style={[styles.planLabel, isSelected && styles.planLabelSelected]}>
                    {plan.label}
                  </Text>
                  <Text style={[styles.planPrice, isSelected && styles.planPriceSelected]}>
                    ₹{plan.amount_inr}
                  </Text>
                  <Text style={[styles.planPerMonth, isSelected && styles.planPerMonthSelected]}>
                    ₹{plan.per_month_inr}/mo
                  </Text>
                  {plan.savings_pct > 0 && (
                    <Text style={styles.planSavings}>Save {plan.savings_pct}%</Text>
                  )}
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Subscribe CTA */}
          <TouchableOpacity
            style={[styles.subscribeBtn, paying && styles.subscribeBtnDisabled]}
            onPress={handleSubscribe}
            disabled={paying}
          >
            {paying ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <Text style={styles.subscribeBtnText}>
                Subscribe for ₹{selectedPlan.amount_inr}
              </Text>
            )}
          </TouchableOpacity>

          <Text style={styles.legalNote}>
            Recurring UPI AutoPay. Cancel anytime. Governed by RBI pre-debit notification guidelines.
            Price inclusive of 18% GST.
          </Text>

          <TouchableOpacity
            style={styles.restoreBtn}
            onPress={handleRestorePurchases}
            disabled={syncing}
          >
            {syncing ? (
              <ActivityIndicator size="small" color={colors.saffron} />
            ) : (
              <Text style={styles.restoreBtnText}>🔄 Restore / Sync Purchases</Text>
            )}
          </TouchableOpacity>
        </>
      )}

      {/* Features list */}
      <View style={styles.featuresSection}>
        <Text style={styles.featuresSectionTitle}>Everything in Jainune+</Text>
        {FEATURES.map((f, i) => (
          <View key={i} style={styles.featureRow}>
            <View style={styles.featureDot} />
            <Text style={styles.featureText}>{f}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  restoreBtn: {
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
    alignItems: "center",
  },
  restoreBtnText: {
    fontFamily: "Outfit_600SemiBold",
    color: colors.saffron,
    fontSize: 14,
  },
  container: { flex: 1, backgroundColor: "#111112" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#111112" },
  header: {
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 56 : 24,
    paddingBottom: spacing.sm,
  },
  backBtn: { paddingVertical: spacing.xs },
  backBtnText: { fontFamily: "Outfit_600SemiBold", color: "rgba(255,255,255,0.6)", fontSize: 15 },
  hero: {
    paddingHorizontal: spacing.base,
    paddingTop: spacing.xl,
    paddingBottom: spacing.xxl,
    alignItems: "center",
  },
  heroLabel: {
    fontFamily: "Outfit_700Bold",
    fontSize: 12,
    color: colors.saffron,
    letterSpacing: 3,
    marginBottom: spacing.sm,
  },
  heroTitle: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 30,
    color: "#FFFFFF",
    textAlign: "center",
    lineHeight: 38,
    marginBottom: spacing.sm,
  },
  heroSubtitle: {
    ...typography.bodySmall,
    color: "rgba(255,255,255,0.55)",
    textAlign: "center",
    lineHeight: 20,
  },
  activeCard: {
    marginHorizontal: spacing.base,
    marginBottom: spacing.xl,
    gap: spacing.sm,
  },
  activeBanner: {
    backgroundColor: colors.green,
    borderRadius: radii.lg,
    padding: spacing.base,
    alignItems: "center",
  },
  activeBannerText: { fontFamily: "Outfit_700Bold", color: colors.white, fontSize: 14 },
  cancelBtn: {
    paddingVertical: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
    borderRadius: radii.full,
  },
  cancelBtnText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "rgba(255,255,255,0.6)",
  },
  plansWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: spacing.sm,
    gap: spacing.sm,
    marginBottom: spacing.xl,
  },
  planCard: {
    flex: 1,
    minWidth: "45%",
    backgroundColor: "rgba(255,255,255,0.07)",
    borderRadius: radii.lg,
    borderWidth: 1.5,
    borderColor: "rgba(255,255,255,0.12)",
    padding: spacing.base,
    alignItems: "center",
    position: "relative",
    overflow: "hidden",
  },
  planCardSelected: {
    borderColor: colors.saffron,
    backgroundColor: "rgba(255,156,74,0.12)",
  },
  recommendedBadge: {
    position: "absolute",
    top: 0,
    right: 0,
    backgroundColor: colors.saffron,
    borderBottomLeftRadius: radii.sm,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
  },
  recommendedBadgeText: { fontFamily: "Outfit_700Bold", fontSize: 9, color: colors.white },
  planLabel: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: "rgba(255,255,255,0.6)",
    marginBottom: spacing.xs,
    marginTop: spacing.sm,
  },
  planLabelSelected: { color: colors.saffron },
  planPrice: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 24,
    color: "rgba(255,255,255,0.85)",
  },
  planPriceSelected: { color: "#FFFFFF" },
  planPerMonth: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "rgba(255,255,255,0.4)",
    marginTop: 2,
  },
  planPerMonthSelected: { color: "rgba(255,255,255,0.7)" },
  planSavings: {
    fontFamily: "Outfit_700Bold",
    fontSize: 10,
    color: colors.green,
    marginTop: spacing.xs,
  },
  subscribeBtn: {
    marginHorizontal: spacing.base,
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
    height: 56,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  subscribeBtnDisabled: { opacity: 0.6 },
  subscribeBtnText: { fontFamily: "Outfit_700Bold", fontSize: 17, color: colors.white },
  legalNote: {
    ...typography.caption,
    color: "rgba(255,255,255,0.3)",
    textAlign: "center",
    marginHorizontal: spacing.xl,
    marginBottom: spacing.xxl,
    lineHeight: 16,
  },
  featuresSection: {
    backgroundColor: "rgba(255,255,255,0.05)",
    marginHorizontal: spacing.base,
    borderRadius: radii.lg,
    padding: spacing.base,
    marginTop: spacing.sm,
  },
  featuresSectionTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    color: "#FFFFFF",
    marginBottom: spacing.base,
  },
  featureRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  featureDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.saffron,
    marginTop: 7,
    flexShrink: 0,
  },
  featureText: { ...typography.bodySmall, color: "rgba(255,255,255,0.7)", flex: 1, lineHeight: 20 },
});
