import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import AdminLayout from "./components/layout/AdminLayout.tsx";
import ClientLayout from "./components/layout/ClientLayout.tsx";
import AdminLoginPage from "./pages/admin/AdminLoginPage.tsx";
import ConversationsPage from "./pages/admin/ConversationsPage.tsx";
import DataAndChunkPage from "./pages/admin/DataAndChunkPage.tsx";
import FaqPage from "./pages/admin/FaqPage.tsx";
import GraphPage from "./pages/admin/GraphPage.tsx";
import OperationsPage from "./pages/admin/OperationsPage.tsx";
import OverviewPage from "./pages/admin/OverviewPage.tsx";
import ChatPage from "./pages/client/ChatPage.tsx";

/**
 * Hai giao diện dùng chung một app:
 *   /      → giao diện người dân
 *   /admin → monitoring nội bộ
 */
export default function App() {
  const [isAdminLoggedIn, setIsAdminLoggedIn] = useState(() => sessionStorage.getItem("adminLoggedIn") === "true");

  function handleAdminLogin() {
    sessionStorage.setItem("adminLoggedIn", "true");
    setIsAdminLoggedIn(true);
  }

  function handleAdminLogout() {
    sessionStorage.removeItem("adminLoggedIn");
    setIsAdminLoggedIn(false);
  }

  return (
    <Routes>
      <Route element={<ClientLayout />}>
        <Route path="/" element={<ChatPage />} />
      </Route>

      <Route
        path="/admin"
        element={isAdminLoggedIn ? <AdminLayout onLogout={handleAdminLogout} /> : <AdminLoginPage onLogin={handleAdminLogin} />}
      >
        <Route index element={<OverviewPage />} />
        <Route path="data" element={<DataAndChunkPage />} />
        <Route path="faq" element={<FaqPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="operations" element={<OperationsPage />} />
        <Route path="conversations" element={<ConversationsPage />} />

        <Route path="data-quality" element={<Navigate to="/admin/data" replace />} />
        <Route path="pipeline" element={<Navigate to="/admin/operations" replace />} />
        <Route path="retrieval" element={<Navigate to="/admin/operations" replace />} />
        <Route path="qa" element={<Navigate to="/admin/faq" replace />} />
        <Route path="rag" element={<Navigate to="/admin/operations" replace />} />
        <Route path="logs" element={<Navigate to="/admin/operations" replace />} />
        <Route path="settings" element={<Navigate to="/admin/operations" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
