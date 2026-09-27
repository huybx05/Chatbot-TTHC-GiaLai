import Placeholder from "../../components/ui/Placeholder.tsx";

/** Hướng C: đọc report từ evaluation/evaluate_retrieval.py. */
export default function RetrievalPage() {
  return (
    <Placeholder
      title="Chất lượng truy xuất"
      note="Recall@5, Recall@10, MRR, nDCG@10, latency p50/p95 cho BM25, Vector, Hybrid, Hybrid + Reranker."
    />
  );
}
