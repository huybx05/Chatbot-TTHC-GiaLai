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

function render_text(
  chu: string,
  fileMap?: Record<string, ProcedureDocument>,
): ReactNode {
  // Một số câu trả lời chèn nguyên cụm "File mẫu: {{file:id}} — tên file".
  // Gộp cả cụm thành một link để không còn chip "Mẫu" rời và tên file đứng riêng.
  const attachment = chu.match(
    /^(.*?)\s*File mẫu:\s*\{\{file:([^}]+)\}\}\s*[—–-]\s*(.+)$/,
  );
  if (attachment) {
    const [, before, fileId, fileName] = attachment;
    const file = fileMap?.[fileId];
    if (file) {
      return (
        <>
          {before ? render_text(before, fileMap) : null}
          <FileChip file={file} fileName={fileName} />
        </>
      );
    }
  }

  const parts = chu.split(/(\*\*.+?\*\*|\{\{file:[^}]+\}\})/g);
  if (parts.length === 1) return chu;

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    const marker = part.match(/^\{\{file:([^}]+)\}\}$/);
    if (marker) {
      const file = fileMap?.[marker[1]];
      return file ? <FileChip key={index} file={file} /> : null;
    }
    return part;
  });
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
