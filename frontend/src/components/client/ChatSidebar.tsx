import type { Conversation } from "../../data/chatTypes";
import ConversationItem from "./ConversationItem";

interface ChatSidebarProps {
  pinned: Conversation[];
  recent: Conversation[];
  activeId: string;
  /** Id của cuộc trò chuyện đang mở menu ba chấm. */
  menuForId: string | null;
  mobileOpen: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
  onTogglePin: (id: string) => void;
  onOpenMenu: (id: string, anchor: HTMLElement) => void;
}

/**
 * Sidebar danh sách cuộc trò chuyện.
 *
 * Desktop: cố định bên trái. Mobile: drawer trượt ra kèm lớp phủ mờ.
 */
export default function ChatSidebar({
  pinned,
  recent,
  activeId,
  menuForId,
  mobileOpen,
  onClose,
  onSelect,
  onNewConversation,
  onTogglePin,
  onOpenMenu,
}: ChatSidebarProps) {
  const handleSelect = (id: string) => {
    onSelect(id);
    onClose();
  };

  return (
    <>
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Đóng danh mục"
          onClick={onClose}
          className="fixed inset-0 z-40 bg-black/25 backdrop-blur-[1px] md:hidden"
        />
      ) : null}

      <aside
        className={[
          "fixed left-0 top-0 z-50 flex h-full w-[260px] flex-col justify-between overflow-y-auto border-r border-border-color bg-sidebar-bg p-4 shadow-[1px_0_6px_rgba(0,0,0,0.02)] transition-transform duration-200 md:translate-x-0 md:overflow-visible",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 py-1">
            <img
              src="/logo.png"
              alt="Logo trợ lý thủ tục hành chính"
              className="h-10 w-10 shrink-0 rounded-lg border border-border-color bg-white object-cover shadow-sm"
            />
            <div className="flex min-w-0 flex-col leading-tight">
              <span className="truncate text-[15px] font-semibold text-text-primary">
                ChatTTHC
              </span>
              <span className="truncate text-[12px] text-text-secondary">Hỗ trợ tra cứu các TTHC</span>
            </div>
          </div>

          <button
            type="button"
            onClick={onNewConversation}
            className="flex h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-primary font-medium text-[15px] text-white shadow-sm transition-colors hover:bg-primary-hover"
          >
            <span className="material-symbols-outlined text-[20px]">add</span>
            <span>Cuộc trò chuyện mới</span>
          </button>

          <nav className="flex max-h-[calc(100vh-240px)] flex-col gap-3 overflow-y-auto pr-1">
            <div className="flex flex-col gap-1">
              <span className="flex items-center gap-1.5 px-2 py-1 text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
                <span className="material-symbols-outlined text-[15px] text-primary">push_pin</span> ĐÃ GHIM
              </span>
              {pinned.map((conversation) => (
                <ConversationItem
                  key={conversation.id}
                  conversation={conversation}
                  isActive={conversation.id === activeId && menuForId !== conversation.id}
                  showMenuButton={menuForId === conversation.id}
                  onSelect={handleSelect}
                  onTogglePin={onTogglePin}
                  onOpenMenu={onOpenMenu}
                />
              ))}
            </div>

            <div className="flex flex-col gap-1 pt-1">
              <span className="flex items-center gap-1.5 px-2 py-1 text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
                <span className="material-symbols-outlined text-[15px] text-primary">schedule</span> GẦN ĐÂY
              </span>
              {recent.map((conversation) => (
                <ConversationItem
                  key={conversation.id}
                  conversation={conversation}
                  isActive={conversation.id === activeId && menuForId !== conversation.id}
                  showMenuButton={menuForId === conversation.id}
                  onSelect={handleSelect}
                  onTogglePin={onTogglePin}
                  onOpenMenu={onOpenMenu}
                />
              ))}
            </div>
          </nav>
        </div>
      </aside>
    </>
  );
}
