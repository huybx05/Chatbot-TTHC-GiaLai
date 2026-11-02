import { request } from "./http";

export interface FaqSuggestion {
  id: string;
  question: string;
}

export function getFaqSuggestions(limit = 5) {
  return request<{ items: FaqSuggestion[] }>(
    `/api/v1/faq/suggestions?limit=${limit}`,
  );
}
