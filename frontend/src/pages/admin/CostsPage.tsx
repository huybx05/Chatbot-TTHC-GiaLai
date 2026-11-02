import { useEffect, useState } from "react";

import { getAdminCostSummary, type AdminCostSummary } from "../../api/admin";
import { ApiError } from "../../api/http";
import { Card, Icon, PageHeader, toneClass, type BadgeTone } from "./shared.tsx";

function formatNumber(value: number) {
  return value.toLocaleString("vi-VN");
}

function formatUsd(value: number) {
  const digits = value > 0 && value < 0.01 ? 6 : 4;
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function statusMeta(status: AdminCostSummary["status"]): { label: string; tone: BadgeTone } {
  switch (status) {
    case "over":
      return { label: "Đã vượt ngân sách", tone: "bad" };
    case "warning":
      return { label: "Sắp chạm ngân sách", tone: "warn" };
    case "notice":
      return { label: "Đã dùng một nửa", tone: "info" };
    default:
      return { label: "Trong ngân sách", tone: "ok" };
  }
}

function modelLabel(model: string) {
  return (
    {
      "deepseek-v4.1-flash": "DeepSeek Flash",
      "qwen3.7-flash": "Qwen3.7 Flash",
      "qwen3.7-text-embedding": "Qwen Embedding",
      "qwen3-rerank": "Qwen Rerank",
    }[model] ?? model
  );
}

function formatRate(value: number) {
  return `$${value.toLocaleString("vi-VN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })}/M`;
}

function PriceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-base">
      <span className="text-text-secondary">{label}</span>
      <span className="font-semibold tabular-nums text-text-primary">{value}</span>
    </div>
  );
}

export default function CostsPage() {
  const [data, setData] = useState<AdminCostSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await getAdminCostSummary());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được dữ liệu chi phí.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const meta = statusMeta(data?.status ?? "normal");
  const percent = Math.min(100, Math.max(0, data?.percent ?? 0));
  const tokens = (data?.tokens.input ?? 0) + (data?.tokens.output ?? 0);

  return (
    <>
      <PageHeader
        eyebrow="Theo dõi chi phí sử dụng AI"
        title="Chi phí sử dụng AI"
        description="Theo dõi chi phí sử dụng mô hình LLM, embedding và reranking trong hệ thống."
      />

      <div className="mb-4 flex items-center justify-between gap-3">
        <span
          className={`inline-flex items-center rounded-full border px-3 py-1.5 text-base font-semibold ${toneClass(meta.tone)}`}
        >
          {meta.label}
        </span>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-lg border border-border-color px-3 py-2 text-base font-semibold text-text-secondary hover:bg-secondary-surface disabled:opacity-50"
        >
          <Icon name="refresh" className="text-[18px]" />
          Làm mới
        </button>
      </div>

      {error ? <Card className="mb-4 border-danger/30 bg-danger-surface text-danger">{error}</Card> : null}

      {loading && !data ? (
        <Card className="text-base text-text-secondary">Đang tải chi phí...</Card>
      ) : null}

      {data ? (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-base text-text-secondary">Đã dùng tháng này</p>
                <p className="mt-1 text-4xl font-bold tracking-tight">{formatUsd(data.spent_usd)}</p>
              </div>
              <div className="text-right text-base text-text-secondary">
                <p>Ngân sách tháng: {formatUsd(data.budget_usd)}</p>
                <p className="mt-1">
                  Ngân sách còn lại: <strong className="text-text-primary">{formatUsd(data.remaining_usd)}</strong>
                </p>
              </div>
            </div>

            <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-secondary-surface">
              <div
                className={`h-full rounded-full ${
                  data.status === "over"
                    ? "bg-danger"
                    : data.status === "warning"
                      ? "bg-[#C58A00]"
                      : "bg-primary"
                }`}
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className="mt-2 flex flex-wrap justify-between gap-2 text-base text-text-secondary">
              <span>{percent.toFixed(2)}% ngân sách</span>
              <span>Cảnh báo ở 80% · không tự dừng khi vượt ngưỡng</span>
            </div>
          </Card>

          <div className="grid gap-3 sm:grid-cols-3">
            <Card>
              <p className="text-base font-semibold uppercase text-text-secondary">Hôm nay</p>
              <p className="mt-2 text-2xl font-bold">{formatUsd(data.today_usd)}</p>
              <p className="mt-1 text-base text-text-secondary">{formatNumber(data.today_calls)} lượt gọi</p>
            </Card>
            <Card>
              <p className="text-base font-semibold uppercase text-text-secondary">Tháng này</p>
              <p className="mt-2 text-2xl font-bold">{formatNumber(data.month_calls)}</p>
              <p className="mt-1 text-base text-text-secondary">lượt gọi model</p>
            </Card>
            <Card>
              <p className="text-base font-semibold uppercase text-text-secondary">Token</p>
              <p className="mt-2 text-2xl font-bold">{formatNumber(tokens)}</p>
              <p className="mt-1 text-base text-text-secondary">
                {formatNumber(data.tokens.input)} vào · {formatNumber(data.tokens.output)} ra
              </p>
            </Card>
          </div>

          <Card>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-lg font-bold">Theo model</h3>
              <span className="text-base text-text-secondary">{data.by_model.length} model</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-base">
                <thead className="border-b border-border-color text-base uppercase text-text-secondary">
                  <tr>
                    <th className="pb-3 pr-4">Model</th>
                    <th className="pb-3 pr-4 text-right">Token</th>
                    <th className="pb-3 pr-4 text-right">Lượt gọi</th>
                    <th className="pb-3 text-right">Chi phí</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-color">
                  {data.by_model.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-text-secondary">
                        Chưa có lượt gọi nào trong tháng.
                      </td>
                    </tr>
                  ) : (
                    data.by_model.map((item) => (
                      <tr key={item.model}>
                        <td className="py-4 pr-4 font-semibold">{modelLabel(item.model)}</td>
                        <td className="py-4 pr-4 text-right tabular-nums font-semibold text-base">
                          {formatNumber(
                            item.input_tokens +
                              item.output_tokens +
                              item.embedding_tokens +
                              item.rerank_tokens,
                          )}
                        </td>
                        <td className="py-4 pr-4 text-right">{formatNumber(item.calls)}</td>
                        <td className="py-4 text-right font-semibold">{formatUsd(item.cost_usd)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h3 className="text-lg font-bold">Gần đây</h3>
            <div className="mt-3 space-y-3">
              {data.recent.length === 0 ? (
                <p className="text-base text-text-secondary">Chưa có lượt gọi nào.</p>
              ) : (
                data.recent.slice(0, 10).map((item, index) => (
                  <div
                    key={`${item.occurred_at}-${index}`}
                    className="flex items-center justify-between gap-3 text-base"
                  >
                    <span className="font-medium text-text-primary">{modelLabel(item.model)}</span>
                    <span className="shrink-0 tabular-nums font-semibold">{formatUsd(item.cost_usd)}</span>
                  </div>
                ))
              )}
            </div>
          </Card>

          <details className="rounded-xl border border-border-color bg-card-surface p-4 text-base">
            <summary className="cursor-pointer font-semibold">
              Bảng giá đang áp dụng
              <span className="ml-2 font-normal text-text-secondary">USD / 1 triệu token</span>
            </summary>
            <div className="mt-4 space-y-3 text-text-secondary">
              {data.pricing.map((price) => (
                <div key={price.model_key} className="rounded-lg border border-border-color p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-text-primary">{price.display_name}</span>
                    <span className="text-base text-text-secondary">
                      {price.kind === "llm" ? "Theo token" : price.kind === "embedding" ? "Embedding" : "Rerank"}
                    </span>
                  </div>

                  {price.input_tiers.length > 0 ? (
                    <div className="mt-3 space-y-3">
                      <div className="hidden grid-cols-[1fr_1fr_1fr] gap-3 px-1 text-base font-medium uppercase text-text-secondary sm:grid">
                        <span>Độ dài input</span>
                        <span>Giá vào</span>
                        <span>Giá ra</span>
                      </div>
                      {price.input_tiers.map((tier) => (
                        <div
                          key={String(tier.max_input_tokens)}
                          className="grid grid-cols-1 gap-1 border-t border-border-color px-1 pt-2 text-base sm:grid-cols-[1fr_1fr_1fr] sm:gap-3"
                        >
                          <span className="text-text-secondary">
                            ≤ {formatNumber(tier.max_input_tokens ?? 0)} token
                          </span>
                          <span>
                            <span className="text-text-secondary sm:hidden">Vào: </span>
                            <span className="font-semibold tabular-nums text-text-primary">
                              {formatRate(tier.input_per_m)}
                            </span>
                          </span>
                          <span>
                            <span className="text-text-secondary sm:hidden">Ra: </span>
                            <span className="font-semibold tabular-nums text-text-primary">
                              {formatRate(tier.output_per_m)}
                            </span>
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 grid gap-x-8 gap-y-1 sm:grid-cols-2">
                      {price.input_cache_hit_per_m !== null ? (
                        <PriceRow label="Input cache hit" value={formatRate(price.input_cache_hit_per_m)} />
                      ) : null}
                      {price.input_cache_miss_per_m !== null ? (
                        <PriceRow label="Input cache miss" value={formatRate(price.input_cache_miss_per_m)} />
                      ) : null}
                      {price.output_per_m !== null ? (
                        <PriceRow label="Output" value={formatRate(price.output_per_m)} />
                      ) : null}
                      {price.embedding_per_m !== null ? (
                        <PriceRow label="Embedding" value={formatRate(price.embedding_per_m)} />
                      ) : null}
                      {price.rerank_per_m !== null ? (
                        <PriceRow label="Rerank" value={formatRate(price.rerank_per_m)} />
                      ) : null}
                    </div>
                  )}

                  {price.peak_multiplier !== 1 ? (
                    <p className="mt-3 rounded-md bg-[#FFF8E8] px-3 py-2 text-base text-[#7A5200]">
                      Giờ cao điểm ×{price.peak_multiplier} ·{" "}
                      {price.peak_windows.map((window) => `${window.start}–${window.end}`).join(", ")}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </details>
        </div>
      ) : null}
    </>
  );
}
