import { useEffect, useMemo, useRef, useState } from "react";

import {
  bulkDeleteAdminFaqs,
  bulkSetAdminFaqStatus,
  createAdminFaq,
  deleteAdminFaq,
  downloadAdminFaqExport,
  downloadAdminFaqTemplate,
  getAdminFaqIntents,
  getAdminFaqs,
  getAdminProcedures,
  importAdminFaqs,
  updateAdminFaq,
  type AdminFaq,
  type AdminFaqIntent,
  type AdminProcedure,
} from "../../api/admin";
import { Badge, Card, PageHeader } from "./shared.tsx";

type FormState = {
  question: string;
  answer: string;
  intent: string;
  status: "ready" | "draft";
  procedure_code: string;
};

type FaqTab = "ready" | "draft";

const FILTER_INTENTS = [
  "required_documents",
  "fee",
  "processing_time",
  "submission_method",
] as const;

const FALLBACK_INTENT_LABELS: Record<string, string> = {
  required_documents: "Hồ sơ, giấy tờ",
  fee: "Phí, lệ phí",
  processing_time: "Thời hạn giải quyết",
  submission_method: "Cách nộp hồ sơ",
};

const EMPTY_FORM: FormState = {
  question: "",
  answer: "",
  intent: "general_info",
  status: "ready",
  procedure_code: "",
};

function statusLabel(status: string) {
  return status === "ready" ? "Đang hoạt động" : "Bản nháp";
}

function searchKey(value: string) {
  return value
    .toLocaleLowerCase("vi")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function procedureDigits(value: string) {
  return String(value || "").replace(/\D/g, "");
}

export default function FaqPage() {
  const [items, setItems] = useState<AdminFaq[]>([]);
  const [intents, setIntents] = useState<AdminFaqIntent[]>([]);
  const [procedures, setProcedures] = useState<AdminProcedure[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [tab, setTab] = useState<FaqTab>("ready");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [procedureQuery, setProcedureQuery] = useState("");
  const [procedureOpen, setProcedureOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [exportStatus, setExportStatus] = useState<"all" | "ready" | "draft">("all");
  const [procedureFilter, setProcedureFilter] = useState("");
  const [selectedIntents, setSelectedIntents] = useState<Set<string>>(new Set());
  const [intentFilterOpen, setIntentFilterOpen] = useState(false);
  const intentFilterRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filteredProcedures = useMemo(() => {
    const query = searchKey(procedureQuery.trim());
    const matches = query
      ? procedures.filter(
          (item) =>
            searchKey(item.code).includes(query) ||
            searchKey(item.name).includes(query),
        )
      : procedures;
    return matches.slice(0, 20);
  }, [procedures, procedureQuery]);

  useEffect(() => {
    const valid = new Set<string>(FILTER_INTENTS);
    setSelectedIntents((current) => {
      const retained = new Set([...current].filter((value) => valid.has(value)));
      return retained.size > 0 ? retained : new Set(valid);
    });
  }, [intents]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [selectedIntents, procedureFilter]);

  useEffect(() => {
    if (!intentFilterOpen) return;
    const closeOnOutside = (event: PointerEvent) => {
      if (
        intentFilterRef.current &&
        !intentFilterRef.current.contains(event.target as Node)
      ) {
        setIntentFilterOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOnOutside);
    return () => document.removeEventListener("pointerdown", closeOnOutside);
  }, [intentFilterOpen]);

  const procedureFilterDigits = procedureDigits(procedureFilter);
  const matchesProcedureFilter = (item: AdminFaq) =>
    !procedureFilterDigits ||
    procedureDigits(item.procedure_code ?? "").includes(procedureFilterDigits);

  const visibleItems = useMemo(
    () =>
      items.filter(
        (item) =>
          item.status === tab &&
          selectedIntents.size > 0 &&
          selectedIntents.has(item.intent) &&
          matchesProcedureFilter(item),
      ),
    [items, tab, selectedIntents, procedureFilterDigits],
  );

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId),
    [items, selectedId],
  );

  const readyCount = items.filter(
    (item) =>
      item.status === "ready" &&
      selectedIntents.has(item.intent) &&
      matchesProcedureFilter(item),
  ).length;
  const draftCount = items.filter(
    (item) =>
      item.status !== "ready" &&
      selectedIntents.has(item.intent) &&
      matchesProcedureFilter(item),
  ).length;
  const allVisibleSelected =
    visibleItems.length > 0 &&
    visibleItems.every((item) => selectedIds.has(item.id));

  const intentFilters = FILTER_INTENTS.map((value) => ({
    value,
    label:
      intents.find((item) => item.value === value)?.label ??
      FALLBACK_INTENT_LABELS[value],
  }));
  const allIntentsSelected = FILTER_INTENTS.every((value) =>
    selectedIntents.has(value),
  );

  function toggleIntent(value: string) {
    setSelectedIntents((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function toggleAllIntents() {
    setSelectedIntents(
      allIntentsSelected ? new Set() : new Set(FILTER_INTENTS),
    );
  }

  const isNew = selectedId === "";

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        visibleItems.forEach((item) => next.delete(item.id));
      } else {
        visibleItems.forEach((item) => next.add(item.id));
      }
      return next;
    });
  }

  function intentLabel(value: string) {
    return intents.find((item) => item.value === value)?.label ?? value;
  }

  function selectFaq(item: AdminFaq) {
    setSelectedId(item.id);
    setForm({
      question: item.question,
      answer: item.answer,
      intent: item.intent,
      status: item.status === "draft" ? "draft" : "ready",
      procedure_code: item.procedure_code ?? "",
    });
    setProcedureQuery(item.procedure_code ?? "");
    setProcedureOpen(false);
    setError("");
  }

  function startNew() {
    setSelectedId("");
    setForm(EMPTY_FORM);
    setProcedureQuery("");
    setProcedureOpen(false);
    setError("");
  }

  function selectProcedure(procedure: AdminProcedure) {
    setForm((current) => ({ ...current, procedure_code: procedure.code }));
    setProcedureQuery(`${procedure.code} — ${procedure.name}`);
    setProcedureOpen(false);
  }

  async function reload(nextTab: FaqTab = tab) {
    const [faqResponse, intentResponse, procedureResponse] = await Promise.all([
      getAdminFaqs(),
      getAdminFaqIntents(),
      getAdminProcedures(),
    ]);

    setItems(faqResponse.items);
    setIntents(intentResponse);
    setProcedures(procedureResponse.items);

    const nextItems = faqResponse.items.filter(
      (item) => item.status === nextTab,
    );

    if (nextItems.length > 0) {
      const stillExists = nextItems.find((item) => item.id === selectedId);
      selectFaq(stillExists ?? nextItems[0]);
    } else {
      startNew();
    }
  }

  function switchTab(nextTab: FaqTab) {
    setTab(nextTab);
    setSelectedIds(new Set());
    const first = items.find((item) => item.status === nextTab);
    if (first) selectFaq(first);
    else startNew();
  }

  useEffect(() => {
    reload().catch(() => setError("Không tải được danh sách FAQ."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    if (!form.question.trim() || !form.answer.trim()) {
      setError("Câu hỏi và câu trả lời không được để trống.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      if (isNew) {
        await createAdminFaq(form);
      } else {
        await updateAdminFaq(selectedId, form);
      }

      setTab(form.status);
      await reload(form.status);
      // Lưu xong thì mở form trắng để nhập FAQ kế tiếp.
      // Muốn tạo mới khi đang xem FAQ cũ vẫn có nút "+ Thêm FAQ".
      startNew();
    } catch {
      setError("Không lưu được FAQ.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!selected || !window.confirm("Xoá FAQ này?")) return;

    try {
      await deleteAdminFaq(selected.id);
      await reload();
    } catch {
      setError("Không xoá được FAQ.");
    }
  }

  async function removeSelected() {
    if (selectedIds.size === 0) return;
    if (
      !window.confirm(
        `Xoá ${selectedIds.size} FAQ đã chọn? Thao tác này không thể hoàn tác.`,
      )
    ) {
      return;
    }
    setBulkBusy(true);
    setError("");
    setNotice("");
    const count = selectedIds.size;
    try {
      await bulkDeleteAdminFaqs([...selectedIds]);
      setSelectedIds(new Set());
      await reload();
      setNotice(`Đã xoá ${count} FAQ.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không xoá được FAQ.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function setSelectedStatus(status: "ready" | "draft") {
    if (selectedIds.size === 0) return;
    setBulkBusy(true);
    setError("");
    setNotice("");
    const count = selectedIds.size;
    try {
      await bulkSetAdminFaqStatus([...selectedIds], status);
      setSelectedIds(new Set());
      await reload();
      setNotice(`Đã cập nhật ${count} FAQ.`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không cập nhật được FAQ.",
      );
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    setImportBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await importAdminFaqs(file);
      await reload();
      setNotice(`Đã import ${result.imported} FAQ.`);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không import được FAQ.",
      );
    } finally {
      setImportBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleExport() {
    setError("");
    setNotice("");
    try {
      await downloadAdminFaqExport(exportStatus, procedureFilter);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không xuất được FAQ.",
      );
    }
  }

  async function handleTemplate() {
    setError("");
    setNotice("");
    try {
      await downloadAdminFaqTemplate();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không tải được file mẫu.",
      );
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="FAQ"
        title="Quản lý câu hỏi thường gặp"
        description="Quản lý cặp câu hỏi và câu trả lời chuẩn hóa, phục vụ tra cứu và phản hồi của chatbot."
      />

      {error ? (
        <div className="mb-4 rounded-lg border border-danger bg-danger-surface p-3 text-sm font-semibold text-danger">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm font-semibold text-green-700">
          {notice}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_440px]">
        <Card>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <select
                aria-label="Phạm vi export FAQ"
                value={exportStatus}
                onChange={(event) =>
                  setExportStatus(event.target.value as "all" | "ready" | "draft")
                }
                className="h-9 rounded-lg border border-border-color bg-white px-2 text-xs font-semibold outline-primary"
              >
                <option value="all">Toàn bộ FAQ</option>
                <option value="ready">FAQ đang hoạt động</option>
                <option value="draft">FAQ bản nháp</option>
              </select>
              <div className="relative">
                <span className="material-symbols-outlined pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[17px] text-text-secondary">
                  search
                </span>
                <input
                  value={procedureFilter}
                  onChange={(event) => setProcedureFilter(event.target.value)}
                  placeholder="Mã thủ tục"
                  aria-label="Tìm theo mã thủ tục"
                  inputMode="numeric"
                  className="h-9 w-40 rounded-lg border border-border-color bg-white pl-8 pr-2 text-xs outline-primary"
                />
              </div>
              <div ref={intentFilterRef} className="relative">
                <button
                  type="button"
                  aria-haspopup="true"
                  aria-expanded={intentFilterOpen}
                  onClick={() => setIntentFilterOpen((current) => !current)}
                  className="flex h-9 items-center gap-1.5 rounded-lg border border-border-color px-3 text-xs font-bold text-text-primary hover:bg-secondary-surface"
                >
                  <span className="material-symbols-outlined text-[18px]">
                    filter_list
                  </span>
                  Bộ lọc
                  {selectedIntents.size !== FILTER_INTENTS.length ? (
                    <span className="text-primary">({selectedIntents.size})</span>
                  ) : null}
                </button>
                {intentFilterOpen ? (
                  <div className="absolute left-0 top-10 z-30 w-64 rounded-lg border border-border-color bg-card-surface p-3 shadow-xl">
                    <label className="flex cursor-pointer items-center gap-2 border-b border-border-color pb-2 text-xs font-bold">
                      <input
                        type="checkbox"
                        checked={allIntentsSelected}
                        onChange={toggleAllIntents}
                        className="h-4 w-4 accent-primary"
                      />
                      Tất cả danh mục
                    </label>
                    <div className="mt-2 space-y-2">
                      {intentFilters.map((intent) => (
                        <label
                          key={intent.value}
                          className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-text-secondary"
                        >
                          <input
                            type="checkbox"
                            checked={selectedIntents.has(intent.value)}
                            onChange={() => toggleIntent(intent.value)}
                            className="h-4 w-4 accent-primary"
                          />
                          {intent.label}
                        </label>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                aria-label="Import FAQ từ Excel"
                title="Import FAQ từ Excel"
                disabled={importBusy}
                onClick={() => fileInputRef.current?.click()}
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-green-200 bg-green-50 text-green-700 transition hover:border-green-500 hover:bg-green-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="material-symbols-outlined text-[20px]">
                  upload_file
                </span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={(event) => void handleImport(event.target.files?.[0])}
              />
              <button
                type="button"
                onClick={() => void handleExport()}
                className="flex h-9 items-center gap-1 rounded-lg border border-border-color px-3 text-xs font-bold text-text-primary hover:bg-secondary-surface"
              >
                <span className="material-symbols-outlined text-[18px]">
                  download
                </span>
                Xuất Excel
              </button>
              <button
                type="button"
                onClick={() => void handleTemplate()}
                className="flex h-9 items-center gap-1 rounded-lg border border-border-color px-3 text-xs font-bold text-text-primary hover:bg-secondary-surface"
              >
                <span className="material-symbols-outlined text-[18px]">
                  description
                </span>
                File mẫu
              </button>
              <button
                type="button"
                onClick={startNew}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:bg-primary-hover"
              >
                + Thêm FAQ
              </button>
            </div>
          </div>

          <div className="mb-3 flex gap-2 border-b border-border-color">
            <button
              type="button"
              onClick={() => switchTab("ready")}
              className={`border-b-2 px-3 py-2 text-sm font-bold transition-colors ${
                tab === "ready"
                  ? "border-primary text-primary"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              Đang hoạt động ({readyCount})
            </button>
            <button
              type="button"
              onClick={() => switchTab("draft")}
              className={`border-b-2 px-3 py-2 text-sm font-bold transition-colors ${
                tab === "draft"
                  ? "border-primary text-primary"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              Bản nháp ({draftCount})
            </button>
          </div>

          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border-color bg-secondary-surface/40 px-3 py-2">
            <label className="flex items-center gap-2 text-xs font-semibold text-text-secondary">
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleSelectAll}
                aria-label="Chọn tất cả FAQ trong tab hiện tại"
                className="h-4 w-4 accent-primary"
              />
              Chọn tất cả trong tab này
            </label>
            {selectedIds.size > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-primary">
                  Đã chọn {selectedIds.size}
                </span>
                <button
                  type="button"
                  disabled={bulkBusy}
                  onClick={() => void setSelectedStatus("ready")}
                  className="rounded-md border border-green-200 bg-green-50 px-2 py-1 text-xs font-bold text-green-700 hover:bg-green-100 disabled:opacity-60"
                >
                  Đang hoạt động
                </button>
                <button
                  type="button"
                  disabled={bulkBusy}
                  onClick={() => void setSelectedStatus("draft")}
                  className="rounded-md border border-border-color bg-white px-2 py-1 text-xs font-bold text-text-secondary hover:bg-secondary-surface disabled:opacity-60"
                >
                  Bản nháp
                </button>
                <button
                  type="button"
                  disabled={bulkBusy}
                  onClick={() => void removeSelected()}
                  className="rounded-md border border-danger px-2 py-1 text-xs font-bold text-danger hover:bg-danger-surface disabled:opacity-60"
                >
                  Xoá đã chọn
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set())}
                  className="text-xs font-semibold text-text-secondary underline"
                >
                  Bỏ chọn
                </button>
              </div>
            ) : null}
          </div>

          <div className="space-y-2">
            {visibleItems.map((item) => (
              <div
                key={item.id}
                className={`flex items-start gap-2 rounded-lg border p-3 transition ${
                  item.id === selectedId
                    ? "border-primary bg-primary-soft/60"
                    : "border-border-color hover:bg-secondary-surface"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(item.id)}
                  onChange={() => toggleSelected(item.id)}
                  aria-label={`Chọn FAQ: ${item.question}`}
                  className="mt-1 h-4 w-4 shrink-0 accent-primary"
                />
                <button
                  type="button"
                  onClick={() => selectFaq(item)}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="font-bold leading-6">{item.question}</p>
                  <p className="mt-1 line-clamp-2 text-sm text-text-secondary">
                    {item.answer}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Badge tone="muted">{intentLabel(item.intent)}</Badge>
                    {item.procedure_code ? (
                      <Badge tone="info">{item.procedure_code}</Badge>
                    ) : null}
                    <Badge tone={item.status === "ready" ? "ok" : "muted"}>
                      {statusLabel(item.status)}
                    </Badge>
                  </div>
                </button>
              </div>
            ))}

            {visibleItems.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border-color p-4 text-sm text-text-secondary">
                {procedureFilterDigits
                  ? `Không tìm thấy FAQ khớp mã thủ tục "${procedureFilter}".`
                  : tab === "ready"
                    ? "Chưa có FAQ đang hoạt động. Bấm “Thêm FAQ” để tạo câu hỏi đầu tiên."
                    : "Chưa có FAQ nháp."}
              </p>
            ) : null}
          </div>
        </Card>

        <Card className="xl:self-start">
          <div className="mb-4 flex items-center justify-between border-b border-border-color pb-3">
            <h3 className="text-base font-bold text-text-primary">
              Thông tin câu hỏi
            </h3>

            <span
              className={`whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${
                form.status === "ready"
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {form.status === "ready" ? "Đang hoạt động" : "Bản nháp"}
            </span>
          </div>

          <div className="mb-4">
            <p className="text-xs font-bold uppercase text-text-secondary">
              FAQ ID
            </p>
            <p className="mt-1 break-all text-sm font-semibold">
              {isNew ? "Chưa có ID" : selectedId}
            </p>
          </div>

          <label className="block text-sm font-semibold">Câu hỏi</label>
          <textarea
            value={form.question}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                question: event.target.value,
              }))
            }
            rows={3}
            className="mt-1 w-full rounded-lg border border-border-color bg-white p-3 text-sm outline-primary"
          />

          <label className="mt-4 block text-sm font-semibold">
            Câu trả lời
          </label>
          <textarea
            value={form.answer}
            onChange={(event) =>
              setForm((current) => ({ ...current, answer: event.target.value }))
            }
            rows={8}
            className="mt-1 w-full rounded-lg border border-border-color bg-white p-3 text-sm outline-primary"
          />

          <label className="mt-4 block text-sm font-semibold">
            Mã thủ tục <span className="font-normal text-text-secondary">(không bắt buộc)</span>
          </label>
          <div className="relative mt-1">
            <input
              value={procedureQuery}
              onChange={(event) => {
                setProcedureQuery(event.target.value);
                setForm((current) => ({ ...current, procedure_code: "" }));
                setProcedureOpen(true);
              }}
              onFocus={() => setProcedureOpen(true)}
              onBlur={() => window.setTimeout(() => setProcedureOpen(false), 150)}
              placeholder="Gõ mã hoặc tên thủ tục…"
              autoComplete="off"
              className="w-full rounded-lg border border-border-color bg-white p-3 pr-10 text-sm outline-primary"
            />
            {form.procedure_code ? (
              <button
                type="button"
                aria-label="Bỏ gắn thủ tục"
                onClick={() => {
                  setProcedureQuery("");
                  setProcedureOpen(false);
                  setForm((current) => ({ ...current, procedure_code: "" }));
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-text-secondary hover:bg-secondary-surface hover:text-text-primary"
              >
                ×
              </button>
            ) : null}

            {procedureOpen ? (
              <div className="absolute z-30 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-border-color bg-white p-1 shadow-lg">
                <button
                  type="button"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    setProcedureQuery("");
                    setProcedureOpen(false);
                    setForm((current) => ({ ...current, procedure_code: "" }));
                  }}
                  className="w-full rounded px-3 py-2 text-left text-sm text-text-secondary hover:bg-secondary-surface"
                >
                  — Không gắn thủ tục —
                </button>
                {filteredProcedures.map((procedure) => (
                  <button
                    key={procedure.code}
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      selectProcedure(procedure);
                    }}
                    className="w-full rounded px-3 py-2 text-left text-sm hover:bg-secondary-surface"
                  >
                    <span className="font-semibold">{procedure.code}</span>
                    <span className="text-text-secondary"> — {procedure.name}</span>
                  </button>
                ))}
                {filteredProcedures.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-text-secondary">
                    Không tìm thấy thủ tục phù hợp.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
          {form.procedure_code ? (
            <p className="mt-1 text-xs text-text-secondary">
              Đang gắn: {form.procedure_code}
            </p>
          ) : null}

          <label className="mt-4 block text-sm font-semibold">Danh mục</label>
          <select
            value={form.intent}
            onChange={(event) =>
              setForm((current) => ({ ...current, intent: event.target.value }))
            }
            className="mt-1 w-full rounded-lg border border-border-color bg-white p-3 text-sm"
          >
            {intents.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <label className="mt-4 block text-sm font-semibold">Trạng thái</label>
          <select
            value={form.status}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                status: event.target.value as FormState["status"],
              }))
            }
            className="mt-1 w-full rounded-lg border border-border-color bg-white p-3 text-sm"
          >
            <option value="ready">Đang hoạt động</option>
            <option value="draft">Bản nháp</option>
          </select>

          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="min-w-[120px] flex-1 rounded-lg bg-primary px-4 py-2.5 text-sm font-bold text-white hover:bg-primary-hover disabled:opacity-60"
            >
              {saving ? "Đang lưu..." : "Lưu"}
            </button>

            {!isNew ? (
              <button
                type="button"
                onClick={remove}
                className="rounded-lg border border-danger px-4 py-2.5 text-sm font-bold text-danger hover:bg-danger-surface"
              >
                Xoá
              </button>
            ) : null}
          </div>
        </Card>
      </div>
    </>
  );
}
