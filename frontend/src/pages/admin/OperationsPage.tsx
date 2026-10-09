import { useEffect, useState } from "react";

import { getAdminSystemStatus, type AdminSystemStatus, type ServiceStatus } from "../../api/admin";
import { Badge, Card, PageHeader, SectionTitle, logs, statusTone } from "./shared.tsx";

const pipelineRows = [
  ["Đọc JSON normalized", "Thành công", "data_test", "Nguồn chuẩn"],
  ["Nạp PostgreSQL", "Thành công", "procedures + sections", "Có thể visualize"],
  ["Nạp Neo4j", "Thành công", "12 relationship", "Có thể visualize"],
  ["Sinh chunk", "Thành công", "procedure_sections", "Đã có chunk để truy xuất"],
  ["Index Elasticsearch", "Thành công", "chunk text", "Sẵn sàng keyword search"],
  ["Index Qdrant", "Thành công", "chunk + FAQ vectors", "Sẵn sàng semantic search"],
];

function serviceStatus(service?: ServiceStatus) {
  return service?.ready ? "Online" : "Offline";
}

function count(value?: number) {
  return typeof value === "number" ? value.toLocaleString("vi-VN") : "0";
}

export default function OperationsPage() {
  const [status, setStatus] = useState<AdminSystemStatus | null>(null);

  useEffect(() => {
    getAdminSystemStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const pg = status?.services.postgresql;
  const neo4j = status?.services.neo4j;
  const es = status?.services.elasticsearch;
  const qdrant = status?.services.qdrant;
  const semantic = qdrant?.collections?.semantic;
  const faq = qdrant?.collections?.faq;

  const configs = [
    ["Backend API", "http://localhost:8000", "Online"],
    ["PostgreSQL", `${count(pg?.counts?.procedures)} thủ tục · ${count(pg?.counts?.sections)} chunk`, serviceStatus(pg)],
    ["Neo4j", `${count(neo4j?.counts?.nodes)} node · ${count(neo4j?.counts?.relationships)} relationship`, serviceStatus(neo4j)],
    ["Elasticsearch", `${es?.index ?? "index"} · ${count(es?.documents)} document`, es?.ready && es.exists ? "Online" : "Offline"],
    ["Qdrant", `${semantic?.name ?? "semantic"}: ${count(semantic?.points)} · ${faq?.name ?? "faq"}: ${count(faq?.points)}`, serviceStatus(qdrant)],
  ];

  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Pipeline, cấu hình và log hệ thống"
        description="Gom các thông tin vận hành vào một nơi: bước dữ liệu nào đã chạy, kho nào sẵn sàng, log nào cần xử lý."
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card>
          <SectionTitle title="Pipeline hiện tại" note="Phản ánh đúng trạng thái: PostgreSQL, Neo4j, Elasticsearch và Qdrant đã có dữ liệu test." />
          <div className="space-y-3">
            {pipelineRows.map(([name, status, count, note], index) => (
              <div key={name} className="grid gap-3 rounded-lg border border-border-color bg-secondary-surface p-3 md:grid-cols-[32px_1fr_120px] md:items-center">
                <div className="flex size-8 items-center justify-center rounded-full bg-card-surface text-sm font-bold text-primary">{index + 1}</div>
                <div>
                  <p className="font-bold">{name}</p>
                  <p className="text-sm text-text-secondary">{count} · {note}</p>
                </div>
                <Badge tone={statusTone(status)}>{status}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle title="Cấu hình kết nối" />
          <div className="space-y-3">
            {configs.map(([name, value, status]) => (
              <div key={name} className="rounded-lg border border-border-color bg-secondary-surface p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-bold">{name}</p>
                  <Badge tone={statusTone(status)}>{status}</Badge>
                </div>
                <p className="mt-1 text-xs text-text-secondary">{value}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <SectionTitle title="Log & cảnh báo" note="V1 chỉ xem nhanh, chưa cần tách thành tab riêng." />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-sm">
            <thead className="border-b border-border-color text-xs uppercase text-text-secondary">
              <tr>
                <th className="py-3 pr-3">Thời gian</th>
                <th className="py-3 pr-3">Mức</th>
                <th className="py-3 pr-3">Module</th>
                <th className="py-3 pr-3">Nội dung</th>
                <th className="py-3 pr-3">Trạng thái</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-color">
              {logs.map(([time, level, module, message, status]) => (
                <tr key={`${time}-${message}`} className="hover:bg-secondary-surface">
                  <td className="py-3 pr-3 font-semibold">{time}</td>
                  <td className="py-3 pr-3"><Badge tone={statusTone(level)}>{level}</Badge></td>
                  <td className="py-3 pr-3 font-bold">{module}</td>
                  <td className="py-3 pr-3 text-text-secondary">{message}</td>
                  <td className="py-3 pr-3"><Badge tone={statusTone(status)}>{status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
