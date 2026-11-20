import { type ReactNode } from "react";

import type { ProcedureDocument } from "../data/chatTypes";

/**
 * Hiển thị văn bản do mô hình sinh: `**in đậm**` và các dòng `- gạch đầu dòng`.
 *
 * Ngoài ra marker `{{file:<id>}}` được render thành chip tải mẫu nếu frontend có
 * metadata file tương ứng. Marker không có metadata bị bỏ, không hiện id thô.
 */
export function RichText({
  text,
  className = "",
  fileMap,
}: {
  text: string;
  className?: string;
  fileMap?: Record<string, ProcedureDocument>;
}) {
  return <div className={className}>{dinh_dang(text, fileMap)}</div>;
}

function FileChip({
  file,
  fileName,
}: {
  file: ProcedureDocument;
  fileName?: string;
}) {
  return (
    <a
      href={file.download_url}
      download={file.file_name}
      className="ml-2 inline-flex items-center gap-1 align-middle text-[12px] font-medium text-primary no-underline transition-colors hover:bg-orange-50 hover:text-orange-700"
      title={`Tải ${fileName || file.file_name}`}
    >
      <span className="flex h-3 w-3 shrink-0 items-center justify-center">
        <span className="material-symbols-outlined text-[12px] leading-none">download</span>
      </span>
      <span className="underline decoration-primary/40 underline-offset-2">
        Tải biểu mẫu
      </span>
      <span className="text-text-primary no-underline">
        — {fileName || file.file_name}
      </span>
    </a>
  );
}

function render_inline(
  chu: string,
  fileMap?: Record<string, ProcedureDocument>,
  keyPrefix = "",
): ReactNode[] {
  const parts = chu.split(/(\*\*[^*]+\*\*|\{\{file:[^}]+\}\})/g);
  return parts
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={`${keyPrefix}-bold-${index}`}>{part.slice(2, -2)}</strong>;
      }
      const marker = part.match(/^\{\{file:([^}]+)\}\}$/);
      if (marker) {
        const file = fileMap?.[marker[1]];
        return file ? (
          <FileChip key={`${keyPrefix}-file-${marker[1]}-${index}`} file={file} />
        ) : null;
      }
      return <span key={`${keyPrefix}-text-${index}`}>{part}</span>;
    })
    .filter((part) => part !== null);
}

function render_text(
  chu: string,
  fileMap?: Record<string, ProcedureDocument>,
): ReactNode {
  // Một dòng có thể chứa NHIỀU cụm "File mẫu: {{file:id}} — tên file".
  // Không dùng regex neo `$` cho cả dòng: tên file sẽ nuốt luôn các marker phía sau.
  const attachment = /File mẫu:\s*\{\{file:([^}]+)\}\}\s*[—–-]\s*(.*?)(?=\s+File mẫu:|$)/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = attachment.exec(chu)) !== null) {
    if (match.index > cursor) {
      nodes.push(...render_inline(chu.slice(cursor, match.index), fileMap, `before-${index}`));
    }

    const fileId = match[1];
    const fileName = match[2].trim();
    const file = fileMap?.[fileId];
    nodes.push(
      file ? (
        <FileChip key={`attachment-${fileId}-${index}`} file={file} fileName={fileName} />
      ) : (
        <span key={`attachment-text-${fileId}-${index}`}>{fileName}</span>
      ),
    );

    cursor = attachment.lastIndex;
    index += 1;
  }

  if (cursor < chu.length) {
    nodes.push(...render_inline(chu.slice(cursor), fileMap, "tail"));
  }

  return nodes.length ? nodes : chu;
}

function dinh_dang(
  van_ban: string,
  fileMap?: Record<string, ProcedureDocument>,
): ReactNode {
  const dong = van_ban.split("\n");
  const khoi: ReactNode[] = [];
  let gach_dau_dong: string[] = [];

  const xong_danh_sach = () => {
    if (!gach_dau_dong.length) return;
    khoi.push(
      <ul key={`ds-${khoi.length}`} className="my-1 list-disc space-y-1 pl-5">
        {gach_dau_dong.map((muc, i) => (
          <li key={i}>{render_text(muc, fileMap)}</li>
        ))}
      </ul>,
    );
    gach_dau_dong = [];
  };

  for (const mot of dong) {
    const chu = mot.trimEnd();
    if (/^\s*[-•*]\s+/.test(chu)) {
      gach_dau_dong.push(chu.replace(/^\s*[-•*]\s+/, ""));
      continue;
    }
    xong_danh_sach();
    if (!chu.trim()) continue;
    khoi.push(
      <p key={`p-${khoi.length}`} className="my-1">
        {render_text(chu, fileMap)}
      </p>,
    );
  }
  xong_danh_sach();
  return khoi;
}
