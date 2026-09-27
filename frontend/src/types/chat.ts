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
  procedure_hint?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  procedure?: ProcedureSummary;
  /** true khi hệ thống không đủ evidence và phải từ chối trả lời. */
  abstained: boolean;
}
