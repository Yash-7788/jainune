/** Step 14 — Height (optional, 120–250 cm) with Imperial display */
import React, { useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import Slider from "@react-native-community/slider";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep14 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step14">;

function cmToFtIn(cm: number): string {
  const totalInches = Math.round(cm / 2.54);
  const ft = Math.floor(totalInches / 12);
  const inches = totalInches % 12;
  return `${ft}'${inches}"`;
}

export default function Step14Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [cm, setCm] = useState(data.heightCm ?? 168);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep14(cm);
      updateData({ heightCm: cm });
      setStep(15);
      navigation.navigate("Step15");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    try {
      await submitStep14(null);
      updateData({ heightCm: null });
    } catch {}
    setStep(15);
    navigation.navigate("Step15");
  };

  return (
    <OnboardingStep
      title="How tall are you?"
      subtitle="Optional — but it helps with compatibility."
      onNext={handleNext}
      loading={loading}
      skipLabel="Prefer not to say"
      onSkip={handleSkip}
      error={error}
    >
      <View style={styles.display}>
        <Text style={styles.cms}>{cm}</Text>
        <Text style={styles.unit}>cm</Text>
      </View>
      <Text style={styles.imperial}>{cmToFtIn(cm)}</Text>
      <Slider
        minimumValue={120}
        maximumValue={250}
        step={1}
        value={cm}
        onValueChange={(v) => setCm(Math.round(v))}
        minimumTrackTintColor={colors.saffron}
        maximumTrackTintColor={colors.border}
        thumbTintColor={colors.saffron}
        style={styles.slider}
      />
      <View style={styles.labels}>
        <Text style={styles.label}>120 cm</Text>
        <Text style={styles.label}>250 cm</Text>
      </View>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  display: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "center",
    marginTop: spacing.xl,
  },
  cms: { fontFamily: "Outfit_800ExtraBold", fontSize: 64, color: colors.saffron },
  unit: { ...typography.h2, color: colors.mid, marginLeft: spacing.sm },
  imperial: { ...typography.body, color: colors.mid, textAlign: "center", marginBottom: spacing.lg },
  slider: { width: "100%", marginTop: spacing.md },
  labels: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm },
  label: { ...typography.bodySmall, color: colors.mid },
});
