import { Badge, Card, Icon, MetricCard, PageHeader, type BadgeTone } from "./shared.tsx";

type ModelUsage = {
  model: string;
  purpose: string;
  inputTokens: number;
  outputTokens: number;
  requests: number;
  cost: number;
  tone: BadgeTone;
};

const MODEL_USAGE: ModelUsage[] = [
  {
    model: "qwen3.7-flash",
    purpose: "LLM router",
    inputTokens: 432_180,
    outputTokens: 94_620,
    requests: 355,
    cost: 1.46,
    tone: "warn",
  },
  {
    model: "deepseek-flash",
    purpose: "LLM response",
    inputTokens: 432_180,
    outputTokens: 94_620,
    requests: 355,
    cost: 1.46,
    tone: "warn",
  },
  {
    model: "qwen3.7-text-embedding",
    purpose: "Embedding chunk & FAQ",
    inputTokens: 1_864_220,
    outputTokens: 0,
    requests: 3_152,
    cost: 0.82,
    tone: "info",
  },
  {
    model: "qwen3-rerank",
    purpose: "Cổng duyệt ngữ cảnh",
    inputTokens: 278_640,
    outputTokens: 126_430,
    requests: 814,
    cost: 1.54,
    tone: "ok",
  },
];

const TOTAL_INPUT = MODEL_USAGE.reduce((sum, item) => sum + item.inputTokens, 0);
const TOTAL_OUTPUT = MODEL_USAGE.reduce((sum, item) => sum + item.outputTokens, 0);
const TOTAL_COST = MODEL_USAGE.reduce((sum, item) => sum + item.cost, 0);
const TOTAL_REQUESTS = MODEL_USAGE.reduce((sum, item) => sum + item.requests, 0);

function formatNumber(value: number) {
  return value.toLocaleString("vi-VN");
}

function formatUsd(value: number) {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(value);
}

export default function CostsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Quản lý chi phí"
        title="Token và chi phí mô hình"
        description="Theo dõi token đầu vào, đầu ra, số lượt gọi và chi phí ước tính theo từng model."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge tone="muted">Dữ liệu mô phỏng</Badge>
        <span className="text-sm text-text-secondary">30 ngày gần nhất</span>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon="token" label="Tổng token" value={formatNumber(TOTAL_INPUT + TOTAL_OUTPUT)} note="Input + output" tone="info" />
        <MetricCard icon="input" label="Input token" value={formatNumber(TOTAL_INPUT)} note="Prompt, context, embedding" tone="info" />
        <MetricCard icon="output" label="Output token" value={formatNumber(TOTAL_OUTPUT)} note="FAQ và câu trả lời" tone="ok" />
        <MetricCard icon="payments" label="Chi phí ước tính" value={formatUsd(TOTAL_COST)} note={`${formatNumber(TOTAL_REQUESTS)} lượt gọi`} tone="warn" />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 className="font-bold">Chi tiết theo model</h3>
              <p className="mt-1 text-sm text-text-secondary">Token và chi phí được cộng dồn theo lần gọi model.</p>
            </div>
            <Badge tone="info">{`${MODEL_USAGE.length} model`}</Badge>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-border-color text-xs uppercase text-text-secondary">
                <tr>
                  <th className="pb-3 pr-4">Model</th>
                  <th className="pb-3 pr-4">Mục đích</th>
                  <th className="pb-3 pr-4 text-right">Input</th>
                  <th className="pb-3 pr-4 text-right">Output</th>
                  <th className="pb-3 pr-4 text-right">Lượt gọi</th>
                  <th className="pb-3 text-right">Chi phí</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color">
                {MODEL_USAGE.map((item) => (
                  <tr key={item.model} className="hover:bg-secondary-surface">
                    <td className="py-3 pr-4 font-bold">{item.model}</td>
                    <td className="py-3 pr-4 text-text-secondary">{item.purpose}</td>
                    <td className="py-3 pr-4 text-right font-mono text-xs">{formatNumber(item.inputTokens)}</td>
                    <td className="py-3 pr-4 text-right font-mono text-xs">{item.outputTokens ? formatNumber(item.outputTokens) : "—"}</td>
                    <td className="py-3 pr-4 text-right">{formatNumber(item.requests)}</td>
                    <td className="py-3 text-right font-bold">{formatUsd(item.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h3 className="font-bold">Tỷ trọng chi phí</h3>
          <p className="mt-1 text-sm text-text-secondary">Phân bổ chi phí theo model trong kỳ.</p>

          <div className="mt-5 space-y-4">
            {MODEL_USAGE.map((item) => {
              const ratio = Math.round((item.cost / TOTAL_COST) * 100);
              return (
                <div key={item.model}>
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-semibold">{item.model}</span>
                    <span className="text-text-secondary">{`${ratio}% · ${formatUsd(item.cost)}`}</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary-surface">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${ratio}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6 border-t border-border-color pt-4">
            <div className="flex items-center gap-2 text-sm text-text-secondary">
              <Icon name="info" className="text-[18px] text-primary" />
              <span>Đơn giá được tính theo model và loại token.</span>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
