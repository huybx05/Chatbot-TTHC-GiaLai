import { useMemo, useState } from "react";

import type { BadgeTone } from "./shared.tsx";
import { Badge, Card, Icon, MetricCard, PageHeader, SectionTitle } from "./shared.tsx";

type Source = "FAQ" | "Hybrid" | "Fact lookup" | "Graph" | "Trực tiếp";
type Feedback = "like" | "dislike" | "none";

type ConversationLog = {
  id: string;
  dateGroup: "today" | "yesterday";
  time: string;
  session: string;
  question: string;
  answer: string;
  context: string;
  source: Source;
  supportingSources: Source[];
  latency: string;
  confidence: string;
  feedback: Feedback;
};

const logs: ConversationLog[] = [
  {
    id: "log-01",
    dateGroup: "today",
    time: "09:42",
    session: "Cấp lại thẻ Căn cước bị mất",
    question: "Tôi mất CCCD thì cấp lại cần giấy tờ gì và làm ở đâu?",
    answer: "Người dân có thể nộp hồ sơ trực tuyến hoặc trực tiếp tại cơ quan quản lý căn cước. Hồ sơ và nơi tiếp nhận được trả lời theo thủ tục tương ứng trên Cổng DVC.",
    context: "[Hybrid] Thủ tục cấp lại thẻ Căn cước: thành phần hồ sơ, nơi tiếp nhận và thời hạn giải quyết.\n[Fact lookup] Mã thủ tục, cơ quan thực hiện và đường dẫn chi tiết từ PostgreSQL.",
    source: "Hybrid",
    supportingSources: ["Fact lookup"],
    latency: "1.38s",
    confidence: "0.91",
    feedback: "like",
  },
  {
    id: "log-02",
    dateGroup: "today",
    time: "09:44",
    session: "Cấp lại thẻ Căn cước bị mất",
    question: "Có cần nộp sổ hộ khẩu giấy không?",
    answer: "Không yêu cầu xuất trình sổ hộ khẩu giấy. Người dân làm theo hướng dẫn tại nơi tiếp nhận hồ sơ hoặc trên Cổng DVC.",
    context: "[Fact lookup] Trường thành phần hồ sơ của thủ tục cấp lại thẻ Căn cước; dữ liệu đã chuẩn hóa từ PostgreSQL.",
    source: "Fact lookup",
    supportingSources: [],
    latency: "620ms",
    confidence: "0.88",
    feedback: "none",
  },
  {
    id: "log-03",
    dateGroup: "today",
    time: "08:17",
    session: "Đăng ký khai sinh liên thông",
    question: "Đăng ký khai sinh cho trẻ dưới 6 tuổi gồm những bước nào?",
    answer: "Câu trả lời được lấy từ FAQ đã duyệt của thủ tục liên thông đăng ký khai sinh, thường trú và cấp thẻ BHYT cho trẻ dưới 6 tuổi.",
    context: "[FAQ] Cặp hỏi đáp đã duyệt về thủ tục 2.002621.\n[Fact lookup] Mã thủ tục và đường dẫn nguồn chính thức.",
    source: "FAQ",
    supportingSources: ["Fact lookup"],
    latency: "94ms",
    confidence: "0.96",
    feedback: "like",
  },
  {
    id: "log-04",
    dateGroup: "yesterday",
    time: "16:03",
    session: "Thủ tục liên quan đến bảo hiểm thất nghiệp",
    question: "Thủ tục điều chỉnh đóng BHXH có liên quan tới thủ tục bảo hiểm thất nghiệp không?",
    answer: "Hệ thống kiểm tra quan hệ thủ tục trên Neo4j và đối chiếu thêm các chunk liên quan. Kết quả chỉ nêu các quan hệ hiện có trong dữ liệu.",
    context: "[Graph] Các node thủ tục, lĩnh vực và quan hệ liên quan trong Neo4j.\n[Hybrid] Chunk thông tin chung và thủ tục liên thông để kiểm chứng.",
    source: "Graph",
    supportingSources: ["Hybrid"],
    latency: "1.02s",
    confidence: "0.74",
    feedback: "dislike",
  },
  {
    id: "log-05",
    dateGroup: "yesterday",
    time: "11:25",
    session: "Chào hỏi và cảm ơn",
    question: "Xin chào, bạn giúp tôi tra cứu thủ tục được không?",
    answer: "Tôi có thể hỗ trợ tra cứu hồ sơ, trình tự thực hiện, cơ quan giải quyết, thời hạn và lệ phí của thủ tục hành chính.",
    context: "Không dùng kho dữ liệu: hệ thống nhận diện câu chào hỏi và trả lời trực tiếp.",
    source: "Trực tiếp",
    supportingSources: [],
    latency: "210ms",
    confidence: "0.99",
    feedback: "like",
  },
];

function sourceTone(source: Source): BadgeTone {
  if (source === "Hybrid") return "ok";
  if (source === "Graph") return "warn";
  if (source === "Trực tiếp") return "muted";
  return "info";
}

function feedbackLabel(feedback: Feedback) {
  return { like: "Hữu ích", dislike: "Không hữu ích", none: "Chưa đánh giá" }[feedback];
}

function feedbackTone(feedback: Feedback): BadgeTone {
  return feedback === "like" ? "ok" : feedback === "dislike" ? "bad" : "muted";
}

export default function ConversationsPage() {
  const [dateRange, setDateRange] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [feedbackFilter, setFeedbackFilter] = useState("all");
  const [selectedLog, setSelectedLog] = useState<ConversationLog | null>(null);

  const filteredLogs = useMemo(
    () => logs.filter((log) =>
      (dateRange !== "today" || log.dateGroup === "today")
      && (sourceFilter === "all" || log.source === sourceFilter)
      && (feedbackFilter === "all" || log.feedback === feedbackFilter),
    ),
    [dateRange, sourceFilter, feedbackFilter],
  );

  const todayQuestions = logs.filter((log) => log.dateGroup === "today").length;
  const positiveFeedback = logs.filter((log) => log.feedback === "like").length;
  const averageLatency = Math.round(logs.reduce((sum, log) => sum + Number.parseFloat(log.latency) * (log.latency.includes("ms") ? 0.001 : 1), 0) / logs.length * 1000);

  return (
    <>
      <PageHeader
        eyebrow="Log hội thoại"
        title="Theo dõi hỏi đáp của người dân"
        description="Xem từng lượt hỏi đáp, nguồn truy xuất, thời gian phản hồi và đánh giá của người dùng."
      />

      <div className="mb-4 flex items-center gap-2 text-xs text-text-secondary">
        <Icon name="science" className="text-[16px] text-primary" />
        Dữ liệu mẫu giao diện, sẽ thay bằng log thực tế khi backend sẵn sàng.
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon="question_answer" label="Câu hỏi hôm nay" value={String(todayQuestions)} note="Theo log đang hiển thị" tone="info" />
        <MetricCard icon="forum" label="Câu hỏi 30 ngày" value={String(logs.length)} note="Trong dữ liệu mẫu" tone="ok" />
        <MetricCard icon="thumb_up" label="Đánh giá hữu ích" value={String(positiveFeedback)} note="Like từ người dùng" tone="ok" />
        <MetricCard icon="schedule" label="Latency trung bình" value={`${averageLatency}ms`} note="Từ các lượt trả lời" tone="info" />
      </div>

      <Card className="mt-4">
        <SectionTitle title="Danh sách log hỏi đáp" note="Chọn một dòng để xem đầy đủ nội dung hội thoại và nguồn truy xuất." />

        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <label className="text-sm font-semibold">Thời gian
            <select className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal" value={dateRange} onChange={(event) => setDateRange(event.target.value)}>
              <option value="all">Tất cả thời gian</option>
              <option value="today">Hôm nay</option>
              <option value="7d">7 ngày gần nhất</option>
              <option value="30d">30 ngày gần nhất</option>
            </select>
          </label>
          <label className="text-sm font-semibold">Nguồn trả lời
            <select className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
              <option value="all">Tất cả nguồn</option><option value="FAQ">FAQ</option><option value="Hybrid">Hybrid</option><option value="Fact lookup">Fact lookup</option><option value="Graph">Graph</option><option value="Trực tiếp">Trực tiếp</option>
            </select>
          </label>
          <label className="text-sm font-semibold">Đánh giá
            <select className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal" value={feedbackFilter} onChange={(event) => setFeedbackFilter(event.target.value)}>
              <option value="all">Tất cả đánh giá</option><option value="like">Hữu ích</option><option value="dislike">Không hữu ích</option><option value="none">Chưa đánh giá</option>
            </select>
          </label>
        </div>

        <p className="mb-3 text-sm text-text-secondary">{filteredLogs.length} lượt hỏi đáp đang hiển thị</p>
        <div className="overflow-x-auto rounded-lg border border-border-color">
          <table className="w-full min-w-[940px] text-left text-sm">
            <thead className="border-b border-border-color bg-secondary-surface text-xs uppercase text-text-secondary"><tr><th className="px-4 py-3 font-semibold">Thời gian</th><th className="min-w-[300px] px-4 py-3 font-semibold">Câu hỏi</th><th className="px-4 py-3 font-semibold">Nguồn</th><th className="px-4 py-3 font-semibold">Latency</th><th className="px-4 py-3 font-semibold">Tin cậy</th><th className="px-4 py-3 font-semibold">Đánh giá</th></tr></thead>
            <tbody>
              {filteredLogs.map((log) => (
                <tr
                  key={log.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedLog(log)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") setSelectedLog(log);
                  }}
                  className="cursor-pointer border-b border-border-color outline-none last:border-0 hover:bg-hover-item focus-visible:bg-primary-soft"
                >
                  <td className="whitespace-nowrap px-4 py-3 align-top text-text-secondary">{log.dateGroup === "today" ? "Hôm nay" : "Hôm qua"}<br />{log.time}</td>
                  <td className="px-4 py-3 align-top"><p className="line-clamp-2 font-semibold">{log.question}</p><p className="mt-1 truncate text-xs text-text-secondary">{log.session}</p></td>
                  <td className="px-4 py-3 align-top"><Badge tone={sourceTone(log.source)}>{log.source}</Badge></td>
                  <td className="whitespace-nowrap px-4 py-3 align-top font-semibold">{log.latency}</td>
                  <td className="px-4 py-3 align-top"><Badge tone={Number(log.confidence) >= 0.85 ? "ok" : "warn"}>{log.confidence}</Badge></td>
                  <td className="px-4 py-3 align-top"><Badge tone={feedbackTone(log.feedback)}>{feedbackLabel(log.feedback)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {selectedLog ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4" role="dialog" aria-modal="true" aria-labelledby="conversation-log-title" onMouseDown={() => setSelectedLog(null)}>
          <section className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-border-color bg-card-surface p-5 shadow-xl" onMouseDown={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <div><p className="text-xs font-bold uppercase tracking-wide text-primary">Chi tiết lượt hỏi đáp</p><h3 id="conversation-log-title" className="mt-1 text-lg font-bold">{selectedLog.session}</h3><p className="mt-1 text-sm text-text-secondary">{selectedLog.dateGroup === "today" ? "Hôm nay" : "Hôm qua"}, {selectedLog.time}</p></div>
              <button type="button" onClick={() => setSelectedLog(null)} aria-label="Đóng chi tiết" className="rounded-lg p-1 text-text-secondary hover:bg-secondary-surface hover:text-text-primary"><Icon name="close" /></button>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div><p className="text-xs font-bold uppercase tracking-wide text-text-secondary">Câu hỏi</p><p className="mt-2 text-sm leading-6">{selectedLog.question}</p></div>
              <div><p className="text-xs font-bold uppercase tracking-wide text-text-secondary">Câu trả lời</p><p className="mt-2 text-sm leading-6 text-text-secondary">{selectedLog.answer}</p></div>
            </div>

            <div className="mt-5 border-t border-border-color pt-4">
              <p className="text-sm font-bold">Context đưa vào LLM</p>
              <pre className="mt-3 whitespace-pre-wrap rounded-lg border border-border-color bg-secondary-surface p-3 font-sans text-sm leading-6 text-text-secondary">{selectedLog.context}</pre>
            </div>

            <div className="mt-5 border-t border-border-color pt-4">
              <p className="text-sm font-bold">Thông tin xử lý</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge tone={sourceTone(selectedLog.source)}>{selectedLog.source}</Badge>
                {selectedLog.supportingSources.map((source) => <Badge key={source} tone={sourceTone(source)}>{source}</Badge>)}
                <Badge tone="muted">{`Latency ${selectedLog.latency}`}</Badge>
                <Badge tone={Number(selectedLog.confidence) >= 0.85 ? "ok" : "warn"}>{`Tin cậy ${selectedLog.confidence}`}</Badge>
                <Badge tone={feedbackTone(selectedLog.feedback)}>{feedbackLabel(selectedLog.feedback)}</Badge>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
