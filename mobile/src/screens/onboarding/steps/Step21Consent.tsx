/**
 * Step 21 — DPDP Act 2023 Consent
 * core_matchmaking is mandatory. family_contact_gotra and relocation_intercity are optional.
 * Backend validator enforces core_matchmaking must be true.
 */
import React, { useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep, { ToggleRow } from "../OnboardingStep";
import { colors, spacing, typography, radii } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep21 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step21">;

export default function Step21Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [coreMatchmaking] = useState(true); // always true — mandatory
  const [familyContact, setFamilyContact] = useState(data.consentFamilyContact ?? false);
  const [relocation, setRelocation] = useState(data.consentRelocation ?? false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep21(true, familyContact, relocation);
      updateData({
        consentCoreMatchmaking: true,
        consentFamilyContact: familyContact,
        consentRelocation: relocation,
      });
      setStep(22);
      navigation.navigate("Step22");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Your data, your choice"
      subtitle="Jainune complies with India's Digital Personal Data Protection Act 2023. Please review and confirm."
      onNext={handleNext}
      loading={loading}
      error={error}
      scrollable
    >
      {/* Mandatory */}
      <View style={styles.mandatoryCard}>
        <Text style={styles.mandatoryTitle}>Core Matchmaking</Text>
        <Text style={styles.mandatoryDesc}>
          Required to use Jainune. Enables us to suggest compatible matches based on your
          profile, dietary practices, and location.
        </Text>
        <Text style={styles.mandatory}>Required</Text>
      </View>

      {/* Optional consents */}
      <ToggleRow
        label="Family & Gotra Sharing"
        sub="Allow us to share compatible gotra information with your family account if linked."
        value={familyContact}
        onToggle={setFamilyContact}
      />
      <ToggleRow
        label="Pan-India Relocation Matching"
        sub="Allow us to suggest profiles outside your city if you've indicated openness to relocation."
        value={relocation}
        onToggle={setRelocation}
      />

      {/* Zero-Tolerance EULA & Community Standards (Apple Guideline 1.2) */}
      <View style={styles.eulaCard}>
        <Text style={styles.eulaTitle}>Zero-Tolerance Community Standards (EULA)</Text>
        <Text style={styles.eulaDesc}>
          By continuing, you agree to our EULA. Jainune has zero tolerance for objectionable content,
          harassment, or abusive behavior. Violators face immediate removal and permanent account ban within 24 hours.
        </Text>
      </View>

      <Text style={styles.legal}>
        You can withdraw optional consents at any time from Settings → Privacy. Core Matchmaking consent can only be withdrawn by deleting your account.
      </Text>
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  mandatoryCard: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.lg,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: colors.saffron,
    marginBottom: spacing.base,
  },
  mandatoryTitle: { fontFamily: "Outfit_700Bold", fontSize: 15, color: colors.dark, marginBottom: 4 },
  mandatoryDesc: { ...typography.bodySmall, color: colors.mid, lineHeight: 18, marginBottom: spacing.sm },
  mandatory: {
    fontFamily: "Outfit_700Bold",
    fontSize: 12,
    color: colors.saffron,
    textTransform: "uppercase",
  },
  eulaCard: {
    backgroundColor: colors.white,
    borderRadius: radii.lg,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.sm,
    marginBottom: spacing.base,
  },
  eulaTitle: { fontFamily: "Outfit_700Bold", fontSize: 14, color: colors.dark, marginBottom: 4 },
  eulaDesc: { ...typography.bodySmall, color: colors.mid, lineHeight: 18 },
  legal: {
    ...typography.bodySmall,
    color: colors.mid,
    marginTop: spacing.base,
    lineHeight: 18,
  },
});
