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

/** GET /v1/chats — all active chat threads */
export async function getChats(): Promise<ChatThread[]> {
  const res = await apiGet<{ chats: ChatThread[] }>("/chats");
  if (!res.success) throw { _apiError: res.error };
  return res.data.chats;
}

/** GET /v1/chats/:match_id/messages (cursor paginated) */
export async function getMessages(matchId: string, cursor?: string): Promise<Message[]> {
  const res = await apiGet<{ messages: Message[] }>(`/chats/${matchId}/messages`, {
    cursor,
    limit: 30,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data.messages;
}

/** POST /v1/chats/:match_id/messages — text */
export async function sendMessage(matchId: string, content: string): Promise<Message> {
  const trimmed = content.trim();
  if (!trimmed || trimmed.length > MAX_MESSAGE_LENGTH) throw new Error("INVALID_MESSAGE_LENGTH");
  const res = await apiPost<Message>(`/chats/${matchId}/messages`, {
    type: "text",
    content: trimmed,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/chats/:match_id/messages — media (photo or voice) */
export async function sendMediaMessage(
  matchId: string,
  type: "photo" | "voice",
  mediaId: string
): Promise<Message> {
  const res = await apiPost<Message>(`/chats/${matchId}/messages`, {
    type,
    media_id: mediaId,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/chats/:match_id/read */
export async function markRead(matchId: string): Promise<void> {
  await apiPost(`/chats/${matchId}/read`);
}

/** GET /v1/chats/weekly-question */
export async function getWeeklyQuestion(): Promise<{ question: string }> {
  const res = await apiGet<{ question: string }>("/chats/weekly-question");
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/ws/ticket — single-use WebSocket ticket (30s TTL) */
export async function getWsTicket(): Promise<string> {
  const res = await apiPost<WsTicket>("/ws/ticket");
  if (!res.success) throw { _apiError: res.error };
  return res.data.ticket;
}

/** POST /v1/users/:user_id/report — report a user */
export async function reportMessage(
  reportedUserId: string,
  reason: string,
  messageId?: string
): Promise<void> {
  const res = await apiPost(`/users/${reportedUserId}/report`, {
    reason,
    detail: messageId ? `Message ID: ${messageId}` : undefined,
  });
  if (!res.success) throw { _apiError: res.error };
}

/** POST /v1/users/:user_id/block — block a user */
export async function blockUser(targetUserId: string): Promise<void> {
  const res = await apiPost(`/users/${targetUserId}/block`, { reason: "blocked_by_user" });
  if (!res.success) throw { _apiError: res.error };
}
