/** Citation luôn lấy từ metadata thật; LLM không tự tạo URL. */
export interface Citation {
  title: string;
  url: string;
  section?: string;
  page?: number;
}

export interface ProcedureSummary {
  procedure_code: string;
  procedure_name: string;
  domain_group?: string;
  source_field?: string;
  agency?: string;
}

export interface ChatRequest {
  question: string;
}

/** Một lựa chọn cho câu hỏi lại — giao diện vẽ thành nút bấm. */
export interface ClarifyOption {
  value: string;
  label: string;
  hint?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  procedure?: ProcedureSummary;
  /** `clarify` = cần người dùng chọn; `abstained` = từ chối; `answered` = có câu trả lời. */
  status?: "answered" | "clarify" | "abstained";
  /** Chỉ có khi `status === "clarify"` và hệ thống biết lựa chọn cụ thể. */
  options?: ClarifyOption[];
  /** true khi hệ thống không đủ evidence và phải từ chối trả lời. */
  abstained: boolean;
}
