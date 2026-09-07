/**
 * useTelemetry — Telemetry event queueing and auto-flush hook
 * - Batches micro-events to POST /v1/telemetry/events
 * - Flushes periodically (every 10s) or on app background / unmount
 * - Fire-and-forget, zero impact on UI thread
 */

import { useEffect, useRef, useCallback } from "react";
import { AppState, AppStateStatus } from "react-native";
import { apiPost } from "../api/client";

export interface TelemetryEvent {
  event_type: string;
  target_user_id?: string | null;
  batch_id?: string | null;
  duration_ms?: number | null;
  payload?: Record<string, any> | null;
  client_ts?: number;
}

export function useTelemetry() {
  const queue = useRef<TelemetryEvent[]>([]);
  const timer = useRef<NodeJS.Timeout | null>(null);

  const flush = useCallback(async () => {
    if (queue.current.length === 0) return;
    const eventsToSend = queue.current.splice(0, 50);

    try {
      await apiPost("/telemetry/events", { events: eventsToSend });
    } catch {
      // Telemetry failures are silent and non-blocking
    }
  }, []);

  const trackEvent = useCallback(
    (
      eventType: string,
      targetUserId?: string | null,
      durationMs?: number | null,
      payload?: Record<string, any> | null,
      batchId?: string | null
    ) => {
      queue.current.push({
        event_type: eventType,
        target_user_id: targetUserId ?? null,
        duration_ms: durationMs ?? null,
        payload: payload ?? null,
        batch_id: batchId ?? null,
        client_ts: Date.now(),
      });

      // Eager flush if queue size exceeds 10
      if (queue.current.length >= 10) {
        flush();
      }
    },
    [flush]
  );

  useEffect(() => {
    // 10-second periodic background flush
    timer.current = setInterval(flush, 10000);

    // Flush immediately on app state change to background
    const sub = AppState.addEventListener(
      "change",
      (nextState: AppStateStatus) => {
        if (nextState === "background" || nextState === "inactive") {
          flush();
        }
      }
    );

    return () => {
      if (timer.current) clearInterval(timer.current);
      flush();
      sub.remove();
    };
  }, [flush]);

  return { trackEvent, flush };
}
