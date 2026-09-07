/**
 * Onboarding API — 22 idempotent PATCH steps
 * Exact field names from backend/app/models/schemas/user.py — byte-for-byte match.
 * Media upload via presigned URLs from /v1/media/presign-upload.
 */

import { apiGet, apiPatch, apiPost, uploadToPresignedUrl } from "./client";

export interface OnboardingStatus {
  current_step: number;
  total_steps: number;
  completed: boolean;
  next_step_hint: string | null;
}

export interface PromptItem {
  prompt_key: string;
  response_text: string;
  position: number; // 1-3
}

export interface PresignData {
  media_id: string;
  upload_url: string;
  cdn_url: string;
}

// GET /v1/onboarding/status
export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await apiGet<OnboardingStatus>("/onboarding/status");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 2: PATCH /v1/onboarding/step/2
export async function submitStep2(firstName: string, dateOfBirth: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/2", {
    first_name: firstName.trim(),
    date_of_birth: dateOfBirth, // ISO date: "1998-05-14"
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 3: gender — "man" | "woman" | "nonbinary"
export async function submitStep3(gender: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/3", { gender });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 4: show_me — "men" | "women" | "everyone"
export async function submitStep4(showMe: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/4", { show_me: showMe });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 5: looking_for — "marriage" | "long_term" | "figuring_out"
export async function submitStep5(lookingFor: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/5", { looking_for: lookingFor });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 6: dietary_strictness — "pure_jain" | "vaishnav" | "ovo_veg" | "vegan"
export async function submitStep6(dietaryStrictness: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/6", {
    dietary_strictness: dietaryStrictness,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 7: dietary details (only for pure_jain / vaishnav)
export async function submitStep7(eatsRootVeg: boolean, eatsOnionGarlic: boolean): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/7", {
    eats_root_vegetables: eatsRootVeg,
    eats_onion_garlic: eatsOnionGarlic,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 8: community_sect
export async function submitStep8(communitySect: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/8", {
    community_sect: communitySect,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 9: paryushan_mode
export async function submitStep9(paryushanMode: boolean): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/9", {
    paryushan_mode: paryushanMode,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 10: city + state
export async function submitStep10(city: string, state: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/10", {
    city: city.trim(),
    state: state.trim(),
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 11: GPS location
export async function submitStep11(
  latitude: number,
  longitude: number,
  isMocked: boolean,
  accuracyMeters: number | null
): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/11", {
    latitude,
    longitude,
    is_mocked: isMocked,
    accuracy_meters: accuracyMeters,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 12: max_distance_km (5–200)
export async function submitStep12(maxDistanceKm: number): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/12", {
    max_distance_km: maxDistanceKm,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 13: open_to_relocation
export async function submitStep13(openToRelocation: boolean): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/13", {
    open_to_relocation: openToRelocation,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 14: height_cm (optional, 120–250)
export async function submitStep14(heightCm: number | null): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/14", {
    height_cm: heightCm,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 15: job_title + company
export async function submitStep15(jobTitle: string | null, company: string | null): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/15", {
    job_title: jobTitle?.trim() ?? null,
    company: company?.trim() ?? null,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 16: education
export async function submitStep16(education: string | null): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/16", {
    education: education?.trim() ?? null,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 17: bio (max 500 chars)
export async function submitStep17(bio: string | null): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/17", {
    bio: bio?.trim() ?? null,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 18: prompts (1–3 items)
export async function submitStep18(prompts: PromptItem[]): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/18", { prompts });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 19: confirm photo media_ids
export async function submitStep19(mediaIds: string[]): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/19", {
    media_ids: mediaIds,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 20: voice snapshot media_id
export async function submitStep20(mediaId: string): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/20", {
    media_id: mediaId,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 21: DPDP consent
export async function submitStep21(
  coreMatchmaking: boolean,
  familyContactGotra: boolean,
  relocationIntercity: boolean
): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/21", {
    core_matchmaking: coreMatchmaking,
    family_contact_gotra: familyContactGotra,
    relocation_intercity: relocationIntercity,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// Step 22: complete onboarding
export async function submitStep22(): Promise<OnboardingStatus> {
  const res = await apiPatch<OnboardingStatus>("/onboarding/step/22", { confirmed: true });
  if (!res.success) {
    if (res.error?.code === "CONFLICT" || res.error?.message?.toLowerCase().includes("already completed")) {
      return { current_step: 22, total_steps: 22, completed: true, next_step_hint: null };
    }
    throw { _apiError: res.error };
  }
  return res.data;
}

// GET /v1/media/presign-upload?type=photo|voice
export async function getPresignedUploadUrl(type: "photo" | "voice"): Promise<PresignData> {
  const res = await apiPost<{
    media_id: string;
    presigned_url: string;
    s3_key: string;
  }>("/media/upload/request", {
    media_type: type,
    content_type: type === "photo" ? "image/jpeg" : "audio/m4a",
    file_size_bytes: type === "photo" ? 2 * 1024 * 1024 : 1024 * 1024,
    position: 0,
  });
  if (!res.success) throw { _apiError: res.error };
  return {
    media_id: res.data.media_id,
    upload_url: res.data.presigned_url,
    cdn_url: `https://cdn.jainune.com/${res.data.s3_key}`,
  };
}

// Upload to S3 directly via presigned URL (clean binary PUT)
export async function uploadToS3(uploadUrl: string, fileUri: string, mimeType: string): Promise<void> {
  await uploadToPresignedUrl(uploadUrl, fileUri, mimeType);
}

// POST /v1/media/upload/confirm
export async function confirmUpload(mediaId: string): Promise<void> {
  const res = await apiPost<void>("/media/upload/confirm", { media_id: mediaId });
  if (!res.success) throw { _apiError: res.error };
}
