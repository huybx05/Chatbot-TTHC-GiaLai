import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { logout, restoreSession, type AuthResponse } from "./api/auth";
import AdminLayout from "./components/layout/AdminLayout.tsx";
import ClientLayout from "./components/layout/ClientLayout.tsx";
import AdminLoginPage from "./pages/admin/AdminLoginPage.tsx";
import ConversationsPage from "./pages/admin/ConversationsPage.tsx";
import CostsPage from "./pages/admin/CostsPage.tsx";
import DataAndChunkPage from "./pages/admin/DataAndChunkPage.tsx";
import FaqPage from "./pages/admin/FaqPage.tsx";
import GraphPage from "./pages/admin/GraphPage.tsx";
import OperationsPage from "./pages/admin/OperationsPage.tsx";
import OverviewPage from "./pages/admin/OverviewPage.tsx";
import RagPlaygroundPage from "./pages/admin/RagPlaygroundPage.tsx";
import UsersPage from "./pages/admin/UsersPage.tsx";
import ChatPage from "./pages/client/ChatPage.tsx";

function AdminAuthLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-main-bg text-sm font-semibold text-text-secondary">
      Đang khôi phục phiên đăng nhập…
    </div>
  );
}

/**
 * Hai giao diện dùng chung một app:
 *   /      → giao diện người dân
 *   /admin → monitoring nội bộ
 */
export default function App() {
  const location = useLocation();
  const isAdminRoute = location.pathname.startsWith("/admin");
  const [adminSession, setAdminSession] = useState<AuthResponse | null>(null);
  const [adminAuthRestoring, setAdminAuthRestoring] = useState(isAdminRoute);

  useEffect(() => {
    if (!isAdminRoute) {
      setAdminAuthRestoring(false);
      return;
    }

    let mounted = true;
    setAdminAuthRestoring(true);

    restoreSession()
      .then((session) => {
        if (!mounted) return;

        if (session.user.role !== "admin") {
          // Refresh cookie là của client: không tự đăng xuất client,
          // chỉ không mở được khu vực admin.
          setAdminSession(null);
          return;
        }

        setAdminSession(session);
      })
      .catch(() => {
        if (mounted) setAdminSession(null);
      })
      .finally(() => {
        if (mounted) setAdminAuthRestoring(false);
      });

    return () => {
      mounted = false;
    };
  }, [isAdminRoute]);

  function handleAdminLogin(session: AuthResponse) {
    setAdminSession(session);
  }

  function handleAdminLogout() {
    setAdminSession(null);
    void logout();
  }

  return (
    <Routes>
      <Route element={<ClientLayout />}>
        <Route path="/" element={<ChatPage />} />
      </Route>

      <Route
        path="/admin"
        element={
          adminAuthRestoring ? (
            <AdminAuthLoading />
          ) : adminSession ? (
            <AdminLayout onLogout={handleAdminLogout} />
          ) : (
            <AdminLoginPage onLogin={handleAdminLogin} />
          )
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="data" element={<DataAndChunkPage />} />
        <Route path="faq" element={<FaqPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="retrieval" element={<RagPlaygroundPage />} />
        <Route path="operations" element={<OperationsPage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="costs" element={<CostsPage />} />
        <Route path="users" element={<UsersPage />} />

        <Route path="data-quality" element={<Navigate to="/admin/data" replace />} />
        <Route path="pipeline" element={<Navigate to="/admin/operations" replace />} />
        <Route path="qa" element={<Navigate to="/admin/faq" replace />} />
        <Route path="rag" element={<Navigate to="/admin/operations" replace />} />
        <Route path="logs" element={<Navigate to="/admin/operations" replace />} />
        <Route path="settings" element={<Navigate to="/admin/operations" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
