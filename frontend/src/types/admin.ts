/**
 * Kiểu dữ liệu cho giao diện monitoring.
 *
 * Nguồn: hướng A (đọc file pipeline sinh ra) và hướng C (benchmark retrieval).
 * Cả hai đều CHƯA có ở backend — xem docs/decisions.md.
 */

/** Hướng A — procedure_manifest.csv + validation_report.csv. */
export interface DataQualityReport {
  total_pdfs: number;
  ingest_ready: number;
  ingest_duplicate: number;
  validation_ready: number;
  validation_need_review: number;
  validation_missing_data: number;
  missing_procedure_name: number;
  missing_source_url: number;
}

/** Hướng C — report từ evaluation/evaluate_retrieval.py. */
export interface RetrievalBenchmark {
  experiment: "BM25" | "VECTOR" | "HYBRID" | "HYBRID_RERANK";
  recall_at_5: number;
  recall_at_10: number;
  mrr: number;
  ndcg_at_10: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
}

export interface PipelineStatus {
  ingest_status: Record<string, number>;
  parse_status: Record<string, number>;
  validation_status: Record<string, number>;
  chunk_count: number;
}

export interface SystemOverview {
  corpus_size: number;
  ready_procedures: number;
  chunk_count: number;
  best_recall_at_5: number | null;
}
