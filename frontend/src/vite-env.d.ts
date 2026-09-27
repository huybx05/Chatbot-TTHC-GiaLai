/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL của backend. Để trống khi dev vì Vite proxy đã chuyển tiếp /chat, /search, /procedures, /admin. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
