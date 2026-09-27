import type { ChatRequest, ChatResponse } from "../types/chat";
import { request } from "./http";

/** POST /chat — gửi câu hỏi, nhận câu trả lời kèm citation. */
export function askChat(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", { method: "POST", body: payload });
}
