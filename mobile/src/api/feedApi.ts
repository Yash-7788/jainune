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

// ── DEV Mock Candidates ───────────────────────────────────────────────────────

const MOCK_FEED_CANDIDATES: FeedCandidate[] = [
  {
    id: "candidate_1",
    first_name: "Ananya",
    age: 25,
    city: "Mumbai",
    state: "Maharashtra",
    distance_display: "5 km away",
    dietary_strictness: "jain_strict",
    eats_root_vegetables: false,
    eats_onion_garlic: false,
    community_sect: "shvetambara",
    education: "Chartered Accountant",
    profession: "Financial Analyst",
    open_to_relocation: true,
    photos: [
      { id: "f_p1", url: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80", order: 1 },
      { id: "f_p2", url: "https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=600&q=80", order: 2 },
    ],
    prompts: [
      { id: "pr_1", question: "My ideal Sunday looks like...", answer: "Temple visit with family, quiet reading, and making Jain sweets!" },
      { id: "pr_2", question: "A non-negotiable for me...", answer: "Pure Jain diet and mutual respect for family values." },
    ],
    voice_snapshot: null,
    compatibility: {
      values_alignment_percentage: 94,
      shared_traditions: ["Pure Jain Diet", "Navkar Chanting", "Paryushan Fasting"],
    },
    is_verified: true,
  },
  {
    id: "candidate_2",
    first_name: "Rohan",
    age: 27,
    city: "Ahmedabad",
    state: "Gujarat",
    distance_display: "12 km away",
    dietary_strictness: "jain_pure",
    eats_root_vegetables: false,
    eats_onion_garlic: false,
    community_sect: "digambara",
    education: "MS in Computer Science",
    profession: "Product Manager",
    open_to_relocation: false,
    photos: [
      { id: "f_p3", url: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=600&q=80", order: 1 },
      { id: "f_p4", url: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=600&q=80", order: 2 },
    ],
    prompts: [
      { id: "pr_3", question: "What I'm looking for...", answer: "Someone who values traditions while embracing modern life." },
    ],
    voice_snapshot: null,
    compatibility: {
      values_alignment_percentage: 88,
      shared_traditions: ["Pure Jain Diet", "Family Orientation"],
    },
    is_verified: true,
  },
  {
    id: "candidate_3",
    first_name: "Priya",
    age: 26,
    city: "Bangalore",
    state: "Karnataka",
    distance_display: "18 km away",
    dietary_strictness: "jain_strict",
    eats_root_vegetables: false,
    eats_onion_garlic: false,
    community_sect: "shvetambara",
    education: "MBA Marketing",
    profession: "Brand Strategist",
    open_to_relocation: true,
    photos: [
      { id: "f_p5", url: "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=600&q=80", order: 1 },
    ],
    prompts: [
      { id: "pr_4", question: "I get excited about...", answer: "Exploring new cities, classical music, and Jain philosophy podcasts." },
    ],
    voice_snapshot: null,
    compatibility: {
      values_alignment_percentage: 91,
      shared_traditions: ["Navkar Chanting", "Travel & Culture"],
    },
    is_verified: true,
  },
];

/** GET /v1/feed */
export async function getFeed(limit = 15): Promise<FeedResponse> {
  try {
    const res = await apiGet<FeedResponse>("/feed", { limit });
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      console.log("[DEV] getFeed failed, returning mock candidates");
      return {
        candidates: MOCK_FEED_CANDIDATES,
        batch_id: "dev_batch_1",
        exhausted: false,
      };
    }
    throw err;
  }
  if (__DEV__) {
    return {
      candidates: MOCK_FEED_CANDIDATES,
      batch_id: "dev_batch_1",
      exhausted: false,
    };
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch feed" } };
}

export const getFeedCandidates = getFeed;

/** GET /v1/feed/daily-compatible */
export async function getDailyCompatible(): Promise<DailyCompatibleResponse> {
  try {
    const res = await apiGet<DailyCompatibleResponse>("/feed/daily-compatible");
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      return {
        candidate: MOCK_FEED_CANDIDATES[0],
        pairing_algorithm: "Ahimsa Value Alignment v2",
        locked_until: new Date(Date.now() + 86400000).toISOString(),
      };
    }
    throw err;
  }
  if (__DEV__) {
    return {
      candidate: MOCK_FEED_CANDIDATES[0],
      pairing_algorithm: "Ahimsa Value Alignment v2",
      locked_until: new Date(Date.now() + 86400000).toISOString(),
    };
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch daily compatible" } };
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
  try {
    const res = await apiPost<any>("/interactions/action", {
      target_id: targetUserId,
      target_user_id: targetUserId,
      action: backendAction,
      target_element_type: targetElementType,
      target_element_id: targetElementId,
      comment: comment ?? null,
      voice_note_id: null,
    });
    if (res.success && res.data) {
      return {
        action,
        is_match: Boolean(res.data?.is_match || res.data?.match_created),
        chat_id: res.data?.chat_id ?? null,
        match_timestamp: res.data?.match_timestamp ?? (res.data?.match_created ? new Date().toISOString() : null),
        momentum_window_hours: res.data?.momentum_window_hours ?? 48,
      };
    }
  } catch (err) {
    if (__DEV__) {
      return {
        action,
        is_match: action === "like" || action === "superlike",
        chat_id: action === "like" || action === "superlike" ? "mock_match_1" : null,
        match_timestamp: new Date().toISOString(),
        momentum_window_hours: 48,
      };
    }
    throw err;
  }
  if (__DEV__) {
    return {
      action,
      is_match: false,
      chat_id: null,
      match_timestamp: null,
      momentum_window_hours: 48,
    };
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to post interaction" } };
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
  try {
    const res = await apiGet<{ profiles: FeedCandidate[] }>("/interactions/matches");
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      return { profiles: [MOCK_FEED_CANDIDATES[0]] };
    }
    throw err;
  }
  if (__DEV__) return { profiles: [MOCK_FEED_CANDIDATES[0]] };
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch likes" } };
}

export async function getLikedMe(cursor?: string): Promise<{ likes: FeedCandidate[]; next_cursor?: string | null }> {
  const url = cursor ? `/interactions/liked-me?cursor=${encodeURIComponent(cursor)}` : "/interactions/liked-me";
  try {
    const res = await apiGet<{ likes: FeedCandidate[]; next_cursor?: string | null }>(url);
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      return { likes: [MOCK_FEED_CANDIDATES[1]], next_cursor: null };
    }
    throw err;
  }
  if (__DEV__) return { likes: [MOCK_FEED_CANDIDATES[1]], next_cursor: null };
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch liked me" } };
}
