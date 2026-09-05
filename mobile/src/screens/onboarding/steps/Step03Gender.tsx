/** Step 3 — Gender: "man" | "woman" | "nonbinary" */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep3 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step03">;

const OPTIONS = [
  { value: "man", label: "Man" },
  { value: "woman", label: "Woman" },
  { value: "nonbinary", label: "Non-binary" },
];

export default function Step03Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState(data.gender ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep3(selected);
      updateData({ gender: selected });
      setStep(4);
      navigation.navigate("Step04");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="How do you identify?"
      subtitle="This helps us find compatible matches for you."
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
