import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

/**
 * Endpoint backend cần chuyển tiếp khi chạy dev.
 *
 * Lưu ý: KHÔNG đưa "/admin" vào đây. "/admin" là route giao diện phía frontend;
 * API monitoring nằm dưới "/api/admin" để hai bên không đụng nhau.
 */
const API_PREFIXES = ["/chat", "/search", "/procedures", "/api/admin", "/health"];

const BACKEND_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      API_PREFIXES.map((prefix) => [prefix, { target: BACKEND_TARGET, changeOrigin: true }]),
    ),
  },
});
