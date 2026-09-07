/**
 * useWebSocket — Reusable WebSocket hook for real-time chat
 * - Ticket-based authentication handshake with JWT token fallback
 * - Automatic ping/pong keepalive
 * - Exponential backoff auto-reconnect
 * - Full type safety
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { AppState, AppStateStatus } from "react-native";
import { getAccessToken, apiPost } from "../api/client";

const WS_BASE_URL =
  process.env.EXPO_PUBLIC_WS_URL || "wss://api.jainune.com/v1/ws/chat";

export type WebSocketStatus = "connecting" | "connected" | "disconnected";

export interface UseWebSocketOptions {
  chatId: string;
  onMessage?: (message: any) => void;
  onTyping?: (senderId: string) => void;
  onReadReceipt?: (senderId: string, messageId?: string) => void;
}

export function useWebSocket({
  chatId,
  onMessage,
  onTyping,
  onReadReceipt,
}: UseWebSocketOptions) {
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const ws = useRef<WebSocket | null>(null);
  const pingTimer = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const isMounted = useRef(true);

  // Acquire authentication credentials
  const getAuthParam = async (): Promise<string | null> => {
    try {
      const ticketRes = await apiPost<{ ticket: string }>("/ws/ticket", {});
      if (ticketRes.success && ticketRes.data?.ticket) {
        return `ticket=${ticketRes.data.ticket}`;
      }
    } catch {}

    try {
      const token = await getAccessToken();
      if (token) return `token=${token}`;
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
    if (!chatId || !isMounted.current) return;
    cleanup();
    setStatus("connecting");

    const authParam = await getAuthParam();
    if (!authParam || !isMounted.current) {
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
        if (data.type === "typing" && onTyping) {
          onTyping(data.payload?.sender_id);
          return;
        }
        if (data.type === "read_receipt" && onReadReceipt) {
          onReadReceipt(data.payload?.sender_id, data.payload?.message_id);
          return;
        }
        if (onMessage) {
          onMessage(data);
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

      // Do not reconnect on intentional close or permission rejection (4001, 4003)
      if (event.code === 4001 || event.code === 4003 || event.code === 1000) {
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
  }, [chatId, cleanup, onMessage, onTyping, onReadReceipt]);

  useEffect(() => {
    isMounted.current = true;
    connect();

    // Reconnect when app returns from background
    const subscription = AppState.addEventListener(
      "change",
      (nextState: AppStateStatus) => {
        if (nextState === "active" && ws.current?.readyState !== WebSocket.OPEN) {
          connect();
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
