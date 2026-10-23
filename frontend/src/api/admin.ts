import { request } from "./http";

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

export type AdminQaPair = {
  id: string;
  faq_id?: string;
  question: string;
  answer: string;
  procedure_code: string;
  procedure_name?: string;
  domain_group?: string;
  source_field?: string;
  intent?: string;
  source_section?: string;
  source_text?: string;
  tags?: string[];
  status: string;
  score: number;
  confidence?: number;
  created_at?: string;
  updated_at?: string;
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

export function getAdminQa(procedureCode: string) {
  return request<{ items: AdminQaPair[] }>(`/api/admin/qa?procedure_code=${encodeURIComponent(procedureCode)}`);
}

export function approveAdminQa(id: string) {
  return request<{ updated: number }>(`/api/admin/qa/${id}/approve`, { method: "POST" });
}

export function approveAllAdminQa(procedureCode = "") {
  return request<{ updated: number }>(`/api/admin/qa/approve-all?procedure_code=${encodeURIComponent(procedureCode)}`, { method: "POST" });
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
  | "faq"
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