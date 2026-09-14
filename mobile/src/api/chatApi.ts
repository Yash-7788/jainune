/**
 * Phase 5 — Chat API additions
 * sendMediaMessage: POST /v1/chats/:matchId/messages (type: photo/voice)
 * reportMessage: POST /v1/reports
 * blockUser: POST /v1/users/block
 */

import { apiGet, apiPost, apiPut, apiDelete } from "./client";
import { MAX_MESSAGE_LENGTH } from "../security/inputValidation";

export interface Message {
  id: string;
  match_id: string;
  sender_id: string;
  type: "text" | "voice" | "photo";
  content: string | null;
  media_url: string | null;
  is_read: boolean;
  created_at: string;
}

export interface ChatThread {
  match_id: string;
  other_user: {
    id: string;
    first_name: string;
    photo_url: string | null;
    is_online: boolean;
  };
  last_message: Message | null;
  unread_count: number;
  momentum_expires_at: string | null;
}

export interface WsTicket {
  ticket: string;
}

// ── DEV Mock Chat Data ───────────────────────────────────────────────────────

const MOCK_CHAT_THREADS: ChatThread[] = [
  {
    match_id: "mock_match_1",
    other_user: {
      id: "candidate_1",
      first_name: "Ananya",
      photo_url: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80",
      is_online: true,
    },
    last_message: {
      id: "m1",
      match_id: "mock_match_1",
      sender_id: "candidate_1",
      type: "text",
      content: "Jai Jinendra! Happy to connect with you here.",
      media_url: null,
      is_read: false,
      created_at: new Date(Date.now() - 3600000).toISOString(),
    },
    unread_count: 1,
    momentum_expires_at: new Date(Date.now() + 86400000).toISOString(),
  },
];

/** GET /v1/chats — all active chat threads */
export async function getChats(): Promise<ChatThread[]> {
  try {
    const res = await apiGet<{ threads?: any[]; chats?: any[] }>("/chats");
    if (res.success && res.data) {
      const rawList = res.data?.threads || res.data?.chats || [];
      return rawList.map((t: any) => ({
        match_id: t.match_id || t.id,
        other_user: {
          id: t.other_user_id || t.other_user?.id || "",
          first_name: t.other_user_first_name || t.other_user?.first_name || "Match",
          photo_url: t.other_user_photo_url || t.other_user?.photo_url || null,
          is_online: t.other_user?.is_online ?? false,
        },
        last_message: t.last_message || (t.last_message_text ? {
          id: "",
          match_id: t.match_id || t.id,
          sender_id: "",
          type: "text" as const,
          content: t.last_message_text,
          media_url: null,
          is_read: true,
          created_at: t.last_message_at || new Date().toISOString(),
        } : null),
        unread_count: t.unread_count || 0,
        momentum_expires_at: t.expires_at || t.momentum_expires_at || null,
      }));
    }
  } catch (err) {
    if (__DEV__) {
      console.log("[DEV] getChats failed, returning mock threads");
      return MOCK_CHAT_THREADS;
    }
    throw err;
  }
  if (__DEV__) return MOCK_CHAT_THREADS;
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch chats" } };
}

/** GET /v1/chats/:match_id/messages (cursor paginated) */
export async function getMessages(matchId: string, cursor?: string): Promise<Message[]> {
  try {
    const res = await apiGet<{ messages: any[] }>(`/chats/${matchId}/messages`, {
      cursor,
      before: cursor,
      limit: 30,
    });
    if (res.success && res.data) {
      const rawMsgs = res.data?.messages || [];
      return rawMsgs.map((m: any) => ({
        id: String(m.id),
        match_id: String(m.chat_id || matchId),
        sender_id: String(m.sender_id),
        type: (m.message_type === "photo" || m.type === "photo") ? "photo" : (m.message_type === "voice" || m.type === "voice") ? "voice" : "text",
        content: m.content || null,
        media_url: m.media_url || null,
        is_read: Boolean(m.is_read),
        created_at: m.created_at || new Date().toISOString(),
      }));
    }
  } catch (err) {
    if (__DEV__) {
      return [
        {
          id: "m0",
          match_id: matchId,
          sender_id: "candidate_1",
          type: "text",
          content: "Jai Jinendra! Glad we matched on Jainune.",
          media_url: null,
          is_read: true,
          created_at: new Date(Date.now() - 7200000).toISOString(),
        },
      ];
    }
    throw err;
  }
  if (__DEV__) {
    return [
      {
        id: "m0",
        match_id: matchId,
        sender_id: "candidate_1",
        type: "text",
        content: "Jai Jinendra! Glad we matched on Jainune.",
        media_url: null,
        is_read: true,
        created_at: new Date(Date.now() - 7200000).toISOString(),
      },
    ];
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch messages" } };
}

/** POST /v1/chats/:match_id/messages — text */
export async function sendMessage(matchId: string, content: string): Promise<Message> {
  const trimmed = content.trim();
  if (!trimmed || trimmed.length > MAX_MESSAGE_LENGTH) throw new Error("INVALID_MESSAGE_LENGTH");
  try {
    const res = await apiPost<any>(`/chats/${matchId}/messages`, {
      message_type: "text",
      type: "text",
      content: trimmed,
    });
    if (res.success && res.data) {
      const m = res.data;
      return {
        id: String(m.id),
        match_id: String(m.chat_id || matchId),
        sender_id: String(m.sender_id),
        type: "text",
        content: m.content,
        media_url: m.media_url || null,
        is_read: Boolean(m.is_read),
        created_at: m.created_at,
      };
    }
  } catch (err) {
    if (__DEV__) {
      return {
        id: `msg_${Date.now()}`,
        match_id: matchId,
        sender_id: "dev_user_1",
        type: "text",
        content: trimmed,
        media_url: null,
        is_read: true,
        created_at: new Date().toISOString(),
      };
    }
    throw err;
  }
  if (__DEV__) {
    return {
      id: `msg_${Date.now()}`,
      match_id: matchId,
      sender_id: "dev_user_1",
      type: "text",
      content: trimmed,
      media_url: null,
      is_read: true,
      created_at: new Date().toISOString(),
    };
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to send message" } };
}

/** POST /v1/chats/:match_id/messages — media (photo or voice) */
export async function sendMediaMessage(
  matchId: string,
  type: "photo" | "voice",
  mediaUrl: string,
  mediaId?: string
): Promise<Message> {
  try {
    const res = await apiPost<any>(`/chats/${matchId}/messages`, {
      message_type: type,
      type,
      media_url: mediaUrl,
      media_id: mediaId || mediaUrl,
    });
    if (res.success && res.data) {
      const m = res.data;
      return {
        id: String(m.id),
        match_id: String(m.chat_id || matchId),
        sender_id: String(m.sender_id),
        type,
        content: m.content || null,
        media_url: m.media_url || mediaUrl,
        is_read: Boolean(m.is_read),
        created_at: m.created_at,
      };
    }
  } catch (err) {
    if (__DEV__) {
      return {
        id: `msg_${Date.now()}`,
        match_id: matchId,
        sender_id: "dev_user_1",
        type,
        content: null,
        media_url: mediaUrl,
        is_read: true,
        created_at: new Date().toISOString(),
      };
    }
    throw err;
  }
  if (__DEV__) {
    return {
      id: `msg_${Date.now()}`,
      match_id: matchId,
      sender_id: "dev_user_1",
      type,
      content: null,
      media_url: mediaUrl,
      is_read: true,
      created_at: new Date().toISOString(),
    };
  }
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to send media message" } };
}

/** POST /v1/chats/:match_id/read */
export async function markRead(matchId: string): Promise<void> {
  try {
    await apiPost(`/chats/${matchId}/read`);
  } catch (err) {
    if (__DEV__) return;
    throw err;
  }
}

/** GET /v1/chats/weekly-question */
export async function getWeeklyQuestion(): Promise<{ question: string }> {
  try {
    const res = await apiGet<{ question: string }>("/chats/weekly-question");
    if (res.success && res.data) return res.data;
  } catch (err) {
    if (__DEV__) {
      return { question: "What is your favorite Jain recipe to make during festivals?" };
    }
    throw err;
  }
  if (__DEV__) return { question: "What is your favorite Jain recipe to make during festivals?" };
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch question" } };
}

/** POST /v1/ws/ticket — single-use WebSocket ticket (30s TTL) */
export async function getWsTicket(): Promise<string> {
  try {
    const res = await apiPost<WsTicket>("/ws/ticket");
    if (res.success && res.data) return res.data.ticket;
  } catch (err) {
    if (__DEV__) return "dev_mock_ws_ticket";
    throw err;
  }
  if (__DEV__) return "dev_mock_ws_ticket";
  throw { _apiError: { code: "TEMPORARY_ERROR", message: "Failed to fetch WS ticket" } };
}

/** POST /v1/users/:user_id/report — report a user */
export async function reportMessage(
  reportedUserId: string,
  reason: string,
  messageId?: string
): Promise<void> {
  try {
    const res = await apiPost(`/users/${reportedUserId}/report`, {
      reason,
      detail: messageId ? `Message ID: ${messageId}` : undefined,
    });
    if (!res.success) throw { _apiError: res.error };
  } catch (err) {
    if (__DEV__) return;
    throw err;
  }
}

/** POST /v1/users/:user_id/block — block a user */
export async function blockUser(targetUserId: string): Promise<void> {
  try {
    const res = await apiPost(`/users/${targetUserId}/block`, { reason: "blocked_by_user" });
    if (!res.success) throw { _apiError: res.error };
  } catch (err) {
    if (__DEV__) return;
    throw err;
  }
}
