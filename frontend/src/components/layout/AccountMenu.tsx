import { useEffect, useRef, useState } from "react";

import {
  updateMyAccount,
  type AuthUser,
} from "../../api/auth";

function initials(username: string): string {
  return username.trim().slice(0, 2).toUpperCase();
}

export default function AccountMenu({
  user,
  onLogout,
  onUserUpdated,
}: {
  user: AuthUser;
  onLogout: () => void;
  onUserUpdated: (user: AuthUser) => void;
}) {
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<"info" | "settings" | null>(null);
  const [username, setUsername] = useState(user.username);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const openSettings = () => {
    setOpen(false);
    setUsername(user.username);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowPassword(false);
    setError("");
    setDialog("settings");
  };

  const openInfo = () => {
    setOpen(false);
    setDialog("info");
  };

  const saveSettings = async () => {
    setError("");
    const nextUsername = username.trim();
    const wantsUsername = nextUsername !== user.username;
    const wantsPassword = newPassword.length > 0;

    if (!currentPassword) {
      setError("Vui lòng nhập mật khẩu hiện tại.");
      return;
    }
    if (!wantsUsername && !wantsPassword) {
      setError("Chưa có thay đổi nào để lưu.");
      return;
    }
    if (wantsUsername && (nextUsername.length < 3 || nextUsername.length > 64)) {
      setError("Tên đăng nhập phải có từ 3 đến 64 ký tự.");
      return;
    }
    if (wantsPassword && newPassword !== confirmPassword) {
      setError("Mật khẩu mới và xác nhận mật khẩu không khớp.");
      return;
    }

    setSaving(true);
    try {
      const result = await updateMyAccount({
        current_password: currentPassword,
        username: wantsUsername ? nextUsername : undefined,
        new_password: wantsPassword ? newPassword : undefined,
      });
      if (wantsPassword) {
        window.alert("Đổi mật khẩu thành công. Vui lòng đăng nhập lại.");
        onLogout();
        return;
      }
      onUserUpdated(result.user);
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không lưu được thay đổi.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-3 rounded-lg bg-sidebar-bg px-3 py-2.5 text-left transition-colors hover:bg-hover-item"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-[12px] font-bold text-white">
          {initials(user.username)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold text-text-primary">
            {user.username}
          </span>
          <span className="block text-[11px] text-text-secondary">
            {user.role === "admin" ? "Quản trị viên" : "Người dùng"}
          </span>
        </span>
        <span className="material-symbols-outlined text-[18px] text-text-secondary">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute bottom-full left-0 right-0 z-40 mb-2 overflow-hidden rounded-xl border border-border-color bg-card-surface p-1.5 shadow-xl"
        >
          <button
            type="button"
            role="menuitem"
            onClick={openInfo}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-medium text-text-primary hover:bg-hover-item"
          >
            <span className="material-symbols-outlined text-[18px]">person</span>
            Thông tin tài khoản
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={openSettings}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-medium text-text-primary hover:bg-hover-item"
          >
            <span className="material-symbols-outlined text-[18px]">settings</span>
            Cài đặt tài khoản
          </button>
          <div className="my-1 border-t border-border-color/70" />
          <button
            type="button"
            role="menuitem"
            onClick={onLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-semibold text-danger hover:bg-danger-surface"
          >
            <span className="material-symbols-outlined text-[18px]">logout</span>
            Đăng xuất
          </button>
        </div>
      ) : null}

      {dialog === "info" ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="account-info-title"
          onMouseDown={() => setDialog(null)}
        >
          <section
            className="w-full max-w-md rounded-xl border border-border-color bg-card-surface p-5 shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                  Tài khoản
                </p>
                <h3 id="account-info-title" className="mt-1 text-lg font-bold">
                  Thông tin tài khoản
                </h3>
              </div>
              <button
                type="button"
                aria-label="Đóng"
                onClick={() => setDialog(null)}
                className="rounded-md px-2 py-1 text-xl leading-none text-text-secondary hover:bg-hover-item"
              >
                ×
              </button>
            </div>
            <dl className="mt-5 space-y-3 text-sm">
              <div className="flex justify-between gap-4 border-b border-border-color/60 pb-3">
                <dt className="text-text-secondary">Tên đăng nhập</dt>
                <dd className="font-semibold">{user.username}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-border-color/60 pb-3">
                <dt className="text-text-secondary">Vai trò</dt>
                <dd className="font-semibold">
                  {user.role === "admin" ? "Quản trị viên" : "Người dùng"}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-text-secondary">Mã tài khoản</dt>
                <dd className="font-semibold">#{user.id}</dd>
              </div>
            </dl>
          </section>
        </div>
      ) : null}

      {dialog === "settings" ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="account-settings-title"
          onMouseDown={() => setDialog(null)}
        >
          <section
            className="w-full max-w-lg rounded-xl border border-border-color bg-card-surface p-5 shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                  Tài khoản
                </p>
                <h3 id="account-settings-title" className="mt-1 text-lg font-bold">
                  Cài đặt tài khoản
                </h3>
              </div>
              <button
                type="button"
                aria-label="Đóng"
                onClick={() => setDialog(null)}
                className="rounded-md px-2 py-1 text-xl leading-none text-text-secondary hover:bg-hover-item"
              >
                ×
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <label className="block text-xs font-semibold text-text-secondary">
                Tên đăng nhập
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
                />
              </label>

              <div className="border-t border-border-color/70 pt-4">
                <p className="text-xs font-semibold text-text-secondary">
                  Đổi mật khẩu
                </p>
                <label className="mt-3 block text-xs font-semibold text-text-secondary">
                  Mật khẩu hiện tại
                  <input
                    type={showPassword ? "text" : "password"}
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    autoComplete="current-password"
                    className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
                  />
                </label>
                <label className="mt-3 block text-xs font-semibold text-text-secondary">
                  Mật khẩu mới
                  <input
                    type={showPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    autoComplete="new-password"
                    className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
                  />
                </label>
                <label className="mt-3 block text-xs font-semibold text-text-secondary">
                  Nhập lại mật khẩu mới
                  <input
                    type={showPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    autoComplete="new-password"
                    className="mt-1.5 w-full rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
                  />
                </label>
                <label className="mt-3 flex items-center gap-2 text-xs font-medium text-text-secondary">
                  <input
                    type="checkbox"
                    checked={showPassword}
                    onChange={(event) => setShowPassword(event.target.checked)}
                    className="accent-primary"
                  />
                  Hiện mật khẩu
                </label>
              </div>

              {error ? (
                <p role="alert" className="text-xs font-semibold text-danger">
                  {error}
                </p>
              ) : null}

              <div className="flex justify-end gap-2 border-t border-border-color/70 pt-4">
                <button
                  type="button"
                  onClick={() => setDialog(null)}
                  className="rounded-md px-3 py-2 text-sm font-semibold text-text-secondary hover:bg-hover-item"
                >
                  Hủy
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void saveSettings()}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-hover disabled:opacity-50"
                >
                  {saving ? "Đang lưu…" : "Lưu thay đổi"}
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
