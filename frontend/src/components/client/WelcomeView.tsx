import type { SuggestedQuestion } from "../../data/chatTypes";
import MessageInput from "./MessageInput";

interface WelcomeViewProps {
  suggestions: SuggestedQuestion[];
  prefill: string;
  onPickSuggestion: (text: string) => void;
  onSend: (text: string) => void;
  isSending?: boolean;
}

/** Màn hình chào khi chưa có hội thoại. */
export default function WelcomeView({
  suggestions,
  prefill,
  onPickSuggestion,
  onSend,
  isSending = false,
}: WelcomeViewProps) {
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col justify-center px-6 py-10">
      <div className="flex flex-col items-center justify-center text-center">
        <img
          src="/logo.png"
          alt="Logo ChatTTHC"
          className="mx-auto mb-5 h-14 w-14 rounded-2xl border border-border-color bg-white object-cover shadow-sm"
        />
        <h1 className="mb-3 text-center text-[26px] font-bold leading-tight text-text-primary md:text-[28px]">
          Xin chào! Tôi có thể hỗ trợ gì cho bạn.
        </h1>
        {/* <p className="mb-8 max-w-[620px] text-center text-[16px] leading-relaxed text-text-secondary">
          Hệ thống hỗ trợ tra cứu thủ tục hành chính.
        </p> */}

        <div className="mb-8 w-full text-left">
          <div className="mb-3 flex items-center gap-2 px-1">
            <span className="material-symbols-outlined text-[17px] text-primary">lightbulb</span>
            <span className="text-[13px] font-semibold uppercase tracking-wider text-text-secondary">
              CÂU HỎI GỢI Ý
            </span>
          </div>
          <div className="flex flex-col gap-2.5">
            {suggestions.map((question) => (
              <button
                key={question.id}
                type="button"
                onClick={() => onPickSuggestion(question.text)}
                className="group flex w-full items-center justify-between rounded-xl border border-border-color bg-card-surface px-4 py-3.5 text-left text-text-primary shadow-[0_1px_3px_rgba(0,0,0,0.03)] transition-all hover:border-border-strong hover:bg-secondary-surface"
              >
                <span className="text-[15px] text-text-primary md:text-[16px]">{question.text}</span>
                <span className="material-symbols-outlined ml-3 shrink-0 text-[20px] text-primary transition-all group-hover:translate-x-0.5">
                  arrow_forward
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="w-full">
          <MessageInput
            prefill={prefill}
            placeholder="Nhập câu hỏi..."
            onSend={onSend}
            disabled={isSending}
          />
          <p className="mt-3 text-center text-[13px] leading-normal text-text-secondary">
            {/* Trợ lý AI chỉ cung cấp thông tin tham khảo. Vui lòng đối chiếu với nguồn chính thức và quy
            định hiện hành. */}
            Thông tin chỉ mang tính tham khảo và Vui lòng đối chiếu với nguồn chính thức trước khi thực hiện.
          </p>
        </div>
      </div>
    </div>
  );
}
