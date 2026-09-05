/** Step 13 — Open to relocation */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep13 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step13">;

export default function Step13Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState<boolean | null>(
    data.openToRelocation !== undefined ? data.openToRelocation : null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep13(selected === true);
      updateData({ openToRelocation: selected === true });
      setStep(14);
      navigation.navigate("Step14");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Pan-India relocation"
      subtitle="Are you open to moving cities for the right person?"
      onNext={handleNext}
      loading={loading}
      disabled={selected === null}
      error={error}
    >
      <ChoiceChip
        label="Yes, I'm open to relocation"
        selected={selected === true}
        onPress={() => setSelected(true)}
      />
      <ChoiceChip
        label="No, I prefer to stay local"
        selected={selected === false}
        onPress={() => setSelected(false)}
      />
    </OnboardingStep>
  );
}
