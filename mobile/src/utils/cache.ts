/**
 * OPTIMIZE.md §2 — 4-Tier Client Cache-Aside Utility
 *
 * Typed AsyncStorage wrapper for Layers 1-3:
 *   L1  @chat_msgs_${matchId}   — per-thread message arrays (capped at 500)
 *   L2  @feed_cards_v1          — discover feed deck
 *   L3  @user_profile           — own profile stale-while-revalidate (30 min TTL)
 *
 * Security invariants (OPTIMIZE.md §7):
 *   - Cache is a read-only display projection of Supabase ground truth.
 *   - No state-changing operation is executed against the cache alone.
 *   - Financial balances / block matrices are never written here.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

// ── Cache key constants ────────────────────────────────────────────────────────

export const CACHE_KEYS = {
  FEED_DECK: "@feed_cards_v1",
  USER_PROFILE: "@user_profile",
  chatThread: (matchId: string) => `@chat_msgs_${matchId}`,
} as const;

// ── 30-minute SWR TTL ─────────────────────────────────────────────────────────

export const PROFILE_TTL_MS = 30 * 60 * 1000; // 30 minutes

// ── Generic typed read/write ───────────────────────────────────────────────────

/** Returns parsed value or null (never throws). */
export async function cacheGet<T>(key: string): Promise<T | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** Serialises value to JSON and persists. Silently swallows storage errors. */
export async function cacheSet<T>(key: string, value: T): Promise<void> {
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
