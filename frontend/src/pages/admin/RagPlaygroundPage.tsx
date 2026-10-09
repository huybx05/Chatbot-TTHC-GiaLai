import type { BadgeTone } from "./shared.tsx";
import { Badge, Card, Icon, PageHeader, SectionTitle } from "./shared.tsx";

export default function RagPlaygroundPage() {
  return (
    <>
      <PageHeader
        eyebrow="RAG Playground"
        title="Chạy thử câu hỏi và xem trace truy xuất"
        description="Dùng để debug tại sao chatbot chọn route, evidence và câu trả lời như hiện tại."
      />

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <label className="text-sm font-bold" htmlFor="rag-question">Câu hỏi truy vấn</label>
          <textarea
            id="rag-question"
            className="mt-2 min-h-28 w-full rounded-lg border border-border-color bg-white p-3 text-sm outline-primary"
            defaultValue="Tôi bị mất căn cước công dân thì cấp lại cần hồ sơ gì và mất bao lâu?"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {["Greeting", "FAQ lookup", "Fact lookup", "Hybrid search", "Full RAG"].map((mode) => (
              <button key={mode} className={`rounded-lg border px-3 py-2 text-sm font-bold ${mode === "Full RAG" ? "border-primary bg-primary text-white" : "border-border-color bg-secondary-surface text-text-secondary"}`}>
                {mode}
              </button>
            ))}
          </div>
          <button className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-bold text-white">
            <Icon name="play_arrow" />
            Chạy thử nghiệm
          </button>
        </Card>

        <Card>
          <SectionTitle title="Trace truy xuất" note="Hiển thị ngắn gọn từng bước thay vì nhiều panel rời." />
          <div className="grid gap-2 md:grid-cols-2">
            {[
              ["Rewrite", "Không cần", "ok"],
              ["Intent", "fact_lookup", "info"],
              ["Keyword", "12 kết quả", "info"],
              ["Vector", "20 kết quả", "info"],
              ["RRF", "hợp nhất top 15", "ok"],
              ["Rerank", "top 5 evidence", "ok"],
            ].map(([name, value, tone]) => (
              <div key={name} className="rounded-lg border border-border-color bg-secondary-surface p-3">
                <p className="text-xs font-bold uppercase text-text-secondary">{name}</p>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <p className="font-bold">{value}</p>
                  <Badge tone={tone as BadgeTone}>OK</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <SectionTitle title="Evidence đưa vào LLM" />
          <div className="space-y-3">
            {[
              ["1.013314", "Thành phần hồ sơ", "score 0.91"],
              ["2.002621", "Thời hạn giải quyết", "score 0.87"],
              ["1.014100", "Căn cứ pháp lý", "score 0.78"],
            ].map(([code, title, score]) => (
              <div key={code} className="rounded-lg border border-border-color p-3">
                <div className="flex items-center justify-between">
                  <p className="font-bold">{code}</p>
                  <span className="text-xs font-semibold text-text-secondary">{score}</span>
                </div>
                <p className="mt-1 text-sm text-text-secondary">{title}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle title="Câu trả lời mẫu" />
          <p className="text-sm leading-6 text-text-secondary">
            Khi cấp lại thẻ căn cước do bị mất, người dân có thể nộp hồ sơ trực tuyến hoặc trực tiếp tại cơ quan quản lý căn cước. Hồ sơ và thời hạn cần đối chiếu theo thủ tục cụ thể và văn bản hiện hành.
          </p>
          <div className="mt-4 rounded-lg bg-primary-soft p-3 text-sm font-semibold text-primary">
            Có gắn nguồn tham chiếu · Không dùng dữ liệu ngoài evidence
          </div>
        </Card>
      </div>
    </>
  );
}
