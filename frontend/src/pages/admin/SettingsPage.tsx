import { Card, PageHeader, SectionTitle } from "./shared.tsx";

export default function SettingsPage() {
  const groups = [
    ["Model", [["Router", "Qwen2.5-14B"], ["Embedding", "text-embedding-v4"], ["Reranker", "gte-rerank"], ["Synthesizer", "DeepSeek"]]],
    ["Retrieval", [["top_k", "20"], ["reranker_top_n", "15"], ["reranker_final_k", "5"], ["FAQ threshold", "0.90"], ["RRF k", "60"]]],
    ["Storage", [["PostgreSQL", "chatbot_tthc"], ["Elasticsearch", "administrative_procedure_chunks"], ["Qdrant semantic", "tthc_chunks"], ["Neo4j database", "neo4j"]]],
    ["Secret status", [["QWEN_API_KEY", "Đã cấu hình"], ["DEEPSEEK_API_KEY", "Đã cấu hình"], ["QDRANT_API_KEY", "Không bắt buộc"], ["SECRET_KEY", "Đã cấu hình"]]],
  ];

  return (
    <>
      <PageHeader
        eyebrow="Cấu hình"
        title="Xem cấu hình vận hành hệ thống"
        description="Module mới bổ sung. V1 chỉ xem trạng thái cấu hình, không cho sửa trực tiếp và không hiển thị secret thật."
      />

      <div className="grid gap-4 xl:grid-cols-2">
        {groups.map(([title, rows]) => (
          <Card key={title as string}>
            <SectionTitle title={title as string} />
            <div className="space-y-2">
              {(rows as string[][]).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between gap-4 rounded-lg border border-border-color bg-secondary-surface p-3">
                  <span className="text-sm font-semibold text-text-secondary">{key}</span>
                  <span className="text-right text-sm font-bold">{value}</span>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
