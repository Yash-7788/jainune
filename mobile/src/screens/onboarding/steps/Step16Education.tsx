/** Step 16 — Education (optional, max 128) */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep16 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step16">;

const OPTIONS = [
  "High School",
  "Bachelor's Degree",
  "Master's Degree",
  "MBA",
  "Ph.D.",
  "CA / CS / CMA",
  "Medical Degree (MBBS / MD)",
  "Law Degree (LLB / LLM)",
  "Diploma / Vocational",
  "Other",
];

export default function Step16Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState(data.education ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep16(selected || null);
      updateData({ education: selected });
      setStep(17);
      navigation.navigate("Step17");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    try { await submitStep16(null); } catch {}
    setStep(17);
    navigation.navigate("Step17");
  };

  return (
    <OnboardingStep
      title="Highest education"
      subtitle="Optional — part of the family compatibility picture."
      onNext={handleNext}
      loading={loading}
      skipLabel="Skip for now"
      onSkip={handleSkip}
      error={error}
      scrollable
    >
      {OPTIONS.map((opt) => (
        <ChoiceChip
          key={opt}
          label={opt}
          selected={selected === opt}
          onPress={() => setSelected(opt)}
        />
      ))}
    </OnboardingStep>
  );
}
