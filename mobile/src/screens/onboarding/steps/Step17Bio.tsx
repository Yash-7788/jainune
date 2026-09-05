/** Step 17 — Bio (optional, max 500 chars) */
import React, { useState } from "react";
import { View, Text, TextInput, StyleSheet } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep17 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step17">;

const MAX_BIO = 500;

export default function Step17Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [bio, setBio] = useState(data.bio ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep17(bio.trim() || null);
      updateData({ bio: bio.trim() });
      setStep(18);
      navigation.navigate("Step18");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    try { await submitStep17(null); } catch {}
    setStep(18);
    navigation.navigate("Step18");
  };

  return (
    <OnboardingStep
      title="Your story"
      subtitle="Write a short bio. What makes you, you?"
      onNext={handleNext}
      loading={loading}
      skipLabel="Skip for now"
      onSkip={handleSkip}
      error={error}
      scrollable
    >
      <View style={styles.inputWrap}>
        <TextInput
          value={bio}
          onChangeText={(t) => setBio(t.slice(0, MAX_BIO))}
          multiline
          numberOfLines={6}
          placeholder="I grew up in a big Jain family in Mumbai, love trekking on weekends, and can debate the perfect chai recipe for hours..."
          placeholderTextColor={colors.mid}
          style={styles.bioInput}
          textAlignVertical="top"
          autoFocus
        />
        <Text style={styles.counter}>{bio.length}/{MAX_BIO}</Text>
      </View>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  inputWrap: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 12,
    padding: spacing.base,
    backgroundColor: colors.white,
  },
  bioInput: {
    ...typography.body,
    color: colors.dark,
    minHeight: 140,
  },
  counter: {
    ...typography.caption,
    color: colors.mid,
    textAlign: "right",
    marginTop: spacing.sm,
  },
});
