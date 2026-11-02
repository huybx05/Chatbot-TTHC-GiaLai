import { useEffect, useState } from "react";

import { getAdminSystemStatus, type AdminSystemStatus } from "../../api/admin";
import { Badge, Card, PageHeader, SectionTitle, type BadgeTone } from "./shared.tsx";

function formatNumber(value?: number | null) {
  return typeof value === "number" ? value.toLocaleString("vi-VN") : "-";
}

function formatTime(value: Date | null) {
  if (value === null) return "Chưa kiểm tra";
  return value.toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function OverviewPage() {
  const [status, setStatus] = useState<AdminSystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const load = async () => {
    setLoading(true);
    setFailed(false);
    try {
      const next = await getAdminSystemStatus();
      setStatus(next);
      setCheckedAt(new Date());
    } catch {
      setStatus(null);
      setFailed(true);
      setCheckedAt(new Date());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const pg = status?.services.postgresql;
  const neo4j = status?.services.neo4j;
  const es = status?.services.elasticsearch;
  const qdrant = status?.services.qdrant;
  const qdrantSemantic = qdrant?.collections?.semantic;

  const procedures = pg?.counts?.procedures ?? null;
  const chunks = pg?.counts?.sections ?? null;
  const faq = pg?.counts?.faq ?? null;
  const nodes = neo4j?.counts?.nodes ?? null;
  const relationships = neo4j?.counts?.relationships ?? null;
  const esChunks = es?.documents ?? null;
  const qdrantChunks = qdrantSemantic?.points ?? null;

  const usersTotal = pg?.counts?.users_total ?? null;
  const visitsTotal = pg?.counts?.visits_total ?? null;
  const sessionsActive = pg?.counts?.sessions_active ?? null;
  const sessionsGuest = pg?.counts?.sessions_guest ?? null;
  const questionsTotal = pg?.counts?.questions_total ?? null;
  const questionsToday = pg?.counts?.questions_today ?? null;

  const canCheckSync =
    !failed &&
    typeof chunks === "number" &&
    typeof esChunks === "number" &&
    typeof qdrantChunks === "number";
  const syncOk = canCheckSync && chunks === esChunks && chunks === qdrantChunks;
  const syncTone: BadgeTone = failed ? "muted" : !canCheckSync ? "warn" : syncOk ? "ok" : "bad";
  const syncLabel = failed
    ? "Chưa kiểm tra"
    : !canCheckSync
      ? "Chưa đủ dữ liệu"
      : syncOk
        ? "Đồng bộ"
        : "Có chênh lệch";

  const usageMetrics = [
    ["Tổng người dùng", usersTotal],
    ["Đang truy cập", sessionsActive],
    ["Lượt truy cập", visitsTotal],
    ["Tổng số câu hỏi", questionsTotal],
    ["Câu hỏi trong ngày", questionsToday],
    ["Phiên khách", sessionsGuest],
  ] as const;

  const dataMetrics = [
    ["Thủ tục hành chính", procedures, "PostgreSQL"],
    ["Chunks lưu trữ", chunks, "PostgreSQL"],
    ["FAQ", faq, "PostgreSQL"],
    [
      "Node / quan hệ",
      nodes === null && relationships === null
        ? null
        : `${formatNumber(nodes)} / ${formatNumber(relationships)}`,
      "Neo4j",
    ],
  ] as const;

  return (
    <>
      <PageHeader
        eyebrow="Tổng quan hệ thống"
        title="Theo dõi hoạt động người dùng, hiệu suất chatbot và tình trạng hạ tầng dữ liệu."
        description="Các con số tổng hợp về hệ thống, người dùng và dữ liệu."
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text-secondary">
          Cập nhật lúc: <span className="font-semibold text-text-primary">{formatTime(checkedAt)}</span>
        </p>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-md border border-border-color bg-card-surface px-3 py-1.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary disabled:cursor-wait disabled:opacity-60"
        >
          {loading ? "Đang kiểm tra…" : "Làm mới"}
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <SectionTitle title="Hoạt động người dùng" note="Thống kê mức độ sử dụng trong hệ thống" />
          <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
            {usageMetrics.map(([label, value]) => (
              <div key={label}>
                <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
                <p className="mt-1 text-2xl font-bold">{formatNumber(value)}</p>
                <p className="mt-1 text-xs leading-5 text-text-secondary"></p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle title="Kho dữ liệu" note="Thống kê dữ liệu được lưu trữ trên các dịch vụ lưu trữ" />

          <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
            {dataMetrics.map(([label, value, note]) => (
              <div key={label}>
                <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
                <p className="mt-1 text-2xl font-bold">
                  {typeof value === "number" ? formatNumber(value) : value ?? "-"}
                </p>
                <p className="mt-1 text-xs leading-5 text-text-secondary">{note}</p>
              </div>
            ))}
          </div>

          <div className="mt-5 border-t border-border-color pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold">Trạng thái đồng bộ kho dữ liệu</p>
              <Badge tone={syncTone}>{syncLabel}</Badge>
            </div>

            <div className="mt-3 divide-y divide-border-color text-sm">
              <div className="flex items-center justify-between gap-3 py-2">
                <span className="text-text-secondary">PostgreSQL</span>
                <span className="font-semibold">{formatNumber(chunks)} chunk</span>
              </div>
              <div className="flex items-center justify-between gap-3 py-2">
                <span className="text-text-secondary">Elasticsearch</span>
                <span className={esChunks === chunks ? "font-semibold" : "font-semibold text-danger"}>
                  {formatNumber(esChunks)} chunk
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 py-2">
                <span className="text-text-secondary">Qdrant</span>
                <span className={qdrantChunks === chunks ? "font-semibold" : "font-semibold text-danger"}>
                  {formatNumber(qdrantChunks)} vector chunk
                </span>
              </div>
            </div>

            {!failed && canCheckSync && !syncOk ? (
              <p className="mt-3 text-xs leading-5 text-text-secondary">
                Chênh lệch: PostgreSQL {formatNumber(chunks)} · Elasticsearch {formatNumber(esChunks)} · Qdrant{" "}
                {formatNumber(qdrantChunks)}.
              </p>
            ) : null}
          </div>
        </Card>
      </div>
    </>
  );
}
