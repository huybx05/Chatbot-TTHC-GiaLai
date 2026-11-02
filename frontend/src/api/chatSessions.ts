import { request } from "./http";

export type ChatSession = {
  id: string;
  title: string;
  is_pinned: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type ChatMessageRole = "user" | "assistant";

export type ChatMessageRecord = {
  id: string;
  session_id: string;
  role: ChatMessageRole;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export function getChatSessions() {
  return request<{ items: ChatSession[] }>("/api/v1/chat-sessions");
}

export function createChatSession() {
  return request<ChatSession>("/api/v1/chat-sessions", {
    method: "POST",
  });
}

export function renameChatSession(id: string, title: string) {
  return request<ChatSession>(`/api/v1/chat-sessions/${id}`, {
    method: "PATCH",
    body: { title },
  });
}

export function setChatSessionPinned(id: string, isPinned: boolean) {
  return request<ChatSession>(`/api/v1/chat-sessions/${id}/pin`, {
    method: "PATCH",
    body: { is_pinned: isPinned },
  });
}

export function deleteChatSession(id: string) {
  return request<{ deleted: boolean }>(`/api/v1/chat-sessions/${id}`, {
    method: "DELETE",
  });
}

export function getChatMessages(sessionId: string) {
  return request<{ items: ChatMessageRecord[] }>(
    `/api/v1/chat-sessions/${sessionId}/messages`,
  );
}

export type GuestSessionResponse = {
  session_id: string;
  expires_at: string | null;
  messages: ChatMessageRecord[];
};

export function createGuestSession() {
  return request<GuestSessionResponse>("/chat/guest-session", { method: "POST" });
}

export function getGuestSession() {
  return request<GuestSessionResponse>("/chat/guest-session");
}

export function deleteGuestSession() {
  return request<{ deleted: boolean }>("/chat/guest-session", { method: "DELETE" });
}

