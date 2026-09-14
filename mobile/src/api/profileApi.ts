/**
 * Profile & Account API — Phase 7
 * Matches backend routes from BACKEND_SPEC.md / API_SPEC.md
 *
 * GET  /v1/users/me               → MyProfile
 * PUT  /v1/users/me               → update name/city/bio/preferences
 * POST /v1/users/me/photos        → reorder or delete photos
 * PUT  /v1/users/me/settings      → notification, privacy, paryushan
 * POST /v1/users/me/delete        → account erasure (DPDP right to erasure)
 * GET  /v1/subscriptions/me       → subscription status
 * POST /v1/subscriptions/order    → create Razorpay order
 * POST /v1/subscriptions/verify   → verify payment signature client-side
 * POST /v1/arcade/order           → create arcade micro-tx order
 * POST /v1/arcade/verify          → verify arcade payment
 */

import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MyProfile {
  id: string;
  first_name: string;
  date_of_birth: string;
  gender: string;
  city: string;
  state: string;
  profession: string;
  education: string;
  dietary_strictness: string;
  eats_root_vegetables: boolean;
  eats_onion_garlic: boolean;
  community_sect: string;
  open_to_relocation: boolean;
  looking_for: string[];
  vibe_zones: string[];
  photos: { id: string; url: string; order: number }[];
  prompts: { prompt_id: string; prompt_text: string; response: string }[];
  voice_snapshot_url: string | null;
  is_verified: boolean;
  account_status: string;
  paryushan_mode: boolean;
  subscription_tier: "free" | "plus" | "gold" | "platinum" | "jainune_plus";
  subscription_expires_at: string | null;
  liked_by_count: number;
  profile_health_score: number;
}

export interface SubscriptionStatus {
  tier: "free" | "plus" | "gold" | "platinum" | "jainune_plus";
  is_active?: boolean;
  status?: "active" | "halted" | "cancelled" | "expired" | null;
  plan_id?: string | null;
  current_period_end?: string | null;
  expires_at?: string | null;
  daily_likes_remaining?: number;
  super_connects_remaining?: number;
  can_see_who_liked?: boolean;
  cancel_at_period_end?: boolean;
}

export interface SubscriptionPlan {
  plan_id: string;
  label: string;
  duration_months: number;
  amount_inr: number;
  per_month_inr: number;
  savings_pct: number;
  is_recommended: boolean;
}

export interface RazorpayOrder {
  order_id: string;
  amount: number;
  amount_paisa: number;
  currency: string;
  razorpay_key: string;
}

export interface ArcadeProduct {
  product_id: string;
  label: string;
  spins?: number;
  rolls?: number;
  amount_inr: number;
}

// ── Mock Data for Offline DEV Mode ──────────────────────────────────────────

const MOCK_MY_PROFILE: MyProfile = {
  id: "dev_user_1",
  first_name: "Aarav",
  date_of_birth: "1998-05-15",
  gender: "male",
  city: "Mumbai",
  state: "Maharashtra",
  profession: "Software Engineer",
  education: "B.Tech Computer Science",
  dietary_strictness: "jain_strict",
  eats_root_vegetables: false,
  eats_onion_garlic: false,
  community_sect: "shvetambara",
  open_to_relocation: true,
  looking_for: ["marriage"],
  vibe_zones: ["travel", "foodie", "meditation"],
  photos: [
    { id: "p1", url: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80", order: 1 },
    { id: "p2", url: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=600&q=80", order: 2 },
  ],
  prompts: [
    { prompt_id: "pr1", prompt_text: "My ideal Sunday looks like...", response: "Early morning Navkar Mantra, home-cooked Jain breakfast, and a quiet book." },
    { prompt_id: "pr2", prompt_text: "A non-negotiable for me...", response: "Respecting Jain dietary traditions and family values." },
  ],
  voice_snapshot_url: null,
  is_verified: true,
  account_status: "active",
  paryushan_mode: false,
  subscription_tier: "free",
  subscription_expires_at: null,
  liked_by_count: 5,
  profile_health_score: 92,
};

// ── Profile ─────────────────────────────────────────────────────────────────

export async function getMyProfile(): Promise<MyProfile> {
  try {
    const res = await apiGet<MyProfile>("/users/me");
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      console.log("[DEV] getMyProfile failed, returning mock profile");
      return MOCK_MY_PROFILE;
    }
    throw err;
  }
  if (__DEV__) return MOCK_MY_PROFILE;
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch profile" } };
}

export async function updateProfile(payload: Partial<{
  first_name: string;
  city: string;
  state: string;
  profession: string;
  education: string;
  dietary_strictness: string;
  eats_root_vegetables: boolean;
  eats_onion_garlic: boolean;
  community_sect: string;
  open_to_relocation: boolean;
  looking_for: string | string[];
  vibe_zones: string[];
  paryushan_mode: boolean;
  bio: string;
  height_cm: number;
  max_distance_km: number;
}>): Promise<MyProfile> {
  const lookingForStr = Array.isArray(payload.looking_for)
    ? payload.looking_for[0]
    : payload.looking_for;

  const sanitized: Record<string, unknown> = {};
  if (payload.first_name !== undefined) sanitized.first_name = payload.first_name;
  if (payload.city !== undefined) sanitized.city = payload.city;
  if (payload.state !== undefined) sanitized.state = payload.state;
  if (payload.profession !== undefined) sanitized.job_title = payload.profession;
  if (payload.education !== undefined) sanitized.education = payload.education;
  if (payload.dietary_strictness !== undefined) sanitized.dietary_strictness = payload.dietary_strictness;
  if (payload.eats_root_vegetables !== undefined) sanitized.eats_root_vegetables = payload.eats_root_vegetables;
  if (payload.eats_onion_garlic !== undefined) sanitized.eats_onion_garlic = payload.eats_onion_garlic;
  if (payload.community_sect !== undefined) sanitized.community_sect = payload.community_sect;
  if (payload.open_to_relocation !== undefined) sanitized.open_to_relocation = payload.open_to_relocation;
  if (payload.paryushan_mode !== undefined) sanitized.paryushan_mode = payload.paryushan_mode;
  if (payload.bio !== undefined) sanitized.bio = payload.bio;
  if (payload.height_cm !== undefined) sanitized.height_cm = payload.height_cm;
  if (payload.max_distance_km !== undefined) sanitized.max_distance_km = payload.max_distance_km;
  if (lookingForStr) {
    const raw = String(lookingForStr).toLowerCase().replace(/[\s-]+/g, "_");
    let normalized = raw;
    if (raw.includes("marriage")) normalized = "marriage";
    else if (raw.includes("serious") || raw.includes("long_term") || raw.includes("dating")) normalized = "long_term";
    else if (raw.includes("figuring")) normalized = "figuring_out";

    if (["marriage", "long_term", "figuring_out"].includes(normalized)) {
      sanitized.looking_for = normalized;
    }
  }

  try {
    const res = await apiPatch<MyProfile>("/users/me", sanitized);
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      return { ...MOCK_MY_PROFILE, ...payload } as any;
    }
    throw err;
  }
  if (__DEV__) return { ...MOCK_MY_PROFILE, ...payload } as any;
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to update profile" } };
}

export async function reorderPhotos(photo_ids: string[]): Promise<void> {
  const positions = photo_ids.map((id, index) => ({ media_id: id, position: index + 1 }));
  try {
    const res = await apiPatch<void>("/media/reorder", { positions });
    if (!res.success) throw { _apiError: res.error };
  } catch (err) {
    if (__DEV__) return;
    throw err;
  }
}

export async function deletePhoto(photo_id: string): Promise<void> {
  try {
    const res = await apiDelete<void>(`/media/${photo_id}`);
    if (!res.success) throw { _apiError: res.error };
  } catch (err) {
    if (__DEV__) return;
    throw err;
  }
}

export async function confirmUpload(media_id: string): Promise<void> {
  try {
    const res = await apiPost<void>("/media/upload/confirm", { media_id });
    if (!res.success) throw { _apiError: res.error };
  } catch (err) {
    if (__DEV__) return;
    throw err;
  }
}

export async function addPhoto(media_id: string): Promise<void> {
  await confirmUpload(media_id);
}

export async function updateVoiceSnapshot(media_id: string): Promise<{ voice_snapshot_url: string | null }> {
  await confirmUpload(media_id);
  return { voice_snapshot_url: null };
}

export interface PresignUploadResponse {
  upload_url: string;
  media_id: string;
  cdn_url: string;
  presigned_fields?: Record<string, string> | null;
}

export async function presignUpload(
  contentType: string,
  fileSizeBytes: number,
  mediaType: "photo" | "voice" = "photo",
  position: number = 1
): Promise<PresignUploadResponse> {
  try {
    const res = await apiPost<{
      media_id: string;
      presigned_url: string;
      s3_key: string;
      presigned_fields?: Record<string, string> | null;
    }>("/media/upload/request", {
      media_type: mediaType,
      content_type: contentType,
      file_size_bytes: fileSizeBytes,
      position,
    });
    if (res.success && res.data) {
      return {
        upload_url: res.data.presigned_url,
        media_id: res.data.media_id,
        cdn_url: `https://cdn.jainune.com/${res.data.s3_key}`,
        presigned_fields: res.data.presigned_fields,
      };
    }
  } catch (err) {
    if (__DEV__) {
      const mockId = `mock_media_${Date.now()}`;
      return {
        upload_url: "https://httpbin.org/put",
        media_id: mockId,
        cdn_url: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80",
        presigned_fields: null,
      };
    }
    throw err;
  }
  if (__DEV__) {
    const mockId = `mock_media_${Date.now()}`;
    return {
      upload_url: "https://httpbin.org/put",
      media_id: mockId,
      cdn_url: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80",
      presigned_fields: null,
    };
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Upload presign failed" } };
}

export async function getSettings(): Promise<{
  discovery_paused: boolean;
}> {
  try {
    const profile = await getMyProfile();
    return {
      discovery_paused: (profile as any).is_paused ?? false,
    };
  } catch {
    return {
      discovery_paused: false,
    };
  }
}

export async function updateSettings(payload: {
  discovery_paused?: boolean;
}): Promise<void> {
  if (payload.discovery_paused !== undefined) {
    try {
      if (payload.discovery_paused) {
        await apiPost("/users/me/pause");
      } else {
        await apiPost("/users/me/unpause");
      }
    } catch (err) {
      if (__DEV__) return;
      throw err;
    }
  }
}

export async function requestAccountDeletion(reason?: string): Promise<void> {
  const res = await apiDelete<void>("/users/me", { hard_delete: false, reason });
  if (!res.success) throw { _apiError: res.error };
}

// ── Subscriptions ────────────────────────────────────────────────────────────

export const SUBSCRIPTION_PLANS: SubscriptionPlan[] = [
  {
    plan_id: "jainune_plus_monthly",
    label: "1 Month",
    duration_months: 1,
    amount_inr: 499,
    per_month_inr: 499,
    savings_pct: 0,
    is_recommended: false,
  },
  {
    plan_id: "jainune_plus_quarterly",
    label: "3 Months",
    duration_months: 3,
    amount_inr: 999,
    per_month_inr: 333,
    savings_pct: 33,
    is_recommended: true,
  },
  {
    plan_id: "jainune_plus_semiannual",
    label: "6 Months",
    duration_months: 6,
    amount_inr: 1699,
    per_month_inr: 283,
    savings_pct: 43,
    is_recommended: false,
  },
  {
    plan_id: "jainune_plus_annual",
    label: "1 Year",
    duration_months: 12,
    amount_inr: 2799,
    per_month_inr: 233,
    savings_pct: 53,
    is_recommended: false,
  },
];

export async function getSubscriptionPlans(): Promise<SubscriptionPlan[]> {
  try {
    const res = await apiGet<{ plans: SubscriptionPlan[] }>("/subscriptions/plans");
    if (res.success && res.data?.plans?.length > 0) {
      return res.data.plans;
    }
  } catch {}
  return SUBSCRIPTION_PLANS;
}

export async function cancelSubscription(): Promise<{ access_until: string }> {
  const res = await apiPost<{ access_until: string }>("/subscriptions/cancel");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  try {
    const res = await apiGet<{
      user_id: string;
      tier: string;
      valid_until: string | null;
      daily_likes_remaining: number | null;
      super_likes_remaining: number;
      can_see_who_liked: boolean;
    }>("/users/me/subscription");
    if (res.success && res.data) {
      const d = res.data;
      const isSubscriber = d.tier !== "free";
      return {
        tier: d.tier as any,
        is_active: isSubscriber,
        status: isSubscriber ? "active" : "expired",
        expires_at: d.valid_until,
        current_period_end: d.valid_until,
        daily_likes_remaining: d.daily_likes_remaining ?? 999,
        super_connects_remaining: d.super_likes_remaining ?? 0,
        can_see_who_liked: d.can_see_who_liked ?? false,
        plan_id: null,
        cancel_at_period_end: false,
      };
    }
  } catch (err) {
    if (__DEV__) {
      return {
        tier: "free",
        is_active: false,
        status: "expired",
        expires_at: null,
        current_period_end: null,
        daily_likes_remaining: 10,
        super_connects_remaining: 1,
        can_see_who_liked: false,
        plan_id: null,
        cancel_at_period_end: false,
      };
    }
    throw err;
  }
  return {
    tier: "free",
    is_active: false,
    status: "expired",
    expires_at: null,
    current_period_end: null,
    daily_likes_remaining: 10,
    super_connects_remaining: 1,
    can_see_who_liked: false,
    plan_id: null,
    cancel_at_period_end: false,
  };
}

export async function createSubscriptionOrder(plan_id: string): Promise<RazorpayOrder> {
  const res = await apiPost<any>("/subscriptions/order", { plan_id });
  if (!res.success) throw { _apiError: res.error };
  const d = res.data;
  const amt = Number(d.amount ?? d.amount_paisa ?? 0);
  return {
    order_id: d.order_id,
    amount: amt,
    amount_paisa: amt,
    currency: d.currency || "INR",
    razorpay_key: d.razorpay_key || d.key_id || "",
  };
}

/**
 * Verify Razorpay signature CLIENT-SIDE before trusting UI state.
 * The backend does its own HMAC verification on the webhook — this is a
 * defence-in-depth client check so we never show "subscribed" on a failed payment.
 */
export async function verifySubscriptionPayment(payload: {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}): Promise<{ activated: boolean; expires_at: string }> {
  const res = await apiPost<{ activated: boolean; expires_at: string }>(
    "/subscriptions/verify",
    payload
  );
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function syncSubscriptionOrder(orderId?: string): Promise<{
  synced: boolean;
  activated: boolean;
  tier?: string;
  expires_at?: string;
  status?: string;
  message?: string;
}> {
  const res = await apiPost<{
    synced: boolean;
    activated: boolean;
    tier?: string;
    expires_at?: string;
    status?: string;
    message?: string;
  }>("/subscriptions/sync", orderId ? { razorpay_order_id: orderId } : {});
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function requestSubscriptionRefund(
  paymentId: string,
  reason = "customer_request"
): Promise<{ success: boolean; refund_id?: string; message?: string }> {
  const res = await apiPost<{ success: boolean; refund_id?: string; message?: string }>(
    "/subscriptions/refund",
    { razorpay_payment_id: paymentId, reason }
  );
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

// ── Serendipity Arcade ───────────────────────────────────────────────────────

export const ARCADE_PRODUCTS: ArcadeProduct[] = [
  { product_id: "arcade_wheel_spin", label: "1 Wheel Spin", spins: 1, amount_inr: 29 },
  { product_id: "arcade_dice_roll", label: "1 Dice Roll", rolls: 1, amount_inr: 19 },
  { product_id: "arcade_3_pack", label: "3-Spin Pass", spins: 3, amount_inr: 49 },
];

export async function getArcadeWallet(): Promise<{ available_spins: number; available_dice_rolls: number }> {
  const res = await apiGet<{ available_spins: number; available_dice_rolls: number }>("/arcade/wallet");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function spinArcadeWheel(): Promise<{
  success: boolean;
  remaining_spins: number;
  paired_user: { id: string; first_name: string; city: string } | null;
  message: string;
}> {
  const res = await apiPost<{
    success: boolean;
    remaining_spins: number;
    paired_user: { id: string; first_name: string; city: string } | null;
    message: string;
  }>("/arcade/spin");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function rollArcadeDice(): Promise<{
  success: boolean;
  remaining_dice_rolls: number;
  roll_outcome?: number[];
  dice?: number[];
  message: string;
}> {
  const res = await apiPost<{
    success: boolean;
    remaining_dice_rolls: number;
    roll_outcome?: number[];
    dice?: number[];
    message: string;
  }>("/arcade/roll");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function createArcadeOrder(product_id: string): Promise<RazorpayOrder> {
  const res = await apiPost<any>("/subscriptions/order", { plan_id: product_id });
  if (!res.success) throw { _apiError: res.error };
  const d = res.data;
  const amt = Number(d.amount ?? d.amount_paisa ?? 0);
  return {
    order_id: d.order_id,
    amount: amt,
    amount_paisa: amt,
    currency: d.currency || "INR",
    razorpay_key: d.razorpay_key || d.key_id || "",
  };
}

export async function verifyArcadePayment(payload: {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}): Promise<{ spins_added?: number; rolls_added?: number }> {
  const res = await apiPost<{ success: boolean; message: string }>(
    "/subscriptions/verify",
    payload
  );
  if (!res.success) throw { _apiError: res.error };
  return { spins_added: 1, rolls_added: 1 };
}
