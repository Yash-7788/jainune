/** Step 5 — Looking for: "marriage" | "long_term" | "figuring_out" */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep5 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step05">;

const OPTIONS = [
  { value: "marriage", label: "Marriage", sub: "Looking for a life partner" },
  { value: "long_term", label: "Long-term relationship", sub: "Open to where things go" },
  { value: "figuring_out", label: "Figuring it out", sub: "Taking it one step at a time" },
];

export default function Step05Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState(data.lookingFor ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep5(selected);
      updateData({ lookingFor: selected });
      setStep(6);
      navigation.navigate("Step06");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="What are you looking for?"
      subtitle="Be honest — it sets the right expectations."
      onNext={handleNext}
      loading={loading}
      disabled={!selected}
      error={error}
    >
      {OPTIONS.map((opt) => (
        <ChoiceChip
          key={opt.value}
          label={opt.label}
          selected={selected === opt.value}
          onPress={() => setSelected(opt.value)}
        />
      ))}
    </OnboardingStep>
  );
}
