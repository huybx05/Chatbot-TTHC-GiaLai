import type { Conversation } from "../../data/chatTypes";

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  /** Hiện nút ba chấm (dùng cho mục đang thao tác). */
  showMenuButton: boolean;
  onSelect: (id: string) => void;
  onTogglePin: (id: string) => void;
  onOpenMenu: (id: string, anchor: HTMLElement) => void;
}

/** Một dòng cuộc trò chuyện trong sidebar. */
export default function ConversationItem({
  conversation,
  isActive,
  showMenuButton,
  onSelect,
  onTogglePin,
  onOpenMenu,
}: ConversationItemProps) {
  const { id, title, pinned } = conversation;

  return (
    <div
      className={[
        "group relative flex items-center justify-between rounded-lg px-2.5 py-2 transition-colors",
        isActive
          ? "border border-primary/40 bg-primary-soft font-semibold text-primary"
          : "text-text-secondary hover:bg-hover-item hover:text-text-primary",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => onSelect(id)}
        aria-label={`Mở ${title}`}
        className="absolute inset-0 rounded-lg border-0 outline-none focus:outline-none focus:ring-0 focus-visible:ring-2 focus-visible:ring-primary/40"
      />
      <span className="pointer-events-none relative z-10 min-w-0 flex-1 truncate text-[13.5px]">
        {title}
      </span>

      <div className="relative z-10 ml-2 flex shrink-0 items-center gap-0.5">
        <button
          type="button"
          title={pinned ? "Bỏ ghim" : "Ghim"}
          aria-label={pinned ? `Bỏ ghim ${title}` : `Ghim ${title}`}
          aria-pressed={pinned}
          onClick={() => onTogglePin(id)}
          className={[
            "material-symbols-outlined rounded p-1 text-[17px] hover:bg-black/5 hover:text-primary",
            pinned ? "text-primary" : "text-text-secondary",
          ].join(" ")}
        >
          {pinned ? "keep_off" : "push_pin"}
        </button>
        <button
          type="button"
          title="Tùy chọn"
          aria-label={`Tùy chọn cho ${title}`}
          onClick={(event) => onOpenMenu(id, event.currentTarget)}
          className={[
            "material-symbols-outlined rounded p-1 text-[18px] hover:bg-black/5 hover:text-text-primary",
            showMenuButton ? "text-primary" : "text-text-secondary",
          ].join(" ")}
        >
          more_vert
        </button>
      </div>
    </div>
  );
}
