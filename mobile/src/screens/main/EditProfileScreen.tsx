/**
 * EditProfileScreen — Phase 7 Full Profile Editing
 * Allows updating:
 * - Photos: upload via presigned S3 URL, delete
 * - Basic details: First name, City, Profession, Education
 * - Community Sect & Dietary Strictness
 * - Root vegetables & Onion/Garlic switches
 * - Looking for & Vibe zones tags
 * - Profile Prompts responses
 *
 * Security:
 * - FLAG_SECURE on mount
 * - Name input validated via validateName()
 */

import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Image,
  Switch,
  ActivityIndicator,
  Alert,
  Platform,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { Audio } from "expo-av";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  getMyProfile,
  updateProfile,
  presignUpload,
  addPhoto,
  deletePhoto,
  updateVoiceSnapshot,
  MyProfile,
} from "../../api/profileApi";
import { uploadToPresignedUrl, extractError } from "../../api/client";
import { validateName } from "../../security/inputValidation";
import {
  enableScreenCaptureProtection,
  disableScreenCaptureProtection,
} from "../../security/antiReversing";

const SECT_OPTIONS = [
  "Digambara",
  "Svetambara Murtipujak",
  "Svetambara Sthanakvasi",
  "Svetambara Terapanthi",
  "Just Jain",
];

const DIET_OPTIONS = [
  "Strict Jain (No root, onion, garlic)",
  "Jain Vegetarian",
  "Vegetarian",
  "Vegan",
];

const LOOKING_FOR_OPTIONS = ["Marriage", "Serious Relationship", "Long-term Dating"];

const VIBE_ZONE_OPTIONS = [
  "Quiet & Contemplative",
  "Food & Cooking",
  "Travel & Adventure",
  "Art & Culture",
  "Family Gatherings",
  "Fitness & Yoga",
  "Philosophy & Dharma",
];

export default function EditProfileScreen() {
  const navigation = useNavigation<any>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  // Editable fields
  const [firstName, setFirstName] = useState("");
  const [city, setCity] = useState("");
  const [profession, setProfession] = useState("");
  const [education, setEducation] = useState("");
  const [communitySect, setCommunitySect] = useState("");
  const [dietaryStrictness, setDietaryStrictness] = useState("");
  const [eatsRootVeg, setEatsRootVeg] = useState(false);
  const [eatsOnionGarlic, setEatsOnionGarlic] = useState(false);
  const [openToRelocation, setOpenToRelocation] = useState(false);
  const [lookingFor, setLookingFor] = useState<string[]>([]);
  const [vibeZones, setVibeZones] = useState<string[]>([]);
  const [photos, setPhotos] = useState<{ id: string; url: string; order: number }[]>([]);
  const [prompts, setPrompts] = useState<{ prompt_id: string; prompt_text: string; response: string }[]>([]);

  const [voiceSnapshotUrl, setVoiceSnapshotUrl] = useState<string | null>(null);
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [uploadingVoice, setUploadingVoice] = useState(false);

  useEffect(() => {
    enableScreenCaptureProtection();
    loadProfile();
    return () => {
      disableScreenCaptureProtection();
      if (recording) {
        recording.stopAndUnloadAsync().catch(() => {});
      }
    };
  }, []);

  const loadProfile = async () => {
    setLoading(true);
    try {
      const data = await getMyProfile();
      setFirstName(data.first_name || "");
      setCity(data.city || "");
      setProfession(data.profession || "");
      setEducation(data.education || "");
      setCommunitySect(data.community_sect || "");
      setDietaryStrictness(data.dietary_strictness || "");
      setEatsRootVeg(data.eats_root_vegetables ?? false);
      setEatsOnionGarlic(data.eats_onion_garlic ?? false);
      setOpenToRelocation(data.open_to_relocation ?? false);
      setLookingFor(data.looking_for || []);
      setVibeZones(data.vibe_zones || []);
      setPhotos(data.photos || []);
      setPrompts(data.prompts || []);
      setVoiceSnapshotUrl(data.voice_snapshot_url || null);
    } catch (err) {
      Alert.alert("Error", extractError(err).message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleVoiceRecording = async () => {
    if (isRecording) {
      if (!recording) return;
      setIsRecording(false);
      setUploadingVoice(true);
      try {
        await recording.stopAndUnloadAsync();
        const uri = recording.getURI();
        setRecording(null);
        if (!uri) throw new Error("Audio recording failed");

        const presign = await presignUpload("audio/m4a", 1024 * 1024);
        await uploadToPresignedUrl(presign.upload_url, uri, "audio/m4a");
        const res = await updateVoiceSnapshot(presign.media_id);
        setVoiceSnapshotUrl(res.voice_snapshot_url || presign.cdn_url);
        Alert.alert("Voice Snapshot Updated", "Your new 7-second voice snippet is now live on your profile!");
      } catch (err) {
        Alert.alert("Voice Upload Error", extractError(err).message);
      } finally {
        setUploadingVoice(false);
      }
    } else {
      const { status: perm } = await Audio.requestPermissionsAsync();
      if (perm !== "granted") {
        Alert.alert("Microphone Access Required", "Please allow microphone access to record your voice snapshot.");
        return;
      }
      try {
        await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
        const rec = new Audio.Recording();
        await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
        await rec.startAsync();
        setRecording(rec);
        setIsRecording(true);
      } catch (err) {
        Alert.alert("Recording Failed", extractError(err).message);
      }
    }
  };

  const handlePickAndUploadPhoto = async () => {
    if (photos.length >= 6) {
      Alert.alert("Maximum Photos", "You can upload up to 6 photos.");
      return;
    }

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [4, 5],
        quality: 0.8,
      });

      if (result.canceled || !result.assets[0]?.uri) return;

      const asset = result.assets[0];
      setUploadingPhoto(true);

      const mime = asset.type === "image" ? "image/jpeg" : "image/jpeg";
      const sizeBytes = asset.fileSize || 1024 * 1024;

      // 1. Presign upload URL
      const presign = await presignUpload(mime, sizeBytes);

      // 2. Upload file directly to S3
      await uploadToPresignedUrl(presign.upload_url, asset.uri, mime);

      // 3. Register photo in user profile
      await addPhoto(presign.media_id);

      // Refresh photos
      setPhotos((prev) => [
        ...prev,
        { id: presign.media_id, url: presign.cdn_url, order: prev.length },
      ]);
    } catch (err) {
      Alert.alert("Upload Failed", extractError(err).message);
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleDeletePhoto = (photoId: string) => {
    if (photos.length <= 1) {
      Alert.alert("Cannot Remove", "You must keep at least 1 profile photo.");
      return;
    }

    Alert.alert("Delete Photo", "Remove this photo from your profile?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: async () => {
          try {
            await deletePhoto(photoId);
            setPhotos((prev) => prev.filter((p) => p.id !== photoId));
          } catch (err) {
            Alert.alert("Error", extractError(err).message);
          }
        },
      },
    ]);
  };

  const toggleTag = (list: string[], item: string, setter: (val: string[]) => void) => {
    if (list.includes(item)) {
      setter(list.filter((x) => x !== item));
    } else {
      setter([...list, item]);
    }
  };

  const updatePromptResponse = (promptId: string, text: string) => {
    setPrompts((prev) =>
      prev.map((p) => (p.prompt_id === promptId ? { ...p, response: text } : p))
    );
  };

  const handleSave = async () => {
    const nameCheck = validateName(firstName);
    if (!nameCheck.valid) {
      Alert.alert("Invalid Name", nameCheck.error);
      return;
    }

    setSaving(true);
    try {
      await updateProfile({
        first_name: firstName.trim(),
        city: city.trim(),
        profession: profession.trim(),
        education: education.trim(),
        community_sect: communitySect,
        dietary_strictness: dietaryStrictness,
        eats_root_vegetables: eatsRootVeg,
        eats_onion_garlic: eatsOnionGarlic,
        open_to_relocation: openToRelocation,
        looking_for: lookingFor,
        vibe_zones: vibeZones,
      });

      Alert.alert("Profile Updated", "Your changes have been saved.", [
        { text: "Done", onPress: () => navigation.goBack() },
      ]);
    } catch (err) {
      Alert.alert("Save Failed", extractError(err).message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.saffron} />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 100 }}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backBtnText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Edit Profile</Text>
        <TouchableOpacity
          style={[styles.saveHeaderBtn, saving && styles.disabledBtn]}
          onPress={handleSave}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator size="small" color={colors.saffron} />
          ) : (
            <Text style={styles.saveHeaderBtnText}>Save</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Photos Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Profile Photos (Max 6)</Text>
        <Text style={styles.sectionHint}>
          The first photo is your primary card image. Tap a photo to delete.
        </Text>
        <View style={styles.photosGrid}>
          {photos.map((photo, index) => (
            <TouchableOpacity
              key={photo.id}
              style={styles.photoBox}
              onPress={() => handleDeletePhoto(photo.id)}
            >
              <Image source={{ uri: photo.url }} style={styles.photoImg} />
              {index === 0 && (
                <View style={styles.mainBadge}>
                  <Text style={styles.mainBadgeText}>Main</Text>
                </View>
              )}
              <View style={styles.deleteOverlay}>
                <Text style={styles.deleteOverlayText}>✕</Text>
              </View>
            </TouchableOpacity>
          ))}
          {photos.length < 6 && (
            <TouchableOpacity
              style={styles.addPhotoBox}
              onPress={handlePickAndUploadPhoto}
              disabled={uploadingPhoto}
            >
              {uploadingPhoto ? (
                <ActivityIndicator color={colors.saffron} />
              ) : (
                <>
                  <Text style={styles.addPhotoIcon}>＋</Text>
                  <Text style={styles.addPhotoText}>Add Photo</Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Basics Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Basic Info</Text>

        <Text style={styles.label}>First Name</Text>
        <TextInput
          style={styles.input}
          value={firstName}
          onChangeText={setFirstName}
          placeholder="First name"
          placeholderTextColor={colors.muted}
          maxLength={50}
        />

        <Text style={styles.label}>City</Text>
        <TextInput
          style={styles.input}
          value={city}
          onChangeText={setCity}
          placeholder="e.g. Bangalore, Mumbai"
          placeholderTextColor={colors.muted}
          maxLength={60}
        />

        <Text style={styles.label}>Profession</Text>
        <TextInput
          style={styles.input}
          value={profession}
          onChangeText={setProfession}
          placeholder="e.g. Software Engineer, Chartered Accountant"
          placeholderTextColor={colors.muted}
          maxLength={80}
        />

        <Text style={styles.label}>Education</Text>
        <TextInput
          style={styles.input}
          value={education}
          onChangeText={setEducation}
          placeholder="e.g. B.Tech, MBA, CA"
          placeholderTextColor={colors.muted}
          maxLength={80}
        />
      </View>

      {/* Voice Snapshot Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Voice Snapshot (7 Seconds)</Text>
        <Text style={styles.sectionHint}>
          {voiceSnapshotUrl
            ? "✦ Voice snapshot active on your profile. Tap below to re-record."
            : "Record a 7-second voice snippet to increase authentic connections."}
        </Text>
        <TouchableOpacity
          style={[
            styles.voiceBtn,
            isRecording && styles.voiceBtnRecording,
            uploadingVoice && styles.disabledBtn,
          ]}
          onPress={handleToggleVoiceRecording}
          disabled={uploadingVoice}
        >
          {uploadingVoice ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <Text style={styles.voiceBtnText}>
              {isRecording
                ? "⏹ Stop & Save Voice Snapshot"
                : voiceSnapshotUrl
                ? "🎙️ Re-record Voice Snapshot"
                : "🎙️ Record 7s Voice Snapshot"}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Community & Dietary Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Community & Dietary</Text>

        <Text style={styles.label}>Jain Community Sect</Text>
        <View style={styles.pillsWrap}>
          {SECT_OPTIONS.map((sect) => (
            <TouchableOpacity
              key={sect}
              style={[styles.pill, communitySect === sect && styles.pillSelected]}
              onPress={() => setCommunitySect(sect)}
            >
              <Text
                style={[
                  styles.pillText,
                  communitySect === sect && styles.pillTextSelected,
                ]}
              >
                {sect}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.label}>Dietary Practice</Text>
        <View style={styles.pillsWrap}>
          {DIET_OPTIONS.map((diet) => (
            <TouchableOpacity
              key={diet}
              style={[styles.pill, dietaryStrictness === diet && styles.pillSelected]}
              onPress={() => setDietaryStrictness(diet)}
            >
              <Text
                style={[
                  styles.pillText,
                  dietaryStrictness === diet && styles.pillTextSelected,
                ]}
              >
                {diet}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.switchRow}>
          <View style={styles.switchTextWrap}>
            <Text style={styles.switchLabel}>Eats Root Vegetables</Text>
            <Text style={styles.switchHint}>Potatoes, carrots, radish, ginger</Text>
          </View>
          <Switch
            value={eatsRootVeg}
            onValueChange={setEatsRootVeg}
            trackColor={{ false: colors.border, true: colors.green }}
            thumbColor={colors.white}
          />
        </View>

        <View style={styles.switchRow}>
          <View style={styles.switchTextWrap}>
            <Text style={styles.switchLabel}>Eats Onion & Garlic</Text>
            <Text style={styles.switchHint}>Kanda, lasan in cooked meals</Text>
          </View>
          <Switch
            value={eatsOnionGarlic}
            onValueChange={setEatsOnionGarlic}
            trackColor={{ false: colors.border, true: colors.green }}
            thumbColor={colors.white}
          />
        </View>

        <View style={styles.switchRow}>
          <View style={styles.switchTextWrap}>
            <Text style={styles.switchLabel}>Open to Relocation</Text>
            <Text style={styles.switchHint}>Willing to relocate for marriage</Text>
          </View>
          <Switch
            value={openToRelocation}
            onValueChange={setOpenToRelocation}
            trackColor={{ false: colors.border, true: colors.saffron }}
            thumbColor={colors.white}
          />
        </View>
      </View>

      {/* Looking For & Vibe Zones */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Intent & Vibe</Text>

        <Text style={styles.label}>Looking For</Text>
        <View style={styles.pillsWrap}>
          {LOOKING_FOR_OPTIONS.map((item) => {
            const isSelected = lookingFor.includes(item);
            return (
              <TouchableOpacity
                key={item}
                style={[styles.pill, isSelected && styles.pillSelected]}
                onPress={() => toggleTag(lookingFor, item, setLookingFor)}
              >
                <Text style={[styles.pillText, isSelected && styles.pillTextSelected]}>
                  {item}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={styles.label}>Vibe Zones</Text>
        <View style={styles.pillsWrap}>
          {VIBE_ZONE_OPTIONS.map((vibe) => {
            const isSelected = vibeZones.includes(vibe);
            return (
              <TouchableOpacity
                key={vibe}
                style={[styles.pill, isSelected && styles.pillSelected]}
                onPress={() => toggleTag(vibeZones, vibe, setVibeZones)}
              >
                <Text style={[styles.pillText, isSelected && styles.pillTextSelected]}>
                  {vibe}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {/* Prompts Section */}
      {prompts.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Your Prompts</Text>
          {prompts.map((p) => (
            <View key={p.prompt_id} style={styles.promptWrap}>
              <Text style={styles.promptQuestion}>{p.prompt_text}</Text>
              <TextInput
                style={styles.promptInput}
                value={p.response}
                onChangeText={(t) => updatePromptResponse(p.prompt_id, t)}
                placeholder="Write your genuine answer..."
                placeholderTextColor={colors.muted}
                multiline
                maxLength={250}
              />
            </View>
          ))}
        </View>
      )}

      {/* Save Button */}
      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.disabledBtn]}
          onPress={handleSave}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <Text style={styles.saveBtnText}>Save Profile Changes</Text>
          )}
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingTop: Platform.OS === "ios" ? 52 : 20,
    paddingBottom: spacing.base,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.white,
  },
  backBtn: { paddingVertical: spacing.xs },
  backBtnText: { fontFamily: "Outfit_600SemiBold", color: colors.dark, fontSize: 16 },
  title: { fontFamily: "Outfit_700Bold", fontSize: 18, color: colors.dark },
  saveHeaderBtn: { paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  saveHeaderBtnText: { fontFamily: "Outfit_700Bold", color: colors.saffron, fontSize: 16 },
  disabledBtn: { opacity: 0.5 },
  section: {
    backgroundColor: colors.white,
    padding: spacing.base,
    marginTop: spacing.sm,
  },
  sectionTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    color: colors.dark,
    marginBottom: spacing.xs,
  },
  sectionHint: {
    ...typography.caption,
    color: colors.muted,
    marginBottom: spacing.base,
  },
  photosGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  photoBox: {
    width: "30%",
    aspectRatio: 0.8,
    borderRadius: radii.md,
    overflow: "hidden",
    position: "relative",
    backgroundColor: colors.light,
  },
  photoImg: { width: "100%", height: "100%", resizeMode: "cover" },
  mainBadge: {
    position: "absolute",
    top: 4,
    left: 4,
    backgroundColor: colors.saffron,
    borderRadius: radii.xs,
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
  mainBadgeText: { fontFamily: "Outfit_700Bold", fontSize: 9, color: colors.white },
  deleteOverlay: {
    position: "absolute",
    top: 4,
    right: 4,
    backgroundColor: "rgba(0,0,0,0.6)",
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  deleteOverlayText: { color: colors.white, fontSize: 11, fontWeight: "bold" },
  addPhotoBox: {
    width: "30%",
    aspectRatio: 0.8,
    borderRadius: radii.md,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.light,
  },
  addPhotoIcon: { fontSize: 24, color: colors.muted, marginBottom: 2 },
  addPhotoText: { fontFamily: "Inter_400Regular", fontSize: 11, color: colors.muted },
  label: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 13,
    color: colors.mid,
    marginTop: spacing.base,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: colors.light,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    fontFamily: "Inter_400Regular",
    fontSize: 15,
    color: colors.dark,
  },
  pillsWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  pill: {
    backgroundColor: colors.light,
    borderRadius: radii.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  pillSelected: {
    backgroundColor: colors.saffronLight,
    borderColor: colors.saffron,
  },
  pillText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    color: colors.mid,
  },
  pillTextSelected: {
    fontFamily: "Outfit_600SemiBold",
    color: colors.saffron,
  },
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.base,
    paddingVertical: spacing.xs,
  },
  switchTextWrap: { flex: 1, paddingRight: spacing.sm },
  switchLabel: { fontFamily: "Outfit_600SemiBold", fontSize: 14, color: colors.dark },
  switchHint: { ...typography.caption, color: colors.muted },
  promptWrap: {
    backgroundColor: colors.light,
    borderRadius: radii.md,
    padding: spacing.base,
    marginTop: spacing.sm,
  },
  promptQuestion: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 14,
    color: colors.dark,
    marginBottom: spacing.xs,
  },
  promptInput: {
    fontFamily: "Inter_400Regular",
    fontSize: 14,
    color: colors.dark,
    minHeight: 60,
    textAlignVertical: "top",
  },
  footer: {
    padding: spacing.base,
    marginTop: spacing.base,
  },
  voiceBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.sm,
  },
  voiceBtnRecording: {
    backgroundColor: colors.red,
  },
  voiceBtnText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 14,
    color: colors.white,
  },
  saveBtn: {
    backgroundColor: colors.saffron,
    borderRadius: radii.full,
    height: 52,
    alignItems: "center",
    justifyContent: "center",
  },
  saveBtnText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    color: colors.white,
  },
});
