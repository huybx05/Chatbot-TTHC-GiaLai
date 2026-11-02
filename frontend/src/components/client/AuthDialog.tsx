import { useEffect, useState } from "react";

type AuthMode = "login" | "register";

type AuthDialogProps = {
  onClose: () => void;
  onAuthenticate: (mode: AuthMode, username: string, password: string) => Promise<void>;
};

export default function AuthDialog({ onClose, onAuthenticate }: AuthDialogProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError("");
    setPassword("");
    setConfirmPassword("");
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!username.trim() || !password) {
      setError("Vui lòng nhập tên đăng nhập và mật khẩu.");
      return;
    }

    if (mode === "register" && password !== confirmPassword) {
      setError("Xác nhận mật khẩu chưa khớp.");
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      await onAuthenticate(mode, username.trim(), password);
      onClose();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể thực hiện yêu cầu.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      aria-labelledby="auth-dialog-title"
      aria-modal="true"
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm"
      role="dialog"
    >
      <button
        aria-label="Đóng cửa sổ tài khoản"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        type="button"
      />

      <section className="relative z-10 w-full max-w-[420px] rounded-lg border border-border-color bg-card-surface p-6 shadow-xl">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <img
              alt="Logo trợ lý thủ tục hành chính"
              className="size-10 rounded-lg border border-border-color bg-white object-cover p-1"
              src="/logo.png"
            />
            <div>
              <h2 className="text-[18px] font-semibold text-text-primary" id="auth-dialog-title">
                {mode === "login" ? "Đăng nhập" : "Đăng ký"}
              </h2>
              <p className="mt-0.5 text-sm text-text-secondary">Lưu lại các cuộc trò chuyện của bạn.</p>
            </div>
          </div>
          <button
            aria-label="Đóng"
            className="rounded-md p-1.5 text-text-secondary transition-colors hover:bg-secondary-surface hover:text-text-primary"
            onClick={onClose}
            type="button"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[22px]">close</span>
          </button>
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-md bg-secondary-surface p-1" role="tablist">
          <button
            aria-selected={mode === "login"}
            className={`rounded px-3 py-2 text-sm font-semibold transition-colors ${
              mode === "login" ? "bg-card-surface text-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
            }`}
            onClick={() => changeMode("login")}
            role="tab"
            type="button"
          >
            Đăng nhập
          </button>
          <button
            aria-selected={mode === "register"}
            className={`rounded px-3 py-2 text-sm font-semibold transition-colors ${
              mode === "register" ? "bg-card-surface text-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
            }`}
            onClick={() => changeMode("register")}
            role="tab"
            type="button"
          >
            Đăng ký
          </button>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-text-primary">Tên đăng nhập</span>
            <div className="flex items-center gap-2 rounded-md border border-border-color bg-white px-3 py-2.5 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15">
              <span aria-hidden="true" className="material-symbols-outlined text-[20px] text-text-secondary">person</span>
              <input
                autoComplete="username"
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-text-secondary/65"
                maxLength={64}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Nhập tên đăng nhập"
                value={username}
              />
            </div>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-text-primary">Mật khẩu</span>
            <div className="flex items-center gap-2 rounded-md border border-border-color bg-white px-3 py-2.5 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15">
              <span aria-hidden="true" className="material-symbols-outlined text-[20px] text-text-secondary">lock</span>
              <input
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-text-secondary/65"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Nhập mật khẩu"
                type={showPassword ? "text" : "password"}
                value={password}
              />
              <button
                aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                className="rounded p-0.5 text-text-secondary hover:text-primary"
                onClick={() => setShowPassword((current) => !current)}
                type="button"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
                  {showPassword ? "visibility_off" : "visibility"}
                </span>
              </button>
            </div>
          </label>

          {mode === "register" ? (
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold text-text-primary">Xác nhận mật khẩu</span>
              <div className="flex items-center gap-2 rounded-md border border-border-color bg-white px-3 py-2.5 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15">
                <span aria-hidden="true" className="material-symbols-outlined text-[20px] text-text-secondary">lock_reset</span>
                <input
                  autoComplete="new-password"
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-text-secondary/65"
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="Nhập lại mật khẩu"
                  type={showPassword ? "text" : "password"}
                  value={confirmPassword}
                />
              </div>
            </label>
          ) : null}

          {error ? <p className="text-sm font-medium text-danger" role="alert">{error}</p> : null}

          <button
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSubmitting}
            type="submit"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[19px]">
              {mode === "login" ? "login" : "person_add"}
            </span>
            {isSubmitting ? "Đang xử lý..." : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
          </button>
        </form>
      </section>
    </div>
  );
}
