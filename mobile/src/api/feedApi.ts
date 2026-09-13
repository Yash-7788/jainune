/**
 * Feed API — exact contract from backend/app/routers/feed.py + interactions.py
 * GET /v1/feed, POST /v1/interactions/action, POST /v1/telemetry/interaction-event
 */

import { apiGet, apiPost } from "./client";

export interface PhotoData {
  id: string;
  url: string;
  order: number;
}

export interface PromptData {
  id: string;
  question: string;
  answer: string;
}

export interface VoiceSnapshot {
  id: string;
  audio_url: string;
  duration_seconds: number;
}

export interface FeedCandidate {
  id: string;
  first_name: string;
  age: number;
  city: string;
  state: string;
  distance_display: string;
  dietary_strictness: string;
  eats_root_vegetables: boolean;
  eats_onion_garlic: boolean;
  community_sect: string;
  education: string;
  profession: string;
  open_to_relocation: boolean;
  photos: PhotoData[];
  prompts: PromptData[];
  voice_snapshot: VoiceSnapshot | null;
  compatibility: {
    values_alignment_percentage: number;
    shared_traditions: string[];
  };
  is_verified?: boolean;
}

export interface FeedResponse {
  candidates: FeedCandidate[];
  batch_id: string;
  exhausted: boolean;
}

export type InteractionAction = "like" | "pass" | "superlike";
export type TargetElementType = "photo" | "prompt" | "voice_snapshot";

export interface InteractionResult {
  action: InteractionAction;
  is_match: boolean;
  chat_id: string | null;
  match_timestamp: string | null;
  momentum_window_hours: number;
}

export interface DailyCompatibleResponse {
  candidate: FeedCandidate | null;
  pairing_algorithm: string;
  locked_until: string;
}

/** GET /v1/feed */
export async function getFeed(limit = 15): Promise<FeedResponse> {
  const res = await apiGet<FeedResponse>("/feed", { limit });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** GET /v1/feed/daily-compatible */
export async function getDailyCompatible(): Promise<DailyCompatibleResponse> {
  const res = await apiGet<DailyCompatibleResponse>("/feed/daily-compatible");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/interactions/action */
export async function postInteraction(
  targetUserId: string,
  action: InteractionAction,
  targetElementType: TargetElementType,
  targetElementId: string,
  comment?: string
): Promise<InteractionResult> {
  const backendAction = action === "superlike" ? "super_connect" : action;
  const res = await apiPost<any>("/interactions/action", {
    target_id: targetUserId,
    target_user_id: targetUserId,
    action: backendAction,
    target_element_type: targetElementType,
    target_element_id: targetElementId,
    comment: comment ?? null,
    voice_note_id: null,
  });
  if (!res.success) throw { _apiError: res.error };
  return {
    action,
    is_match: Boolean(res.data?.is_match || res.data?.match_created),
    chat_id: res.data?.chat_id ?? null,
    match_timestamp: res.data?.match_timestamp ?? (res.data?.match_created ? new Date().toISOString() : null),
    momentum_window_hours: res.data?.momentum_window_hours ?? 48,
  };
}

/** POST /v1/telemetry/interaction-event — fire-and-forget, non-blocking */
export async function sendTelemetry(payload: {
  target_user_id: string;
  action: InteractionAction;
  total_dwell_ms: number;
  photo_dwell_ms: number;
  prompt_dwell_ms: number;
  voice_played_ratio: number;
  comment_char_count: number;
}): Promise<void> {
  try {
    await apiPost("/telemetry/interaction-event", payload);
  } catch {
    // Telemetry failure is silent — never breaks UX
  }
}

// ── Convenience helpers for screens ────────────────────────────────────────────

export async function likeProfile(targetUserId: string): Promise<InteractionResult> {
  return postInteraction(targetUserId, "like", "photo", targetUserId);
}

export async function passProfile(targetUserId: string): Promise<void> {
  await postInteraction(targetUserId, "pass", "photo", targetUserId);
}

export async function getLikes(): Promise<{ profiles: FeedCandidate[] }> {
  const res = await apiGet<{ profiles: FeedCandidate[] }>("/interactions/matches");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

export async function getLikedMe(cursor?: string): Promise<{ likes: FeedCandidate[]; next_cursor?: string | null }> {
  const url = cursor ? `/interactions/liked-me?cursor=${encodeURIComponent(cursor)}` : "/interactions/liked-me";
  const res = await apiGet<{ likes: FeedCandidate[]; next_cursor?: string | null }>(url);
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}
