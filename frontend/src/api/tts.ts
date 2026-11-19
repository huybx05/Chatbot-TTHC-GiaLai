import { API_V1_URL } from "./config";
import { ApiError } from "./http";

/**
 * Gọi backend để đổi một đoạn văn bản thành audio.
 *
 * Không gọi thẳng VieNeu từ trình duyệt: API key phải nằm ở server.
 */
export async function synthesizeSpeech(
  text: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(`${API_V1_URL}/tts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!response.ok) {
    let message = "Không tạo được âm thanh cho câu trả lời này.";
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail;
      }
    } catch {
      // Body không phải JSON: giữ thông điệp mặc định.
    }
    throw new ApiError(message, response.status);
  }

  return response.blob();
}
