/** Step 9 — Paryushan mode (boolean) */
import React, { useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ChoiceChip } from "../OnboardingStep";
import { colors, spacing, typography } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep9 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step09">;

export default function Step09Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [selected, setSelected] = useState<boolean | null>(
    data.paryushanMode !== undefined ? data.paryushanMode : null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep9(selected === true);
      updateData({ paryushanMode: selected === true });
      setStep(10);
      navigation.navigate("Step10");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Paryushan observance"
      subtitle="Do you follow stricter dietary and spiritual practices during Paryushan?"
      onNext={handleNext}
      loading={loading}
      disabled={selected === null}
      error={error}
    >
      <View style={styles.info}>
        <Text style={styles.infoText}>
          Paryushan mode ensures matches who share your festival observances and dietary
          restrictions during this sacred period.
        </Text>
      </View>
      <ChoiceChip
        label="Yes, I observe Paryushan strictly"
        selected={selected === true}
        onPress={() => setSelected(true)}
      />
      <ChoiceChip
        label="No, I follow standard practices"
        selected={selected === false}
        onPress={() => setSelected(false)}
      />
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  info: {
    backgroundColor: "#FFF8F0",
    borderRadius: 10,
    padding: spacing.base,
    marginBottom: spacing.xl,
    borderLeftWidth: 3,
    borderLeftColor: "#FF9C4A",
  },
  infoText: { ...typography.bodySmall, color: colors.mid, lineHeight: 18 },
});
