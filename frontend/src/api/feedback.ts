import { request } from "./http";

export type AnswerFeedback = "like" | "dislike";

export type AnswerFeedbackPayload = {
  feedback: AnswerFeedback | null;
  reasons?: string[];
  comment?: string;
};

export function saveAnswerFeedback(messageId: string, payload: AnswerFeedbackPayload) {
  return request<{ message_id: string; feedback: AnswerFeedback | null }>(
    `/chat/messages/${messageId}/feedback`,
    { method: "POST", body: payload },
  );
}
