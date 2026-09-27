import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

interface ContextMenuProps {
  anchor: HTMLElement;
  pinned: boolean;
  onTogglePin: () => void;
  onDelete: () => void;
  onClose: () => void;
}

const MENU_WIDTH = 160;
const MENU_GAP = 4;

/** Menu ba chấm của một cuộc trò chuyện: Ghim/Bỏ ghim và Xóa. */
export default function ContextMenu({
  anchor,
  pinned,
  onTogglePin,
  onDelete,
  onClose,
}: ContextMenuProps) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    const update = () => {
      const rect = anchor.getBoundingClientRect();
      const maxLeft = window.innerWidth - MENU_WIDTH - 8;
      setPosition({
        top: rect.top,
        left: Math.max(8, Math.min(rect.right + MENU_GAP, maxLeft)),
      });
    };

    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [anchor]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointerDown = (event: MouseEvent) => {
      if (!(event.target as HTMLElement).closest("[data-context-menu]")) onClose();
    };

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [onClose]);

  if (!position) return null;

  return createPortal(
    <div
      data-context-menu
      style={{ top: position.top, left: position.left, width: MENU_WIDTH }}
      className="fixed z-[60] flex select-none flex-col rounded-[10px] border border-border-color bg-card-surface py-1.5 shadow-[0_4px_16px_-2px_rgba(46,46,46,0.1),0_2px_6px_rgba(0,0,0,0.04)]"
    >
      <button
        type="button"
        onClick={onTogglePin}
        className="group flex w-full items-center gap-2.5 px-3 py-2 text-left text-text-primary transition-colors hover:bg-secondary-surface"
      >
        <span className="material-symbols-outlined text-[17px] text-text-secondary group-hover:text-primary">
          push_pin
        </span>
        <span className="text-[13.5px] font-medium">{pinned ? "Bỏ ghim" : "Ghim"}</span>
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="group flex w-full items-center gap-2.5 px-3 py-2 text-left text-danger transition-colors hover:bg-danger-surface"
      >
        <span className="material-symbols-outlined text-[17px] text-danger">delete</span>
        <span className="text-[13.5px] font-medium text-danger">Xóa</span>
      </button>
    </div>,
    document.body,
  );
}
