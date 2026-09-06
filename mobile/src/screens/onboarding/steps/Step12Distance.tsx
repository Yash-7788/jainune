/** Step 12 — Max distance km: slider 5–200, default 30 */
import React, { useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import Slider from "@react-native-community/slider";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep12 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step12">;

export default function Step12Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [km, setKm] = useState(data.maxDistanceKm ?? 30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep12(km);
      updateData({ maxDistanceKm: km });
      setStep(13);
      navigation.navigate("Step13");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Search radius"
      subtitle="How far should we look for your match?"
      onNext={handleNext}
      loading={loading}
      error={error}
    >
      <View style={styles.display}>
        <Text style={styles.kms}>{km}</Text>
        <Text style={styles.unit}>km</Text>
      </View>
      <Slider
        minimumValue={5}
        maximumValue={200}
        step={5}
        value={km}
        onValueChange={(v: number) => setKm(Math.round(v))}
        minimumTrackTintColor={colors.saffron}
        maximumTrackTintColor={colors.border}
        thumbTintColor={colors.saffron}
        style={styles.slider}
      />
      <View style={styles.labels}>
        <Text style={styles.label}>5 km</Text>
        <Text style={styles.label}>200 km</Text>
      </View>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  display: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "center",
    marginVertical: spacing.xl,
  },
  kms: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 64,
    color: colors.saffron,
  },
  unit: { ...typography.h2, color: colors.mid, marginLeft: spacing.sm },
  slider: { width: "100%", marginTop: spacing.md },
  labels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: spacing.sm,
  },
  label: { ...typography.bodySmall, color: colors.mid },
});
