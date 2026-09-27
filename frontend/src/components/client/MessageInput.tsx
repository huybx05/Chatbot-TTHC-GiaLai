import { useEffect, useRef, useState } from "react";

interface MessageInputProps {
  /** Câu hỏi được đổ vào ô nhập khi bấm câu gợi ý. */
  prefill: string;
  placeholder: string;
  onSend: (text: string) => void;
}

/** Ô nhập câu hỏi, tự giãn chiều cao. Enter gửi, Shift+Enter xuống dòng. */
export default function MessageInput({ prefill, placeholder, onSend }: MessageInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (prefill) {
      setValue(prefill);
      textareaRef.current?.focus();
    }
  }, [prefill]);

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  };

  const submit = () => {
    const text = value.trim();
    if (!text) return;
    onSend(text);
    setValue("");
    const el = textareaRef.current;
    if (el) el.style.height = "auto";
  };

  return (
    <div className="flex items-center gap-3 rounded-[14px] border border-border-strong bg-card-surface p-2.5 pl-4 shadow-[0_2px_12px_rgba(46,46,46,0.04)] transition-colors focus-within:border-primary">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onInput={resize}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        className="max-h-32 min-h-[44px] flex-1 resize-none border-0 bg-transparent py-1.5 text-[16px] leading-[24px] text-text-primary placeholder:text-text-secondary/60 focus:outline-none"
      />
      <button
        type="button"
        aria-label="Gửi câu hỏi"
        onClick={submit}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-white shadow-sm transition-colors hover:bg-primary-hover"
      >
        <span className="material-symbols-outlined text-[20px]">arrow_upward</span>
      </button>
    </div>
  );
}
