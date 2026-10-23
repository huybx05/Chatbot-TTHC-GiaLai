import type { ChatRequest, ChatResponse } from "../types/chat";
import { API_BASE_URL } from "./config";
import { request } from "./http";

/** POST /chat — gửi câu hỏi, nhận câu trả lời kèm citation (dùng cho trang quản trị). */
export function askChat(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", { method: "POST", body: payload, timeoutMs: 90_000 });
}

/** Kết quả của một lượt stream — đủ để dựng lại đúng khung chat như đường không stream. */
export interface StreamKetQua {
  answer: string;
  meta: {
    status: "answered" | "clarify" | "abstained";
    procedure: { procedure_code: string; procedure_name: string } | null;
    citations: { title: string; url: string; section: string }[];
    options: { value: string; label: string; hint?: string }[];
    /** `true` = câu trả lời phát lại từ cache (không gọi mô hình lần này). */
    cached?: boolean;
  } | null;
  /** `false` = mô hình không phát mẩu nào (câu hỏi lại, từ chối, hoặc lỗi) — chữ đến một lần. */
  streamed: boolean;
}

/**
 * Gọi `POST /chat/stream` và phát từng mẩu chữ cho nơi gọi.
 *
 * Vì sao không dùng `EventSource`: nó chỉ gửi được GET, mà câu hỏi phải nằm trong body. Nên đọc
 * luồng bằng `fetch` rồi tự tách khung SSE — định dạng chỉ có hai dòng `event:` và `data:`.
 *
 * Trả về kết quả đầy đủ sau khi luồng đóng, để giao diện chốt lại lần cuối (đề phòng mẩu cuối
 * bị mất do mạng đứt).
 */
export async function askChatStream(
  payload: ChatRequest,
  hooks: {
    onMeta?: (meta: NonNullable<StreamKetQua["meta"]>) => void;
    onDelta?: (text: string) => void;
    signal?: AbortSignal;
  } = {},
): Promise<StreamKetQua> {
  const phan_hoi = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal: hooks.signal,
  });

  if (!phan_hoi.ok || !phan_hoi.body) {
    // Lỗi ở tầng HTTP (422/429/503) — đọc `detail` như đường không stream để hiện đúng nguyên nhân.
    let thong_diep = `Máy chủ trả lỗi ${phan_hoi.status}.`;
    try {
      const du_lieu = (await phan_hoi.json()) as { detail?: unknown };
      if (typeof du_lieu.detail === "string" && du_lieu.detail.trim()) {
        thong_diep = du_lieu.detail;
      }
    } catch {
      // body không phải JSON — giữ thông điệp mặc định
    }
    throw new Error(thong_diep);
  }

  const ket_qua: StreamKetQua = { answer: "", meta: null, streamed: false };
  const doc = phan_hoi.body.getReader();
  const giai_ma = new TextDecoder();
  let dem = "";

  const xu_ly_khung = (khung: string) => {
    let ten = "";
    let du_lieu = "";
    for (const dong of khung.split("\n")) {
      if (dong.startsWith("event: ")) ten = dong.slice(7).trim();
      else if (dong.startsWith("data: ")) du_lieu += dong.slice(6);
    }
    if (!ten || !du_lieu) return;

    const da_doc = JSON.parse(du_lieu) as Record<string, unknown>;
    if (ten === "meta") {
      ket_qua.meta = da_doc as unknown as StreamKetQua["meta"];
      hooks.onMeta?.(ket_qua.meta as NonNullable<StreamKetQua["meta"]>);
    } else if (ten === "delta") {
      const manh = String(da_doc.text ?? "");
      ket_qua.answer += manh;
      hooks.onDelta?.(manh);
    } else if (ten === "done") {
      // `done` là bản chốt: nếu nội dung lệch với những gì đã nhận, tin bản chốt.
      ket_qua.answer = String(da_doc.answer ?? ket_qua.answer);
      ket_qua.streamed = Boolean(da_doc.streamed);
    } else if (ten === "error") {
      throw new Error(String(da_doc.message ?? "Luồng trả lời bị đứt."));
    }
  };

  for (;;) {
    const { done, value } = await doc.read();
    if (done) break;
    dem += giai_ma.decode(value, { stream: true });
    // Khung SSE ngăn nhau bằng một dòng trống.
    let vi_tri = dem.indexOf("\n\n");
    while (vi_tri >= 0) {
      xu_ly_khung(dem.slice(0, vi_tri));
      dem = dem.slice(vi_tri + 2);
      vi_tri = dem.indexOf("\n\n");
    }
  }
  if (dem.trim()) xu_ly_khung(dem);

  return ket_qua;
}
