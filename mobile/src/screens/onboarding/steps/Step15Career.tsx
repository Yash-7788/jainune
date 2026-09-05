/** Step 15 — Career: job_title + company (both optional, max 128) */
import React, { useState } from "react";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { JainuneInput } from "../../../components/core";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep15 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step15">;

export default function Step15Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [jobTitle, setJobTitle] = useState(data.jobTitle ?? "");
  const [company, setCompany] = useState(data.company ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep15(jobTitle || null, company || null);
      updateData({ jobTitle, company });
      setStep(16);
      navigation.navigate("Step16");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    try { await submitStep15(null, null); } catch {}
    setStep(16);
    navigation.navigate("Step16");
  };

  return (
    <OnboardingStep
      title="What do you do?"
      subtitle="Optional — helps spark conversation and compatibility."
      onNext={handleNext}
      loading={loading}
      skipLabel="Skip for now"
      onSkip={handleSkip}
      error={error}
      scrollable
    >
      <JainuneInput
        label="Job title"
        value={jobTitle}
        onChangeText={(t) => setJobTitle(t.slice(0, 128))}
        placeholder="Software Engineer"
        autoFocus
      />
      <JainuneInput
        label="Company (optional)"
        value={company}
        onChangeText={(t) => setCompany(t.slice(0, 128))}
        placeholder="Infosys"
      />
    </OnboardingStep>
  );
}
