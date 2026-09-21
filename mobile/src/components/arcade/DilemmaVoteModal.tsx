/**
 * DilemmaVoteModal — BUG-008
 * Shows arcade dilemmas one at a time. User picks A or B, then sees live
 * vote percentages. Swipe through the deck via Next button.
 */

import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TouchableOpacity,
  Animated,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import {
  getDilemmas,
  voteDilemma,
  getDilemmaResults,
  Dilemma,
  DilemmaResults,
} from "../../api/profileApi";
import { colors, spacing, radii } from "../../theme/tokens";
import { extractError } from "../../api/client";

interface Props {
  visible: boolean;
  onClose: () => void;
}

export default function DilemmaVoteModal({ visible, onClose }: Props) {
  const [dilemmas, setDilemmas] = useState<Dilemma[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [voting, setVoting] = useState(false);
  const [results, setResults] = useState<DilemmaResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const barA = useRef(new Animated.Value(0)).current;
  const barB = useRef(new Animated.Value(0)).current;

  // Load deck on open
  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    setIndex(0);
    setResults(null);
    setError(null);
    getDilemmas(10, 0)
      .then((d) => setDilemmas(d))
      .catch((e) => setError(extractError(e).message || "Failed to load dilemmas."))
      .finally(() => setLoading(false));
  }, [visible]);

  const current: Dilemma | undefined = dilemmas[index];

  // Animate bars whenever results change
  useEffect(() => {
    if (!results) {
      barA.setValue(0);
      barB.setValue(0);
      return;
    }
    Animated.parallel([
      Animated.timing(barA, {
        toValue: results.pct_a,
        duration: 500,
        useNativeDriver: false,
      }),
      Animated.timing(barB, {
        toValue: results.pct_b,
        duration: 500,
        useNativeDriver: false,
      }),
    ]).start();
  }, [results]);

  const handleVote = async (choice: "A" | "B") => {
    if (!current || voting) return;
    setVoting(true);
    setError(null);
    try {
      await voteDilemma(current.id, choice);
      const r = await getDilemmaResults(current.id);
      setResults(r);
    } catch (e: any) {
      const err = extractError(e);
      const errText = (
        typeof e?._apiError === "string"
          ? e._apiError
          : (e?._apiError?.message || e?._apiError?.code || err.message || "")
      ).toLowerCase();

      // already_voted — still fetch results to show them
      if (errText.includes("already") || errText.includes("voted")) {
        try {
          const r = await getDilemmaResults(current.id);
          setResults(r);
        } catch {
          setError("Couldn't load results.");
        }
      } else {
        setError(err.message || "Vote failed.");
      }
    } finally {
      setVoting(false);
    }
  };

  const handleNext = () => {
    setResults(null);
    setError(null);
    barA.setValue(0);
    barB.setValue(0);
    setIndex((i) => i + 1);
  };

  const renderContent = () => {
    if (loading) {
      return (
        <View style={styles.center}>
          <ActivityIndicator color={colors.saffron} size="large" />
          <Text style={styles.loadingText}>Loading dilemmas…</Text>
        </View>
      );
    }

    if (error && !results) {
      return (
        <View style={styles.center}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity
            style={styles.retryBtn}
            onPress={() => {
              setLoading(true);
              setError(null);
              getDilemmas(10, 0)
                .then((d) => {
                  setDilemmas(d);
                  setIndex(0);
                })
                .catch((e) => setError(extractError(e).message || "Failed."))
                .finally(() => setLoading(false));
            }}
          >
            <Text style={styles.retryBtnText}>Retry</Text>
          </TouchableOpacity>
        </View>
      );
    }

    if (!current || index >= dilemmas.length) {
      return (
        <View style={styles.center}>
          <Text style={styles.doneEmoji}>🎉</Text>
          <Text style={styles.doneText}>You've seen all dilemmas!</Text>
          <TouchableOpacity style={styles.closeAction} onPress={onClose}>
            <Text style={styles.closeActionText}>Close</Text>
          </TouchableOpacity>
        </View>
      );
    }

    const voted = !!results;

    return (
      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Counter */}
        <Text style={styles.counter}>
          {index + 1} / {dilemmas.length}
        </Text>

        {/* Tags */}
        {Array.isArray(current.tags) && current.tags.length > 0 && (
          <View style={styles.tagRow}>
            {current.tags.slice(0, 3).map((t) => (
              <View key={t} style={styles.tag}>
                <Text style={styles.tagText}>{t}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Question */}
        <Text style={styles.question}>{current.question_text}</Text>

        {/* Vote buttons / Result bars */}
        {!voted ? (
          <View style={styles.optionsRow}>
            <TouchableOpacity
              style={[styles.optionBtn, styles.optionA, voting && styles.optionDisabled]}
              onPress={() => handleVote("A")}
              disabled={voting}
            >
              {voting ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.optionText}>{current.option_a}</Text>
              )}
            </TouchableOpacity>

            <View style={styles.vsCircle}>
              <Text style={styles.vsText}>VS</Text>
            </View>

            <TouchableOpacity
              style={[styles.optionBtn, styles.optionB, voting && styles.optionDisabled]}
              onPress={() => handleVote("B")}
              disabled={voting}
            >
              {voting ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.optionText}>{current.option_b}</Text>
              )}
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.resultsWrap}>
            {/* Option A bar */}
            <View style={styles.resultRow}>
              <Text style={styles.resultLabel} numberOfLines={1}>
                {results.option_a}
              </Text>
              <View style={styles.barTrack}>
                <Animated.View
                  style={[
                    styles.barFill,
                    styles.barFillA,
                    {
                      width: barA.interpolate({
                        inputRange: [0, 100],
                        outputRange: ["0%", "100%"],
                      }) as any,
                    },
                  ]}
                />
              </View>
              <Text style={styles.pctText}>{Math.round(results.pct_a)}%</Text>
            </View>

            {/* Option B bar */}
            <View style={styles.resultRow}>
              <Text style={styles.resultLabel} numberOfLines={1}>
                {results.option_b}
              </Text>
              <View style={styles.barTrack}>
                <Animated.View
                  style={[
                    styles.barFill,
                    styles.barFillB,
                    {
                      width: barB.interpolate({
                        inputRange: [0, 100],
                        outputRange: ["0%", "100%"],
                      }) as any,
                    },
                  ]}
                />
              </View>
              <Text style={styles.pctText}>{Math.round(results.pct_b)}%</Text>
            </View>

            <Text style={styles.totalVotes}>{results.total_votes} votes</Text>
          </View>
        )}

        {/* Error after vote */}
        {error && voted && <Text style={styles.errorText}>{error}</Text>}

        {/* Next / Done */}
        {voted && (
          <TouchableOpacity
            style={styles.nextBtn}
            onPress={index + 1 < dilemmas.length ? handleNext : onClose}
          >
            <Text style={styles.nextBtnText}>
              {index + 1 < dilemmas.length ? "Next →" : "Done"}
            </Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    );
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.headerTitle}>Jain Dilemmas 🧩</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeBtnText}>✕</Text>
            </TouchableOpacity>
          </View>

          {renderContent()}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.75)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#16181D",
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    padding: spacing.xl,
    paddingBottom: spacing.xxl,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    maxHeight: "85%",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.base,
  },
  headerTitle: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 20,
    color: "#fff",
  },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.1)",
    alignItems: "center",
    justifyContent: "center",
  },
  closeBtnText: {
    color: "#fff",
    fontSize: 16,
  },
  center: {
    alignItems: "center",
    paddingVertical: spacing.xl,
    gap: spacing.base,
  },
  loadingText: {
    color: "rgba(255,255,255,0.5)",
    fontFamily: "Outfit_400Regular",
    fontSize: 14,
    marginTop: spacing.sm,
  },
  errorText: {
    color: "#FF6B6B",
    fontFamily: "Outfit_400Regular",
    fontSize: 14,
    textAlign: "center",
    marginTop: spacing.sm,
  },
  retryBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    marginTop: spacing.sm,
  },
  retryBtnText: {
    color: "#fff",
    fontFamily: "Outfit_600SemiBold",
    fontSize: 15,
  },
  doneEmoji: {
    fontSize: 48,
  },
  doneText: {
    color: "#fff",
    fontFamily: "Outfit_700Bold",
    fontSize: 18,
    textAlign: "center",
  },
  closeAction: {
    backgroundColor: "rgba(255,255,255,0.1)",
    borderRadius: radii.md,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    marginTop: spacing.sm,
  },
  closeActionText: {
    color: "#fff",
    fontFamily: "Outfit_600SemiBold",
    fontSize: 15,
  },
  counter: {
    color: "rgba(255,255,255,0.4)",
    fontFamily: "Outfit_400Regular",
    fontSize: 12,
    textAlign: "right",
    marginBottom: spacing.sm,
  },
  tagRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  tag: {
    backgroundColor: "rgba(255,255,255,0.07)",
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  tagText: {
    color: "rgba(255,255,255,0.5)",
    fontFamily: "Outfit_400Regular",
    fontSize: 11,
  },
  question: {
    color: "#fff",
    fontFamily: "Outfit_700Bold",
    fontSize: 20,
    lineHeight: 28,
    marginBottom: spacing.xl,
    textAlign: "center",
  },
  optionsRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.base,
  },
  optionBtn: {
    flex: 1,
    minHeight: 80,
    borderRadius: radii.lg,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.base,
  },
  optionA: {
    backgroundColor: "#7C3AED",
  },
  optionB: {
    backgroundColor: "#DB2777",
  },
  optionDisabled: {
    opacity: 0.6,
  },
  optionText: {
    color: "#fff",
    fontFamily: "Outfit_600SemiBold",
    fontSize: 14,
    textAlign: "center",
  },
  vsCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
  vsText: {
    color: "rgba(255,255,255,0.5)",
    fontFamily: "Outfit_700Bold",
    fontSize: 11,
  },
  resultsWrap: {
    gap: spacing.base,
    marginBottom: spacing.base,
  },
  resultRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  resultLabel: {
    color: "rgba(255,255,255,0.7)",
    fontFamily: "Outfit_400Regular",
    fontSize: 13,
    width: 80,
  },
  barTrack: {
    flex: 1,
    height: 12,
    backgroundColor: "rgba(255,255,255,0.08)",
    borderRadius: 6,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    borderRadius: 6,
  },
  barFillA: {
    backgroundColor: "#7C3AED",
  },
  barFillB: {
    backgroundColor: "#DB2777",
  },
  pctText: {
    color: "#fff",
    fontFamily: "Outfit_700Bold",
    fontSize: 13,
    width: 38,
    textAlign: "right",
  },
  totalVotes: {
    color: "rgba(255,255,255,0.35)",
    fontFamily: "Outfit_400Regular",
    fontSize: 12,
    textAlign: "center",
  },
  nextBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.md,
    paddingVertical: spacing.base,
    alignItems: "center",
    marginTop: spacing.base,
  },
  nextBtnText: {
    color: "#fff",
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
  },
});
