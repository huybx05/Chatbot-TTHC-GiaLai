import type { ProcedureDocument } from "../../data/chatTypes";

function formatSize(bytes: number | null): string {
  if (bytes === null || bytes <= 0) return "Không rõ dung lượng";

  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileLabel(mimeType: string | null, fileName: string): string {
  const extension = fileName.split(".").pop()?.toLowerCase() ?? "";

  if (extension === "pdf") return "PDF";
  if (extension === "doc" || extension === "docx") return "Word";
  if (extension === "xls" || extension === "xlsx") return "Excel";

  return mimeType?.includes("pdf") ? "PDF" : "Tài liệu";
}

function fileIcon(fileName: string): string {
  const extension = fileName.split(".").pop()?.toLowerCase() ?? "";

  if (extension === "pdf") return "picture_as_pdf";
  if (extension === "xls" || extension === "xlsx") return "table_chart";

  return "description";
}

export function FileAttachment({
  item,
}: {
  item: ProcedureDocument;
}) {
  return (
    <a
      href={item.download_url}
      download={item.file_name}
      aria-label={`Tải ${item.file_name}`}
      className="group flex w-full items-center gap-3 rounded-lg border border-border-color/70 bg-white px-3 py-2.5 text-left no-underline shadow-sm transition-colors hover:border-primary/50 hover:bg-primary-soft/40"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
        <span className="material-symbols-outlined text-[20px]">
          {fileIcon(item.file_name)}
        </span>
      </span>

      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-medium text-text-primary">
          {item.file_name}
        </span>
        <span className="mt-0.5 block text-[11.5px] text-text-secondary">
          {fileLabel(item.mime_type, item.file_name)}
          {" · "}
          {formatSize(item.size_bytes)}
        </span>
      </span>

      <span className="flex shrink-0 items-center gap-1 text-[12px] font-medium text-primary">
        <span className="material-symbols-outlined text-[18px]">
          download
        </span>
        <span className="hidden sm:inline">Tải mẫu</span>
      </span>
    </a>
  );
}

export function FileList({ items }: { items: ProcedureDocument[] }) {
  if (items.length === 0) return null;

  const unique = items.filter(
    (item, index) => items.findIndex((other) => other.id === item.id) === index,
  );

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[13px] font-semibold text-text-primary">
        File mẫu
      </span>
      <div className="flex flex-col gap-2">
        {unique.map((item) => (
          <FileAttachment key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
