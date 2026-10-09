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
  init: { method?: HttpMethod; body?: unknown } = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method ?? "GET",
      headers: init.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new ApiError("Không thể xử lý yêu cầu lúc này.", response.status);
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
