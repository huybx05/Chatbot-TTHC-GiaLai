import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { getAdminSystemStatus, type AdminSystemStatus } from "../../api/admin";

const NAV_ITEMS = [
  { to: "/admin", label: "Tổng quan", icon: "dashboard", end: true },
  { to: "/admin/data", label: "Dữ liệu PostgreSQL", icon: "database", end: false },
  { to: "/admin/faq", label: "FAQ", icon: "quiz", end: false },
  { to: "/admin/graph", label: "Neo4j Graph", icon: "hub", end: false },
  { to: "/admin/retrieval", label: "Kiểm thử truy xuất", icon: "manage_search", end: false },
  { to: "/admin/conversations", label: "Log hội thoại", icon: "forum", end: false },
  { to: "/admin/costs", label: "Quản lý chi phí", icon: "payments", end: false },
  { to: "/admin/operations", label: "Vận hành", icon: "settings_suggest", end: false },
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
              <p className="text-xs font-semibold uppercase tracking-wide text-primary">Monitoring nội bộ</p>
              <p className="truncate text-sm text-text-secondary">PostgreSQL + Neo4j · data_test · monitoring v1</p>
            </div>
            <div className="hidden items-center gap-2 xl:flex">
              {services.map(([name, ready]) => (
                <span
                  key={name}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border-color bg-card-surface px-3 py-1 text-xs font-semibold text-text-secondary"
                >
                  <span className={`size-2 rounded-full ${ready ? "bg-[#2E7D4F]" : "bg-[#B33A2F]"}`} />
                  {name} {ready ? "ready" : "offline"}
                </span>
              ))}
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
