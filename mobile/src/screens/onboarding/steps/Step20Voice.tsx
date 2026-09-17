/**
 * Step 20 — Voice snapshot: record 7-second audio clip
 * Upload via presigned URL to S3. Backend: media_id UUID.
 */
import React, { useState, useRef } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { Audio } from "expo-av";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { VoiceIcon } from "../../../components/core/Icons";
import { colors, spacing, typography, radii } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep20, getPresignedUploadUrl, uploadToS3, confirmUpload } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step20">;

const MAX_DURATION = 7000; // 7 seconds

export default function Step20Screen() {
  const navigation = useNavigation<Nav>();
  const { updateData, setStep } = useOnboardingStore();
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [status, setStatus] = useState<"idle" | "recording" | "done" | "uploading">("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [mediaId, setMediaId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const elapsed = useRef(0);

  const startRecording = async () => {
    const { status: perm } = await Audio.requestPermissionsAsync();
    if (perm !== "granted") {
      setError({ title: "Microphone Access", message: "Please allow microphone access to record your voice snapshot." });
      return;
    }
    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
    const rec = new Audio.Recording();
    await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
    await rec.startAsync();
    setRecording(rec);
    setStatus("recording");
    elapsed.current = 0;

    timerRef.current = setInterval(() => {
      elapsed.current += 100;
      setDurationMs(elapsed.current);
      if (elapsed.current >= MAX_DURATION) {
        stopRecording(rec);
      }
    }, 100);
  };

  const stopRecording = async (rec?: Audio.Recording) => {
    const r = rec ?? recording;
    if (!r) return;
    if (timerRef.current) clearInterval(timerRef.current);
    await r.stopAndUnloadAsync();
    const uri = r.getURI();
    setRecordingUri(uri);
    setRecording(null);
    setStatus("done");
  };

  const uploadAndContinue = async () => {
    if (!recordingUri) return;
    setStatus("uploading");
    setLoading(true);
    try {
      const { media_id, upload_url, presigned_fields } = await getPresignedUploadUrl("voice");
      await uploadToS3(upload_url, recordingUri, "audio/m4a", presigned_fields);
      await confirmUpload(media_id);
      await submitStep20(media_id);
      updateData({ voiceSnapshotId: media_id });
      setMediaId(media_id);
      setStep(21);
      navigation.navigate("Step21");
    } catch (err) {
      setError(extractError(err));
      setStatus("done");
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    setStep(21);
    navigation.navigate("Step21");
  };

  const progressPct = Math.min((durationMs / MAX_DURATION) * 100, 100);

  return (
    <OnboardingStep
      title="Voice Snapshot"
      subtitle="Voice snapshots have been retired in Jainune v2."
      onNext={handleSkip}
      disabled={false}
      nextLabel="Continue"
      skipLabel="Skip"
      onSkip={handleSkip}
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
  center: { alignItems: "center", paddingVertical: spacing.xxl },
  recordBtn: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.saffronLight,
    borderWidth: 2,
    borderColor: colors.saffron,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xl,
  },
  recordBtnActive: {
    backgroundColor: colors.saffron,
    borderColor: colors.saffronMid,
  },
  progressTrack: {
    width: "80%",
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: "hidden",
    marginBottom: spacing.base,
  },
  progressFill: {
    height: "100%",
    backgroundColor: colors.saffron,
  },
  done: { ...typography.body, color: colors.green, marginBottom: spacing.sm },
  hint: { ...typography.bodySmall, color: colors.mid, textAlign: "center" },
});
