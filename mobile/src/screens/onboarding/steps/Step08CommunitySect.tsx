/** Step 8 — Community sect */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep8 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step08">;

const OPTIONS = [
  { value: "digambar", label: "Digambar" },
  { value: "shwetambar_murtipujak", label: "Shwetambar Murtipujak" },
  { value: "shwetambar_sthanakvasi", label: "Shwetambar Sthanakvasi" },
  { value: "terapanthi", label: "Terapanthi" },
  { value: "open", label: "Open / Not sure" },
];

export default function Step08Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState(data.communitySect ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep8(selected);
      updateData({ communitySect: selected });
      setStep(9);
      navigation.navigate("Step09");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Your community roots"
      subtitle="Used for family-compatibility matching. Can be kept open."
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
