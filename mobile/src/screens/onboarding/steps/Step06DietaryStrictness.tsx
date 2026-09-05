/** Step 6 — Dietary strictness: "pure_jain" | "vaishnav" | "ovo_veg" | "vegan" */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep6 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step06">;

const OPTIONS = [
  { value: "pure_jain", label: "Pure Jain", desc: "No root vegetables, strict observances" },
  { value: "vaishnav", label: "Vaishnav", desc: "No onion, garlic; root-veg varies" },
  { value: "ovo_veg", label: "Ovo-vegetarian", desc: "Vegetarian including eggs" },
  { value: "vegan", label: "Vegan", desc: "Fully plant-based" },
];

export default function Step06Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState(data.dietaryStrictness ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep6(selected);
      updateData({ dietaryStrictness: selected });
      setStep(7);
      // Step 7 only shown for pure_jain / vaishnav — always navigate, step handles skip
      navigation.navigate("Step07", { dietaryStrictness: selected });
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Your dietary practice"
      subtitle="This is a core compatibility signal in our matching algorithm."
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
