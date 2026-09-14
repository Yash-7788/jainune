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
  Alert,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useAuthStore } from "../../store/authStore";
import { useOnboardingStore } from "../../store/onboardingStore";
import { colors, spacing, typography } from "../../theme/tokens";
import { BackIcon } from "../../components/core/Icons";
import { PrimaryButton, ErrorToast } from "../../components/core";

interface OnboardingStepProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onNext: () => void;
  nextLabel?: string;
  loading?: boolean;
  disabled?: boolean;
  error?: { title: string; message: string } | null;
  onDismissError?: () => void;
  skipLabel?: string;
  onSkip?: () => void;
  scrollable?: boolean;
}

const screenNameToStep: Record<string, number> = {
  Step02: 2,
  Step03: 3,
  Step04: 4,
  Step05: 5,
  Step06: 6,
  Step07: 7,
  Step08: 8,
  Step09: 9,
  Step10: 10,
  Step11: 11,
  Step12: 12,
  Step13: 13,
  Step14: 14,
  Step15: 15,
  Step16: 16,
  Step17: 17,
  Step18: 18,
  Step19: 19,
  Step20: 20,
  Step21: 21,
  Step22: 22,
};

const stepToScreenName: Record<number, string> = {
  2: "Step02",
  3: "Step03",
  4: "Step04",
  5: "Step05",
  6: "Step06",
  7: "Step07",
  8: "Step08",
  9: "Step09",
  10: "Step10",
  11: "Step11",
  12: "Step12",
  13: "Step13",
  14: "Step14",
  15: "Step15",
  16: "Step16",
  17: "Step17",
  18: "Step18",
  19: "Step19",
  20: "Step20",
  21: "Step21",
  22: "Step22",
};

export default function OnboardingStep({
  title,
  subtitle,
  children,
  onNext,
  nextLabel = "Continue",
  loading,
  disabled,
  error,
  onDismissError,
  skipLabel,
  onSkip,
  scrollable = false,
}: OnboardingStepProps) {
  const navigation = useNavigation();
  const [toastVisible, setToastVisible] = React.useState(!!error);

  React.useEffect(() => {
    setToastVisible(!!error);
  }, [error]);

  React.useEffect(() => {
    if (loading) {
      setToastVisible(false);
    } else if (error) {
      setToastVisible(true);
    }
  }, [loading, error]);

  const handleBack = () => {
    if (navigation.canGoBack()) {
      const routes = (navigation as any).getState?.()?.routes;
      const prevRoute = routes && routes.length > 1 ? routes[routes.length - 2] : null;
      if (prevRoute && screenNameToStep[prevRoute.name]) {
        useOnboardingStore.getState().setStep(screenNameToStep[prevRoute.name]);
      } else {
        const curStep = useOnboardingStore.getState().step;
        if (curStep > 2) {
          useOnboardingStore.getState().setStep(curStep - 1);
        }
      }
      navigation.goBack();
    } else {
      const curStep = useOnboardingStore.getState().step;
      if (curStep > 2) {
        const prevStep = curStep - 1;
        useOnboardingStore.getState().setStep(prevStep);
        const prevScreen = stepToScreenName[prevStep];
        if (prevScreen) {
          (navigation as any).navigate(prevScreen);
          return;
        }
      }
      Alert.alert(
        "Exit Onboarding?",
        "Are you sure you want to exit and return to the login screen?",
        [
          { text: "Stay", style: "cancel" },
          {
            text: "Log Out",
            style: "destructive",
            onPress: () => useAuthStore.getState().logout(),
          },
        ]
      );
    }
  };

  const handleNextPress = () => {
    setToastVisible(false);
    onNext();
  };

  const content = (
    <View style={styles.inner}>
      {/* Back */}
      <TouchableOpacity onPress={handleBack} style={styles.back}>
        <BackIcon color={colors.dark} />
      </TouchableOpacity>

      {/* Title */}
      <Text style={styles.title} maxFontSizeMultiplier={1.35}>{title}</Text>
      {subtitle ? <Text style={styles.subtitle} maxFontSizeMultiplier={1.35}>{subtitle}</Text> : null}

      {/* Step content */}
      <View style={styles.body}>{children}</View>

      {/* CTA */}
      <View style={styles.cta}>
        <PrimaryButton
          label={nextLabel}
          onPress={handleNextPress}
          loading={loading}
          disabled={disabled || loading}
        />
        {skipLabel && onSkip ? (
          <TouchableOpacity onPress={onSkip} style={styles.skip}>
            <Text style={styles.skipText} maxFontSizeMultiplier={1.35}>{skipLabel}</Text>
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
      {error && toastVisible && (
        <ErrorToast
          title={error.title}
          message={error.message}
          visible={toastVisible}
          onDismiss={() => {
            setToastVisible(false);
            onDismissError?.();
          }}
        />
      )}

      <ScrollView
        contentContainerStyle={{ flexGrow: 1 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {content}
      </ScrollView>
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
      accessible={true}
      accessibilityRole="checkbox"
      accessibilityLabel={label}
      accessibilityState={{ selected: !!selected }}
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
      accessible={true}
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityHint={sub}
      accessibilityState={{ checked: !!value }}
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
