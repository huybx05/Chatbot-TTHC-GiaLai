import { useEffect, useState } from "react";

import {
  createManagedUser,
  deleteManagedUser,
  listManagedUsers,
  type ManagedUser,
  updateManagedUser,
} from "../../api/adminUsers";
import { Badge, Card, Icon, PageHeader } from "./shared";

type UserForm = {
  username: string;
  password: string;
  role: "client" | "admin";
  is_active: boolean;
};

const EMPTY_FORM: UserForm = { username: "", password: "", role: "client", is_active: true };

function roleLabel(role: ManagedUser["role"]) {
  return role === "admin" ? "Quản trị viên" : "Người dùng";
}

function formatLastSeen(value: string | null) {
  if (!value) return "Chưa đăng nhập";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function UsersPage() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<UserForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const dialogOpen = creating || editingUser !== null;

  const loadUsers = async () => {
    setLoading(true);
    try {
      setUsers(await listManagedUsers());
      setError("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể tải danh sách tài khoản.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadUsers(); }, []);

  const closeDialog = () => {
    if (submitting) return;
    setCreating(false);
    setEditingUser(null);
    setForm(EMPTY_FORM);
  };

  const openCreateDialog = () => {
    setCreating(true);
    setEditingUser(null);
    setForm(EMPTY_FORM);
    setError("");
  };

  const openEditDialog = (user: ManagedUser) => {
    setEditingUser(user);
    setCreating(false);
    setForm({ username: user.username, password: "", role: user.role, is_active: user.is_active });
    setError("");
  };

  const saveUser = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.username.trim() || (creating && !form.password)) {
      setError("Vui lòng nhập tên đăng nhập và mật khẩu.");
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        username: form.username.trim(),
        role: form.role,
        is_active: form.is_active,
        ...(form.password ? { password: form.password } : {}),
      };
      const saved = creating
        ? await createManagedUser({ ...payload, password: form.password })
        : await updateManagedUser(editingUser!.id, payload);
      setUsers((current) => creating ? [saved, ...current] : current.map((item) => item.id === saved.id ? saved : item));
      setError("");
      setCreating(false);
      setEditingUser(null);
      setForm(EMPTY_FORM);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể lưu tài khoản.");
    } finally {
      setSubmitting(false);
    }
  };

  const removeUser = async (user: ManagedUser) => {
    if (!window.confirm(`Xóa vĩnh viễn tài khoản ${user.username} và dữ liệu hội thoại liên quan?`)) return;
    try {
      await deleteManagedUser(user.id);
      setUsers((current) => current.filter((item) => item.id !== user.id));
      setError("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể xóa tài khoản.");
    }
  };

  const adminCount = users.filter((user) => user.role === "admin").length;
  const clientCount = users.length - adminCount;

  return (
    <>
      <PageHeader eyebrow="Quản lý tài khoản" title="Quản lý người dùng" description="Quản lý tài khoản, vai trò và theo dõi thời gian truy cập gần nhất của người dùng." />
      <div className="mb-4 flex justify-end">
        <button type="button" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-primary-hover" onClick={openCreateDialog}>
          <Icon name="person_add" className="text-[18px]" /> Thêm người dùng
        </button>
      </div>
      {error && !dialogOpen ? <p className="mb-4 text-sm font-medium text-danger">{error}</p> : null}

      <div className="grid gap-3 md:grid-cols-3">
        {[["Tổng tài khoản", users.length, "Tổng số tài khoản trong hệ thống"], ["Người dùng", clientCount, "Tài khoản có vai trò người dùng"], ["Quản trị viên", adminCount, "Tài khoản có quyền quản trị"]].map(([label, value, note]) => (
          <Card key={label}><p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</p><p className="mt-2 text-2xl font-bold">{value}</p><p className="mt-1 text-sm text-text-secondary">{note}</p></Card>
        ))}
      </div>

      <Card className="mt-4">
        <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-bold">Danh sách tài khoản</h3><p className="mt-1 text-sm text-text-secondary">Thông tin tài khoản, vai trò và trạng thái hoạt động.</p></div><span className="text-sm font-semibold text-text-secondary">{users.length} tài khoản</span></div>
        {loading ? <p className="py-8 text-center text-sm text-text-secondary">Đang tải danh sách tài khoản...</p> : null}
        {!loading && users.length === 0 ? <p className="py-8 text-center text-sm text-text-secondary">Chưa có tài khoản nào.</p> : null}
        {!loading && users.length > 0 ? <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="border-b border-border-color text-xs uppercase text-text-secondary"><tr><th className="pb-3 pr-4">Tên đăng nhập</th><th className="pb-3 pr-4 text-center">Vai trò</th><th className="pb-3 pr-4 text-center">Truy cập gần nhất</th><th className="pb-3 pr-4 text-center">Trạng thái</th><th className="pb-3 text-right">Thao tác</th></tr></thead><tbody className="divide-y divide-border-color">
          {users.map((user) => <tr key={user.id} className="hover:bg-secondary-surface"><td className="py-3 pr-4 font-semibold text-text-primary">{user.username}</td><td className="py-3 pr-4 text-center"><Badge tone={user.role === "admin" ? "warn" : "info"}>{roleLabel(user.role)}</Badge></td><td className="py-3 pr-4 text-center text-text-secondary">{formatLastSeen(user.last_seen_at)}</td><td className="py-3 pr-4 text-center"><Badge tone={user.is_active ? "ok" : "muted"}>{user.is_active ? "Hoạt động" : "Vô hiệu hoá"}</Badge></td><td className="py-3 text-right"><div className="inline-flex items-center gap-1"><button type="button" className="rounded-md p-2 text-text-secondary hover:bg-hover-item hover:text-primary" aria-label={`Chỉnh sửa ${user.username}`} title="Chỉnh sửa người dùng" onClick={() => openEditDialog(user)}><Icon name="edit" className="text-[18px]" /></button><button type="button" className="rounded-md p-2 text-text-secondary hover:bg-danger-surface hover:text-danger" aria-label={`Xóa ${user.username}`} title="Xóa người dùng" onClick={() => void removeUser(user)}><Icon name="delete" className="text-[18px]" /></button></div></td></tr>)}
        </tbody></table></div> : null}
      </Card>

      {dialogOpen ? <div className="fixed inset-0 z-[70] flex items-center justify-center bg-text-primary/40 p-4 backdrop-blur-[2px]"><form className="w-full max-w-md rounded-xl border border-border-color bg-card-surface p-6 shadow-xl" onSubmit={saveUser}><div className="mb-5 flex items-start justify-between gap-4"><div><h2 className="text-lg font-bold">{creating ? "Thêm người dùng" : "Cập nhật người dùng"}</h2><p className="mt-1 text-sm text-text-secondary">{creating ? "Tài khoản mới có thể đăng nhập ngay khi được kích hoạt." : "Để trống mật khẩu nếu không cần thay đổi."}</p></div><button type="button" aria-label="Đóng" className="rounded-md p-1 text-text-secondary hover:bg-secondary-surface" onClick={closeDialog} disabled={submitting}><Icon name="close" /></button></div><div className="space-y-4"><label className="block text-sm font-semibold">Tên đăng nhập<input className="mt-1.5 h-10 w-full rounded-lg border border-border-color bg-main-bg px-3 font-normal outline-none focus:border-primary" value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} maxLength={64} disabled={submitting} /></label><label className="block text-sm font-semibold">Mật khẩu {!creating ? <span className="font-normal text-text-secondary">(để trống nếu giữ nguyên)</span> : null}<input className="mt-1.5 h-10 w-full rounded-lg border border-border-color bg-main-bg px-3 font-normal outline-none focus:border-primary" value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} type="password" disabled={submitting} /></label><label className="block text-sm font-semibold">Vai trò<select className="mt-1.5 h-10 w-full rounded-lg border border-border-color bg-main-bg px-3 font-normal outline-none focus:border-primary" value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value as UserForm["role"] }))} disabled={submitting}><option value="client">Người dùng</option><option value="admin">Quản trị viên</option></select></label><label className="flex items-center gap-2 text-sm font-semibold"><input type="checkbox" checked={form.is_active} onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))} disabled={submitting} />Cho phép đăng nhập vào hệ thống</label></div>{error ? <p className="mt-4 text-sm font-medium text-danger">{error}</p> : null}<div className="mt-6 flex justify-end gap-3"><button type="button" className="rounded-lg border border-border-color px-4 py-2 text-sm font-semibold hover:bg-secondary-surface" onClick={closeDialog} disabled={submitting}>Hủy</button><button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:bg-primary-hover disabled:opacity-60" disabled={submitting}>{submitting ? "Đang lưu..." : "Lưu"}</button></div></form></div> : null}
    </>
  );
}
