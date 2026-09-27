import { Navigate, Route, Routes } from "react-router-dom";

import AdminLayout from "./components/layout/AdminLayout.tsx";
import ClientLayout from "./components/layout/ClientLayout.tsx";
import DataQualityPage from "./pages/admin/DataQualityPage.tsx";
import OverviewPage from "./pages/admin/OverviewPage.tsx";
import PipelinePage from "./pages/admin/PipelinePage.tsx";
import RetrievalPage from "./pages/admin/RetrievalPage.tsx";
import ChatPage from "./pages/client/ChatPage.tsx";

/**
 * Hai giao diện dùng chung một app, tách theo route:
 *
 *   /        → client cho người dân
 *   /admin   → monitoring nội bộ
 */
export default function App() {
  return (
    <Routes>
      <Route element={<ClientLayout />}>
        <Route path="/" element={<ChatPage />} />
      </Route>

      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="data-quality" element={<DataQualityPage />} />
        <Route path="retrieval" element={<RetrievalPage />} />
        <Route path="pipeline" element={<PipelinePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
