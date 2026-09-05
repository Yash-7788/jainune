/**
 * SerendipityArcadeModal — Phase 7 Micro-Transactions & Gamified Discovery
 * - Wheel of Serendipity (Spin for instant matches, bonus likes, question unlocks)
 * - Karma Dice (Roll for serendipitous icebreakers & momentum boosts)
 * - Razorpay micro-transactions (₹19, ₹29, ₹49)
 * - Safe client signature verification
 */

import React, { useState, useRef } from "react";
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Easing,
  ActivityIndicator,
  Alert,
} from "react-native";
import RazorpayCheckout from "react-native-razorpay";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  ARCADE_PRODUCTS,
  ArcadeProduct,
  createArcadeOrder,
  verifyArcadePayment,
  getArcadeWallet,
  spinArcadeWheel,
  rollArcadeDice,
} from "../../api/profileApi";
import { validatePaymentResponse } from "../../security/inputValidation";
import { extractError } from "../../api/client";

const WHEEL_REWARDS = [
  { label: "10 Bonus Likes", icon: "❤️" },
  { label: "Serendipity Match", icon: "✨" },
  { label: "Revival Pass", icon: "⚡" },
  { label: "Icebreaker Unlock", icon: "💬" },
  { label: "Double Chemistry", icon: "🔥" },
  { label: "5 Intentional Likes", icon: "💫" },
];

const DICE_REWARDS = [
  "Reveal A Shared Value",
  "Free Voice Spark Pass",
  "Unlock Question Bounty",
  "Bangalore Vibe Map Boost",
  "Priority In Mutual Feed",
  "Serendipity Match Highlight",
];

interface Props {
  visible: boolean;
  onClose: () => void;
}

export default function SerendipityArcadeModal({ visible, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<"wheel" | "dice">("wheel");
  const [spins, setSpins] = useState(1);
  const [rolls, setRolls] = useState(1);
  const [isSpinning, setIsSpinning] = useState(false);
  const [isRolling, setIsRolling] = useState(false);
  const [lastWon, setLastWon] = useState<string | null>(null);
  const [purchasing, setPurchasing] = useState(false);

  // Animations
  const wheelSpinAnim = useRef(new Animated.Value(0)).current;
  const diceRollAnim = useRef(new Animated.Value(0)).current;
  const [diceNumber, setDiceNumber] = useState(1);

  React.useEffect(() => {
    if (visible) {
      getArcadeWallet()
        .then((w) => {
          setSpins(w.available_spins);
          setRolls(w.available_dice_rolls);
        })
        .catch(() => {});
    }
  }, [visible]);

  const handleSpinWheel = async () => {
    if (spins <= 0) {
      Alert.alert("No Spins Left", "Top up your arcade passes below to spin again!");
      return;
    }
    if (isSpinning) return;

    setIsSpinning(true);
    setLastWon(null);

    const randomDegrees = 1440 + Math.floor(Math.random() * 360);
    const winningIndex = Math.floor((randomDegrees % 360) / (360 / WHEEL_REWARDS.length));
    const prize = WHEEL_REWARDS[winningIndex];

    wheelSpinAnim.setValue(0);
    Animated.timing(wheelSpinAnim, {
      toValue: randomDegrees,
      duration: 3500,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start(async () => {
      setIsSpinning(false);
      try {
        const res = await spinArcadeWheel();
        setSpins(res.remaining_spins);
        if (res.paired_user) {
          setLastWon(`✨ Paired with ${res.paired_user.first_name} (${res.paired_user.city})!`);
        } else {
          setLastWon(`${prize.icon} ${prize.label}`);
        }
      } catch {
        setSpins((s) => Math.max(0, s - 1));
        setLastWon(`${prize.icon} ${prize.label}`);
      }
    });
  };

  const handleRollDice = async () => {
    if (rolls <= 0) {
      Alert.alert("No Rolls Left", "Top up your dice rolls below to roll again!");
      return;
    }
    if (isRolling) return;

    setIsRolling(true);
    setLastWon(null);

    diceRollAnim.setValue(0);
    Animated.sequence([
      Animated.timing(diceRollAnim, {
        toValue: 1,
        duration: 800,
        easing: Easing.bounce,
        useNativeDriver: true,
      }),
    ]).start(async () => {
      try {
        const res = await rollArcadeDice();
        const rolled = res.roll_outcome?.[0] || Math.floor(Math.random() * 6) + 1;
        setDiceNumber(rolled);
        setRolls(res.remaining_dice_rolls);
        setLastWon(`🎲 Rolled ${rolled}: ${DICE_REWARDS[rolled - 1]}`);
      } catch {
        const rolled = Math.floor(Math.random() * 6) + 1;
        setDiceNumber(rolled);
        setRolls((r) => Math.max(0, r - 1));
        setLastWon(`🎲 Rolled ${rolled}: ${DICE_REWARDS[rolled - 1]}`);
      } finally {
        setIsRolling(false);
      }
    });
  };

  const handlePurchase = async (product: ArcadeProduct) => {
    setPurchasing(true);
    try {
      // 1. Create server order
      const order = await createArcadeOrder(product.product_id);

      // 2. Open Razorpay Checkout
      const paymentResult = await RazorpayCheckout.open({
        key: order.razorpay_key,
        order_id: order.order_id,
        amount: order.amount_paisa,
        currency: order.currency,
        name: "Serendipity Arcade",
        description: product.label,
        theme: { color: colors.saffron },
        modal: { backdropclose: false },
      });

      // 3. Client signature check
      if (!validatePaymentResponse(paymentResult)) {
        throw new Error("INVALID_PAYMENT_RESPONSE");
      }

      // 4. Verification
      await verifyArcadePayment({
        razorpay_order_id: paymentResult.razorpay_order_id,
        razorpay_payment_id: paymentResult.razorpay_payment_id,
        razorpay_signature: paymentResult.razorpay_signature,
      });

      // Refresh wallet from backend
      try {
        const w = await getArcadeWallet();
        setSpins(w.available_spins);
        setRolls(w.available_dice_rolls);
      } catch {
        setSpins((s) => s + (product.spins || 0));
        setRolls((r) => r + (product.rolls || 0));
      }

      Alert.alert("Purchased!", `${product.label} added to your arcade balance.`);
    } catch (err: any) {
      if (err?.code !== 0) {
        Alert.alert("Payment Failed", extractError(err).message);
      }
    } finally {
      setPurchasing(false);
    }
  };

  const spinInterpolation = wheelSpinAnim.interpolate({
    inputRange: [0, 360],
    outputRange: ["0deg", "360deg"],
  });

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          {/* Header */}
          <View style={styles.header}>
            <View>
              <Text style={styles.headerTitle}>Serendipity Arcade 🎡</Text>
              <Text style={styles.headerSubtitle}>
                Spins: {spins} | Rolls: {rolls}
              </Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeBtnText}>✕</Text>
            </TouchableOpacity>
          </View>

          {/* Mode Switcher */}
          <View style={styles.tabWrap}>
            <TouchableOpacity
              style={[styles.tabBtn, activeTab === "wheel" && styles.tabBtnActive]}
              onPress={() => setActiveTab("wheel")}
            >
              <Text style={[styles.tabBtnText, activeTab === "wheel" && styles.tabBtnTextActive]}>
                Wheel of Serendipity
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tabBtn, activeTab === "dice" && styles.tabBtnActive]}
              onPress={() => setActiveTab("dice")}
            >
              <Text style={[styles.tabBtnText, activeTab === "dice" && styles.tabBtnTextActive]}>
                Karma Dice
              </Text>
            </TouchableOpacity>
          </View>

          {/* Interactive Game Area */}
          {activeTab === "wheel" ? (
            <View style={styles.gameArea}>
              <Animated.View
                style={[
                  styles.wheelGraphic,
                  { transform: [{ rotate: spinInterpolation }] },
                ]}
              >
                <Text style={styles.wheelEmojis}>🌟 ❤️ 💫 ✨ ⚡ 💬</Text>
              </Animated.View>
              <TouchableOpacity
                style={[styles.actionBtn, isSpinning && styles.actionBtnDisabled]}
                onPress={handleSpinWheel}
                disabled={isSpinning}
              >
                <Text style={styles.actionBtnText}>
                  {isSpinning ? "Spinning..." : `Spin Wheel (${spins} Left)`}
                </Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.gameArea}>
              <Animated.View style={styles.diceBox}>
                <Text style={styles.diceText}>{diceNumber}</Text>
              </Animated.View>
              <TouchableOpacity
                style={[styles.actionBtn, isRolling && styles.actionBtnDisabled]}
                onPress={handleRollDice}
                disabled={isRolling}
              >
                <Text style={styles.actionBtnText}>
                  {isRolling ? "Rolling..." : `Roll Dice (${rolls} Left)`}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Result Alert */}
          {lastWon && (
            <View style={styles.resultBadge}>
              <Text style={styles.resultText}>🎉 {lastWon}</Text>
            </View>
          )}

          {/* Top-up Passes */}
          <Text style={styles.storeTitle}>Top-up Passes</Text>
          <View style={styles.productRow}>
            {ARCADE_PRODUCTS.map((prod) => (
              <TouchableOpacity
                key={prod.product_id}
                style={styles.productCard}
                onPress={() => handlePurchase(prod)}
                disabled={purchasing}
              >
                <Text style={styles.prodLabel}>{prod.label}</Text>
                <Text style={styles.prodPrice}>₹{prod.amount_inr}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.7)",
    justifyContent: "center",
    padding: spacing.base,
  },
  sheet: {
    backgroundColor: "#16181D",
    borderRadius: radii.xl,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.base,
  },
  headerTitle: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 20,
    color: colors.white,
  },
  headerSubtitle: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: colors.saffron,
    marginTop: 2,
  },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.1)",
    alignItems: "center",
    justifyContent: "center",
  },
  closeBtnText: { color: colors.white, fontSize: 14, fontWeight: "bold" },
  tabWrap: {
    flexDirection: "row",
    backgroundColor: "rgba(255,255,255,0.06)",
    borderRadius: radii.full,
    padding: 3,
    marginBottom: spacing.lg,
  },
  tabBtn: {
    flex: 1,
    paddingVertical: spacing.xs,
    borderRadius: radii.full,
    alignItems: "center",
  },
  tabBtnActive: { backgroundColor: colors.saffron },
  tabBtnText: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: "rgba(255,255,255,0.6)",
  },
  tabBtnTextActive: {
    fontFamily: "Outfit_700Bold",
    color: colors.white,
  },
  gameArea: {
    alignItems: "center",
    paddingVertical: spacing.base,
  },
  wheelGraphic: {
    width: 130,
    height: 130,
    borderRadius: 65,
    borderWidth: 4,
    borderColor: colors.saffron,
    backgroundColor: "rgba(255,156,74,0.15)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.base,
  },
  wheelEmojis: { fontSize: 20, letterSpacing: 4 },
  diceBox: {
    width: 80,
    height: 80,
    borderRadius: radii.lg,
    backgroundColor: colors.saffron,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.base,
  },
  diceText: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 36,
    color: colors.white,
  },
  actionBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
  },
  actionBtnDisabled: { opacity: 0.5 },
  actionBtnText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 14,
    color: colors.white,
  },
  resultBadge: {
    backgroundColor: "rgba(16,185,129,0.2)",
    borderWidth: 1,
    borderColor: colors.green,
    borderRadius: radii.md,
    padding: spacing.xs,
    alignItems: "center",
    marginVertical: spacing.sm,
  },
  resultText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 13,
    color: colors.green,
  },
  storeTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 14,
    color: "rgba(255,255,255,0.7)",
    marginTop: spacing.base,
    marginBottom: spacing.xs,
  },
  productRow: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  productCard: {
    flex: 1,
    backgroundColor: "rgba(255,255,255,0.06)",
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    padding: spacing.sm,
    alignItems: "center",
  },
  prodLabel: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: "rgba(255,255,255,0.7)",
    textAlign: "center",
  },
  prodPrice: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 16,
    color: colors.saffron,
    marginTop: 4,
  },
});
