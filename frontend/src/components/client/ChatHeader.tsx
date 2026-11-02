import { useEffect, useRef, useState } from "react";
import { PanelLeft } from "lucide-react";

/** Thanh header phía trên vùng chat. */
export default function ChatHeader({
  onOpenSidebar,
  onToggleSidebar,
  onOpenAuth,
  onLogout,
  onDeleteGuestConversation,
  showSidebar,
  sidebarCollapsed,
  username,
}: {
  onOpenSidebar: () => void;
  onToggleSidebar: () => void;
  onOpenAuth: () => void;
  onLogout: () => Promise<void>;
  onDeleteGuestConversation?: () => void;
  showSidebar: boolean;
  sidebarCollapsed: boolean;
  username: string | null;
}) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setAccountMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccountMenuOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const handleAccountClick = () => {
    if (username) {
      setAccountMenuOpen((current) => !current);
      return;
    }
    onOpenAuth();
  };

  const handleLogout = async () => {
    setAccountMenuOpen(false);
    await onLogout();
  };

  return (
    <header
      className={[
        "fixed top-0 left-0 right-0 z-40 flex h-16 items-center border-b border-border-color bg-main-bg/90 px-4 backdrop-blur-md md:px-8",
        showSidebar && !sidebarCollapsed ? "md:left-[260px]" : "",
      ].join(" ")}
    >
      <div className="flex items-center gap-3">
        {showSidebar ? (
          <button
            type="button"
            aria-label="Mở danh mục"
            onClick={onOpenSidebar}
            className="rounded-lg p-2 text-text-secondary hover:bg-sidebar-bg hover:text-text-primary md:hidden"
          >
            <span className="material-symbols-outlined">menu</span>
          </button>
        ) : null}
        {showSidebar && sidebarCollapsed ? (
          <button
            type="button"
            aria-label="Mở danh mục"
            onClick={onToggleSidebar}
            className="hidden rounded-lg p-2 text-text-secondary transition-colors hover:bg-sidebar-bg hover:text-text-primary md:inline-flex"
          >
            <PanelLeft aria-hidden="true" size={20} strokeWidth={2} />
          </button>
        ) : null}
        <div className="flex items-center gap-2">
          <span className="text-[17px] font-semibold text-text-primary">
            Hệ Thống Hỗ Trợ Tra Cứu Thủ Tục Hành Chính Tại Tỉnh Gia Lai
          </span>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2" ref={accountMenuRef}>
        {onDeleteGuestConversation ? (
          <button
            type="button"
            aria-label="Xóa cuộc trò chuyện"
            onClick={onDeleteGuestConversation}
            className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-danger-surface hover:text-danger"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[19px]">delete</span>
            <span className="hidden sm:inline">Xóa cuộc trò chuyện</span>
          </button>
        ) : null}
        <div className="relative">
        <button
          aria-expanded={username ? accountMenuOpen : undefined}
          className="inline-flex items-center gap-2 rounded-md border border-border-strong bg-card-surface px-3 py-2 text-sm font-semibold text-text-primary transition-colors hover:border-primary hover:text-primary"
          onClick={handleAccountClick}
          type="button"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[19px]">account_circle</span>
          <span className="hidden max-w-36 truncate sm:inline">{username ?? "Đăng nhập/Đăng ký"}</span>
          {username ? (
            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">expand_more</span>
          ) : null}
        </button>

        {username && accountMenuOpen ? (
          <div className="absolute right-0 top-[calc(100%+8px)] w-48 rounded-md border border-border-color bg-card-surface p-1 shadow-lg">
            <p className="truncate px-3 py-2 text-xs font-semibold text-text-secondary">{username}</p>
            <button
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm font-semibold text-danger transition-colors hover:bg-danger-surface"
              onClick={() => void handleLogout()}
              type="button"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">logout</span>
              Đăng xuất
            </button>
          </div>
        ) : null}
      </div>
      </div>
    </header>
  );
}
