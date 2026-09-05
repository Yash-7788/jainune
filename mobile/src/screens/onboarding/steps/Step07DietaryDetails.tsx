/**
 * Step 7 — Dietary details: root vegetables + onion/garlic
 * Only meaningful for pure_jain / vaishnav.
 * For ovo_veg / vegan: auto-submits defaults and skips to step 8.
 */
import React, { useEffect, useState } from "react";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ToggleRow } from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep7 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step07">;
type Route = RouteProp<OnboardingStackParams, "Step07">;

export default function Step07Screen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { dietaryStrictness } = route.params;
  const { data, updateData, setStep } = useOnboardingStore();
  const [eatsRootVeg, setEatsRootVeg] = useState(data.eatsRootVeg ?? false);
  const [eatsOnionGarlic, setEatsOnionGarlic] = useState(data.eatsOnionGarlic ?? false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const isDetailStep = dietaryStrictness === "pure_jain" || dietaryStrictness === "vaishnav";

  // For non-detail diets, auto-advance to step 8
  useEffect(() => {
    if (!isDetailStep) {
      (async () => {
        setLoading(true);
        try {
          await submitStep7(false, false);
          updateData({ eatsRootVeg: false, eatsOnionGarlic: false });
          setStep(8);
          navigation.navigate("Step08");
        } catch {
          navigation.navigate("Step08");
        } finally {
          setLoading(false);
        }
      })();
    }
  }, []);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep7(eatsRootVeg, eatsOnionGarlic);
      updateData({ eatsRootVeg, eatsOnionGarlic });
      setStep(8);
      navigation.navigate("Step08");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  if (!isDetailStep) {
    return null; // auto-advancing
  }

  return (
    <OnboardingStep
      title="A bit more detail"
      subtitle="These help us find truly compatible matches for your dietary values."
      onNext={handleNext}
      loading={loading}
      error={error}
    >
      <ToggleRow
        label="Root vegetables"
        sub="Potato, carrot, onion, etc."
        value={eatsRootVeg}
        onToggle={setEatsRootVeg}
      />
      <ToggleRow
        label="Onion & garlic"
        sub="Including processed forms"
        value={eatsOnionGarlic}
        onToggle={setEatsOnionGarlic}
      />
    </OnboardingStep>
  );
}
