import { useEffect, useState } from "react";

import { getAdminSystemStatus, type AdminSystemStatus, type ServiceStatus } from "../../api/admin";
import { Badge, Card, Icon, MetricCard, PageHeader, Progress, SectionTitle, type BadgeTone } from "./shared.tsx";

function serviceTone(service?: ServiceStatus): BadgeTone {
  return service?.ready ? "ok" : "bad";
}

function serviceLabel(service?: ServiceStatus) {
  return service?.ready ? "Online" : "Offline";
}

function formatNumber(value?: number) {
  return typeof value === "number" ? value.toLocaleString("vi-VN") : "0";
}

export default function OverviewPage() {
  const [status, setStatus] = useState<AdminSystemStatus | null>(null);

  useEffect(() => {
    getAdminSystemStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const pg = status?.services.postgresql;
  const neo4j = status?.services.neo4j;
  const es = status?.services.elasticsearch;
  const qdrant = status?.services.qdrant;
  const qdrantSemantic = qdrant?.collections?.semantic;
  const qdrantFaq = qdrant?.collections?.faq;

  const stores = [
    ["database", "PostgreSQL", serviceLabel(pg), `${formatNumber(pg?.counts?.procedures)} thủ tục · ${formatNumber(pg?.counts?.sections)} chunk · ${formatNumber(pg?.counts?.faq)} FAQ`, serviceTone(pg)],
    ["hub", "Neo4j", serviceLabel(neo4j), `${formatNumber(neo4j?.counts?.nodes)} node · ${formatNumber(neo4j?.counts?.relationships)} relationship`, serviceTone(neo4j)],
    ["search", "Elasticsearch", es?.ready && es.exists ? "Đã index" : serviceLabel(es), `${es?.index ?? "index"} · ${formatNumber(es?.documents)} document`, es?.ready && es.exists ? "ok" : serviceTone(es)],
    ["scatter_plot", "Qdrant", qdrant?.ready ? "Online" : "Offline", `${qdrantSemantic?.name ?? "semantic"}: ${formatNumber(qdrantSemantic?.points)} · ${qdrantFaq?.name ?? "faq"}: ${formatNumber(qdrantFaq?.points)}`, serviceTone(qdrant)],
  ] as const;

  return (
    <>
      <PageHeader
        eyebrow="Tổng quan"
        title="Bảng điều khiển hệ thống"
        description="Một màn hình để biết dữ liệu đã vào đâu, phần nào sẵn sàng, phần nào chưa chạy và chỗ nào cần xử lý tiếp."
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {stores.map(([icon, label, status, note, tone]) => (
          <Card key={label}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold">{label}</p>
                <p className="mt-1 text-xs text-text-secondary">{note}</p>
              </div>
              <Icon name={icon} className="text-[24px] text-primary" />
            </div>
            <div className="mt-3">
              <Badge tone={tone}>{status}</Badge>
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard icon="folder_open" label="TTHC" value={formatNumber(pg?.counts?.procedures)} note="Từ PostgreSQL" tone={serviceTone(pg)} />
        <MetricCard icon="database" label="Chunk" value={formatNumber(pg?.counts?.sections)} note="procedure_sections" tone={serviceTone(pg)} />
        <MetricCard icon="hub" label="Neo4j graph" value={formatNumber(neo4j?.counts?.relationships)} note="relationship" tone={serviceTone(neo4j)} />
        <MetricCard icon="search" label="Elasticsearch" value={formatNumber(es?.documents)} note="document đã index" tone={es?.ready && es.exists ? "ok" : "bad"} />
        <MetricCard icon="quiz" label="Q/A cache" value={formatNumber(qdrantFaq?.points)} note="vector FAQ trong Qdrant" tone={qdrantFaq?.exists ? "ok" : "bad"} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_0.9fr]">
        <Card>
          <SectionTitle title="Tiến độ kết nối dữ liệu" note="PostgreSQL, Neo4j, Elasticsearch và Qdrant đã có dữ liệu test để kiểm tra retrieval." />
          <div className="space-y-3">
            {[
              ["Nạp PostgreSQL", pg?.ready ? 100 : 0, `${formatNumber(pg?.counts?.procedures)} thủ tục`],
              ["Nạp Neo4j", neo4j?.ready ? 100 : 0, `${formatNumber(neo4j?.counts?.nodes)} node`],
              ["Sinh chunk", pg?.counts?.sections ? 100 : 0, `${formatNumber(pg?.counts?.sections)} chunk`],
              ["Index Elasticsearch", es?.ready && es.exists ? 100 : 0, `${formatNumber(es?.documents)} document`],
              ["Index Qdrant", qdrant?.ready && qdrantSemantic?.exists ? 100 : 0, `${formatNumber(qdrantSemantic?.points)} chunk vector · ${formatNumber(qdrantFaq?.points)} FAQ vector`],
            ].map(([label, value, note]) => (
              <div key={label as string}>
                <div className="mb-1 flex justify-between gap-3 text-sm">
                  <span className="font-semibold">{label}</span>
                  <span className="text-right text-text-secondary">{note}</span>
                </div>
                <Progress value={Number(value)} />
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle title="Việc nên làm tiếp" note="Các bước này phục vụ trực tiếp cho monitor v1." />
          <div className="space-y-3">
            {[
              ["1", "Smoke test Elasticsearch", "Tìm theo mã thủ tục, tên giấy tờ, cơ quan, căn cứ pháp lý."],
              ["2", "Smoke test Qdrant", "Tìm semantic trên chunk và FAQ ready."],
              ["3", "Ghép hybrid retrieval", "Gộp ES + Qdrant, sau đó kiểm tra citation trước khi nối chatbot."],
            ].map(([step, title, note]) => (
              <div key={step} className="flex gap-3 rounded-lg border border-border-color bg-secondary-surface p-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">{step}</span>
                <div>
                  <p className="text-sm font-bold">{title}</p>
                  <p className="mt-1 text-xs text-text-secondary">{note}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
