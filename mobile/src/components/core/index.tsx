/**
 * Core Components — PrimaryButton, GhostButton, TextInput, ProgressBar
 * Spec: FRONTEND_SPEC.md §1.3
 */

import React from "react";
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  View,
  TextInput as RNTextInput,
  TextInputProps,
  Animated,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { colors, spacing, radii, typography, gradients } from "../../theme/tokens";

// ── PrimaryButton ─────────────────────────────────────────────────────────────

interface PrimaryButtonProps {
  label: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  style?: object;
}

export function PrimaryButton({ label, onPress, loading, disabled, style }: PrimaryButtonProps) {
  const handlePress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onPress();
  };

  return (
    <TouchableOpacity
      onPress={handlePress}
      disabled={disabled || loading}
      activeOpacity={0.85}
      style={[styles.primaryOuter, style]}
    >
      <LinearGradient
        colors={disabled ? ["#CCBCB0", "#CCBCB0"] : gradients.button}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={styles.primaryGradient}
      >
        {loading ? (
          <ActivityIndicator color={colors.white} size="small" />
        ) : (
          <Text style={styles.primaryLabel} maxFontSizeMultiplier={1.35}>{label}</Text>
        )}
      </LinearGradient>
    </TouchableOpacity>
  );
}

// ── GhostButton ───────────────────────────────────────────────────────────────

interface GhostButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  style?: object;
}

export function GhostButton({ label, onPress, disabled, style }: GhostButtonProps) {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled}
      activeOpacity={0.7}
      style={[styles.ghost, style]}
    >
      <Text style={styles.ghostLabel} maxFontSizeMultiplier={1.35}>{label}</Text>
    </TouchableOpacity>
  );
}

// ── JaiuneTextInput ───────────────────────────────────────────────────────────

interface JainuneInputProps extends TextInputProps {
  label?: string;
  error?: string;
}

export function JainuneInput({ label, error, style, ...props }: JainuneInputProps) {
  const [focused, setFocused] = React.useState(false);
  return (
    <View style={styles.inputWrapper}>
      {label ? <Text style={styles.inputLabel} maxFontSizeMultiplier={1.35}>{label}</Text> : null}
      <RNTextInput
        style={[
          styles.input,
          focused && styles.inputFocused,
          error ? styles.inputError : null,
          style,
        ]}
        maxFontSizeMultiplier={1.35}
        placeholderTextColor={colors.muted}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        {...props}
      />
      {error ? <Text style={styles.errorText} maxFontSizeMultiplier={1.35}>{error}</Text> : null}
    </View>
  );
}

// ── OTPInput ──────────────────────────────────────────────────────────────────

interface OTPInputProps {
  value: string;
  onChange: (val: string) => void;
  error?: string;
}

export function OTPInput({ value, onChange, error }: OTPInputProps) {
  const inputRef = React.useRef<RNTextInput>(null);

  const digits = value.padEnd(6, " ").split("").slice(0, 6);

  return (
    <View>
      <TouchableOpacity onPress={() => inputRef.current?.focus()} activeOpacity={1}>
        <View style={styles.otpRow}>
          {digits.map((d, i) => {
            const filled = d.trim().length > 0;
            const active = i === value.length;
            return (
              <View
                key={i}
                style={[
                  styles.otpBox,
                  filled && styles.otpBoxFilled,
                  active && styles.otpBoxActive,
                  error ? styles.otpBoxError : null,
                ]}
              >
                <Text style={styles.otpDigit}>{filled ? d : ""}</Text>
              </View>
            );
          })}
        </View>
      </TouchableOpacity>
      <RNTextInput
        ref={inputRef}
        value={value}
        onChangeText={(t) => {
          const digits = t.replace(/\D/g, "").slice(0, 6);
          onChange(digits);
          if (digits.length > 0) Haptics.selectionAsync();
        }}
        keyboardType="number-pad"
        maxLength={6}
        style={styles.otpHidden}
        autoFocus
        caretHidden
      />
      {error ? <Text style={[styles.errorText, { textAlign: "center", marginTop: spacing.sm }]}>{error}</Text> : null}
    </View>
  );
}

// ── ProgressBar ───────────────────────────────────────────────────────────────

interface ProgressBarProps {
  current: number;
  total: number;
}

export function ProgressBar({ current, total }: ProgressBarProps) {
  const progress = Math.min(current / total, 1);
  const animVal = React.useRef(new Animated.Value(0)).current;

  React.useEffect(() => {
    Animated.timing(animVal, {
      toValue: progress,
      duration: 300,
      useNativeDriver: false,
    }).start();
  }, [progress]);

  return (
    <View style={styles.progressTrack}>
      <Animated.View
        style={[
          styles.progressFill,
          {
            width: animVal.interpolate({
              inputRange: [0, 1],
              outputRange: ["0%", "100%"],
            }),
          },
        ]}
      />
    </View>
  );
}

// ── Toast (friendly error display) ───────────────────────────────────────────

interface ToastProps {
  title: string;
  message: string;
  visible: boolean;
}

export function ErrorToast({ title, message, visible }: ToastProps) {
  if (!visible) return null;
  return (
    <View style={styles.toast}>
      <Text style={styles.toastTitle}>{title}</Text>
      <Text style={styles.toastMsg}>{message}</Text>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  // PrimaryButton
  primaryOuter: {
    borderRadius: radii.full,
    overflow: "hidden",
    shadowColor: colors.saffron,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 6,
  },
  primaryGradient: {
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
  },
  primaryLabel: {
    ...typography.cta,
    color: colors.white,
  },

  // GhostButton
  ghost: {
    minHeight: 52,
    borderRadius: radii.full,
    borderWidth: 1.5,
    borderColor: colors.saffron,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
  },
  ghostLabel: {
    ...typography.cta,
    color: colors.saffron,
  },

  // TextInput
  inputWrapper: { marginBottom: spacing.md },
  inputLabel: {
    ...typography.bodySmall,
    color: colors.mid,
    marginBottom: spacing.xs,
  },
  input: {
    ...typography.body,
    color: colors.dark,
    borderBottomWidth: 1.5,
    borderBottomColor: colors.border,
    paddingVertical: spacing.sm,
    paddingHorizontal: 0,
  },
  inputFocused: { borderBottomColor: colors.saffron },
  inputError: { borderBottomColor: colors.red },
  errorText: {
    ...typography.bodySmall,
    color: colors.red,
    marginTop: spacing.xs,
  },

  // OTP (optimized for 320px screens and large fonts)
  otpRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 6,
  },
  otpBox: {
    width: 44,
    height: 52,
    borderRadius: radii.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  otpBoxFilled: { borderColor: colors.saffron, backgroundColor: colors.saffronLight },
  otpBoxActive: { borderColor: colors.saffron },
  otpBoxError: { borderColor: colors.red },
  otpDigit: { ...typography.h3, color: colors.dark },
  otpHidden: {
    position: "absolute",
    width: 1,
    height: 1,
    opacity: 0,
  },

  // ProgressBar
  progressTrack: {
    height: 3,
    backgroundColor: colors.pinkLight,
    borderRadius: 2,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: colors.saffron,
    borderRadius: 2,
  },

  // Toast
  toast: {
    position: "absolute",
    top: 60,
    left: spacing.base,
    right: spacing.base,
    backgroundColor: colors.dark,
    borderRadius: radii.md,
    padding: spacing.base,
    zIndex: 9999,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 10,
  },
  toastTitle: {
    ...typography.h3,
    color: colors.white,
    marginBottom: 4,
  },
  toastMsg: {
    ...typography.bodySmall,
    color: "#CCCCCC",
  },
});
