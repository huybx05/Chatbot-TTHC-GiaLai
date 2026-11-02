import { useState } from "react";

import { login, logout, type AuthResponse } from "../../api/auth";

type AdminLoginPageProps = {
  onLogin: (session: AuthResponse) => void;
};

export default function AdminLoginPage({ onLogin }: AdminLoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!username.trim() || !password) {
      setError("Vui lòng nhập tên đăng nhập và mật khẩu.");
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      const session = await login(username.trim(), password);
      if (session.user.role !== "admin") {
        // Đăng nhập client đã set cookie refresh_token; phải thu hồi ngay,
        // nếu không trình duyệt vẫn giữ một phiên client dù không vào được admin.
        try {
          await logout();
        } catch {
          // Lỗi thu hồi không được che mất thông báo "không có quyền".
        }
        setError("Tài khoản này không có quyền truy cập trang quản trị.");
        return;
      }
      onLogin(session);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể đăng nhập.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-main-bg px-5 py-8 text-text-primary">
      <main className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3">
          <img
            src="/logo.png"
            alt="ChatTTHC"
            className="size-12 rounded-xl bg-card-surface object-contain p-2 shadow-sm ring-1 ring-border-color"
          />
          <div>
            <p className="text-lg font-bold">Chat TTHC Admin</p>
            <p className="text-sm text-text-secondary">Giám sát hệ thống nội bộ</p>
          </div>
        </div>

            <form className="rounded-2xl border border-border-color bg-card-surface p-6 shadow-sm" onSubmit={handleSubmit}>
              <div className="mb-6">
                <p className="text-sm font-bold uppercase text-primary">Đăng nhập</p>
              </div>

              <label className="block text-sm font-semibold" htmlFor="admin-username">
                Tên đăng nhập
              </label>
              <div className="mt-2 flex items-center gap-2 rounded-xl border border-border-color bg-secondary-surface px-3 py-2.5">
                <span className="material-symbols-outlined text-[20px] text-primary">person</span>
                <input
                  autoComplete="username"
                  id="admin-username"
                  className="w-full bg-transparent text-sm outline-none placeholder:text-text-secondary/70"
                  onChange={(event) => setUsername(event.target.value)}
                  type="text"
                  value={username}
                />
              </div>

              <label className="mt-4 block text-sm font-semibold" htmlFor="admin-password">
                Mật khẩu
              </label>
              <div className="mt-2 flex items-center gap-2 rounded-xl border border-border-color bg-secondary-surface px-3 py-2.5">
                <span className="material-symbols-outlined text-[20px] text-primary">lock</span>
                <input
                  id="admin-password"
                  className="w-full bg-transparent text-sm outline-none placeholder:text-text-secondary/70"
                  autoComplete="current-password"
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  value={password}
                />
              </div>

              {error ? <p className="mt-4 text-sm font-medium text-danger" role="alert">{error}</p> : null}

              <button
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isSubmitting}
                type="submit"
              >
                {isSubmitting ? "Đang đăng nhập..." : "Đăng nhập"}
              </button>

              <a
                className="mt-4 flex items-center justify-center gap-2 text-sm font-semibold text-text-secondary hover:text-primary"
                href="/"
              >
                Quay lại chatbot
              </a>
            </form>
      </main>
    </div>
  );
}
