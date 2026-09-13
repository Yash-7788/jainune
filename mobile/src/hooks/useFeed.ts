/**
 * useFeed — Reusable feed candidate fetcher hook
 */

import { useState, useCallback } from "react";
import { getFeed, FeedCandidate } from "../api/feedApi";

export function useFeed() {
  const [candidates, setCandidates] = useState<FeedCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getFeed();
      setCandidates(data.candidates || []);
    } catch (err: any) {
      setError(err?.message || "Failed to load feed");
    } finally {
      setLoading(false);
    }
  }, []);

  return { candidates, setCandidates, loading, error, loadFeed };
}
