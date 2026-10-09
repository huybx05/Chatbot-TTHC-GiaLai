import { useEffect, useState } from "react";

import {
  getAdminProcedure,
  getAdminProcedures,
  getAdminSections,
  type AdminProcedure,
  type AdminProcedureDetail,
  type AdminSection,
} from "../../api/admin";
import { Card, MetricCard, PageHeader } from "./shared.tsx";

export default function DataAndChunkPage() {
  const [tab, setTab] = useState<"detail" | "sections">("detail");
  const [items, setItems] = useState<AdminProcedure[]>([]);
  const [selectedCode, setSelectedCode] = useState("");
  const [detail, setDetail] = useState<AdminProcedureDetail | null>(null);
  const [sections, setSections] = useState<AdminSection[]>([]);
  const [selectedSection, setSelectedSection] = useState<AdminSection | null>(null);
  const [error, setError] = useState("");

  const selected = items.find((item) => item.code === selectedCode) ?? items[0];

  useEffect(() => {
    getAdminProcedures()
      .then((res) => {
        setItems(res.items);
        setSelectedCode(res.items[0]?.code ?? "");
      })
      .catch(() => setError("Không tải được dữ liệu PostgreSQL."));
  }, []);

  useEffect(() => {
    if (!selectedCode) return;

    Promise.all([
      getAdminProcedure(selectedCode),
      getAdminSections(selectedCode),
    ])
      .then(([procedureRes, sectionsRes]) => {
        setDetail(procedureRes.item);
        setSections(sectionsRes.items);
      })
      .catch(() => setError("Không tải được chi tiết thủ tục."));
  }, [selectedCode]);

  return (
    <>
      <PageHeader
        eyebrow="Dữ liệu PostgreSQL"
        title="Xem thủ tục, chunk và Q/A cùng một nơi"
        description="Trang này đọc trực tiếp từ PostgreSQL qua backend admin API."
      />

      {error ? (
        <div className="mb-4 rounded-lg border border-danger bg-danger-surface p-3 text-sm font-semibold text-danger">
          {error}
        </div>
      ) : null}

      <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon="folder_open" label="Thủ tục" value={String(items.length)} note="Đang tải theo limit API" tone="info" />
        <MetricCard icon="view_list" label="Số Chunk thủ tục đang xem" value={String(sections.length)} note="Từ procedure_sections" tone="ok" />
        <MetricCard icon="verified" label="Trạng thái" value={selected?.status ?? "-"} note="Từ bảng procedures" tone="info" />
        <MetricCard icon="warning" label="Cần review" value="0" note="Chưa nối rule kiểm tra" tone="ok" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_420px]">
        <Card>
          <div className="mb-4 grid gap-2 md:grid-cols-[1fr_180px_160px]">
            <input className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm outline-primary" placeholder="Tìm mã hoặc tên thủ tục..." />
            <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm">
              <option>Toàn bộ lĩnh vực</option>
            </select>
            {/* <select className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm">
              <option>Tất cả trạng thái</option>
            </select> */}
          </div>

          <div className="overflow-x-auto xl:max-h-[calc(100vh-16rem)] xl:overflow-y-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-border-color text-xs uppercase text-text-secondary">
                <tr>
                  <th className="py-3 pr-3">Mã</th>
                  <th className="py-3 pr-3">Tên thủ tục</th>
                  <th className="py-3 pr-3">Lĩnh vực</th>
                  {/* <th className="py-3 pr-3">Trạng thái</th> */}
                  <th className="py-3 pr-3">Chunk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color">
                {items.map((item) => (
                  <tr
                    key={item.code}
                    className={item.code === selected?.code ? "bg-primary-soft/50" : "hover:bg-secondary-surface"}
                    onClick={() => setSelectedCode(item.code)}
                  >
                    <td className="py-3 pr-3 font-bold text-primary">{item.code}</td>
                    <td className="py-3 pr-3">{item.name}</td>
                    <td className="py-3 pr-3 text-text-secondary">{item.source_field}</td>
                    {/* <td className="py-3 pr-3">
                      <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                    </td> */}
                    <td className="py-3 pr-3 font-semibold">{item.section_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:self-start xl:overflow-auto">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase text-text-secondary">Đang xem</p>
              <h3 className="mt-1 text-lg font-bold">{selected?.code ?? "Chưa có dữ liệu"}</h3>
              <p className="mt-1 text-sm leading-6 text-text-secondary">{selected?.name ?? "Backend chưa trả thủ tục."}</p>
            </div>
            {/* {selected ? <Badge tone={statusTone(selected.status)}>{selected.status}</Badge> : null} */}
          </div>

          <div className="mt-4 grid grid-cols-2 rounded-lg bg-secondary-surface p-1">
            {[
              ["detail", "Chi tiết"],
              ["sections", "Chunk"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={`rounded-md px-3 py-2 text-sm font-bold ${tab === value ? "bg-card-surface text-primary shadow-sm" : "text-text-secondary"}`}
                onClick={() => setTab(value as "detail" | "sections")}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "detail" ? (
            <dl className="mt-4 grid gap-3 text-sm">
              {[
                ["domain_group", detail?.domain_group],
                ["source_field", detail?.source_field],
                ["canonical_field", detail?.canonical_field],
                ["issuing_agency", detail?.issuing_agency],
                ["detail_url", detail?.detail_url],
              ].map(([key, value]) => (
                <div key={key as string} className="rounded-lg border border-border-color bg-secondary-surface p-3">
                  <dt className="text-xs font-bold uppercase text-text-secondary">{String(key)}</dt>
                  <dd className="mt-1 break-words font-semibold">{String(value ?? "")}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {tab === "sections" ? (
            <div className="mt-4 space-y-3">
              {sections.map((section) => (
                <button
                  key={section.section_id}
                  className="w-full rounded-lg border border-border-color p-3 text-left transition hover:bg-secondary-surface"
                  type="button"
                  onClick={() => setSelectedSection(section)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-bold">{section.title}</p>
          
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">{section.section_type} · {section.section_id}</p>
                  <p className="mt-2 max-h-20 overflow-hidden text-sm leading-6 text-text-secondary">{section.content}</p>
                </button>
              ))}
            </div>
          ) : null}
        </Card>
      </div>

      {selectedSection ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
          <div className="max-h-[86vh] w-full max-w-3xl overflow-hidden rounded-xl border border-border-color bg-card-surface shadow-xl">
            <div className="flex items-start justify-between gap-4 border-b border-border-color p-4">
              <div>
                <p className="text-xs font-bold uppercase text-primary">{selectedSection.section_type}</p>
                <h3 className="mt-1 text-lg font-bold">{selectedSection.title}</h3>
                <p className="mt-1 break-all text-xs text-text-secondary">{selectedSection.section_id}</p>
              </div>
              <button
                className="flex size-9 shrink-0 items-center justify-center rounded-lg text-text-secondary hover:bg-hover-item"
                type="button"
                onClick={() => setSelectedSection(null)}
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            <div className="max-h-[62vh] overflow-auto p-4">
              <pre className="whitespace-pre-wrap break-words rounded-lg bg-secondary-surface p-4 text-sm leading-6 text-text-primary">
                {selectedSection.content}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
