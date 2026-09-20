/**
 * Step 20 — Voice Snapshot: Informational / Retired Step in v2
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep20 } from "../../../api/onboardingApi";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step20">;

export default function Step20Screen() {
  const navigation = useNavigation<Nav>();
  const { setStep } = useOnboardingStore();

  const handleContinue = async () => {
    try {
      await submitStep20();
    } catch {
      // Ignored: step 20 is optional/retired in v2
    }
    setStep(21);
    navigation.navigate("Step21");
  };

  return (
    <OnboardingStep
      title="Voice Snapshot"
      subtitle="Voice snapshots have been retired in Jainune v2."
      onNext={handleContinue}
      disabled={false}
      nextLabel="Continue"
      skipLabel="Skip"
      onSkip={handleContinue}
    >
      <View style={styles.center}>
        <Text style={styles.hint}>
          Voice intro is no longer required. Tap Continue to proceed to the final consent step.
        </Text>
      </View>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  center: {
    paddingVertical: spacing.xl,
    alignItems: "center",
  },
  hint: {
    ...typography.body,
    color: colors.muted,
    textAlign: "center",
    lineHeight: 22,
  },
});
