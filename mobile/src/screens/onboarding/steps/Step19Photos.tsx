/**
 * Step 19 — Photos: upload 1–6 photos via presigned S3 URL
 * Backend: submitStep19(media_ids[]) confirms already-uploaded photos
 * Actual upload uses getPresignedUploadUrl() → PUT to S3 presigned URL
 */
import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  Alert,
  Platform,
  Linking,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import OnboardingStep from "../OnboardingStep";
import { colors, spacing, typography, radii } from "../../../theme/tokens";
import { useOnboardingStore } from "../../../store/onboardingStore";
import { submitStep19, getPresignedUploadUrl, uploadToS3, confirmUpload } from "../../../api/onboardingApi";
import { extractError } from "../../../api/client";
import type { OnboardingStackParams } from "../OnboardingNavigator";

type Nav = NativeStackNavigationProp<OnboardingStackParams, "Step19">;

interface UploadedPhoto {
  mediaId: string;
  localUri: string;
  cdnUrl: string;
}

export default function Step19Screen() {
  const navigation = useNavigation<Nav>();
  const { data, updateData, setStep } = useOnboardingStore();
  const [photos, setPhotos] = useState<UploadedPhoto[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);

  const processAndUploadAsset = useCallback(async (asset: ImagePicker.ImagePickerAsset) => {
    setUploading(true);
    setError(null);
    try {
      const { media_id, upload_url, cdn_url } = await getPresignedUploadUrl("photo");
      await uploadToS3(upload_url, asset.uri, asset.mimeType ?? "image/jpeg");
      await confirmUpload(media_id);
      setPhotos((prev) => [...prev, { mediaId: media_id, localUri: asset.uri, cdnUrl: cdn_url }]);
    } catch (err) {
      setError(extractError(err));
    } finally {
      setUploading(false);
    }
  }, []);

  // Android Activity destruction recovery (budget devices / low memory)
  useEffect(() => {
    if (Platform.OS === "android") {
      ImagePicker.getPendingResultAsync()
        .then((results) => {
          if (Array.isArray(results)) {
            for (const res of results) {
              if ("canceled" in res && !res.canceled && res.assets && res.assets.length > 0) {
                processAndUploadAsset(res.assets[0]);
                break;
              }
            }
          }
        })
        .catch(() => {});
    }
  }, [processAndUploadAsset]);

  const pickAndUpload = async () => {
    if (photos.length >= 6) return;
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Permission Required",
        "Photo library access is needed to upload photos. Please grant permission in Settings.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Open Settings", onPress: () => Linking.openSettings() },
        ]
      );
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [4, 5],
      quality: 0.8,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;

    await processAndUploadAsset(result.assets[0]);
  };

  const removePhoto = (mediaId: string) => {
    setPhotos((prev) => prev.filter((p) => p.mediaId !== mediaId));
  };

  const handleNext = async () => {
    if (photos.length === 0) return;
    setLoading(true);
    try {
      await submitStep19(photos.map((p) => p.mediaId));
      updateData({ photoIds: photos.map((p) => p.mediaId) });
      setStep(20);
      navigation.navigate("Step20");
    } catch (err) {
      setError(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingStep
      title="Add your photos"
      subtitle="Upload 1–6 photos. First photo is your main profile picture."
      onNext={handleNext}
      loading={loading}
      disabled={photos.length === 0 || loading}
      error={error}
      scrollable
    >
      <View style={styles.grid}>
        {/* Existing photos */}
        {photos.map((photo, idx) => (
          <View key={photo.mediaId} style={styles.slot}>
            <Image source={{ uri: photo.localUri }} style={styles.slotImage} />
            {idx === 0 && (
              <View style={styles.mainBadge}>
                <Text style={styles.mainText}>Main</Text>
              </View>
            )}
            <TouchableOpacity
              style={styles.removeBtn}
              onPress={() => removePhoto(photo.mediaId)}
            >
              <Text style={styles.removeBtnText}>×</Text>
            </TouchableOpacity>
          </View>
        ))}

        {/* Add slot */}
        {photos.length < 6 && (
          <TouchableOpacity
            style={[styles.slot, styles.addSlot]}
            onPress={pickAndUpload}
            disabled={uploading}
          >
            {uploading ? (
              <ActivityIndicator color={colors.saffron} />
            ) : (
              <Text style={styles.addSlotText}>+</Text>
            )}
          </TouchableOpacity>
        )}

        {/* Empty slots */}
        {Array.from({ length: Math.max(0, 6 - photos.length - (photos.length < 6 ? 1 : 0)) }).map(
          (_, i) => (
            <View key={`empty-${i}`} style={[styles.slot, styles.emptySlot]} />
          )
        )}
      </View>

      <Text style={styles.tip}>
        Clear face photos get 3× more connections. Avoid sunglasses or group photos.
      </Text>
    </OnboardingStep>
  );
}

const SLOT_SIZE = 100;

const styles = StyleSheet.create({
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginBottom: spacing.xl,
  },
  slot: {
    width: SLOT_SIZE,
    height: SLOT_SIZE,
    borderRadius: radii.lg,
    overflow: "hidden",
  },
  slotImage: { width: "100%", height: "100%", resizeMode: "cover" },
  mainBadge: {
    position: "absolute",
    bottom: 4,
    left: 4,
    backgroundColor: colors.saffron,
    borderRadius: radii.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  mainText: { ...typography.caption, color: colors.white, fontSize: 10 },
  removeBtn: {
    position: "absolute",
    top: 4,
    right: 4,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center",
    justifyContent: "center",
  },
  removeBtnText: { color: colors.white, fontSize: 14, lineHeight: 14 },
  addSlot: {
    backgroundColor: colors.saffronLight,
    borderWidth: 2,
    borderColor: colors.saffron,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
  },
  addSlotText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 32,
    color: colors.saffron,
  },
  emptySlot: {
    backgroundColor: colors.light,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tip: {
    ...typography.bodySmall,
    color: colors.mid,
    textAlign: "center",
    lineHeight: 18,
  },
});
