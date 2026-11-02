import { useEffect, useMemo, useState } from "react";

import {
  createAdminFaq,
  deleteAdminFaq,
  getAdminFaqIntents,
  getAdminFaqs,
  getAdminProcedures,
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

  const visibleItems = useMemo(
    () => items.filter((item) => item.status === tab),
    [items, tab],
  );

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId),
    [items, selectedId],
  );

  const readyCount = items.filter((item) => item.status === "ready").length;
  const draftCount = items.filter((item) => item.status !== "ready").length;

  const isNew = selectedId === "";

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

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_440px]">
        <Card>
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-text-secondary">
              Danh sách câu hỏi
            </p>
            <button
              type="button"
              onClick={startNew}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:bg-primary-hover"
            >
              + Thêm FAQ
            </button>
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

          <div className="space-y-2">
            {visibleItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => selectFaq(item)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  item.id === selectedId
                    ? "border-primary bg-primary-soft/60"
                    : "border-border-color hover:bg-secondary-surface"
                }`}
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
            ))}

            {visibleItems.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border-color p-4 text-sm text-text-secondary">
                {tab === "ready"
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
