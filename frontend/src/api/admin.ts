import { request } from "./http";
import { API_BASE_URL } from "./config";

export type AdminProcedure = {
  code: string;
  name: string;
  domain_group: string;
  source_field: string;
  canonical_field: string;
  administrative_levels: string[];
  issuing_agency: string;
  status: string;
  detail_url: string;
  section_count: number;
};

export type AdminProcedureDetail = Record<string, unknown> & {
  procedure_code: string;
  procedure_name: string;
  agencies?: { agency_name: string; role: string; is_inferred: boolean }[];
};

export type AdminSection = {
  section_id: string;
  chunk_id: string;
  section_type: string;
  title: string;
  content: string;
  chunk_order: number;
  detail_url: string;
};

export type AdminFaq = {
  id: string;
  procedure_code?: string | null;
  question: string;
  answer: string;
  intent: string;
  status: string;
  priority: number;
  created_at?: string;
  updated_at?: string;
};

export type AdminFaqIntent = {
  value: string;
  label: string;
};

export type AdminFaqPayload = {
  question: string;
  answer: string;
  intent: string;
  status: "ready" | "draft";
  procedure_code?: string | null;
};

export type GraphNode = {
  id: string;
  label: string;
  name: string;
  properties?: Record<string, unknown>;
};

export type GraphEdge = {
  source: string;
  target: string;
  type: string;
};

export type GraphStats = {
  nodes: { label: string; count: number }[];
  relationships: { type: string; count: number }[];
};

export type AdminConversation = {
  id: string;
  session_id: string;
  session_title: string;
  user_name: string;
  user_type: "auth" | "guest";
  question: string;
  answer: string;
  created_at: string;
  status: string;
  source: string;
  social_intent: string;
  ttft_ms: number | null;
  total_ms: number | null;
  streamed: boolean;
  feedback: {
    value?: "like" | "dislike";
    reasons?: string[];
    comment?: string;
    updated_at?: string;
  } | null;
};

export type AdminConversationPage = {
  items: AdminConversation[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminConversationQuery = {
  offset?: number;
  limit?: number;
  dateRange?: "today" | "7d" | "30d";
  source?: string;
  feedback?: "all" | "like" | "dislike" | "none";
  search?: string;
};

export function getAdminConversations(query: AdminConversationQuery = {}) {
  const suffix = conversationParams(query);
  return request<AdminConversationPage>(
    `/api/admin/conversations${suffix ? `?${suffix}` : ""}`,
  );
}

function conversationParams(query: AdminConversationQuery): string {
  const params = new URLSearchParams();
  const sourceValues: Record<string, string> = {
    FAQ: "faq",
    "FAQ toàn cục": "faq_global",
    Hybrid: "hybrid",
    "Fact lookup": "fact_lookup",
    Graph: "graph",
    "Không truy xuất": "none",
  };
  if (typeof query.offset === "number") params.set("offset", String(query.offset));
  if (typeof query.limit === "number") params.set("limit", String(query.limit));
  if (query.dateRange) params.set("date_range", query.dateRange);
  if (query.source && query.source !== "all") {
    params.set("source", sourceValues[query.source] ?? query.source);
  }
  if (query.feedback && query.feedback !== "all") {
    params.set("feedback", query.feedback);
  }
  if (query.search?.trim()) params.set("q", query.search.trim());
  return params.toString();
}

export function getAdminConversationIds(query: AdminConversationQuery = {}) {
  const suffix = conversationParams(query);
  return request<{ ids: string[]; total: number }>(
    `/api/admin/conversations/ids${suffix ? `?${suffix}` : ""}`,
  );
}

export function bulkDeleteAdminConversations(ids: string[]) {
  return request<{ deleted: number }>("/api/admin/conversations/bulk-delete", {
    method: "POST",
    body: { ids },
  });
}

export type ConversationExportFilters = {
  dateRange: "today" | "7d" | "30d";
  source: string;
  feedback: "all" | "like" | "dislike" | "none";
  search: string;
};

export async function downloadAdminConversations(filters: ConversationExportFilters) {
  const params = new URLSearchParams({ date_range: filters.dateRange });
  const sourceValues: Record<string, string> = {
    FAQ: "faq",
    "FAQ toàn cục": "faq_global",
    Hybrid: "hybrid",
    "Fact lookup": "fact_lookup",
    Graph: "graph",
    "Không truy xuất": "none",
  };
  if (filters.source !== "all") params.set("source", sourceValues[filters.source] ?? filters.source);
  if (filters.feedback !== "all") params.set("feedback", filters.feedback);
  if (filters.search.trim()) params.set("q", filters.search.trim());

  const response = await fetch(`${API_BASE_URL}/api/admin/conversations/export?${params}`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error("Không thể xuất lịch sử hội thoại.");

  const file = await response.blob();
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = "conversation_logs.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

export type AdminConversationDetail = AdminConversation & {
  messages: {
    id: string;
    role: "user" | "assistant";
    content: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }[];
};

export function getAdminConversation(messageId: string) {
  return request<AdminConversationDetail>(`/api/admin/conversations/${messageId}`);
}

export function deleteAdminConversation(messageId: string) {
  return request<{ deleted: number }>(`/api/admin/conversations/${messageId}`, {
    method: "DELETE",
  });
}

export type ServiceStatus = {
  ready: boolean;
  error: string;
  counts?: Record<string, number>;
  index?: string;
  exists?: boolean;
  documents?: number;
  collections?: {
    semantic?: { name: string; exists: boolean; points: number };
    faq?: { name: string; exists: boolean; points: number };
  };
};

export type AdminCostSummary = {
  budget_usd: number;
  spent_usd: number;
  remaining_usd: number;
  percent: number;
  status: "normal" | "notice" | "warning" | "over";
  month_start: string;
  month_end: string;
  today_usd: number;
  today_calls: number;
  month_calls: number;
  tokens: { input: number; cached: number; output: number };
  by_model: Array<{
    model: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    embedding_tokens: number;
    rerank_tokens: number;
    cost_usd: number;
  }>;
  by_stage: Array<{ stage: string; calls: number; cost_usd: number }>;
  recent: Array<{
    occurred_at: string;
    stage: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    is_peak: boolean;
    input_tier: string;
  }>;
  pricing: Array<{
    model_key: string;
    display_name: string;
    provider: string;
    kind: string;
    input_cache_hit_per_m: number | null;
    input_cache_miss_per_m: number | null;
    output_per_m: number | null;
    embedding_per_m: number | null;
    rerank_per_m: number | null;
    peak_multiplier: number;
    peak_timezone: string;
    peak_windows: Array<{ start: string; end: string }>;
    input_tiers: Array<{
      max_input_tokens: number | null;
      input_per_m: number;
      output_per_m: number;
    }>;
  }>;
};

export function getAdminCostSummary() {
  return request<AdminCostSummary>("/api/admin/costs/summary");
}

export type AdminSystemStatus = {
  services: Record<"api" | "postgresql" | "neo4j" | "elasticsearch" | "qdrant", ServiceStatus>;
};

export function getAdminSystemStatus() {
  return request<AdminSystemStatus>("/api/admin/system/status");
}

export function getAdminProcedures(q = "") {
  return request<{ items: AdminProcedure[] }>(`/api/admin/procedures?q=${encodeURIComponent(q)}`);
}

export function getAdminProcedure(code: string) {
  return request<{ item: AdminProcedureDetail | null }>(`/api/admin/procedures/${code}`);
}

export function getAdminSections(code: string) {
  return request<{ items: AdminSection[] }>(`/api/admin/procedures/${code}/sections`);
}

export function getAdminFaqs(q = "", intent = "") {
  return request<{ items: AdminFaq[] }>(
    `/api/admin/faq?q=${encodeURIComponent(q)}&intent=${encodeURIComponent(intent)}`,
  );
}

export function getAdminFaqIntents() {
  return request<AdminFaqIntent[]>("/api/admin/faq/intents");
}

export function createAdminFaq(payload: AdminFaqPayload) {
  return request<AdminFaq>("/api/admin/faq", {
    method: "POST",
    body: payload,
  });
}

export function updateAdminFaq(id: string, payload: AdminFaqPayload) {
  return request<AdminFaq>(`/api/admin/faq/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteAdminFaq(id: string) {
  return request<{ deleted: number }>(`/api/admin/faq/${id}`, {
    method: "DELETE",
  });
}

export function bulkDeleteAdminFaqs(ids: string[]) {
  return request<{ deleted: number }>("/api/admin/faq/bulk/delete", {
    method: "POST",
    body: { ids },
  });
}

export function bulkSetAdminFaqStatus(
  ids: string[],
  status: "ready" | "draft",
) {
  return request<{ updated: number }>("/api/admin/faq/bulk/status", {
    method: "POST",
    body: { ids, status },
  });
}

export type FaqImportIssue = {
  row: number;
  column: string;
  message: string;
};

async function readImportError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      detail?: string | { message?: string; errors?: FaqImportIssue[] };
    };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail && typeof payload.detail === "object") {
      const errors = payload.detail.errors ?? [];
      const first = errors
        .slice(0, 5)
        .map((item) => `Dòng ${item.row} · ${item.column}: ${item.message}`)
        .join("\n");
      return [payload.detail.message, first].filter(Boolean).join("\n");
    }
  } catch {
    // body không phải JSON
  }
  return "Không import được file FAQ.";
}

export async function importAdminFaqs(file: File): Promise<{ imported: number }> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/admin/faq/import`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await readImportError(response));
  }
  return (await response.json()) as { imported: number };
}

async function downloadFaqFile(
  path: string,
  filename: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Không tải được file FAQ.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

export function downloadAdminFaqExport(status: "all" | "ready" | "draft", procedureCode = "") {
  const params = new URLSearchParams({ status });
  if (procedureCode.trim()) params.set("procedure_code", procedureCode.trim());
  return downloadFaqFile(
    `/api/admin/faq/export?${params.toString()}`,
    `faq_${status}_${procedureCode.trim() || "all"}.xlsx`,
  );
}

export function downloadAdminFaqTemplate() {
  return downloadFaqFile("/api/admin/faq/template", "faq_template.xlsx");
}

export function downloadAdminProcedureExport(options: {
  q?: string;
  sourceFields?: string[];
}) {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set("q", options.q.trim());
  for (const field of options.sourceFields ?? []) {
    if (field.trim()) params.append("source_field", field);
  }
  const query = params.toString();
  return downloadFaqFile(
    `/api/admin/procedures/export${query ? `?${query}` : ""}`,
    "danh_sach_tthc.xlsx",
  );
}

export function getGraphStats() {
  return request<GraphStats>("/api/admin/graph/stats");
}

export function getFullGraph() {
  return request<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/api/admin/graph");
}

export function getProcedureGraph(code: string) {
  return request<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/api/admin/graph/procedures/${code}`);
}


/** ---------------------------------------------------------------------------
 * Kiểm thử truy xuất — dùng cho trang `/admin/rag-playground`.
 *
 * Trả **top-K kèm điểm** thay vì chỉ top-1, kèm cờ `passed` cho từng candidate.
 * Nhờ vậy người tune ngưỡng thấy được candidate dưới ngưỡng và biết câu hỏi
 * trượt vì 0,74 (sát ngưỡng) hay vì 0,50 (xa).
 * ------------------------------------------------------------------------- */

export type RetrievalMode =
  | "keyword"
  | "vector"
  | "hybrid"
  | "fact_lookup"
  | "graph";

export type RetrievalCandidate = {
  id: string;
  source: RetrievalMode;
  score: number;
  /** Điểm có vượt ngưỡng cosine của hệ thống không. */
  passed: boolean;
  /** Loại thông tin: fee, processing_time, required_documents, … */
  intent: string;
  procedure_code: string;
  procedure_name: string;
  /**
   * FAQ: trường JSON gốc mà FAQ được sinh từ đó (`trinh_tu_thuc_hien`, …).
   * Chunk (keyword/vector/hybrid): `section_type` của chunk (`FEE`, `STEPS`, …).
   */
  section_type: string;
  /** FAQ: câu hỏi mẫu khớp được. Chunk: tiêu đề mục. */
  title: string;
  /** FAQ: câu trả lời nguyên văn. Chunk: nội dung chunk. */
  content: string;
  detail_url: string;
  /**
   * Chunk này do **BM25** tìm ra.
   *
   * Ở mode `keyword` luôn `true`; ở `hybrid` cho biết nhánh nào đã đóng góp chunk vào
   * kết quả trộn. `source` bị RRF ghi đè thành `"hybrid"` nên phải có hai cờ riêng mới
   * biết được nguồn gốc.
   */
  by_keyword: boolean;
  /** Chunk này do **vector (Qdrant)** tìm ra. */
  by_vector: boolean;
  /**
   * Thứ hạng trong nhánh BM25 (1 = đứng đầu). `null` = nhánh không tìm ra.
   *
   * Cần thứ hạng chứ không chỉ cờ đúng/sai: bộ dữ liệu nhỏ nên hai nhánh lấy 30 chunk
   * mỗi bên và gần như mọi chunk đều có ở cả hai → cờ luôn `true/true`. Thứ hạng cho
   * biết chunk mạnh ở nhánh nào.
   */
  keyword_rank: number | null;
  /** Thứ hạng trong nhánh vector. `null` = nhánh không tìm ra. */
  vector_rank: number | null;
};

export type RetrievalTestResponse = {
  mode: RetrievalMode;
  top_k: number;
  /**
   * Ngưỡng cosine — chỉ có ở mode `faq`; `keyword`, `vector`, `hybrid` trả `null`.
   * UI dựa vào `null` để biết không có ngưỡng nào để so.
   */
  threshold: number | null;
  /** Candidate top-1 có vượt ngưỡng không. Chỉ có nghĩa khi `threshold !== null`. */
  passed: boolean;
  candidate_count: number;
  elapsed_ms: number;
  /**
   * Câu trả lời sinh từ ngữ cảnh (13.13). Rỗng khi chưa bật ô "Sinh câu trả lời",
   * hoặc khi mô hình không dùng được (`answer_error` nói lý do).
   */
  answer: string;
  /** Vì sao chưa sinh được câu trả lời — chỉ có khi `answer` rỗng mà vẫn có candidate. */
  answer_error: string;
  /** Nguồn ứng với `[1]`, `[2]`… trong `answer`, cùng thứ tự. */
  citations: WorkflowCitation[];
  context: string;
  candidates: RetrievalCandidate[];
  /**
   * `null` = mode không dùng rerank (faq/keyword/vector).
   * `true` = rerank đã chạy và thành công.
   * `false` = **rerank lỗi** — danh sách chỉ là thứ tự trước rerank. Khi đó `warning`
   * có nội dung và **không được** dùng số liệu này để so sánh.
   */
  rerank_used: boolean | null;
  /** Cảnh báo không chặn (khác `error`): rerank lỗi, mã thủ tục không tồn tại… */
  warning: string;
  /**
   * `true` = hệ thống **chủ động không trả lời**: điểm liên quan của kết quả tốt nhất
   * dưới ngưỡng, nên trả context rỗng thay vì đưa ngữ liệu ngoài phạm vi cho LLM.
   */
  refused: boolean;
  /** Điểm liên quan của top-1 do reranker chấm (cổng từ chối). `null` = chưa chấm được. */
  gate_score: number | null;
  /**
   * `true` = cổng **bị bỏ qua có chủ ý** vì câu hỏi đã nêu mã thủ tục tồn tại (câu hỏi
   * mặc nhiên trong phạm vi). Khác với `gate_score = null` do rerank lỗi.
   */
  gate_skipped: boolean;
  /** Mục (`section_type`) của thủ tục đang **có** trong ngữ cảnh. Rỗng khi không có mã. */
  sections_present: string[];
  /** Mục của thủ tục **chưa** có trong ngữ cảnh — dùng để biết còn thiếu gì. */
  sections_absent: string[];
  /** Nhánh graph: tên template Cypher đã chạy. Chỉ mode `graph`. */
  graph_template?: string;
  /** Nhánh graph: intent đã nhận diện. Chỉ mode `graph`. */
  graph_intent?: string;
  /**
   * `true` = **đang hỏi lại** vì mơ hồ (ví dụ nhiều thủ tục cùng khớp tên). Không phải
   * từ chối: hệ thống mời người dùng chọn thay vì đoán. Chỉ mode `graph` hiện có.
   */
  clarify?: boolean;
  /** Câu hỏi lại, ví dụ "Bạn muốn hỏi thủ tục nào?". */
  clarify_question?: string;
  /** Lựa chọn để người dùng chọn. */
  clarify_options?: { value: string; label: string; hint?: string }[];
};

export function testAdminRetrieval(body: {
  question: string;
  mode: RetrievalMode;
  top_k?: number;
  generate_answer?: boolean;
  /**
   * Rerank **đầy đủ** (xếp lại toàn bộ danh sách). Mặc định **tắt** — đo được là làm
   * giảm độ chính xác mục 7/7 → 4/7.
   *
   * Tắt ở đây **không** có nghĩa là không dùng reranker: cổng từ chối vẫn gọi rerank
   * cho 3 tài liệu đầu. Giao diện không còn nút bật/tắt; chỉ truyền `true` khi cần so
   * sánh bằng script.
   */
  use_rerank?: boolean;
  /**
   * Cổng từ chối. Mặc định **bật** và giao diện **luôn** dùng mặc định này — không còn
   * nút bật/tắt, vì đây là cơ chế an toàn duy nhất của nhánh hybrid (cosine không tách
   * được câu ngoài phạm vi). Chỉ truyền `false` khi đo đạc bằng script.
   */
  use_refusal_gate?: boolean;
}) {
  return request<RetrievalTestResponse>("/api/admin/retrieval/test", {
    method: "POST",
    body: {
      question: body.question,
      mode: body.mode,
      top_k: body.top_k ?? 5,
      generate_answer: body.generate_answer ?? false,
      use_rerank: body.use_rerank ?? false,
      use_refusal_gate: body.use_refusal_gate ?? true,
    },
  });
}

/** Một mục bằng chứng do luồng tìm được. */
export interface WorkflowEvidence {
  kind: "fact" | "graph" | "chunk" | "faq";
  procedure_code?: string;
  procedure_name?: string;
  detail_url?: string;
  section_type?: string;
  title?: string;
  content?: string;
  score?: number;
  by_keyword?: boolean;
  by_vector?: boolean;
  /** Thứ hạng trong nhánh từ khoá (1 = cao nhất); `null` = nhánh đó không tìm ra. */
  keyword_rank?: number | null;
  /** Thứ hạng trong nhánh vector. */
  vector_rank?: number | null;
  provenance?: string;
  part_index?: number;
  part_title?: string;
}

/** Một nguồn được trích trong câu trả lời — ứng với `[1]`, `[2]`… */
export interface WorkflowCitation {
  procedure_code: string;
  procedure_name: string;
  detail_url: string;
  document_code: string;
}

/** Kết quả chạy **trọn luồng** cho một câu hỏi. */
export interface WorkflowAskResponse {
  question: string;
  branch: string;
  branch_signal: string;
  outcome: string;
  branch_reason: string;
  router_source: string;
  embedding_used: boolean;
  evidence: WorkflowEvidence[];
  clarify: { question?: string; options?: { value: string; label?: string; hint?: string }[] };
  codes: string[];
  documents: string[];
  resolution: { code?: string; name?: string; method?: string; note?: string };
  error: string;
  ms: number;
  answerable: boolean;
  /** Mốc 1 chưa sinh câu trả lời nên luôn là `false`. */
  has_answer: boolean;
  /** Câu trả lời sinh từ bằng chứng (13.13); rỗng = chưa sinh được. */
  answer: string;
  /** Vì sao chưa sinh được — chỉ có khi `answer` rỗng mà vẫn có bằng chứng. */
  answer_error: string;
  /** Nguồn ứng với `[1]`, `[2]`… trong câu trả lời, cùng thứ tự. */
  citations: WorkflowCitation[];
  /** Bản đọc được, dựng ở máy chủ — cùng nội dung với CLI. */
  summary: string;
}

/**
 * Chạy một câu hỏi qua **cả luồng** (luồng tự chọn nhánh, không phải người dùng chọn).
 *
 * Dùng để so sánh "chạy lẻ một động cơ" với "chạy đủ luồng": quyết định định tuyến có đúng
 * không, và bằng chứng cuối cùng là gì.
 */
export function askAdminWorkflow(question: string) {
  return request<WorkflowAskResponse>("/api/admin/workflow/ask", {
    method: "POST",
    body: { question },
  });
}
