import { type ReactNode, useEffect, useState } from "react";

import { RichText } from "../../components/RichText";
import { Badge, Icon, type BadgeTone } from "./shared.tsx";

/**
 * Bố cục kết quả **hai bên** cho trang kiểm thử.
 *
 * Bên trái là **câu trả lời** người dân sẽ nhận; bên phải là **ngữ cảnh và quyết định** đã dẫn
 * tới câu trả lời đó. Hai thứ này phải nằm cạnh nhau: một câu trả lời không kèm ngữ cảnh là thứ
 * không kiểm chứng được — người đọc không biết nó dựa vào đoạn văn nào, đi nhánh nào, mô hình
 * hay luật quyết định, mất bao lâu.
 *
 * Chi tiết (danh sách đoạn văn kèm điểm, toàn bộ dòng vết) **không** đặt ngay đây — chúng dài
 * và chỉ cần khi soi lỗi, nên nằm sau một nút và mở ra trong hộp thoại.
 */

/** Một nguồn dưới câu trả lời — kèm đường dẫn để người đọc đối chiếu. */
export interface NguonTraLoi {
  nhan: string;
  url?: string;
}

/** Một dòng trong bảng ngữ cảnh bên phải. */
export interface DongNguCanh {
  label: string;
  value: string;
  tone?: BadgeTone;
}

/**
 * Một mục ngữ cảnh **đã tìm được** — thứ thật sự được đưa cho mô hình đọc.
 *
 * Đây không phải dòng vết: không có nhánh, không có token, không có thời gian. Chỉ có nội
 * dung và nguồn của nó, vì đó là thứ quyết định câu trả lời đúng hay sai.
 */
export interface MucNguCanh {
  /** ``fact`` | ``graph`` | ``chunk`` | ``faq``. */
  kind: string;
  title: string;
  content: string;
  procedureCode?: string;
  /** Đường dẫn trang gốc của thủ tục — để mã thủ tục thành liên kết bấm được. */
  detailUrl?: string;
  section?: string;
  score?: number;
  provenance?: string;
  partTitle?: string;
  byKeyword?: boolean;
  byVector?: boolean;
  /** Thứ hạng trong nhánh **từ khoá** (1 = cao nhất). `null`/bỏ trống = nhánh đó không tìm ra. */
  keywordRank?: number | null;
  /** Thứ hạng trong nhánh **vector**. */
  vectorRank?: number | null;
}

/** Nhãn loại ngữ cảnh — dùng **tên nguồn dữ liệu** để đồng nhất với nhãn nhánh. */
const NHAN_LOAI: Record<string, string> = {
  fact: "PostgreSQL",
  graph: "Neo4j",
  chunk: "Hybrid",
  faq: "FAQ",
  section: "PostgreSQL",
};

/** Nguồn dữ liệu — để biết mục này lấy từ đâu khi cần đối chiếu. */
const NHAN_NGUON: Record<string, string> = {
  postgres: "PostgreSQL",
  neo4j: "Neo4j",
  "es+qdrant": "ES + Qdrant",
  qdrant_faq: "Qdrant",
};

/** Danh sách ngữ cảnh, gọn: mỗi mục vài dòng, phần dài xem trong hộp thoại. */
export function NguCanhBangChung({
  items,
  dayDu = false,
  loaiHienThi,
}: {
  items: MucNguCanh[];
  /** `true` = hiện đầy đủ, không cắt dòng (dùng trong hộp thoại). */
  dayDu?: boolean;
  /**
   * Nhãn loại dùng cho **mọi** mục, thay cho nhãn theo `kind`.
   *
   * Cần cho sáu chế độ truy xuất: cùng một đoạn văn nhưng tìm bằng Keyword hay bằng Vector thì
   * nhãn phải nói đúng **cách tìm**, không phải "Hybrid".
   */
  loaiHienThi?: string;
}) {
  if (!items.length) {
    return (
      <p className="px-4 py-4 text-sm text-text-secondary">
        Nhánh này không tìm được ngữ cảnh nào — nên không có gì để mô hình đọc.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border-color px-4">
      {items.map((muc, i) => (
        <li key={`${muc.procedureCode ?? muc.title}-${i}`} className="py-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="info">{loaiHienThi ?? NHAN_LOAI[muc.kind] ?? muc.kind}</Badge>
            {muc.procedureCode ? (
              muc.detailUrl ? (
                <a
                  href={muc.detailUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-xs font-semibold text-primary hover:underline"
                >
                  {muc.procedureCode}
                </a>
              ) : (
                <span className="font-mono text-xs font-semibold text-text-secondary">
                  {muc.procedureCode}
                </span>
              )
            ) : null}
            {muc.score ? (
              <span className="text-xs text-text-secondary">
                · điểm {muc.score.toFixed(3)}
              </span>
            ) : null}
            {/*
              Thứ hạng từng nhánh (chỉ nhánh lai có): cho biết đoạn này do **từ khoá** hay
              **vector** kéo lên, và kéo lên ở vị trí nào. Cần vì với 541 đoạn, hai nhánh gần
              như cùng tìm ra mọi đoạn — "cả hai cùng có" không phân biệt được gì.
            */}
            {muc.keywordRank != null ? (
              <span className="text-[11px] font-semibold text-text-secondary">
                keyword #{muc.keywordRank}
              </span>
            ) : null}
            {muc.vectorRank != null ? (
              <span className="text-[11px] font-semibold text-text-secondary">
                vector #{muc.vectorRank}
              </span>
            ) : null}
            {muc.provenance && NHAN_NGUON[muc.provenance] !== NHAN_LOAI[muc.kind] ? (
              <span className="ml-auto text-[11px] text-text-secondary">
                {NHAN_NGUON[muc.provenance] ?? muc.provenance}
              </span>
            ) : null}
          </div>

          <p className="mt-1 text-xs font-semibold text-text-primary">
            {muc.partTitle ? `${muc.partTitle} · ` : ""}
            {muc.title}
          </p>
          <p
            className={`mt-0.5 whitespace-pre-wrap text-xs leading-5 text-text-secondary ${
              dayDu ? "" : "overflow-hidden"
            }`}
            style={dayDu ? undefined : { maxHeight: "3.75rem" }}
          >
            {muc.content}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function KetQuaHaiBen({
  traLoi,
  ghiChuTraLoi,
  nguon,
  nguCanh = [],
  noiDungNguCanh,
  chiTiet,
  nhanChiTiet = "Xem chi tiết",
  tieuDeNguCanh = "Ngữ cảnh & quyết định",
  huyHieuNguCanh,
}: {
  /** Câu trả lời của mô hình. `null` = chưa có bước sinh câu trả lời. */
  traLoi: string | null;
  /** Ghi chú ngắn dưới khung trống — bỏ trống thì chỉ hiện tiêu đề. */
  ghiChuTraLoi?: string;
  /** Nguồn sẽ dùng để trả lời (mã thủ tục, văn bản, mục nội dung). */
  nguon?: NguonTraLoi[];
  nguCanh?: DongNguCanh[];
  /** Nội dung ngữ cảnh tuỳ biến (ví dụ danh sách bằng chứng). Thay cho ``nguCanh``. */
  noiDungNguCanh?: ReactNode;
  /** Nội dung chi tiết, chỉ hiện khi mở hộp thoại. */
  chiTiet?: ReactNode;
  nhanChiTiet?: string;
  /** Tiêu đề cột phải — đổi khi nội dung là ngữ cảnh cấp cho mô hình. */
  tieuDeNguCanh?: string;
  /** Huy hiệu cạnh tiêu đề (ví dụ nhánh đã chạy). */
  huyHieuNguCanh?: ReactNode;
}) {
  return (
    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
      <section
        aria-label="Câu trả lời"
        className="flex min-w-0 flex-col rounded-lg border border-border-color bg-card-surface shadow-sm"
      >
        <header className="flex items-center justify-between gap-2 border-b border-border-color px-4 py-2.5">
          <h3 className="flex items-center gap-2 text-sm font-bold">
            <Icon name="chat" className="text-[18px] text-primary" />
            Câu trả lời
          </h3>
          {traLoi ? <Badge tone="ok">Đã sinh</Badge> : <Badge tone="muted">Chưa bật</Badge>}
        </header>

        <div className="min-w-0 flex-1 px-4 py-3">
          {traLoi ? (
            <RichText text={traLoi} className="text-sm leading-7 text-text-primary" />
          ) : (
            <div className="rounded-lg border border-dashed border-border-color bg-secondary-surface px-3 py-6 text-center">
              <p className="text-sm font-semibold text-text-secondary">Chưa có câu trả lời</p>
              {ghiChuTraLoi ? (
                <p className="mx-auto mt-1 max-w-prose text-xs leading-6 text-text-secondary">
                  {ghiChuTraLoi}
                </p>
              ) : null}
            </div>
          )}

          {nguon?.length ? (
            <div className="mt-3 border-t border-border-color pt-2.5">
              <p className="text-xs font-semibold text-text-secondary">Nguồn</p>
              <ul className="mt-1 space-y-1">
                {nguon.map((mot, i) => (
                  <li key={`${mot.nhan}-${i}`} className="text-xs">
                    {mot.url ? (
                      <a
                        href={mot.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-semibold text-primary hover:underline"
                      >
                        {mot.nhan}
                        <Icon name="open_in_new" className="text-[14px]" />
                      </a>
                    ) : (
                      <span className="font-semibold text-text-secondary">{mot.nhan}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </section>

      <section
        aria-label="Ngữ cảnh và quyết định"
        className="flex min-w-0 flex-col rounded-lg border border-border-color bg-card-surface shadow-sm"
      >
        <header className="flex items-center justify-between gap-2 border-b border-border-color px-4 py-2.5">
          <h3 className="flex items-center gap-2 text-sm font-bold">
            <Icon name="account_tree" className="text-[18px] text-text-secondary" />
            {tieuDeNguCanh}
            {huyHieuNguCanh}
          </h3>
          {chiTiet ? <ChiTietModal nhan={nhanChiTiet}>{chiTiet}</ChiTietModal> : null}
        </header>

        {noiDungNguCanh ? (
          /**
           * Ngữ cảnh hiện **đầy đủ, không cần bấm** — đó là thứ quyết định câu trả lời đúng
           * hay sai, nên nó phải nhìn thấy được ngay. Chỉ giới hạn **chiều cao khung** để
           * trang không dài hàng chục màn hình khi nhánh lai trả về 50 đoạn văn; nội dung
           * bên trong vẫn nguyên vẹn và cuộn được, không cắt dòng nào.
           */
          <div className="max-h-[36rem] overflow-y-auto">{noiDungNguCanh}</div>
        ) : (
          <dl className="divide-y divide-border-color px-4">
            {nguCanh.length ? (
              nguCanh.map((dong) => (
                <div
                  key={dong.label}
                  className="flex items-baseline justify-between gap-3 py-2 text-sm"
                >
                  <dt className="shrink-0 text-text-secondary">{dong.label}</dt>
                  <dd className="min-w-0 text-right font-semibold text-text-primary">
                    {dong.tone ? <Badge tone={dong.tone}>{dong.value}</Badge> : dong.value}
                  </dd>
                </div>
              ))
            ) : (
              <div className="py-3 text-sm text-text-secondary">Không có số liệu.</div>
            )}
          </dl>
        )}
      </section>
    </div>
  );
}

/**
 * Hiển thị câu trả lời của mô hình.
 *
 * Mô hình trả văn bản thuần có gạch đầu dòng và `**in đậm**`. Hiện nguyên văn thì người đọc
 * thấy cả dấu sao — trông như lỗi. Ở đây chỉ xử lý đúng hai thứ đó, cố ý **không** dựng
 * markdown đầy đủ: nội dung này do mô hình sinh, không phải tài liệu.
 */
/** Hộp thoại chi tiết: mở bằng nút, đóng bằng Esc, nút đóng, hoặc bấm ra ngoài. */
function ChiTietModal({ nhan, children }: { nhan: string; children: ReactNode }) {
  const [mo, setMo] = useState(false);

  useEffect(() => {
    if (!mo) return;
    const xuLy = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMo(false);
    };
    document.addEventListener("keydown", xuLy);
    // Khoá cuộn nền: hộp thoại dài mà nền vẫn cuộn thì rất khó đọc.
    const cu = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", xuLy);
      document.body.style.overflow = cu;
    };
  }, [mo]);

  return (
    <>
      <button
        type="button"
        onClick={() => setMo(true)}
        className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border-color px-2 py-1 text-xs font-bold text-text-secondary transition-colors hover:bg-secondary-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <Icon name="open_in_full" className="text-[15px]" />
        {nhan}
      </button>

      {mo ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 p-4 sm:p-8"
          onClick={() => setMo(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={nhan}
            className="w-full max-w-5xl rounded-xl border border-border-color bg-white shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="sticky top-0 flex items-center justify-between gap-3 rounded-t-xl border-b border-border-color bg-white px-4 py-3">
              <h2 className="text-sm font-bold">{nhan}</h2>
              <button
                type="button"
                onClick={() => setMo(false)}
                className="inline-flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-sm font-semibold text-text-secondary hover:bg-secondary-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <Icon name="close" className="text-[18px]" />
                Đóng
              </button>
            </header>
            <div className="px-4 py-4">{children}</div>
          </div>
        </div>
      ) : null}
    </>
  );
}
