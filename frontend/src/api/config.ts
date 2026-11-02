/** Cấu hình dùng chung cho tầng gọi API. */

/** Base URL của backend. Dev dùng Vite proxy nên để rỗng. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/** Prefix phiên bản API được backend khai báo tại `settings.api_v1_prefix`. */
export const API_V1_URL = `${API_BASE_URL}/api/v1`;

export const REQUEST_TIMEOUT_MS = 30_000;

/** Giao diện người dân hay admin — dùng để đổi cách xử lý lỗi/hiển thị. */
export type AppMode = "client" | "admin";

export function resolveMode(pathname: string): AppMode {
  return pathname.startsWith("/admin") ? "admin" : "client";
}
