import { useEffect, useState } from "react";

import { getAdminSystemStatus, type AdminSystemStatus, type ServiceStatus } from "../../api/admin";
import { Badge, Card, Icon, PageHeader, SectionTitle, type BadgeTone } from "./shared.tsx";

function serviceTone(service?: ServiceStatus): BadgeTone {
  return service?.ready ? "ok" : "bad";
}

function serviceLabel(service?: ServiceStatus) {
  return service?.ready ? "Online" : "Offline";
}

function formatNumber(value?: number) {
  return typeof value === "number" ? value.toLocaleString("vi-VN") : "-";
}

export default function OverviewPage() {
  const [status, setStatus] = useState<AdminSystemStatus | null>(null);

  useEffect(() => {
    getAdminSystemStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const pg = status?.services.postgresql;
  const api = status?.services.api;
  const neo4j = status?.services.neo4j;
  const es = status?.services.elasticsearch;
  const qdrant = status?.services.qdrant;
  const qdrantSemantic = qdrant?.collections?.semantic;
  const qdrantFaq = qdrant?.collections?.faq;

  const services = [
    ["api", "API", api],
    ["database", "PostgreSQL", pg],
    ["hub", "Neo4j", neo4j],
    ["search", "Elasticsearch", es],
    ["scatter_plot", "Qdrant", qdrant],
  ] as const;

  const storeMetrics = [
    ["folder_open", "Thủ tục hành chính", formatNumber(pg?.counts?.procedures), "PostgreSQL", serviceTone(pg)],
    ["database", "Chunk", formatNumber(pg?.counts?.sections), "PostgreSQL", serviceTone(pg)],
    ["quiz", "FAQ", formatNumber(pg?.counts?.faq), "PostgreSQL", serviceTone(pg)],
    ["hub", "Node / quan hệ", `${formatNumber(neo4j?.counts?.nodes)} / ${formatNumber(neo4j?.counts?.relationships)}`, "Neo4j", serviceTone(neo4j)],
    ["search", "Tài liệu tìm kiếm", formatNumber(es?.documents), "Elasticsearch", es?.ready && es.exists ? "ok" : "bad"],
    ["scatter_plot", "Vector chunk / FAQ", `${formatNumber(qdrantSemantic?.points)} / ${formatNumber(qdrantFaq?.points)}`, "Qdrant", qdrant?.ready ? "ok" : "bad"],
  ] as const;

  return (
    <>
      <PageHeader
        eyebrow="Tổng quan"
        title="Bảng điều khiển hệ thống"
        description="Theo dõi trạng thái dịch vụ, dữ liệu đã lưu trữ và hoạt động sử dụng chatbot."
      />

      <div className="mt-4">
        <Card>
          <SectionTitle title="Trạng thái hệ thống" note="Kiểm tra trực tiếp từ API quản trị khi mở trang." />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {services.map(([icon, label, service]) => (
              <div key={label} className="flex items-center justify-between gap-3 rounded-lg border border-border-color bg-secondary-surface px-4 py-3">
                <div className="flex items-center gap-3">
                  <Icon name={icon} className="text-[22px] text-primary" />
                  <span className="text-sm font-bold">{label}</span>
                </div>
                <Badge tone={serviceTone(service)}>{serviceLabel(service)}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <Card>
          <SectionTitle title="Số lượng dữ liệu trong kho lưu trữ" note="Số liệu thực tế từ các dịch vụ dữ liệu đang kết nối." />
          <div className="grid gap-3 sm:grid-cols-2">
            {storeMetrics.map(([icon, label, value, store, tone]) => (
              <div key={label} className="flex items-start justify-between gap-3 rounded-lg border border-border-color bg-secondary-surface px-4 py-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
                  <p className="mt-1 text-2xl font-bold">{value}</p>
                  <p className="mt-1 text-xs text-text-secondary">{store}</p>
                </div>
                <div className={`flex size-9 items-center justify-center rounded-lg border ${tone === "ok" ? "bg-[#E7F4EC] text-[#2E7D4F] border-[#B8DDC6]" : "bg-danger-surface text-danger border-[#E6B8B2]"}`}>
                  <Icon name={icon} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle title="Hoạt động chatbot" note="Sẽ hiển thị khi hệ thống bắt đầu ghi nhận log sử dụng." />
          <div className="space-y-3">
            {[
              ["forum", "Tổng số câu hỏi"],
              ["visibility", "Lượt truy cập chatbot"],
            ].map(([icon, label]) => (
              <div key={label} className="flex items-center justify-between rounded-lg border border-border-color bg-secondary-surface px-4 py-3">
                <div>
                  <p className="text-sm font-bold">{label}</p>
                  <p className="mt-1 text-xs text-text-secondary">Chưa có dữ liệu</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold">-</span>
                  <Icon name={icon} className="text-[22px] text-text-secondary" />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
