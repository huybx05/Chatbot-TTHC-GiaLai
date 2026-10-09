import { useEffect, useMemo, useState } from "react";

import { approveAdminQa, approveAllAdminQa, getAdminQa, type AdminQaPair } from "../../api/admin";
import { Badge, Card, MetricCard, PageHeader } from "./shared.tsx";

const INTENT_LABELS: Record<string, string> = {
  agency: "Cơ quan",
  condition: "Điều kiện",
  fee: "Lệ phí",
  general: "Chung",
  legal_basis: "Căn cứ pháp lý",
  process_steps: "Trình tự",
  processing_time: "Thời hạn xử lý",
  required_documents: "Hồ sơ",
  result: "Kết quả",
  submit_method: "Cách nộp",
  target_audience: "Đối tượng",
};

function intentLabel(intent = "general") {
  return INTENT_LABELS[intent] ?? intent;
}

function statusLabel(status: string) {
  return status === "ready" ? "Sẵn sàng" : "Nháp";
}

function faqTone(status: string) {
  return status === "ready" ? "ok" : "muted";
}

export default function FaqPage() {
  const [items, setItems] = useState<AdminQaPair[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [procedureCode, setProcedureCode] = useState("");
  const [status, setStatus] = useState("all");
  const [intent, setIntent] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const filtered = useMemo(
    () => items.filter((item) => (status === "all" || item.status === status) && (intent === "all" || item.intent === intent)),
    [items, intent, status],
  );
  const selected = filtered.find((item) => item.id === selectedId) ?? filtered[0];
  const draftCount = items.filter((item) => item.status !== "ready").length;
  const intents = useMemo(() => Array.from(new Set(items.map((item) => item.intent).filter(Boolean))).sort(), [items]);

  function loadFaq(code = procedureCode) {
    setLoading(true);
    setError("");
    getAdminQa(code.trim())
      .then((res) => {
        setItems(res.items);
        setSelectedId(res.items[0]?.id ?? "");
      })
      .catch(() => setError("Không tải được danh sách FAQ."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadFaq("");
  }, []);

  function approveOne(id: string) {
    approveAdminQa(id).then(() => loadFaq());
  }

  function approveAll() {
    approveAllAdminQa(procedureCode.trim()).then(() => loadFaq());
  }

  return (
    <>
      <PageHeader
        eyebrow="FAQ"
        title="Quản lý bộ câu hỏi thường gặp"
        description="Duyệt các cặp Q/A sinh từ dữ liệu chuẩn hóa trước khi đưa vào luồng trả lời nhanh."
      />

      {error ? <div className="mb-4 rounded-lg border border-danger bg-danger-surface p-3 text-sm font-semibold text-danger">{error}</div> : null}

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <MetricCard icon="quiz" label="Tổng FAQ" value={String(items.length)} note="Từ bảng faq" tone="info" />
        <MetricCard icon="rate_review" label="Nháp" value={String(draftCount)} note="draft" tone={draftCount ? "warn" : "ok"} />
        <MetricCard icon="verified" label="Sẵn sàng" value={String(items.length - draftCount)} note="ready" tone="ok" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_420px]">
        <Card>
          <div className="mb-4 grid gap-2 md:grid-cols-[1fr_170px_170px_150px]">
            <input
              className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm outline-primary"
              placeholder="Lọc theo mã thủ tục, ví dụ 1.115341"
              value={procedureCode}
              onChange={(event) => setProcedureCode(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") loadFaq();
              }}
            />
            <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">Tất cả trạng thái</option>
              <option value="draft">Nháp</option>
              <option value="ready">Sẵn sàng</option>
            </select>
            <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm" value={intent} onChange={(event) => setIntent(event.target.value)}>
              <option value="all">Tất cả loại FAQ</option>
              {intents.map((value) => (
                <option key={value} value={value}>
                  {intentLabel(value)}
                </option>
              ))}
            </select>
            <button className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:bg-primary-hover" type="button" onClick={() => loadFaq()}>
              Lọc FAQ
            </button>
          </div>

          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-text-secondary">{loading ? "Đang tải..." : `${filtered.length} FAQ đang hiển thị`}</p>
            <button className="rounded-lg border border-border-color bg-card-surface px-4 py-2 text-sm font-bold text-primary hover:bg-primary-soft" type="button" onClick={approveAll}>
              Duyệt toàn bộ
            </button>
          </div>

          <div className="space-y-2 xl:max-h-[calc(100vh-19rem)] xl:overflow-y-auto xl:pr-1">
            {filtered.map((item) => (
              <button
                key={item.id}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  item.id === selected?.id ? "border-primary bg-primary-soft/60" : "border-border-color hover:bg-secondary-surface"
                }`}
                type="button"
                onClick={() => setSelectedId(item.id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="font-bold leading-6">{item.question}</p>
                  <Badge tone={faqTone(item.status)}>{statusLabel(item.status)}</Badge>
                </div>
                <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-secondary">{item.answer}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge tone="info">{item.procedure_code}</Badge>
                  {item.intent ? <Badge tone="muted">{intentLabel(item.intent)}</Badge> : null}
                  <Badge tone="muted">{`score ${Number(item.score ?? 0).toFixed(2)}`}</Badge>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card className="xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:self-start xl:overflow-auto">
          {selected ? (
            <div>
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge tone="info">{selected.procedure_code}</Badge>
                  <Badge tone={faqTone(selected.status)}>{statusLabel(selected.status)}</Badge>
                  {selected.intent ? <Badge tone="muted">{intentLabel(selected.intent)}</Badge> : null}
                </div>
                <h3 className="text-base font-bold leading-6">{selected.question}</h3>
              </div>

              <div className="mt-4 rounded-lg border border-border-color bg-secondary-surface p-3">
                <p className="text-xs font-bold uppercase text-text-secondary">Câu trả lời</p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{selected.answer}</p>
              </div>

              <div className="mt-4 grid gap-3 text-sm">
                {[
                  ["Tên thủ tục", selected.procedure_name],
                  ["Lĩnh vực", selected.source_field],
                  ["Nhóm domain", selected.domain_group],
                  ["Loại FAQ", intentLabel(selected.intent)],
                  ["Nguồn", selected.source_section],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-border-color p-3">
                    <p className="text-xs font-bold uppercase text-text-secondary">{label}</p>
                    <p className="mt-1 break-words font-semibold">{value || "Chưa có"}</p>
                  </div>
                ))}
              </div>

              {selected.source_text ? (
                <div className="mt-4 rounded-lg border border-border-color bg-secondary-surface p-3">
                  <p className="text-xs font-bold uppercase text-text-secondary">Đoạn nguồn</p>
                  <p className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap text-sm leading-6">{selected.source_text}</p>
                </div>
              ) : null}

              <button
                className="mt-4 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-bold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                disabled={selected.status === "ready"}
                onClick={() => approveOne(selected.id)}
              >
                {selected.status === "ready" ? "Sẵn sàng" : "Duyệt"}
              </button>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">Chưa có FAQ để hiển thị.</p>
          )}
        </Card>
      </div>
    </>
  );
}
