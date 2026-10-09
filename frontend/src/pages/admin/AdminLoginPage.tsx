type AdminLoginPageProps = {
  onLogin: () => void;
};

export default function AdminLoginPage({ onLogin }: AdminLoginPageProps) {
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

            <form
              className="rounded-2xl border border-border-color bg-card-surface p-6 shadow-sm"
              onSubmit={(event) => {
                event.preventDefault();
                onLogin();
              }}
            >
              <div className="mb-6">
                <p className="text-sm font-bold uppercase text-primary">Đăng nhập</p>
              </div>

              <label className="block text-sm font-semibold" htmlFor="admin-email">
                Tài khoản
              </label>
              <div className="mt-2 flex items-center gap-2 rounded-xl border border-border-color bg-secondary-surface px-3 py-2.5">
                <span className="material-symbols-outlined text-[20px] text-primary">person</span>
                <input
                  id="admin-email"
                  className="w-full bg-transparent text-sm outline-none placeholder:text-text-secondary/70"
                  defaultValue="admin@tthc.local"
                  type="text"
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
                  defaultValue="monitoring"
                  type="password"
                />
              </div>

              <button
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-primary-hover"
                type="submit"
              >
                Đăng nhập
                
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
