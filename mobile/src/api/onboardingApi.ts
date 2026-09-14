/**
 * Onboarding API — 22 idempotent PATCH steps
 * Exact field names from backend/app/models/schemas/user.py — byte-for-byte match.
 * Media upload via presigned URLs from /v1/media/presign-upload.
 * Dev Sandbox Fallback: in __DEV__ mode, if remote backend is unreachable, gracefully returns step status.
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
  presigned_fields?: Record<string, string> | null;
}

function devStepFallback(step: number): OnboardingStatus {
  return {
    current_step: Math.min(step + 1, 22),
    total_steps: 22,
    completed: step >= 22,
    next_step_hint: null,
  };
}

// GET /v1/onboarding/status
export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  try {
    const res = await apiGet<OnboardingStatus>("/onboarding/status");
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return { current_step: 2, total_steps: 22, completed: false, next_step_hint: null };
    throw err;
  }
}

// Step 2: PATCH /v1/onboarding/step/2
export async function submitStep2(firstName: string, dateOfBirth: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/2", {
      first_name: firstName.trim(),
      date_of_birth: dateOfBirth, // ISO date: "1998-05-14"
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(2);
    throw err;
  }
}

// Step 3: gender — "man" | "woman" | "nonbinary"
export async function submitStep3(gender: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/3", { gender });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(3);
    throw err;
  }
}

// Step 4: show_me — "men" | "women" | "everyone"
export async function submitStep4(showMe: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/4", { show_me: showMe });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(4);
    throw err;
  }
}

// Step 5: looking_for — "marriage" | "long_term" | "figuring_out"
export async function submitStep5(lookingFor: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/5", { looking_for: lookingFor });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(5);
    throw err;
  }
}

// Step 6: dietary_strictness — "pure_jain" | "vaishnav" | "ovo_veg" | "vegan"
export async function submitStep6(dietaryStrictness: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/6", {
      dietary_strictness: dietaryStrictness,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(6);
    throw err;
  }
}

// Step 7: dietary details (only for pure_jain / vaishnav)
export async function submitStep7(eatsRootVeg: boolean, eatsOnionGarlic: boolean): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/7", {
      eats_root_vegetables: eatsRootVeg,
      eats_onion_garlic: eatsOnionGarlic,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(7);
    throw err;
  }
}

// Step 8: community_sect
export async function submitStep8(communitySect: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/8", {
      community_sect: communitySect,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(8);
    throw err;
  }
}

// Step 9: paryushan_mode
export async function submitStep9(paryushanMode: boolean): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/9", {
      paryushan_mode: paryushanMode,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(9);
    throw err;
  }
}

// Step 10: city + state
export async function submitStep10(city: string, state: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/10", {
      city: city.trim(),
      state: state.trim(),
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(10);
    throw err;
  }
}

// Step 11: GPS location
export async function submitStep11(
  latitude: number,
  longitude: number,
  isMocked: boolean,
  accuracyMeters: number | null
): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/11", {
      latitude,
      longitude,
      is_mocked: isMocked,
      accuracy_meters: accuracyMeters,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(11);
    throw err;
  }
}

// Step 12: max_distance_km (5–200)
export async function submitStep12(maxDistanceKm: number): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/12", {
      max_distance_km: maxDistanceKm,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(12);
    throw err;
  }
}

// Step 13: open_to_relocation
export async function submitStep13(openToRelocation: boolean): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/13", {
      open_to_relocation: openToRelocation,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(13);
    throw err;
  }
}

// Step 14: height_cm (optional, 120–250)
export async function submitStep14(heightCm: number | null): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/14", {
      height_cm: heightCm,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(14);
    throw err;
  }
}

// Step 15: job_title + company
export async function submitStep15(jobTitle: string | null, company: string | null): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/15", {
      job_title: jobTitle?.trim() ?? null,
      company: company?.trim() ?? null,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(15);
    throw err;
  }
}

// Step 16: education
export async function submitStep16(education: string | null): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/16", {
      education: education?.trim() ?? null,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(16);
    throw err;
  }
}

// Step 17: bio (max 500 chars)
export async function submitStep17(bio: string | null): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/17", {
      bio: bio?.trim() ?? null,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(17);
    throw err;
  }
}

// Step 18: prompts (1–3 items)
export async function submitStep18(prompts: PromptItem[]): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/18", { prompts });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(18);
    throw err;
  }
}

// Step 19: confirm photo media_ids
export async function submitStep19(mediaIds: string[]): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/19", {
      media_ids: mediaIds,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(19);
    throw err;
  }
}

// Step 20: voice snapshot media_id
export async function submitStep20(mediaId: string): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/20", {
      media_id: mediaId,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(20);
    throw err;
  }
}

// Step 21: DPDP consent
export async function submitStep21(
  coreMatchmaking: boolean,
  familyContactGotra: boolean,
  relocationIntercity: boolean,
  marketing: boolean = false
): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/21", {
      core_matchmaking: coreMatchmaking,
      family_contact_gotra: familyContactGotra,
      relocation_intercity: relocationIntercity,
      marketing: marketing,
    });
    if (!res.success) throw { _apiError: res.error };
    return res.data;
  } catch (err) {
    if (__DEV__) return devStepFallback(21);
    throw err;
  }
}

// Step 22: complete onboarding
export async function submitStep22(): Promise<OnboardingStatus> {
  try {
    const res = await apiPatch<OnboardingStatus>("/onboarding/step/22", { confirmed: true });
    if (!res.success) {
      if (res.error?.code === "CONFLICT" || res.error?.message?.toLowerCase().includes("already completed")) {
        return { current_step: 22, total_steps: 22, completed: true, next_step_hint: null };
      }
      throw { _apiError: res.error };
    }
    return res.data;
  } catch (err) {
    if (__DEV__) return { current_step: 22, total_steps: 22, completed: true, next_step_hint: null };
    throw err;
  }
}

// GET /v1/media/presign-upload?type=photo|voice
export async function getPresignedUploadUrl(type: "photo" | "voice"): Promise<PresignData> {
  try {
    const res = await apiPost<{
      media_id: string;
      presigned_url: string;
      s3_key: string;
      presigned_fields?: Record<string, string> | null;
    }>("/media/upload/request", {
      media_type: type,
      content_type: type === "photo" ? "image/jpeg" : "audio/m4a",
      file_size_bytes: type === "photo" ? 2 * 1024 * 1024 : 1024 * 1024,
      position: 1,
    });
    if (!res.success) throw { _apiError: res.error };
    return {
      media_id: res.data.media_id,
      upload_url: res.data.presigned_url,
      cdn_url: `https://cdn.jainune.com/${res.data.s3_key}`,
      presigned_fields: res.data.presigned_fields,
    };
  } catch (err) {
    if (__DEV__) {
      const devMediaId = `dev_media_${Date.now()}`;
      return {
        media_id: devMediaId,
        upload_url: "https://httpbin.org/post",
        cdn_url: "https://picsum.photos/400/500",
        presigned_fields: null,
      };
    }
    throw err;
  }
}

// Upload to S3 directly via presigned URL (clean binary PUT or multipart POST)
export async function uploadToS3(
  uploadUrl: string,
  fileUri: string,
  mimeType: string,
  presignedFields?: Record<string, string> | null
): Promise<void> {
  try {
    await uploadToPresignedUrl(uploadUrl, fileUri, mimeType, presignedFields);
  } catch (err) {
    if (!__DEV__) throw err;
  }
}

// POST /v1/media/upload/confirm
export async function confirmUpload(mediaId: string): Promise<void> {
  try {
    const res = await apiPost<void>("/media/upload/confirm", { media_id: mediaId });
    if (!res.success) throw { _apiError: res.error };
  } catch (err) {
    if (!__DEV__) throw err;
  }
}
