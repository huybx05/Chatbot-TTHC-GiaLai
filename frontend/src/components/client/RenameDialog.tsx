import { useEffect, useState } from "react";

interface RenameDialogProps {
  conversationTitle: string;
  onCancel: () => void;
  onConfirm: (title: string) => Promise<void>;
}

export default function RenameDialog({
  conversationTitle,
  onCancel,
  onConfirm,
}: RenameDialogProps) {
  const [title, setTitle] = useState(conversationTitle);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel, saving]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTitle = title.trim();
    if (!nextTitle) {
      setError("Tên cuộc trò chuyện không được để trống.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await onConfirm(nextTitle);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể đổi tên cuộc trò chuyện.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-text-primary/40 p-4 backdrop-blur-[2px]">
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-dialog-title"
        className="flex w-full max-w-[420px] flex-col gap-5 rounded-xl border border-border-color bg-card-surface p-6 shadow-[0_16px_32px_-4px_rgba(46,46,46,0.18)]"
      >
        <div className="flex items-start gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary-soft">
            <span className="material-symbols-outlined text-[22px] text-primary">edit</span>
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <h2 id="rename-dialog-title" className="text-[17px] font-semibold text-text-primary">
              Đổi tên cuộc trò chuyện
            </h2>
            <p className="text-[14px] leading-relaxed text-text-secondary">Tên mới sẽ hiển thị trong danh sách.</p>
          </div>
        </div>

        <div>
          <label htmlFor="conversation-title" className="mb-1.5 block text-[13.5px] font-medium text-text-primary">
            Tên cuộc trò chuyện
          </label>
          <input
            id="conversation-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={120}
            autoFocus
            disabled={saving}
            className="h-10 w-full rounded-[8px] border border-border-color bg-main-bg px-3 text-[14px] text-text-primary outline-none transition-colors focus:border-primary disabled:cursor-not-allowed disabled:opacity-60"
          />
          {error ? <p className="mt-1.5 text-[13px] text-danger">{error}</p> : null}
        </div>

        <div className="flex items-center justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="flex h-10 items-center justify-center rounded-[8px] border border-border-color bg-sidebar-bg px-[20px] py-[10px] text-[14px] font-medium text-text-primary shadow-sm transition-colors hover:bg-border-color disabled:cursor-not-allowed disabled:opacity-60"
          >
            Hủy
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex h-10 items-center justify-center gap-1.5 rounded-[8px] bg-primary px-[20px] py-[10px] text-[14px] font-medium text-white shadow-sm transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className={`material-symbols-outlined text-[17px] ${saving ? "animate-spin" : ""}`}>
              {saving ? "progress_activity" : "check"}
            </span>
            <span>{saving ? "Đang lưu..." : "Lưu"}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
