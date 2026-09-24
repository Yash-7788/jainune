/**
 * OPTIMIZE.md §2 — 4-Tier Client Cache-Aside Utility
 *
 * Typed AsyncStorage wrapper for Layers 1-3:
 *   L1  @chat_msgs_${matchId}   — per-thread message arrays (capped at 500)
 *   L2  @user:${userId}:feed_cards_v1 — discover feed deck
 *   L3  @user:${userId}:profile       — own profile stale-while-revalidate (30 min TTL)
 *
 * Security invariants (OPTIMIZE.md §7):
 *   - Cache is a read-only display projection of Supabase ground truth.
 *   - No state-changing operation is executed against the cache alone.
 *   - Financial balances / block matrices are never written here.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { Image as ExpoImage } from "expo-image";

// ── Cache key constants ────────────────────────────────────────────────────────

// Capture these keys before async work starts; never select a new owner at write time.
// Legacy global profile/feed entries are intentionally not read or migrated.
export const CACHE_KEYS = {
  feedDeck: (userId: string | null) => userId ? `@user:${userId}:feed_cards_v1` : null,
  userProfile: (userId: string | null) => userId ? `@user:${userId}:profile` : null,
  chatThread: (matchId: string) => `@chat_msgs_${matchId}`,
} as const;

// ── 30-minute SWR TTL ─────────────────────────────────────────────────────────

export const PROFILE_TTL_MS = 30 * 60 * 1000; // 30 minutes

// ── Generic typed read/write ───────────────────────────────────────────────────

/** Returns parsed value or null (never throws). */
export async function cacheGet<T>(key: string | null): Promise<T | null> {
  if (!key) return null;
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** Serialises value to JSON and persists. Silently swallows storage errors. */
export async function cacheSet<T>(key: string | null, value: T): Promise<void> {
  if (!key) return;
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or unavailable — degrade gracefully; network path still works
  }
}

/** Removes a cache entry (e.g. on 403 unmatch / block). */
export async function cacheRemove(key: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(key);
  } catch {
    // ignore
  }
}

// ── LRU cap helper (OPTIMIZE.md §2.1 F) ──────────────────────────────────────

/**
 * Keeps only the latest `limit` messages to prevent unbounded JSON blob growth.
 * OPTIMIZE.md mandates a strict 500-message cap per thread in AsyncStorage.
 */
export function capMessages<T extends { created_at: string }>(
  messages: T[],
  limit = 500
): T[] {
  if (messages.length <= limit) return messages;
  // Messages are stored newest-first in ChatScreen; keep the first `limit`
  return messages.slice(0, limit);
}

// ── Staleness check ────────────────────────────────────────────────────────────

/** Returns true if the cached snapshot is older than `ttlMs`. */
export function isStale(lastSyncedAt: number, ttlMs: number): boolean {
  return Date.now() - lastSyncedAt > ttlMs;
}

// ── L4 Cache Invalidation ──────────────────────────────────────────────────────

/**
 * Purges expo-image memory and disk caches.
 * Call on photo upload, replacement, or deletion to prevent stale on-device image persistence.
 */
export async function clearImageCache(): Promise<void> {
  try {
    if (ExpoImage && typeof ExpoImage.clearMemoryCache === "function") {
      await ExpoImage.clearMemoryCache();
    }
    if (ExpoImage && typeof ExpoImage.clearDiskCache === "function") {
      await ExpoImage.clearDiskCache();
    }
  } catch {}
}
