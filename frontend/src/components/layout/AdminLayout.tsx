import { NavLink, Outlet } from "react-router-dom";

import ThemeToggle from "../ui/ThemeToggle.tsx";

const NAV_ITEMS = [
  { to: "/admin", label: "Tổng quan", end: true },
  { to: "/admin/data-quality", label: "Chất lượng dữ liệu", end: false },
  { to: "/admin/retrieval", label: "Chất lượng truy xuất", end: false },
  { to: "/admin/pipeline", label: "Trạng thái pipeline", end: false },
];

export default function AdminLayout() {
  return (
    <div className="layout layout--admin">
      <aside className="sidebar">
        <h1 className="sidebar__title">Giám sát hệ thống</h1>

        <nav className="sidebar__nav">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="sidebar__link">
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          <NavLink to="/" className="sidebar__link">
            ← Về giao diện người dân
          </NavLink>
          <ThemeToggle />
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
