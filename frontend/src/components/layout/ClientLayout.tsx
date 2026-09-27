import { Outlet } from "react-router-dom";

/**
 * Layout lớp ngoài cho vùng người dân.
 *
 * Khung sidebar/header do ChatPage tự dựng vì cần state mở drawer trên mobile.
 */
export default function ClientLayout() {
  return <Outlet />;
}
