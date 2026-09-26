/**
 * useWebSocket — Reusable WebSocket hook for real-time chat
 * - Ticket-based single-use authentication handshake (BUG-005, BUG-031)
 * - Automatic ping/pong keepalive
 * - Exponential backoff auto-reconnect
 * - Full type safety
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { AppState, AppStateStatus } from "react-native";
import { getAccessToken, apiPost } from "../api/client";
import { WS_CHAT_URL } from "../config/endpoints";

const WS_BASE_URL = WS_CHAT_URL;

export type WebSocketStatus = "connecting" | "connected" | "disconnected";

export interface UseWebSocketOptions {
  chatId: string;
  onMessage?: (message: any) => void;
  onTyping?: (senderId: string) => void;
  onReadReceipt?: (senderId: string, messageId?: string) => void;
  onPermanentFailure?: () => void;
  enabled?: boolean;
}

const MAX_RECONNECT_ATTEMPTS = 10;

export function useWebSocket({
  chatId,
  onMessage,
  onTyping,
  onReadReceipt,
  onPermanentFailure,
  enabled = true,
}: UseWebSocketOptions) {
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const ws = useRef<WebSocket | null>(null);
  const pingTimer = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const isMounted = useRef(true);

  // Store callbacks in refs to prevent connection thrashing on callback identity changes
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onTypingRef = useRef(onTyping);
  onTypingRef.current = onTyping;
  const onReadReceiptRef = useRef(onReadReceipt);
  onReadReceiptRef.current = onReadReceipt;
  const onPermanentFailureRef = useRef(onPermanentFailure);
  onPermanentFailureRef.current = onPermanentFailure;

  // Acquire authentication credentials via single-use ticket (BUG-005, BUG-031)
  const getAuthParam = async (): Promise<string | null> => {
    try {
      const ticketRes = await apiPost<{ ticket: string }>("/ws/ticket", {});
      if (ticketRes.success && ticketRes.data?.ticket) {
        return `ticket=${ticketRes.data.ticket}`;
      }
    } catch {}

    return null;
  };

  const cleanup = useCallback(() => {
    if (pingTimer.current) {
      clearInterval(pingTimer.current);
      pingTimer.current = null;
    }
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.onerror = null;
      ws.current.onmessage = null;
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!chatId || !isMounted.current || !enabled) return;
    cleanup();
    setStatus("connecting");

    const authParam = await getAuthParam();
    if (!authParam || !isMounted.current || !enabled) {
      setStatus("disconnected");
      return;
    }

    const socketUrl = `${WS_BASE_URL}/${chatId}?${authParam}`;
    const socket = new WebSocket(socketUrl);
    ws.current = socket;

    socket.onopen = () => {
      if (!isMounted.current) return;
      setStatus("connected");
      reconnectAttempts.current = 0;

      // Heartbeat keepalive every 30 seconds
      pingTimer.current = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "ping" }));
        }
      }, 30000);
    };

    socket.onmessage = (event) => {
      if (!isMounted.current) return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === "pong") return;
        if (data.type === "typing" && onTypingRef.current) {
          onTypingRef.current(data.payload?.sender_id);
          return;
        }
        if (data.type === "read_receipt" && onReadReceiptRef.current) {
          onReadReceiptRef.current(data.payload?.sender_id, data.payload?.message_id);
          return;
        }
        if (onMessageRef.current) {
          onMessageRef.current(data);
        }
      } catch {}
    };

    socket.onclose = (event) => {
      if (!isMounted.current) return;
      setStatus("disconnected");
      if (pingTimer.current) {
        clearInterval(pingTimer.current);
        pingTimer.current = null;
      }

      // Do not reconnect on intentional close, rate-limit, or permission rejection (4001, 4003, 1008)
      if (event.code === 4001 || event.code === 4003 || event.code === 1000 || event.code === 1008) {
        if (event.code === 1008 && onPermanentFailureRef.current) {
          onPermanentFailureRef.current();
        }
        return;
      }

      // Cap maximum reconnection attempts (BUG-054)
      if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
        if (onPermanentFailureRef.current) {
          onPermanentFailureRef.current();
        }
        return;
      }

      // Exponential backoff up to 16s
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 16000);
      reconnectAttempts.current += 1;
      reconnectTimer.current = setTimeout(() => {
        if (isMounted.current) connect();
      }, delay);
    };

    socket.onerror = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
    };
  }, [chatId, cleanup, enabled]);

  useEffect(() => {
    reconnectAttempts.current = 0;
  }, [chatId]);

  useEffect(() => {
    isMounted.current = true;
    reconnectAttempts.current = 0;
    if (enabled) {
      connect();
    } else {
      cleanup();
      setStatus("disconnected");
    }

    // Reconnect when app returns from background; teardown on background/inactive
    const subscription = AppState.addEventListener(
      "change",
      (nextState: AppStateStatus) => {
        if (nextState === "active") {
          if (ws.current?.readyState !== WebSocket.OPEN) {
            reconnectAttempts.current = 0;
            connect();
          }
        } else if (nextState === "background" || nextState === "inactive") {
          cleanup();
          setStatus("disconnected");
        }
      }
    );

    return () => {
      isMounted.current = false;
      cleanup();
      subscription.remove();
    };
  }, [connect, cleanup]);

  const sendEvent = useCallback((type: string, payload: Record<string, any> = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type, payload }));
    }
  }, []);

  const sendTyping = useCallback(() => {
    sendEvent("typing");
  }, [sendEvent]);

  const sendReadReceipt = useCallback((messageId?: string) => {
    sendEvent("read_receipt", messageId ? { message_id: messageId } : {});
  }, [sendEvent]);

  return {
    status,
    isConnected: status === "connected",
    sendEvent,
    sendTyping,
    sendReadReceipt,
    reconnect: connect,
  };
}
