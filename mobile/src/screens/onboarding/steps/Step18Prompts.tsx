/**
 * Step 18 — Prompts: 1–3 items, each with prompt_key + response_text (5–200 chars) + position
 * Backend: PromptItem schema with unique position validation
 */
import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography, radii } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep18 } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step18">;

const PROMPT_OPTIONS = [
  "The most important thing my family taught me",
  "My love language is",
  "A perfect Sunday for me looks like",
  "I'll know it's a match if",
  "My Paryushan ritual that I'm most proud of",
  "The dish I could eat every day",
  "I want someone who",
  "Two truths and a lie",
  "My most controversial opinion",
  "The quality I value most in a partner",
];

interface PromptEntry {
  prompt_key: string;
  response_text: string;
  position: number;
}

export default function Step18Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [prompts, setPrompts] = useState<PromptEntry[]>(
    data.prompts?.length ? data.prompts : [{ prompt_key: "", response_text: "", position: 1 }]
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [showPicker, setShowPicker] = useState<number | null>(null);

  const isValid = prompts.every(
    (p) => p.prompt_key && p.response_text.trim().length >= 5
  );

  const updatePrompt = (index: number, patch: Partial<PromptEntry>) => {
    setPrompts((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  };

  const addPrompt = () => {
    if (prompts.length < 3) {
      setPrompts((prev) => [
        ...prev,
        { prompt_key: "", response_text: "", position: prev.length + 1 },
      ]);
    }
  };

  const removePrompt = (index: number) => {
    setPrompts((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((p, i) => ({ ...p, position: i + 1 }))
    );
  };

  const handleNext = async () => {
    setLoading(true);
    try {
      await submitStep18(prompts.filter((p) => p.prompt_key && p.response_text.trim().length >= 5));
      updateData({ prompts });
      setStep(19);
      navigation.navigate("Step19");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Your conversation starters"
      subtitle="Answer 1–3 prompts. These are the heart of your profile."
      onNext={handleNext}
      loading={loading}
      disabled={!isValid}
      error={error}
      scrollable
    >
      {prompts.map((prompt, idx) => (
        <View key={idx} style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardNum}>Prompt {idx + 1}</Text>
            {prompts.length > 1 && (
              <TouchableOpacity onPress={() => removePrompt(idx)}>
                <Text style={styles.remove}>Remove</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Prompt picker */}
          <TouchableOpacity
            style={styles.promptPicker}
            onPress={() => setShowPicker(showPicker === idx ? null : idx)}
          >
            <Text style={[styles.promptKey, !prompt.prompt_key && styles.placeholder]}>
              {prompt.prompt_key || "Choose a prompt..."}
            </Text>
          </TouchableOpacity>

          {/* Prompt options dropdown */}
          {showPicker === idx && (
            <ScrollView style={styles.dropdown} nestedScrollEnabled>
              {PROMPT_OPTIONS.filter(
                (o) => !prompts.some((p, i) => i !== idx && p.prompt_key === o)
              ).map((opt) => (
                <TouchableOpacity
                  key={opt}
                  style={styles.dropdownItem}
                  onPress={() => {
                    updatePrompt(idx, { prompt_key: opt });
                    setShowPicker(null);
                  }}
                >
                  <Text style={styles.dropdownText}>{opt}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          {/* Response text */}
          <TextInput
            value={prompt.response_text}
            onChangeText={(t) => updatePrompt(idx, { response_text: t.slice(0, 200) })}
            placeholder="Your answer..."
            placeholderTextColor={colors.mid}
            multiline
            style={styles.response}
            textAlignVertical="top"
          />
          <Text style={styles.counter}>{prompt.response_text.length}/200</Text>
        </View>
      ))}

      {prompts.length < 3 && (
        <TouchableOpacity style={styles.addBtn} onPress={addPrompt}>
          <Text style={styles.addText}>+ Add another prompt</Text>
        </TouchableOpacity>
      )}
    </OnboardingStep>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.base,
    backgroundColor: colors.white,
    marginBottom: spacing.md,
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  cardNum: { ...typography.caption, color: colors.mid, textTransform: "uppercase" },
  remove: { ...typography.bodySmall, color: colors.red },
  promptPicker: {
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    paddingBottom: spacing.sm,
    marginBottom: spacing.sm,
  },
  promptKey: { ...typography.body, color: colors.dark },
  placeholder: { color: colors.mid },
  dropdown: {
    maxHeight: 180,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    backgroundColor: colors.white,
    marginBottom: spacing.sm,
  },
  dropdownItem: {
    padding: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.light,
  },
  dropdownText: { ...typography.bodySmall, color: colors.dark },
  response: {
    ...typography.body,
    color: colors.dark,
    minHeight: 80,
  },
  counter: { ...typography.caption, color: colors.mid, textAlign: "right", marginTop: 4 },
  addBtn: {
    paddingVertical: spacing.md,
    alignItems: "center",
    borderWidth: 1.5,
    borderColor: colors.saffron,
    borderRadius: radii.lg,
    borderStyle: "dashed",
  },
  addText: { ...typography.body, color: colors.saffron, fontFamily: "Outfit_600SemiBold" },
});
