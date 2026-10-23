import { type ReactNode } from "react";

/**
 * Hiển thị văn bản do mô hình sinh: `**in đậm**` và các dòng `- gạch đầu dòng`.
 *
 * Cố ý **không** dựng markdown đầy đủ: nội dung này là câu trả lời cho người dân, không phải
 * tài liệu. Mô hình chỉ dùng đúng hai kiểu nhấn mạnh đó, nên xử lý hai kiểu đó là đủ — và giữ
 * cho mọi chỗ hiển thị câu trả lời (trang quản trị và giao diện người dân) trông giống nhau.
 */
export function RichText({ text, className = "" }: { text: string; className?: string }) {
  return <div className={className}>{dinh_dang(text)}</div>;
}

function dinh_dang(van_ban: string): ReactNode {
  const dong = van_ban.split("\n");
  const khoi: ReactNode[] = [];
  let gach_dau_dong: string[] = [];

  const xong_danh_sach = () => {
    if (!gach_dau_dong.length) return;
    khoi.push(
      <ul key={`ds-${khoi.length}`} className="my-1 list-disc space-y-1 pl-5">
        {gach_dau_dong.map((muc, i) => (
          <li key={i}>{in_dam(muc)}</li>
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
        {in_dam(chu)}
      </p>,
    );
  }
  xong_danh_sach();
  return khoi;
}

/** Chỉ đổi `**chữ**` thành in đậm — mô hình dùng đúng một kiểu nhấn mạnh. */
function in_dam(chu: string): ReactNode {
  const phan = chu.split(/\*\*(.+?)\*\*/g);
  if (phan.length === 1) return chu;
  return phan.map((mot, i) => (i % 2 === 1 ? <strong key={i}>{mot}</strong> : mot));
}
