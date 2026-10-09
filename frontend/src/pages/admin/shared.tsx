import type { ReactNode } from "react";

export type BadgeTone = "ok" | "warn" | "bad" | "info" | "muted";

export const procedures = [
  {
    code: "1.014100",
    name: "Cấp lại Chứng chỉ hành nghề dược theo hình thức xét hồ sơ",
    domain: "15. Y_TE_SUC_KHOE",
    source: "Dược phẩm",
    fee: "SO_TIEN",
    time: "SO",
    chunks: 9,
  },
  {
    code: "1.115349",
    name: "Đăng ký đất đai lần đầu đối với trường hợp được Nhà nước giao đất để quản lý",
    domain: "10. TAI_NGUYEN_MOI_TRUONG",
    source: "Đất đai",
    fee: "THEO_QUY_DINH_CHUNG",
    time: "SO",
    chunks: 12,
  },
  {
    code: "2.002621",
    name: "Đăng ký khai sinh, đăng ký thường trú, cấp thẻ BHYT cho trẻ em dưới 6 tuổi",
    domain: "11. TU_PHAP_BO_TRO",
    source: "Hộ tịch",
    fee: "MIEN_PHI",
    time: "SO",
    chunks: 11,
  },
];

export const chunkRows = [
  ["overview", "Thông tin chung", "READY", "612 ký tự"],
  ["dossier", "Thành phần hồ sơ", "READY", "1.420 ký tự"],
  ["fee", "Phí, lệ phí", "READY", "318 ký tự"],
  ["legal_basis", "Căn cứ pháp lý", "Cảnh báo", "2.940 ký tự"],
];

export const pipelineSteps = [
  ["Đọc JSON normalized", "Thành công", "1.955 / 1.955", "18s"],
  ["Validate schema", "Thành công", "0 lỗi", "7s"],
  ["Sinh chunk production", "Thành công", "1.955 thủ tục", "04m 18s"],
  ["Ghi chunks JSONL", "Thành công", "18.420 chunk", "21s"],
  ["Index PostgreSQL", "Thành công", "18.420 row", "32s"],
  ["Index Elasticsearch", "Cảnh báo", "18.419 doc", "41s"],
  ["Index Qdrant", "Thành công", "18.420 vector", "02m 09s"],
  ["Index Neo4j", "Thành công", "6.734 relationship", "54s"],
];

export const logs = [
  ["10:42:11", "WARN", "Elasticsearch", "Index production thiếu 1 document so với chunks.jsonl", "Chưa xử lý"],
  ["10:39:04", "ERROR", "Reranker", "Timeout khi gọi endpoint rerank sau 15s", "Chưa xử lý"],
  ["10:28:33", "INFO", "Pipeline", "Validate production hoàn tất: 1.955 READY", "Đã xử lý"],
  ["09:58:15", "WARN", "Neo4j", "THU_TUC_LIEN_QUAN chỉ có 3 bản ghi có dữ liệu thật", "Đã ghi nhận"],
];

export const graphNodes = [
  ["TTHC", "1.955", "info"],
  ["Căn cứ pháp lý", "5.000+", "info"],
  ["Lĩnh vực", "124", "ok"],
  ["Cơ quan", "312", "warn"],
  ["Nhóm domain", "15", "muted"],
];

export const qaRows = [
  {
    question: "Làm hộ chiếu phổ thông lần đầu cần chuẩn bị giấy tờ gì?",
    answer: "Cần tờ khai, giấy tờ tùy thân và hồ sơ theo nhóm thủ tục xuất nhập cảnh.",
    domain: "Xuất nhập cảnh",
    source: "1.003390",
    status: "Published",
    split: "Cache",
    score: "0.94",
  },
  {
    question: "Cấp lại căn cước công dân bị mất mất bao lâu?",
    answer: "Thời hạn phụ thuộc thủ tục căn cước cụ thể và nơi tiếp nhận hồ sơ.",
    domain: "Cư trú - căn cước",
    source: "1.013314",
    status: "Review",
    split: "Cache",
    score: "0.89",
  },
  {
    question: "Đăng ký khai sinh cho trẻ dưới 6 tuổi gồm những bước nào?",
    answer: "Thủ tục liên thông gồm đăng ký khai sinh, đăng ký thường trú và cấp thẻ BHYT.",
    domain: "Hộ tịch",
    source: "2.002621",
    status: "Published",
    split: "Eval holdout",
    score: "0.96",
  },
];

export function Icon({ name, className = "text-[20px]" }: { name: string; className?: string }) {
  return <span className={`material-symbols-outlined ${className}`}>{name}</span>;
}

export function toneClass(tone: BadgeTone) {
  return {
    ok: "bg-[#E7F4EC] text-[#2E7D4F] border-[#B8DDC6]",
    warn: "bg-[#FFF3D6] text-[#9A6100] border-[#E7C66D]",
    bad: "bg-danger-surface text-danger border-[#E6B8B2]",
    info: "bg-[#E7F0FA] text-[#2563A8] border-[#B6CDE6]",
    muted: "bg-secondary-surface text-text-secondary border-border-color",
  }[tone];
}

export function Badge({ children, tone = "muted" }: { children: string; tone?: BadgeTone }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClass(tone)}`}>
      {children}
    </span>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: string;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <p className="text-xs font-bold uppercase tracking-wide text-primary">{eyebrow}</p>
        <h2 className="mt-1 text-2xl font-bold tracking-tight text-text-primary">{title}</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-text-secondary">{description}</p>
      </div>
      {action ? (
        <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white shadow-sm hover:bg-primary-hover">
          <Icon name="play_arrow" />
          {action}
        </button>
      ) : null}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-border-color bg-card-surface p-4 shadow-sm ${className}`}>{children}</section>;
}

export function MetricCard({
  icon,
  label,
  value,
  note,
  tone = "info",
}: {
  icon: string;
  label: string;
  value: string;
  note: string;
  tone?: BadgeTone;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
          <p className="mt-2 text-2xl font-bold">{value}</p>
          <p className="mt-1 text-sm text-text-secondary">{note}</p>
        </div>
        <div className={`flex size-10 items-center justify-center rounded-lg border ${toneClass(tone)}`}>
          <Icon name={icon} />
        </div>
      </div>
    </Card>
  );
}

export function SectionTitle({ title, note }: { title: string; note?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-base font-bold">{title}</h3>
      {note ? <p className="mt-1 text-sm text-text-secondary">{note}</p> : null}
    </div>
  );
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 rounded-full bg-secondary-surface">
      <div className="h-2 rounded-full bg-primary" style={{ width: `${value}%` }} />
    </div>
  );
}

export function statusTone(status: string): BadgeTone {
  if (["READY", "Thành công", "Online", "Khớp", "Đã xử lý"].includes(status)) return "ok";
  if (["Cảnh báo", "WARN", "Đang chạy", "Chưa xử lý"].includes(status)) return "warn";
  if (["ERROR", "Lỗi", "Lệch"].includes(status)) return "bad";
  if (["INFO", "Chưa chạy", "Đã ghi nhận"].includes(status)) return "info";
  return "muted";
}
