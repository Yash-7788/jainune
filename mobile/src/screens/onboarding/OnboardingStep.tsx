/**
 * Shared layout for all onboarding steps
 */

import React from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TouchableOpacity,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { colors, spacing, typography } from "../../../theme/tokens";
import { BackIcon } from "../../../components/core/Icons";
import { PrimaryButton, ErrorToast } from "../../../components/core";

interface OnboardingStepProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onNext: () => void;
  nextLabel?: string;
  loading?: boolean;
  disabled?: boolean;
  error?: { title: string; message: string } | null;
  skipLabel?: string;
  onSkip?: () => void;
  scrollable?: boolean;
}

export default function OnboardingStep({
  title,
  subtitle,
  children,
  onNext,
  nextLabel = "Continue",
  loading,
  disabled,
  error,
  skipLabel,
  onSkip,
  scrollable = false,
}: OnboardingStepProps) {
  const navigation = useNavigation();

  const content = (
    <View style={styles.inner}>
      {/* Back */}
      <TouchableOpacity onPress={() => navigation.goBack()} style={styles.back}>
        <BackIcon color={colors.dark} />
      </TouchableOpacity>

      {/* Title */}
      <Text style={styles.title}>{title}</Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}

      {/* Step content */}
      <View style={styles.body}>{children}</View>

      {/* CTA */}
      <View style={styles.cta}>
        <PrimaryButton
          label={nextLabel}
          onPress={onNext}
          loading={loading}
          disabled={disabled || loading}
        />
        {skipLabel && onSkip ? (
          <TouchableOpacity onPress={onSkip} style={styles.skip}>
            <Text style={styles.skipText}>{skipLabel}</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      {error && <ErrorToast title={error.title} message={error.message} visible />}

      {scrollable ? (
        <ScrollView
          contentContainerStyle={{ flexGrow: 1 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {content}
        </ScrollView>
      ) : (
        content
      )}
    </KeyboardAvoidingView>
  );
}

// Reusable choice chip for single-select steps
interface ChipProps {
  label: string;
  selected: boolean;
  onPress: () => void;
  emoji?: string;
}

export function ChoiceChip({ label, selected, onPress, emoji }: ChipProps) {
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.8}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      {emoji ? <Text style={styles.chipEmoji}>{emoji}</Text> : null}
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>{label}</Text>
    </TouchableOpacity>
  );
}

// Toggle switch row for boolean answers
interface ToggleRowProps {
  label: string;
  sub?: string;
  value: boolean;
  onToggle: (val: boolean) => void;
}

export function ToggleRow({ label, sub, value, onToggle }: ToggleRowProps) {
  return (
    <TouchableOpacity
      onPress={() => onToggle(!value)}
      style={styles.toggleRow}
      activeOpacity={0.85}
    >
      <View style={styles.toggleLeft}>
        <Text style={styles.toggleLabel}>{label}</Text>
        {sub ? <Text style={styles.toggleSub}>{sub}</Text> : null}
      </View>
      <View style={[styles.toggle, value && styles.toggleOn]}>
        <View style={[styles.toggleThumb, value && styles.toggleThumbOn]} />
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  inner: {
    flex: 1,
    paddingHorizontal: spacing.base,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  back: {
    width: 40,
    height: 40,
    justifyContent: "center",
    marginBottom: spacing.base,
  },
  title: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 26,
    color: colors.dark,
    marginBottom: spacing.sm,
    lineHeight: 34,
  },
  subtitle: {
    ...typography.body,
    color: colors.mid,
    marginBottom: spacing.xl,
    lineHeight: 22,
  },
  body: { flex: 1 },
  cta: { gap: spacing.sm },
  skip: { alignItems: "center", paddingVertical: spacing.sm },
  skipText: { ...typography.body, color: colors.mid },

  // Choice chips
  chip: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.base,
    borderRadius: spacing.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.white,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
  chipSelected: {
    borderColor: colors.saffron,
    backgroundColor: colors.saffronLight,
  },
  chipEmoji: { fontSize: 20 },
  chipLabel: { ...typography.body, color: colors.dark },
  chipLabelSelected: { fontFamily: "Outfit_700Bold", color: colors.saffron },

  // Toggle
  toggleRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  toggleLeft: { flex: 1, marginRight: spacing.base },
  toggleLabel: { ...typography.body, color: colors.dark },
  toggleSub: { ...typography.bodySmall, color: colors.mid, marginTop: 2 },
  toggle: {
    width: 46,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.border,
    padding: 2,
    justifyContent: "center",
  },
  toggleOn: { backgroundColor: colors.saffron },
  toggleThumb: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.white,
    alignSelf: "flex-start",
  },
  toggleThumbOn: { alignSelf: "flex-end" },
});
