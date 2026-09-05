/** Step 10 — City + State */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { JainuneInput } from "../../../components/core";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep10 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step10">;

const CITIES = ["Mumbai", "Pune", "Bengaluru", "Ahmedabad", "Surat", "Jaipur", "Delhi", "Chennai", "Hyderabad"];
const STATES = ["Maharashtra", "Karnataka", "Gujarat", "Rajasthan", "Delhi", "Tamil Nadu", "Telangana"];

export default function Step10Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [city, setCity] = useState(data.city ?? "");
  const [state, setState] = useState(data.state ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep10(city, state);
      updateData({ city, state });
      setStep(11);
      navigation.navigate("Step11");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Where are you based?"
      subtitle="Your city is used for proximity matching. Exact address is never shown."
      onNext={handleNext}
      loading={loading}
      disabled={city.trim().length < 2 || state.trim().length < 2}
      error={error}
      scrollable
    >
      <JainuneInput
        label="City"
        value={city}
        onChangeText={(t) => setCity(t.slice(0, 64))}
        placeholder="Mumbai"
        autoFocus
      />
      <JainuneInput
        label="State"
        value={state}
        onChangeText={(t) => setState(t.slice(0, 64))}
        placeholder="Maharashtra"
      />
    </OnboardingStep>
  );
}
