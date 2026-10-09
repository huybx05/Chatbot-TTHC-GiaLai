import { Badge, Card, MetricCard, PageHeader, Progress, SectionTitle, qaRows } from "./shared.tsx";

export default function QaCachePage() {
  const selectedQa = qaRows[0];

  return (
    <>
      <PageHeader
        eyebrow="Semantic FAQ Cache"
        title="Quản lý cặp Q/A fast-path cho câu hỏi phổ biến"
        description="Theo GUIDE Phase 10: Q/A đã thẩm định pháp lý được nạp vào Qdrant faq_cache để trả lời nhanh các câu hỏi lặp lại, giảm độ trễ và chi phí LLM."
        action="Đồng bộ faq_cache"
      />

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <MetricCard icon="quiz" label="Cặp Q/A" value="128" note="100+ cặp đã biên soạn" tone="info" />
        <MetricCard icon="bolt" label="FAQ hit rate" value="34%" note="Fast-path trước RAG" tone="ok" />
        <MetricCard icon="verified" label="Đã publish" value="96" note="Đã thẩm định nội dung" tone="ok" />
        <MetricCard icon="rule" label="Holdout eval" value="32" note="Không nạp cache để đánh giá" tone="warn" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <div className="mb-4 grid gap-2 md:grid-cols-[1fr_180px_160px]">
            <input className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm outline-primary" placeholder="Tìm câu hỏi, mã thủ tục, lĩnh vực..." />
            <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm">
              <option>Mọi lĩnh vực</option>
              <option>Cư trú - căn cước</option>
              <option>Hộ tịch</option>
              <option>Xuất nhập cảnh</option>
            </select>
            <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm">
              <option>Mọi trạng thái</option>
              <option>Published</option>
              <option>Review</option>
              <option>Eval holdout</option>
            </select>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="border-b border-border-color text-xs uppercase text-text-secondary">
                <tr>
                  <th className="py-3 pr-3">Câu hỏi</th>
                  <th className="py-3 pr-3">Lĩnh vực</th>
                  <th className="py-3 pr-3">Nguồn</th>
                  <th className="py-3 pr-3">Split</th>
                  <th className="py-3 pr-3">Score</th>
                  <th className="py-3 pr-3">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color">
                {qaRows.map((item) => (
                  <tr
                    key={item.question}
                    className={item.question === selectedQa.question ? "bg-primary-soft/40" : "hover:bg-secondary-surface"}
                  >
                    <td className="max-w-[360px] py-3 pr-3">
                      <p className="font-bold">{item.question}</p>
                      <p className="mt-1 line-clamp-2 text-xs text-text-secondary">{item.answer}</p>
                    </td>
                    <td className="py-3 pr-3 text-text-secondary">{item.domain}</td>
                    <td className="py-3 pr-3 font-bold text-primary">{item.source}</td>
                    <td className="py-3 pr-3"><Badge tone={item.split === "Cache" ? "info" : "warn"}>{item.split}</Badge></td>
                    <td className="py-3 pr-3 font-semibold">{item.score}</td>
                    <td className="py-3 pr-3"><Badge tone={item.status === "Published" ? "ok" : "warn"}>{item.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <SectionTitle title="Chi tiết cặp Q/A" note="Xem dữ liệu sẽ được nạp vào faq_cache hoặc giữ lại làm eval holdout." />
            <div className="space-y-3">
              <div className="rounded-lg border border-border-color bg-secondary-surface p-3">
                <p className="text-xs font-bold uppercase text-text-secondary">Câu hỏi</p>
                <p className="mt-1 text-sm font-bold leading-6">{selectedQa.question}</p>
              </div>
              <div className="rounded-lg border border-border-color bg-secondary-surface p-3">
                <p className="text-xs font-bold uppercase text-text-secondary">Câu trả lời chuẩn</p>
                <p className="mt-1 text-sm leading-6">{selectedQa.answer}</p>
              </div>
              <dl className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                {[
                  ["Mã nguồn", selectedQa.source],
                  ["Lĩnh vực", selectedQa.domain],
                  ["Split", selectedQa.split],
                  ["Similarity", selectedQa.score],
                  ["Trạng thái", selectedQa.status],
                  ["Collection", selectedQa.split === "Cache" ? "faq_cache" : "eval_holdout"],
                ].map(([key, value]) => (
                  <div key={key} className="rounded-lg border border-border-color bg-secondary-surface p-3">
                    <dt className="text-xs font-bold uppercase text-text-secondary">{key}</dt>
                    <dd className="mt-1 font-semibold">{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="rounded-lg border border-border-color bg-primary-soft p-3 text-sm font-semibold text-primary">
                Cặp Q/A phải giữ nguồn thủ tục và không dùng để đánh giá nếu đã nạp vào cache.
              </div>
            </div>
          </Card>

          <Card>
            <SectionTitle title="Coverage lĩnh vực" />
            <div className="space-y-3">
              {[
                ["Đất đai", 28],
                ["Cư trú - căn cước", 24],
                ["Hộ tịch", 18],
                ["GPLX", 15],
                ["Khác", 43],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="font-semibold">{label}</span>
                    <span className="text-text-secondary">{value} Q/A</span>
                  </div>
                  <Progress value={Number(value)} />
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
