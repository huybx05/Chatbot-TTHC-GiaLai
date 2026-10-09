import { useState } from "react";

import type { BadgeTone } from "./shared.tsx";
import { Badge, Card, Icon, MetricCard, PageHeader, SectionTitle } from "./shared.tsx";

type AnswerSource = {
  type: "Q/A" | "Hybrid" | "Graph" | "Fact" | "Smalltalk";
  label: string;
  detail: string;
  tone: BadgeTone;
};

type Turn = {
  id: string;
  question: string;
  answer: string;
  route: string;
  latency: string;
  confidence: string;
  sources: AnswerSource[];
};

type ConversationSession = {
  id: string;
  user: string;
  title: string;
  time: string;
  status: string;
  statusTone: BadgeTone;
  turns: Turn[];
  tokens: string;
  cost: string;
  satisfaction: string;
};

const sessions: ConversationSession[] = [
  {
    id: "s1",
    user: "Người dân ẩn danh",
    title: "Cấp lại thẻ Căn cước bị mất",
    time: "Hôm nay, 09:42",
    status: "Đã trả lời kèm nguồn",
    statusTone: "ok",
    tokens: "2.840",
    cost: "1.420đ",
    satisfaction: "Hữu ích",
    turns: [
      {
        id: "t1",
        question: "Tôi mất CCCD thì cấp lại cần giấy tờ gì và làm ở đâu?",
        answer:
          "Hệ thống trả lời theo thủ tục cấp lại thẻ Căn cước, nêu nơi tiếp nhận, hồ sơ cần chuẩn bị và thời hạn giải quyết. Câu trả lời được gắn nguồn từ mã thủ tục và đường dẫn chi tiết trên Cổng DVC.",
        route: "SEARCH",
        latency: "1.38s",
        confidence: "0.91",
        sources: [
          {
            type: "Hybrid",
            label: "Elasticsearch + Qdrant",
            detail: "Chunk hồ sơ, trình tự, thời hạn của thủ tục căn cước",
            tone: "info",
          },
          {
            type: "Fact",
            label: "PostgreSQL",
            detail: "Mã TTHC, tên thủ tục, cơ quan thực hiện, detail_url",
            tone: "ok",
          },
        ],
      },
      {
        id: "t2",
        question: "Có cần nộp sổ hộ khẩu giấy không?",
        answer:
          "Hệ thống dùng ngữ cảnh hội thoại trước đó để hiểu vẫn đang hỏi về cấp lại Căn cước, sau đó trả lời ngắn và giữ nguồn trích dẫn cũ.",
        route: "FACT_LOOKUP",
        latency: "620ms",
        confidence: "0.88",
        sources: [
          {
            type: "Fact",
            label: "PostgreSQL",
            detail: "Metadata thủ tục và trường thành phần hồ sơ đã chuẩn hóa",
            tone: "ok",
          },
        ],
      },
    ],
  },
  {
    id: "s2",
    user: "Cán bộ phường",
    title: "Đăng ký khai sinh liên thông",
    time: "Hôm nay, 08:17",
    status: "Trúng Q/A cache",
    statusTone: "info",
    tokens: "860",
    cost: "380đ",
    satisfaction: "Chưa đánh giá",
    turns: [
      {
        id: "t1",
        question: "Đăng ký khai sinh cho trẻ dưới 6 tuổi gồm những bước nào?",
        answer:
          "Câu trả lời lấy nhanh từ cặp Q/A đã duyệt, sau đó gắn mã thủ tục liên thông 2.002621 để người dùng đối chiếu.",
        route: "Q/A_LOOKUP",
        latency: "94ms",
        confidence: "0.96",
        sources: [
          {
            type: "Q/A",
            label: "Q/A cache đã duyệt",
            detail: "FAQ: khai sinh, thường trú, cấp thẻ BHYT cho trẻ dưới 6 tuổi",
            tone: "info",
          },
          {
            type: "Fact",
            label: "PostgreSQL",
            detail: "Mã TTHC 2.002621 và detail_url nguồn",
            tone: "ok",
          },
        ],
      },
    ],
  },
  {
    id: "s3",
    user: "Người dân ẩn danh",
    title: "Thủ tục nào liên quan đến bảo hiểm thất nghiệp?",
    time: "Hôm qua, 16:03",
    status: "Dùng Graph",
    statusTone: "warn",
    tokens: "3.120",
    cost: "1.760đ",
    satisfaction: "Cần kiểm tra",
    turns: [
      {
        id: "t1",
        question: "Thủ tục điều chỉnh đóng BHXH có liên quan tới thủ tục bảo hiểm thất nghiệp không?",
        answer:
          "Hệ thống ưu tiên Neo4j để kiểm tra quan hệ thủ tục. Vì dữ liệu quan hệ liên thông còn mỏng, câu trả lời nêu rõ quan hệ tìm được và phần chưa đủ dữ liệu.",
        route: "GRAPH",
        latency: "1.02s",
        confidence: "0.74",
        sources: [
          {
            type: "Graph",
            label: "Neo4j Knowledge Graph",
            detail: "Quan hệ THU_TUC_LIEN_QUAN, cơ quan thực hiện, lĩnh vực",
            tone: "warn",
          },
          {
            type: "Hybrid",
            label: "Hybrid Search kiểm chứng",
            detail: "Chunk thông tin chung và thủ tục liên thông",
            tone: "info",
          },
        ],
      },
    ],
  },
  {
    id: "s4",
    user: "Người dân ẩn danh",
    title: "Chào hỏi và cảm ơn",
    time: "Hôm qua, 11:25",
    status: "Không truy xuất",
    statusTone: "muted",
    tokens: "120",
    cost: "45đ",
    satisfaction: "Hữu ích",
    turns: [
      {
        id: "t1",
        question: "Xin chào, bạn giúp tôi tra cứu thủ tục được không?",
        answer:
          "Hệ thống nhận diện đây là lời chào nên trả lời trực tiếp, không gọi kho dữ liệu để tiết kiệm chi phí và latency.",
        route: "SMALLTALK",
        latency: "210ms",
        confidence: "0.99",
        sources: [
          {
            type: "Smalltalk",
            label: "LLM trả lời trực tiếp",
            detail: "Không dùng Q/A, Hybrid Search hay Graph",
            tone: "muted",
          },
        ],
      },
    ],
  },
];

function sourceIcon(type: AnswerSource["type"]) {
  return {
    "Q/A": "quiz",
    Hybrid: "travel_explore",
    Graph: "hub",
    Fact: "storage",
    Smalltalk: "chat_bubble",
  }[type];
}

export default function ConversationsPage() {
  const [selectedId, setSelectedId] = useState(sessions[0].id);
  const selected = sessions.find((session) => session.id === selectedId) ?? sessions[0];
  const totalTurns = sessions.reduce((sum, session) => sum + session.turns.length, 0);

  return (
    <>
      <PageHeader
        eyebrow="Hội thoại"
        title="Lịch sử hỏi đáp người dùng"
        description="Theo dõi phiên hỏi đáp, nguồn sinh câu trả lời và từng lượt truy xuất để phát hiện câu trả lời thiếu nguồn, route sai hoặc cần bổ sung Q/A."
      />

      <div className="mb-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon="forum" label="Phiên hôm nay" value="428" note="+12% so với hôm qua" tone="info" />
        <MetricCard icon="question_answer" label="Lượt hỏi đáp" value={String(totalTurns)} note="Trong dữ liệu mẫu đang xem" tone="ok" />
        <MetricCard icon="bolt" label="Q/A cache hit" value="31%" note="Mục tiêu v1: 25-40%" tone="info" />
        <MetricCard icon="schedule" label="P95 latency" value="1.42s" note="Hybrid đang là nhánh chậm nhất" tone="warn" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card className="space-y-4">
          <SectionTitle
            title="Tổng quan phiên"
            note="Chọn một phiên để xem chi tiết từng câu hỏi, câu trả lời và nguồn đã dùng."
          />

          <div className="grid grid-cols-2 gap-2 text-sm">
            {[
              ["Q/A", "31%"],
              ["Hybrid", "46%"],
              ["Graph", "9%"],
              ["Không truy xuất", "14%"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-border-color bg-secondary-surface p-3">
                <p className="text-xs font-semibold uppercase text-text-secondary">{label}</p>
                <p className="mt-1 text-xl font-bold">{value}</p>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => setSelectedId(session.id)}
                className={[
                  "w-full rounded-lg border p-3 text-left transition",
                  selected.id === session.id
                    ? "border-primary bg-primary-soft"
                    : "border-border-color hover:bg-secondary-surface",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-bold">{session.title}</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      {session.user} · {session.time}
                    </p>
                  </div>
                  <Badge tone={session.statusTone}>{session.status}</Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold text-text-secondary">
                  <span>{session.turns.length} lượt</span>
                  <span>{session.tokens} token</span>
                  <span>{session.cost}</span>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-primary">Chi tiết phiên</p>
                <h3 className="mt-1 text-xl font-bold">{selected.title}</h3>
                <p className="mt-1 text-sm text-text-secondary">
                  {selected.user} · {selected.time} · Đánh giá: {selected.satisfaction}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={selected.statusTone}>{selected.status}</Badge>
                <Badge tone="muted">{`${selected.tokens} token`}</Badge>
                <Badge tone="muted">{selected.cost}</Badge>
              </div>
            </div>
          </Card>

          {selected.turns.map((turn, index) => (
            <Card key={turn.id} className="space-y-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">Lượt {index + 1}</p>
                  <h4 className="mt-1 text-base font-bold">Route: {turn.route}</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone="info">{`Latency ${turn.latency}`}</Badge>
                  <Badge tone={Number(turn.confidence) >= 0.9 ? "ok" : "warn"}>{`Tin cậy ${turn.confidence}`}</Badge>
                </div>
              </div>

              <div className="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <div className="rounded-lg border border-border-color bg-user-bubble p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm font-bold">
                    <Icon name="person" className="text-[18px]" />
                    Câu hỏi người dùng
                  </div>
                  <p className="text-sm leading-6">{turn.question}</p>
                </div>

                <div className="rounded-lg border border-border-color bg-secondary-surface p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm font-bold">
                    <Icon name="smart_toy" className="text-[18px]" />
                    Câu trả lời hệ thống
                  </div>
                  <p className="text-sm leading-6 text-text-secondary">{turn.answer}</p>
                </div>
              </div>

              <div>
                <SectionTitle title="Nguồn đã dùng" note="Theo route trong GUIDE: Q/A, Fact Lookup, Hybrid Search, Graph hoặc Smalltalk." />
                <div className="grid gap-3 lg:grid-cols-2">
                  {turn.sources.map((source) => (
                    <div key={`${turn.id}-${source.type}`} className="rounded-lg border border-border-color p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <span className="flex size-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
                            <Icon name={sourceIcon(source.type)} className="text-[18px]" />
                          </span>
                          <div>
                            <p className="text-sm font-bold">{source.label}</p>
                            <p className="text-xs text-text-secondary">{source.type}</p>
                          </div>
                        </div>
                        <Badge tone={source.tone}>{source.type}</Badge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-text-secondary">{source.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </>
  );
}
