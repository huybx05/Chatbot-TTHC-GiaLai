import { useEffect, useState } from "react";

interface DeleteDialogProps {
  conversationTitle: string;
  /** Chuỗi mô tả, ví dụ "Tạo ngày 24/10/2024 • 2 tin nhắn". */
  meta: string;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Hộp thoại xác nhận xóa cuộc trò chuyện. Esc để đóng. */
export default function DeleteDialog({
  conversationTitle,
  meta,
  onCancel,
  onConfirm,
}: DeleteDialogProps) {
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  const handleConfirm = () => {
    setDeleting(true);
    onConfirm();
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-text-primary/40 p-4 backdrop-blur-[2px] transition-all duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
        className="flex w-full max-w-[420px] flex-col gap-5 rounded-xl border border-border-color bg-card-surface p-6 shadow-[0_16px_32px_-4px_rgba(46,46,46,0.18)]"
      >
        <div className="flex items-start gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-danger/20 bg-danger-surface">
            <span className="material-symbols-outlined text-[22px] text-danger">delete_forever</span>
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <h2 id="delete-dialog-title" className="text-[17px] font-semibold text-text-primary">
              Xóa cuộc trò chuyện này?
            </h2>
            <p className="text-[14px] leading-relaxed text-text-secondary">
              Thao tác này không thể hoàn tác.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-border-color bg-main-bg p-3">
          <span className="material-symbols-outlined shrink-0 text-[18px] text-text-secondary">
            history_edu
          </span>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-[13.5px] font-medium text-text-primary">
              {conversationTitle}
            </span>
            <span className="text-[12px] text-text-secondary">{meta}</span>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="flex h-10 items-center justify-center rounded-[8px] border border-border-color bg-sidebar-bg px-[20px] py-[10px] text-[14px] font-medium text-text-primary shadow-sm transition-colors hover:bg-border-color"
          >
            Hủy
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={deleting}
            className="flex h-10 items-center justify-center gap-1.5 rounded-[8px] bg-danger px-[20px] py-[10px] text-[14px] font-medium text-white shadow-sm transition-colors hover:bg-danger-hover"
          >
            <span
              className={`material-symbols-outlined text-[17px] ${deleting ? "animate-spin" : ""}`}
            >
              {deleting ? "progress_activity" : "delete"}
            </span>
            <span>{deleting ? "Đang xóa..." : "Xác nhận xóa"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
