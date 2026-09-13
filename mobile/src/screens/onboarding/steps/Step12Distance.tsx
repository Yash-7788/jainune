/** Step 12 — Max distance km: slider 5–200, default 30 */
import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import Slider from "@react-native-community/slider";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography, radii } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep12 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step12">;

const PRESET_DISTANCES = [15, 30, 50, 100, 200];

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

  const adjustKm = (delta: number) => {
    setKm((prev) => Math.min(200, Math.max(5, prev + delta)));
  };

  return (
    <OnboardingStep
      title="Search radius"
      subtitle="How far should we look for your match?"
      onNext={handleNext}
      loading={loading}
      error={error}
    >
      <View style={styles.displayRow}>
        <TouchableOpacity
          style={styles.stepperBtn}
          onPress={() => adjustKm(-5)}
          disabled={km <= 5}
          accessibilityLabel="Decrease search radius"
        >
          <Text style={[styles.stepperText, km <= 5 && styles.stepperDisabled]}>−</Text>
        </TouchableOpacity>

        <View style={styles.display}>
          <Text style={styles.kms}>{km}</Text>
          <Text style={styles.unit}>km</Text>
        </View>

        <TouchableOpacity
          style={styles.stepperBtn}
          onPress={() => adjustKm(5)}
          disabled={km >= 200}
          accessibilityLabel="Increase search radius"
        >
          <Text style={[styles.stepperText, km >= 200 && styles.stepperDisabled]}>+</Text>
        </TouchableOpacity>
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

      {/* Quick preset radius pills */}
      <View style={styles.presetsRow}>
        {PRESET_DISTANCES.map((preset) => (
          <TouchableOpacity
            key={preset}
            style={[styles.presetChip, km === preset && styles.presetChipActive]}
            onPress={() => setKm(preset)}
          >
            <Text style={[styles.presetText, km === preset && styles.presetTextActive]}>
              {preset} km
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  displayRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginVertical: spacing.lg,
    gap: spacing.md,
  },
  display: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "center",
    minWidth: 140,
  },
  stepperBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.light,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  stepperText: {
    fontSize: 24,
    fontFamily: "Outfit_700Bold",
    color: colors.dark,
    lineHeight: 28,
  },
  stepperDisabled: {
    color: colors.muted,
  },
  kms: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 56,
    color: colors.saffron,
  },
  unit: { ...typography.h2, color: colors.mid, marginLeft: spacing.xs },
  slider: { width: "100%", marginTop: spacing.md },
  labels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: spacing.xs,
  },
  label: { ...typography.bodySmall, color: colors.mid },
  presetsRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.sm,
    marginTop: spacing.lg,
    flexWrap: "wrap",
  },
  presetChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radii.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.light,
  },
  presetChipActive: {
    borderColor: colors.saffron,
    backgroundColor: colors.saffronLight,
  },
  presetText: {
    ...typography.bodySmall,
    color: colors.mid,
  },
  presetTextActive: {
    color: colors.saffron,
    fontFamily: "Outfit_700Bold",
  },
});
