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
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSourceFields, setSelectedSourceFields] = useState<string[]>([]);
  const [detail, setDetail] = useState<AdminProcedureDetail | null>(null);
  const [sections, setSections] = useState<AdminSection[]>([]);
  const [selectedSection, setSelectedSection] = useState<AdminSection | null>(null);
  const [error, setError] = useState("");

  const selected = items.find((item) => item.code === selectedCode) ?? items[0];
  const sourceFields = [...new Set(items.map((item) => item.source_field).filter(Boolean))].sort((a, b) => a.localeCompare(b, "vi"));
  const normalizedQuery = searchQuery.trim().toLocaleLowerCase("vi");
  const filteredItems = items.filter((item) => (
    (!selectedSourceFields.length || selectedSourceFields.includes(item.source_field))
    && (!normalizedQuery || item.code.toLocaleLowerCase("vi").includes(normalizedQuery) || item.name.toLocaleLowerCase("vi").includes(normalizedQuery))
  ));

  function toggleSourceField(sourceField: string) {
    setSelectedSourceFields((current) => (
      current.includes(sourceField)
        ? current.filter((value) => value !== sourceField)
        : [...current, sourceField]
    ));
  }

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
        eyebrow="KHO DỮ LIỆU"
        title="Quản lý dữ liệu thủ tục hành chính"
        description="Tra cứu thông tin thủ tục, theo dõi chunks và kiểm tra nội dung được lưu trữ trong hệ thống."
      />

      {error ? (
        <div className="mb-4 rounded-lg border border-danger bg-danger-surface p-3 text-sm font-semibold text-danger">
          {error}
        </div>
      ) : null}

      <div className="mb-4 grid gap-3 md:grid-cols-2">
        <MetricCard label="Tổng số thủ tục" value={String(items.length)} note="Nguồn dữ liệu: Cổng Dịch vụ công Quốc gia" />
        <MetricCard label="Số chunks thủ tục được chọn" value={String(sections.length)} note="" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_420px]">
        <Card>
          <div className="mb-4 grid gap-2 md:grid-cols-[1fr_240px]">
            <input
              className="rounded-lg border border-border-color bg-white px-3 py-2 text-sm outline-primary"
              placeholder="Tìm mã hoặc tên thủ tục..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <details className="relative">
              <summary className="flex cursor-pointer list-none items-center justify-between rounded-lg border border-border-color bg-white px-3 py-2 text-sm [&::-webkit-details-marker]:hidden">
                {selectedSourceFields.length ? `Đã chọn ${selectedSourceFields.length} lĩnh vực` : "Toàn bộ lĩnh vực"}
                <span className="material-symbols-outlined text-[18px] text-text-secondary">expand_more</span>
              </summary>
              <div className="absolute right-0 z-20 mt-1 w-72 rounded-lg border border-border-color bg-card-surface p-2 shadow-lg">
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm font-semibold hover:bg-secondary-surface">
                  <input
                    type="checkbox"
                    checked={!selectedSourceFields.length}
                    onChange={() => setSelectedSourceFields([])}
                  />
                  Toàn bộ lĩnh vực
                </label>
                <div className="max-h-64 overflow-y-auto border-t border-border-color pt-1">
                  {sourceFields.map((sourceField) => (
                    <label key={sourceField} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-secondary-surface">
                      <input
                        type="checkbox"
                        checked={selectedSourceFields.includes(sourceField)}
                        onChange={() => toggleSourceField(sourceField)}
                      />
                      <span>{sourceField}</span>
                    </label>
                  ))}
                </div>
              </div>
            </details>
          </div>

          <div className="overflow-x-auto xl:max-h-[calc(100vh-16rem)] xl:overflow-y-auto">
            <table className="w-full min-w-[900px] table-fixed text-left text-sm">
              <colgroup>
                <col className="w-[96px]" />
                <col />
                <col className="w-[240px]" />
                <col className="w-[100px]" />
              </colgroup>
              <thead className="border-b border-border-color text-xs uppercase text-text-secondary">
                <tr>
                  <th className="py-3 pr-3">Mã TTHC</th>
                  <th className="py-3 pr-3">Tên thủ tục hành chính</th>
                  <th className="py-3 pr-3">Lĩnh vực</th>
                  <th className="whitespace-nowrap py-3 pr-3 text-center">Số chunks</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color">
                {filteredItems.map((item) => (
                  <tr
                    key={item.code}
                    className={item.code === selected?.code ? "bg-primary-soft/50" : "hover:bg-secondary-surface"}
                    onClick={() => setSelectedCode(item.code)}
                  >
                    <td className="py-3 pr-3 font-bold text-primary">{item.code}</td>
                    <td className="break-words py-3 pr-3 leading-5">{item.name}</td>
                    <td className="overflow-hidden text-ellipsis whitespace-nowrap py-3 pr-3 text-text-secondary" title={item.source_field}>{item.source_field}</td>
                    <td className="whitespace-nowrap py-3 pr-3 text-center font-semibold">{item.section_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:self-start xl:overflow-auto">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase text-text-secondary">Thông tin thủ tục</p>
              <h3 className="mt-1 text-lg font-bold">{selected?.code ?? "Chưa có dữ liệu"}</h3>
              <p className="mt-1 text-sm leading-6 text-text-secondary">{selected?.name ?? "Backend chưa trả thủ tục."}</p>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 rounded-lg bg-secondary-surface p-1">
            {[
              ["detail", "Thông tin chung"],
              ["sections", "Chunks"],
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
                ["Nhóm lĩnh vực", detail?.domain_group],
                ["Lĩnh vực chi tiết", detail?.source_field],
                ["Mã lĩnh vực", detail?.canonical_field],
                ["Cơ quan ban hành", detail?.issuing_agency],
                ["Liên kết thủ tục gốc  ", detail?.detail_url],
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
