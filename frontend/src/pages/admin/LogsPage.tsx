import { Badge, Card, MetricCard, PageHeader, logs, statusTone } from "./shared.tsx";

export default function LogsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Log lỗi"
        title="Theo dõi lỗi runtime và lỗi tích hợp"
        description="Module mới bổ sung, gom lỗi backend, model, database và pipeline ở một nơi."
      />

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <MetricCard icon="error" label="ERROR" value="1" note="Reranker timeout" tone="bad" />
        <MetricCard icon="warning" label="WARN" value="2" note="Index và graph warning" tone="warn" />
        <MetricCard icon="info" label="INFO" value="1" note="Pipeline done" tone="info" />
        <MetricCard icon="task_alt" label="Đã xử lý" value="2" note="50% log mẫu" tone="ok" />
      </div>

      <Card>
        <div className="mb-4 grid gap-2 md:grid-cols-[1fr_150px_180px]">
          <input className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm outline-primary" placeholder="Tìm message, request_id, procedure_code..." />
          <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm"><option>Mọi severity</option><option>ERROR</option><option>WARN</option></select>
          <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm"><option>Mọi module</option><option>Pipeline</option><option>Reranker</option><option>Database</option></select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-border-color text-xs uppercase text-text-secondary">
              <tr><th className="py-3 pr-3">Thời gian</th><th className="py-3 pr-3">Severity</th><th className="py-3 pr-3">Module</th><th className="py-3 pr-3">Message</th><th className="py-3 pr-3">Trạng thái</th></tr>
            </thead>
            <tbody className="divide-y divide-border-color">
              {logs.map(([time, severity, module, message, status]) => (
                <tr key={`${time}-${module}`} className="hover:bg-secondary-surface">
                  <td className="py-3 pr-3 font-semibold">{time}</td>
                  <td className="py-3 pr-3"><Badge tone={statusTone(severity)}>{severity}</Badge></td>
                  <td className="py-3 pr-3 font-semibold">{module}</td>
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
