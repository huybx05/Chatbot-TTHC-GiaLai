import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { getAdminSystemStatus, type AdminSystemStatus } from "../../api/admin";

const NAV_ITEMS = [
  { to: "/admin", label: "Tổng quan", icon: "dashboard", end: true },
  { to: "/admin/data", label: "Cơ sở dữ liệu", icon: "database", end: false },
  { to: "/admin/faq", label: "Quản lý FAQ", icon: "quiz", end: false },
  { to: "/admin/graph", label: "Đồ thị tri thức", icon: "hub", end: false },
  { to: "/admin/retrieval", label: "Kiểm thử truy xuất", icon: "manage_search", end: false },
  { to: "/admin/conversations", label: "Lịch sử hội thoại", icon: "forum", end: false },
  { to: "/admin/costs", label: "Quản lý chi phí AI", icon: "payments", end: false },
  { to: "/admin/users", label: "Quản lý người dùng", icon: "group", end: false },
  { to: "/admin/operations", label: "Vận hành (Đang thử nghiệm)", icon: "settings_suggest", end: false },
];

function navClass({ isActive }: { isActive: boolean }) {
  return [
    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition",
    isActive
      ? "bg-primary text-white shadow-sm"
      : "text-text-secondary hover:bg-hover-item hover:text-text-primary",
  ].join(" ");
}

type AdminLayoutProps = {
  onLogout: () => void;
};

export default function AdminLayout({ onLogout }: AdminLayoutProps) {
  const [status, setStatus] = useState<AdminSystemStatus | null>(null);

  useEffect(() => {
    getAdminSystemStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const services = [
    ["API", status?.services.api.ready],
    ["PostgreSQL", status?.services.postgresql.ready],
    ["Neo4j", status?.services.neo4j.ready],
    ["Elasticsearch", status?.services.elasticsearch.ready],
    ["Qdrant", status?.services.qdrant.ready],
  ] as const;
  const readyCount = services.filter(([, ready]) => ready).length;
  const allReady = readyCount === services.length;
  const serviceTitle = services
    .map(([name, ready]) => `${name}: ${ready ? "online" : "offline"}`)
    .join("\n");

  return (
    <div className="min-h-screen bg-main-bg text-text-primary lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="hidden border-r border-border-color bg-sidebar-bg lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
        <div className="border-b border-border-color px-5 py-5">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Logo TTHC AI Monitor"
              className="size-10 rounded-lg border border-border-color bg-white object-cover shadow-sm"
            />
            <div>
              <h1 className="text-[15px] font-bold leading-5">Gia Lai Chatbot Admin</h1>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="space-y-3 border-t border-border-color p-3">
          <NavLink
            to="/"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-text-secondary hover:bg-hover-item"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Giao diện chatbot
          </NavLink>
          <button
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-danger hover:bg-danger-surface"
            type="button"
            onClick={onLogout}
          >
            <span className="material-symbols-outlined text-[18px]">logout</span>
            Đăng xuất
          </button>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-border-color bg-main-bg/95 px-4 py-3 backdrop-blur lg:px-6">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary">Hệ thống quản trị và giám sát Chatbot AI Gia Lai</p>
              {/* <p className="truncate text-sm text-text-secondary">PostgreSQL + Neo4j · data_test · monitoring v1</p> */}
            </div>
            <div className="hidden xl:block">
              <span
                title={serviceTitle}
                className={[
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold",
                  status === null
                    ? "border-border-color bg-card-surface text-text-secondary"
                    : allReady
                      ? "border-[#B8DDC6] bg-[#E7F4EC] text-[#2E7D4F]"
                      : "border-[#E6B8B2] bg-danger-surface text-danger",
                ].join(" ")}
              >
                <span
                  className={[
                    "size-2 rounded-full",
                    status === null
                      ? "bg-text-secondary/40"
                      : allReady
                        ? "bg-[#2E7D4F]"
                        : "bg-danger",
                  ].join(" ")}
                />
                {status === null
                  ? "Đang kiểm tra dịch vụ"
                  : allReady
                    ? `Hệ thống ổn định · ${readyCount}/${services.length} dịch vụ`
                    : `${readyCount}/${services.length} dịch vụ online`}
              </span>
            </div>
          </div>
          <nav className="mt-3 flex gap-2 overflow-x-auto lg:hidden">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                <span className="material-symbols-outlined text-[18px]">{item.icon}</span>
                <span className="whitespace-nowrap">{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="px-4 py-5 lg:px-6 lg:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
