import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "./config";

/** Lỗi HTTP đã chuẩn hóa để UI không phải đọc chi tiết kỹ thuật. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type HttpMethod = "GET" | "POST" | "PATCH";

export async function request<T>(
  path: string,
  init: { method?: HttpMethod; body?: unknown; timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), init.timeoutMs ?? REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method ?? "GET",
      headers: init.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });

    if (!response.ok) {
      // Đọc `detail` từ body lỗi của FastAPI để hiện đúng nguyên nhân.
      //
      // Trước đây chỗ này ném một câu chung "Không thể xử lý yêu cầu lúc này.",
      // nên thông báo như "Chế độ 'hybrid' chưa triển khai" bị nuốt mất và trang
      // kiểm thử chỉ hiện lỗi vô nghĩa. Vẫn giữ câu chung làm dự phòng khi body
      // không phải JSON hoặc không có `detail`.
      let message = "Không thể xử lý yêu cầu lúc này.";
      try {
        const payload = (await response.json()) as { detail?: unknown };
        if (typeof payload.detail === "string" && payload.detail.trim()) {
          message = payload.detail;
        }
      } catch {
        // body không phải JSON — dùng câu chung
      }
      throw new ApiError(message, response.status);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError("Không thể kết nối tới máy chủ.", 0);
  } finally {
    window.clearTimeout(timeout);
  }
}
