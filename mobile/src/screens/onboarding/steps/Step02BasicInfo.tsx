/**
 * Step 2 — Name + Date of Birth
 * Backend: first_name (2–64 chars), date_of_birth (must be 18–70 years old)
 */

import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, TextInput, TouchableOpacity } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { colors, spacing, typography } from "../../../theme/tokens";
import { JainuneInput, ErrorToast } from "../../../components/core";
import OnboardingStep from "../OnboardingStep";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep2 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import { validateAgeGate, validateName } from "../../../security/inputValidation";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step02">;

export default function Step02Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();

  const [firstName, setFirstName] = useState(data.firstName ?? "");
  const [dob, setDob] = useState(data.dateOfBirth ?? ""); // YYYY-MM-DD
  const [dobDisplay, setDobDisplay] = useState(
    data.dateOfBirth
      ? (() => {
          const parts = data.dateOfBirth.split("-");
          return parts.length === 3 ? `${parts[2]} / ${parts[1]} / ${parts[0]}` : "";
        })()
      : ""
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [firstNameError, setFirstNameError] = useState<string | undefined>();
  const [dobError, setDobError] = useState<string | undefined>();

  const handleDobChange = (raw: string) => {
    // Format: DD/MM/YYYY — auto-insert slashes
    const digits = raw.replace(/\D/g, "").slice(0, 8);
    let formatted = digits;
    if (digits.length > 4) {
      formatted = `${digits.slice(0, 2)} / ${digits.slice(2, 4)} / ${digits.slice(4)}`;
    } else if (digits.length > 2) {
      formatted = `${digits.slice(0, 2)} / ${digits.slice(2)}`;
    }
    setDobDisplay(formatted);

    if (digits.length === 8) {
      const day = parseInt(digits.slice(0, 2), 10);
      const month = parseInt(digits.slice(2, 4), 10);
      const year = parseInt(digits.slice(4), 10);

      // Construct ISO format YYYY-MM-DD
      const isoStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const gate = validateAgeGate(isoStr);

      if (!gate.valid) {
        setDobError(gate.error || "Please enter a valid date of birth (must be 18+).");
        setDob("");
      } else {
        setDobError(undefined);
        setDob(isoStr);
      }
    } else {
      setDob("");
    }
  };

  const handleNext = async () => {
    // Validate
    const nameValidation = validateName(firstName);
    if (!nameValidation.valid) {
      setFirstNameError(nameValidation.error || "Please enter a valid first name.");
      return;
    }
    if (!dob) {
      setDobError("Please enter your date of birth.");
      return;
    }
    setLoading(true);
    try {
      await submitStep2(firstName.trim(), dob);
      updateData({ firstName: firstName.trim(), dateOfBirth: dob });
      setStep(3);
      navigation.navigate("Step03");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="What's your name?"
      subtitle="This is how you'll appear on your profile."
      onNext={handleNext}
      loading={loading}
      disabled={!firstName || !dob}
      error={error}
      scrollable
    >
      <JainuneInput
        label="First name"
        value={firstName}
        onChangeText={(t: string) => {
          setFirstName(t.slice(0, 64));
          if (firstNameError) setFirstNameError(undefined);
        }}
        placeholder="Priya"
        autoFocus
        error={firstNameError}
      />
      <JainuneInput
        label="Date of birth"
        value={dobDisplay}
        onChangeText={handleDobChange}
        placeholder="DD / MM / YYYY"
        keyboardType="number-pad"
        error={dobError}
      />
    </OnboardingStep>
  );
}
