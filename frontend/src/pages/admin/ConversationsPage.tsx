import { useEffect, useMemo, useState } from "react";

import {
  bulkDeleteAdminConversations,
  deleteAdminConversation,
  downloadAdminConversations,
  getAdminConversationIds,
  getAdminConversations,
  type AdminConversation,
  type ConversationExportFilters,
} from "../../api/admin";
import type { BadgeTone } from "./shared.tsx";
import { Badge, Card, Icon, PageHeader } from "./shared.tsx";

type Source =
  | "FAQ"
  | "FAQ toàn cục"
  | "Hybrid"
  | "Fact lookup"
  | "Graph"
  | "Không truy xuất"
  | "Chưa xác định";
type Feedback = "like" | "dislike" | "none";

type ConversationLog = {
  id: string;
  dateGroup: "today" | "yesterday";
  dateLabel?: string;
  createdAt?: string;
  time: string;
  user: string;
  userType: "auth" | "guest";
  session: string;
  question: string;
  answer: string;
  context: string;
  source: Source;
  supportingSources: Source[];
  latency: string;
  ttft?: string;
  totalMs?: number;
  ttftMs?: number;
  feedback: Feedback;
  feedbackReasons?: string[];
  feedbackComment?: string;
  socialIntent?: string;
};

const logs: ConversationLog[] = [
  {
    id: "log-01",
    dateGroup: "today",
    time: "09:42",
    user: "Nguyễn Văn A",
    userType: "auth",
    session: "Cấp lại thẻ Căn cước bị mất",
    question: "Tôi mất CCCD thì cấp lại cần giấy tờ gì và làm ở đâu?",
    answer: "Người dân có thể nộp hồ sơ trực tuyến hoặc trực tiếp tại cơ quan quản lý căn cước. Hồ sơ và nơi tiếp nhận được trả lời theo thủ tục tương ứng trên Cổng DVC.",
    context: "[Hybrid] Thủ tục cấp lại thẻ Căn cước: thành phần hồ sơ, nơi tiếp nhận và thời hạn giải quyết.\n[Fact lookup] Mã thủ tục, cơ quan thực hiện và đường dẫn chi tiết từ PostgreSQL.",
    source: "Hybrid",
    supportingSources: ["Fact lookup"],
    latency: "1.38s",
    ttft: "420ms",
    feedback: "like",
  },
  {
    id: "log-02",
    dateGroup: "today",
    time: "09:44",
    user: "Nguyễn Văn A",
    userType: "auth",
    session: "Cấp lại thẻ Căn cước bị mất",
    question: "Có cần nộp sổ hộ khẩu giấy không?",
    answer: "Không yêu cầu xuất trình sổ hộ khẩu giấy. Người dân làm theo hướng dẫn tại nơi tiếp nhận hồ sơ hoặc trên Cổng DVC.",
    context: "[Fact lookup] Trường thành phần hồ sơ của thủ tục cấp lại thẻ Căn cước; dữ liệu đã chuẩn hoá từ PostgreSQL.",
    source: "Fact lookup",
    supportingSources: [],
    latency: "620ms",
    ttft: "180ms",
    feedback: "none",
  },
  {
    id: "log-03",
    dateGroup: "today",
    time: "08:17",
    user: "Trần Thị B",
    userType: "auth",
    session: "Đăng ký khai sinh liên thông",
    question: "Đăng ký khai sinh cho trẻ dưới 6 tuổi gồm những bước nào?",
    answer: "Câu trả lời được lấy từ FAQ đã duyệt của thủ tục liên thông đăng ký khai sinh, thường trú và cấp thẻ BHYT cho trẻ dưới 6 tuổi.",
    context: "[FAQ] Cặp hỏi đáp đã duyệt về thủ tục 2.002621.\n[Fact lookup] Mã thủ tục và đường dẫn nguồn chính thức.",
    source: "FAQ",
    supportingSources: ["Fact lookup"],
    latency: "94ms",
    ttft: "35ms",
    feedback: "like",
  },
  {
    id: "log-04",
    dateGroup: "yesterday",
    time: "16:03",
    user: "Khách",
    userType: "guest",
    session: "Thủ tục liên quan đến bảo hiểm thất nghiệp",
    question: "Thủ tục điều chỉnh đóng BHXH có liên quan tới thủ tục bảo hiểm thất nghiệp không?",
    answer: "Hệ thống kiểm tra quan hệ thủ tục trên Neo4j và đối chiếu thêm các chunk liên quan. Kết quả chỉ nêu các quan hệ hiện có trong dữ liệu.",
    context: "[Graph] Các node thủ tục, lĩnh vực và quan hệ liên quan trong Neo4j.\n[Hybrid] Chunk thông tin chung và thủ tục liên thông để kiểm chứng.",
    source: "Graph",
    supportingSources: ["Hybrid"],
    latency: "1.02s",
    ttft: "300ms",
    feedback: "dislike",
    feedbackReasons: ["Không chính xác hoặc chưa đầy đủ", "Nguồn tham khảo không phù hợp"],
    feedbackComment: "Câu trả lời chưa nêu rõ thủ tục nào liên quan.",
  },
  {
    id: "log-05",
    dateGroup: "yesterday",
    time: "11:25",
    user: "Khách",
    userType: "guest",
    session: "Chào hỏi và cảm ơn",
    question: "Xin chào, bạn giúp tôi tra cứu thủ tục được không?",
    answer: "Tôi có thể hỗ trợ tra cứu hồ sơ, trình tự thực hiện, cơ quan giải quyết, thời hạn và lệ phí của thủ tục hành chính.",
    context: "Không dùng kho dữ liệu: hệ thống nhận diện câu chào hỏi và trả lời trực tiếp.",
    source: "Không truy xuất",
    supportingSources: [],
    latency: "210ms",
    ttft: "80ms",
    feedback: "like",
    socialIntent: "greeting",
  },
];

function sourceTone(source: Source): BadgeTone {
  if (source === "Hybrid") return "ok";
  if (source === "FAQ toàn cục") return "ok";
  if (source === "Graph") return "warn";
  if (source === "Không truy xuất") return "muted";
  if (source === "Chưa xác định") return "muted";
  return "info";
}

function feedbackLabel(feedback: Feedback) {
  return { like: "Hữu ích", dislike: "Không hữu ích", none: "Chưa đánh giá" }[feedback];
}

function feedbackTone(feedback: Feedback): BadgeTone {
  return feedback === "like" ? "ok" : feedback === "dislike" ? "bad" : "muted";
}

const SOCIAL_LABELS: Record<string, string> = {
  greeting: "Chào hỏi",
  thanks: "Cảm ơn",
  goodbye: "Tạm biệt",
  acknowledgement: "Xác nhận",
  other: "Xã giao",
};

function userLabel(log: ConversationLog) {
  return log.userType === "guest" ? "Khách" : log.user;
}

function normalizeSource(value: string): Source {
  const labels: Record<string, Source> = {
    faq: "FAQ",
    faq_global: "FAQ toàn cục",
    hybrid: "Hybrid",
    fact_lookup: "Fact lookup",
    graph: "Graph",
    direct: "Không truy xuất",
    none: "Không truy xuất",
    "": "Chưa xác định",
    FAQ: "FAQ",
    "FAQ toàn cục": "FAQ toàn cục",
    Hybrid: "Hybrid",
    "Fact lookup": "Fact lookup",
    Graph: "Graph",
    "Không truy xuất": "Không truy xuất",
    "Chưa xác định": "Chưa xác định",
  };
  return labels[value] ?? "Chưa xác định";
}

function formatDuration(ms: number | null | undefined): string {
  if (typeof ms !== "number" || !Number.isFinite(ms)) return "—";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

function toConversationLog(item: AdminConversation): ConversationLog {
  const created = new Date(item.created_at);
  const today = new Date();
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  const dateGroup = sameDay(created, today) ? "today" : "yesterday";
  const dateLabel = Number.isNaN(created.getTime())
    ? item.created_at
    : new Intl.DateTimeFormat("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }).format(created);
  const feedback = item.feedback?.value;
  return {
    id: item.id,
    dateGroup,
    dateLabel,
    createdAt: item.created_at,
    time: Number.isNaN(created.getTime())
      ? "--:--"
      : created.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
    user: item.user_name || "Khách",
    userType: item.user_type,
    session: item.session_title,
    question: item.question,
    answer: item.answer,
    context: "",
    source: normalizeSource(item.source),
    supportingSources: [],
    latency: formatDuration(item.total_ms),
    ttft: formatDuration(item.ttft_ms),
    totalMs: typeof item.total_ms === "number" ? item.total_ms : undefined,
    ttftMs: typeof item.ttft_ms === "number" ? item.ttft_ms : undefined,
    feedback: feedback === "like" || feedback === "dislike" ? feedback : "none",
    feedbackReasons: Array.isArray(item.feedback?.reasons)
      ? item.feedback.reasons.filter((reason): reason is string => typeof reason === "string")
      : [],
    feedbackComment: typeof item.feedback?.comment === "string" ? item.feedback.comment : "",
    socialIntent: item.social_intent,
  };
}

export default function ConversationsPage() {
  const [items, setItems] = useState<ConversationLog[]>(logs);
  const [usingMock, setUsingMock] = useState(true);
  const [dateRange, setDateRange] = useState<ConversationExportFilters["dateRange"]>("today");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [feedbackFilter, setFeedbackFilter] = useState<ConversationExportFilters["feedback"]>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize] = useState(50);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selectedLog, setSelectedLog] = useState<ConversationLog | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [selectAllBusy, setSelectAllBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [exportError, setExportError] = useState("");
  const [isExporting, setIsExporting] = useState(false);

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const handleSelectAll = async () => {
    if (allFilteredSelected) {
      setSelectedIds(new Set());
      return;
    }
    if (usingMock) {
      setSelectedIds(new Set(filteredLogs.map((log) => log.id)));
      return;
    }
    setSelectAllBusy(true);
    setActionError("");
    try {
      const response = await getAdminConversationIds({
        dateRange,
        source: sourceFilter,
        feedback: feedbackFilter,
        search,
      });
      setSelectedIds(new Set(response.ids));
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Không lấy được danh sách để chọn tất cả.",
      );
    } finally {
      setSelectAllBusy(false);
    }
  };

  const handleDelete = async (log: ConversationLog) => {
    const ok = window.confirm("Xoá câu hỏi và câu trả lời này khỏi log hội thoại?");
    if (!ok) return;
    setActionError("");
    if (!usingMock) {
      try {
        await deleteAdminConversation(log.id);
      } catch {
        setActionError("Không xoá được lượt hỏi đáp. Vui lòng thử lại.");
        return;
      }
    }
    setItems((current) => current.filter((item) => item.id !== log.id));
    if (!usingMock) setTotal((current) => Math.max(0, current - 1));
    setSelectedIds((current) => {
      const next = new Set(current);
      next.delete(log.id);
      return next;
    });
    setSelectedLog((current) => (current?.id === log.id ? null : current));
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (
      !window.confirm(
        `Xoá ${selectedIds.size} lượt hỏi đáp đã chọn? Thao tác này không thể hoàn tác.`,
      )
    ) {
      return;
    }

    setActionError("");
    setNotice("");
    setBulkBusy(true);
    const ids = [...selectedIds];

    if (!usingMock) {
      try {
        await bulkDeleteAdminConversations(ids);
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : "Không xoá được các lượt đã chọn.",
        );
        setBulkBusy(false);
        return;
      }
    }

    const deletedIds = new Set(ids);
    setItems((current) => current.filter((item) => !deletedIds.has(item.id)));
    setTotal((current) => Math.max(0, current - ids.length));
    setSelectedIds(new Set());
    setSelectedLog((current) =>
      current && deletedIds.has(current.id) ? null : current,
    );
    setNotice(`Đã xoá ${ids.length} lượt hỏi đáp.`);
    setBulkBusy(false);
  };

  const handleExport = async () => {
    if (usingMock) {
      setExportError("Chỉ có thể xuất khi đã kết nối được dữ liệu lịch sử thực tế.");
      return;
    }
    setExportError("");
    setIsExporting(true);
    try {
      await downloadAdminConversations({ dateRange, source: sourceFilter, feedback: feedbackFilter, search });
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Không thể xuất lịch sử hội thoại.");
    } finally {
      setIsExporting(false);
    }
  };

  useEffect(() => {
    setPage(0);
  }, [dateRange, sourceFilter, feedbackFilter, search]);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      void getAdminConversations({
        offset: page * pageSize,
        limit: pageSize,
        dateRange,
        source: sourceFilter,
        feedback: feedbackFilter,
        search,
      })
        .then((response) => {
          if (cancelled) return;
          setItems(response.items.map(toConversationLog));
          setTotal(response.total);
          setUsingMock(false);
        })
        .catch(() => {
          // Backend chưa sẵn sàng: giữ dữ liệu mẫu để xem giao diện.
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, search.trim() ? 250 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [page, pageSize, dateRange, sourceFilter, feedbackFilter, search]);

  const filteredLogs = useMemo(() => {
    if (!usingMock) return items;
    const query = search.trim().toLocaleLowerCase("vi");
    return items.filter((log) => {
      let matchesDate = true;
      if (dateRange === "today") {
        matchesDate = log.dateGroup === "today";
      } else if (log.createdAt) {
        const created = new Date(log.createdAt);
        if (!Number.isNaN(created.getTime())) {
          const cutoff = new Date();
          cutoff.setHours(0, 0, 0, 0);
          cutoff.setDate(cutoff.getDate() - (dateRange === "7d" ? 6 : 29));
          matchesDate = created >= cutoff;
        }
      }
      const matchesSource = sourceFilter === "all" || log.source === sourceFilter;
      const matchesFeedback =
        feedbackFilter === "all" || log.feedback === feedbackFilter;
      const matchesSearch =
        !query ||
        [log.question, log.session, userLabel(log)].some((value) =>
          value.toLocaleLowerCase("vi").includes(query),
        );
      return matchesDate && matchesSource && matchesFeedback && matchesSearch;
    });
  }, [usingMock, items, dateRange, sourceFilter, feedbackFilter, search]);

  useEffect(() => {
    // Đổi bộ lọc thì bỏ lựa chọn cũ; đổi trang thì giữ lựa chọn
    // để có thể chọn tất cả xuyên trang rồi xoá một lần.
    setSelectedIds(new Set());
    setNotice("");
  }, [dateRange, sourceFilter, feedbackFilter, search]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  useEffect(() => {
    if (page > totalPages - 1) setPage(totalPages - 1);
  }, [page, totalPages]);
  const allFilteredSelected = usingMock
    ? filteredLogs.length > 0 && filteredLogs.every((log) => selectedIds.has(log.id))
    : total > 0 && selectedIds.size >= total;

  const todayQuestions = items.filter((log) => log.dateGroup === "today").length;
  const positiveFeedback = items.filter((log) => log.feedback === "like").length;
  const negativeFeedback = items.filter((log) => log.feedback === "dislike").length;
  const totalSamples = items
    .map((log) => log.totalMs)
    .filter((value): value is number => typeof value === "number");
  const ttftSamples = items
    .map((log) => log.ttftMs)
    .filter((value): value is number => typeof value === "number");
  const averageLatency = totalSamples.length
    ? formatDuration(
        totalSamples.reduce((sum, value) => sum + value, 0) / totalSamples.length,
      )
    : "—";
  const averageTtft = ttftSamples.length
    ? formatDuration(
        ttftSamples.reduce((sum, value) => sum + value, 0) / ttftSamples.length,
      )
    : "—";

  const summaryCards: { label: string; value: number | string; caption?: string }[] = [
    { label: "Câu hỏi hôm nay", value: todayQuestions },
    { label: "Lượt hỏi đáp", value: usingMock ? items.length : total },
    { label: "Đánh giá hữu ích", value: positiveFeedback },
    { label: "Đánh giá Không hữu ích", value: negativeFeedback },
    { label: "Thời gian trung bình hiển thị token đầu tiên (TTFT)", value: averageTtft, caption: "*TTFT: Time to first token" },
    { label: "Thời gian phản hồi trung bình", value: averageLatency, caption: "Thời gian hoàn tất câu trả lời" },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Lịch sử hội thoại"
        title="Theo dõi lịch sử hỏi đáp của người dùng"
        description="Theo dõi câu hỏi, câu trả lời, nguồn truy xuất, thời gian phản hồi và mức độ hài lòng của người dùng."
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {summaryCards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-border-color bg-card-surface px-4 py-3"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              {card.label}
            </p>
            <p className="mt-1 text-xl font-bold text-text-primary">{card.value}</p>
            {card.caption ? (
              <p className="mt-1 text-[11px] leading-4 text-text-secondary">{card.caption}</p>
            ) : null}
          </div>
        ))}
      </div>

      {usingMock ? (
        <p className="mb-3 inline-flex rounded-full border border-border-color bg-secondary-surface px-2 py-0.5 text-xs font-semibold text-text-secondary">
          Dữ liệu mẫu
        </p>
      ) : null}

      <Card>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs font-semibold text-text-secondary">
              <span className="mb-1 block">Khoảng thời gian</span>
              <select
                className="h-9 rounded-lg border border-border-color bg-card-surface px-3 text-sm font-normal text-text-primary"
                value={dateRange}
                onChange={(event) =>
                  setDateRange(event.target.value as ConversationExportFilters["dateRange"])
                }
              >
                <option value="today">Hôm nay</option>
                <option value="7d">7 ngày qua</option>
                <option value="30d">30 ngày qua</option>
              </select>
            </label>

            <label className="text-xs font-semibold text-text-secondary">
              <span className="mb-1 block">Nguồn truy xuất</span>
              <select
                className="h-9 rounded-lg border border-border-color bg-card-surface px-3 text-sm font-normal text-text-primary"
                value={sourceFilter}
                onChange={(event) => setSourceFilter(event.target.value)}
              >
                <option value="all">Tất cả nguồn</option>
                <option value="FAQ">FAQ</option>
                <option value="FAQ toàn cục">FAQ toàn cục</option>
                <option value="Hybrid">Hybrid</option>
                <option value="Fact lookup">Fact lookup</option>
                <option value="Graph">Graph</option>
                <option value="Không truy xuất">Không truy xuất</option>
              </select>
            </label>

            <label className="text-xs font-semibold text-text-secondary">
              <span className="mb-1 block">Đánh giá của người dùng</span>
              <select
                className="h-9 rounded-lg border border-border-color bg-card-surface px-3 text-sm font-normal text-text-primary"
                value={feedbackFilter}
                onChange={(event) =>
                  setFeedbackFilter(event.target.value as ConversationExportFilters["feedback"])
                }
              >
                <option value="all">Tất cả đánh giá</option>
                <option value="like">Hữu ích</option>
                <option value="dislike">Không hữu ích</option>
                <option value="none">Chưa đánh giá</option>
              </select>
            </label>

            <label className="min-w-52 flex-1 text-xs font-semibold text-text-secondary">
              <span className="mb-1 block">Tìm kiếm</span>
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Tìm theo người dùng, nội dung câu hỏi hoặc cuộc hội thoại..."
                className="h-9 w-full rounded-lg border border-border-color bg-card-surface px-3 text-sm font-normal text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
              />
            </label>

            <button
              type="button"
              onClick={() => void handleExport()}
              disabled={isExporting}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-border-color bg-card-surface px-4 text-sm font-bold text-text-primary transition hover:bg-page-bg disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Icon name="download" className="text-[18px]" />
              {isExporting ? "Đang xuất..." : "Xuất Excel"}
            </button>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-color pt-3">
            <div>
              <p className="text-sm text-text-secondary">{filteredLogs.length} lượt hỏi đáp</p>
            </div>
            {selectedIds.size > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-primary">
                  Đã chọn {selectedIds.size}
                </span>
                <button
                  type="button"
                  disabled={bulkBusy}
                  onClick={() => void handleDeleteSelected()}
                  className="rounded-md border border-danger px-2 py-1 text-xs font-bold text-danger hover:bg-danger-surface disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {bulkBusy ? "Đang xoá..." : "Xoá đã chọn"}
                </button>
                <button
                  type="button"
                  disabled={bulkBusy}
                  onClick={() => setSelectedIds(new Set())}
                  className="text-xs font-semibold text-text-secondary underline disabled:opacity-60"
                >
                  Bỏ chọn
                </button>
              </div>
            ) : null}
          </div>

          {actionError ? (
            <p className="text-sm font-semibold text-danger">{actionError}</p>
          ) : null}
          {notice ? <p className="text-sm font-semibold text-green-700">{notice}</p> : null}
          {exportError ? <p className="text-sm font-semibold text-danger">{exportError}</p> : null}

          <div className="overflow-x-auto rounded-lg border border-border-color">
            <table className="w-full min-w-[1000px] text-center text-sm">
              <thead className="border-b border-border-color bg-secondary-surface text-xs uppercase text-text-secondary">
                <tr>
                  <th className="whitespace-nowrap px-4 py-3 text-left font-semibold">
                    <label className="inline-flex items-center gap-2 normal-case">
                      <input
                        type="checkbox"
                        checked={allFilteredSelected}
                        disabled={selectAllBusy || (usingMock ? filteredLogs.length === 0 : total === 0)}
                        onChange={() => void handleSelectAll()}
                        aria-label="Chọn tất cả lượt hỏi đáp theo bộ lọc hiện tại"
                        className="h-4 w-4 accent-primary disabled:opacity-50"
                      />
                      {selectAllBusy ? "Đang chọn..." : "Chọn tất cả"}
                    </label>
                  </th>
                  <th className="px-4 py-3 text-left font-semibold">Thời gian</th>
                  <th className="px-4 py-3 text-left font-semibold">Người dùng</th>
                  <th className="min-w-[300px] py-3 pl-16 pr-4 text-left font-semibold">Nội dung hỏi đáp</th>
                  <th className="px-4 py-3 font-semibold">Nguồn truy xuất</th>
                  <th className="px-4 py-3 font-semibold">Đánh giá</th>
                  <th className="px-4 py-3 text-right font-semibold" title="Thời gian đến token đầu tiên">
                    TTFT
                  </th>
                  <th className="px-4 py-3 text-right font-semibold">Thời gian phản hồi</th>
                  <th className="px-4 py-3 font-semibold">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedLog(log)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        setSelectedLog(log);
                      }
                    }}
                    className="cursor-pointer border-b border-border-color outline-none last:border-0 hover:bg-hover-item focus-visible:bg-primary-soft"
                  >
                    <td className="px-4 py-3 text-left align-middle">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(log.id)}
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                        onChange={() => toggleSelected(log.id)}
                        aria-label={`Chọn lượt hỏi đáp: ${log.question}`}
                        className="h-4 w-4 accent-primary"
                      />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-left align-middle text-text-secondary">
                      {log.dateLabel ?? (log.dateGroup === "today" ? "Hôm nay" : "Hôm qua")}
                      <br />
                      {log.time}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-left align-middle">
                      <p className="font-semibold">{userLabel(log)}</p>
                      <p className="mt-1 text-xs text-text-secondary">
                        {log.userType === "guest" ? "Khách" : "Đăng nhập"}
                      </p>
                    </td>
                    <td className="py-3 pl-16 pr-4 text-left align-middle">
                      <p className="line-clamp-2 font-semibold">{log.question}</p>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <Badge tone={sourceTone(log.source)}>{log.source}</Badge>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <Badge tone={feedbackTone(log.feedback)}>
                        {feedbackLabel(log.feedback)}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right align-middle font-semibold text-text-secondary">
                      {log.ttft ?? "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right align-middle font-semibold">
                      {log.latency}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 align-middle">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDelete(log);
                        }}
                        className="text-sm font-semibold text-danger hover:underline"
                      >
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!usingMock ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-text-secondary">
                Tổng {total} lượt · Trang {page + 1}/{totalPages}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page === 0 || loading}
                  onClick={() => setPage((current) => Math.max(0, current - 1))}
                  className="rounded-md border border-border-color px-3 py-1.5 text-xs font-bold text-text-primary hover:bg-secondary-surface disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Trang trước
                </button>
                <button
                  type="button"
                  disabled={page + 1 >= totalPages || loading}
                  onClick={() => setPage((current) => current + 1)}
                  className="rounded-md border border-border-color px-3 py-1.5 text-xs font-bold text-text-primary hover:bg-secondary-surface disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Trang sau
                </button>
              </div>
            </div>
          ) : null}

          {filteredLogs.length === 0 ? (
            <p className="py-6 text-center text-sm text-text-secondary">
              Không có lượt hỏi đáp phù hợp với bộ lọc.
            </p>
          ) : null}
        </div>
      </Card>

      {selectedLog ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="conversation-log-title"
          onMouseDown={() => setSelectedLog(null)}
        >
          <section
            className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-border-color bg-card-surface p-5 shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-primary">
                  Chi tiết lượt hỏi đáp
                </p>
                <h3 id="conversation-log-title" className="mt-1 text-lg font-bold">
                  {userLabel(selectedLog)}
                </h3>
                <p className="mt-1 text-sm text-text-secondary">
                  {selectedLog.session} ·{" "}
                  {selectedLog.dateLabel ??
                    (selectedLog.dateGroup === "today" ? "Hôm nay" : "Hôm qua")}
                  , {selectedLog.time}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedLog(null)}
                aria-label="Đóng chi tiết"
                className="rounded-lg p-1 text-text-secondary hover:bg-secondary-surface hover:text-text-primary"
              >
                <Icon name="close" />
              </button>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
                  Câu hỏi
                </p>
                <p className="mt-2 text-sm leading-6">{selectedLog.question}</p>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
                  Câu trả lời
                </p>
                <p className="mt-2 text-sm leading-6 text-text-secondary">{selectedLog.answer}</p>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-2 border-t border-border-color pt-4">
              <Badge tone={sourceTone(selectedLog.source)}>{selectedLog.source}</Badge>
              {selectedLog.supportingSources.map((source) => (
                <Badge key={source} tone={sourceTone(source)}>
                  {source}
                </Badge>
              ))}
              <Badge tone="muted">{`TTFT ${selectedLog.ttft ?? "—"}`}</Badge>
              <Badge tone="muted">{`Tổng ${selectedLog.latency}`}</Badge>
              <Badge tone={feedbackTone(selectedLog.feedback)}>
                {feedbackLabel(selectedLog.feedback)}
              </Badge>
              {selectedLog.socialIntent ? (
                <Badge tone="muted">
                  {SOCIAL_LABELS[selectedLog.socialIntent] ?? "Xã giao"}
                </Badge>
              ) : null}
            </div>

            {selectedLog.feedback === "dislike" &&
            (selectedLog.feedbackReasons?.length || selectedLog.feedbackComment) ? (
              <div className="mt-3 rounded-lg border border-border-color bg-secondary-surface px-3 py-2 text-sm">
                <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
                  Lý do
                </p>
                {selectedLog.feedbackReasons?.length ? (
                  <p className="mt-1 leading-6">{selectedLog.feedbackReasons.join(" · ")}</p>
                ) : null}
                {selectedLog.feedbackComment ? (
                  <p className="mt-1 leading-6 text-text-secondary">{selectedLog.feedbackComment}</p>
                ) : null}
              </div>
            ) : null}

            {selectedLog.context ? (
              <details className="mt-5 border-t border-border-color pt-4">
                <summary className="cursor-pointer text-sm font-bold">Ngữ cảnh truy xuất</summary>
                <pre className="mt-3 whitespace-pre-wrap rounded-lg border border-border-color bg-secondary-surface p-3 font-sans text-sm leading-6 text-text-secondary">
                  {selectedLog.context}
                </pre>
              </details>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}

