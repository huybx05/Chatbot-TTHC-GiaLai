import { useState } from "react";
import { RichText } from "../RichText";
import { FileList } from "./FileAttachment";
import { saveAnswerFeedback, type AnswerFeedback } from "../../api/feedback";

import type {
  AnswerBlock,
  AssistantMessage,
  ListItem,
  ProcedureDocument,
  UserMessage,
} from "../../data/chatTypes";

/** Bong bóng câu hỏi của người dùng. */
export function UserBubble({ message }: { message: UserMessage }) {
  return (
    <div className="flex w-full items-start justify-end gap-2">
      <div className="max-w-[85%] rounded-xl border border-border-color/60 bg-user-bubble p-3.5 text-text-primary shadow-sm sm:max-w-[70%]">
        <p className="text-[14.5px] leading-relaxed">{message.text}</p>
        <div className="mt-1 flex items-center justify-end gap-1 text-[11px] text-text-secondary">
          <span>{message.time}</span>
        </div>
      </div>
    </div>
  );
}

function CitationBlock({ block }: { block: Extract<AnswerBlock, { kind: "citation" }> }) {
  return (
    <div className="flex flex-col gap-1.5 pt-2 text-sm">
      <span className="font-semibold text-text-primary">Nguồn tham khảo:</span>
      <ul className="flex flex-col gap-2 pl-1 text-text-secondary">
        {block.items.map((item) => (
          <li key={item.title} className="flex items-start justify-between gap-3">
            <span className="min-w-0 flex-1 font-serif text-[13px] leading-relaxed">
              {item.title}
            </span>
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex shrink-0 items-center gap-0.5 whitespace-nowrap pt-0.5 font-sans font-medium text-primary hover:underline"
              >
                Xem nguồn
                <span className="material-symbols-outlined text-[14px]">
                  open_in_new
                </span>
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ListItems({ items }: { items: ListItem[] }) {
  return (
    <>
      {items.map((item) => (
        <li key={item.label}>
          <strong className="font-semibold">{item.label}</strong> {item.text}
          {item.legal ? (
            <>
              {" "}
              <em className="font-medium not-italic">{item.legal}</em>
            </>
          ) : null}
        </li>
      ))}
    </>
  );
}

function Block({
  block,
  fileMap,
}: {
  block: AnswerBlock;
  fileMap?: Record<string, ProcedureDocument>;
}) {
  switch (block.kind) {
    case "heading":
      return <h4 className="text-[16px] font-bold text-text-primary">{block.text}</h4>;

    case "paragraph":
      // Câu trả lời của mô hình có `**in đậm**` và gạch đầu dòng; hiện nguyên văn thì người dân
      // thấy cả dấu sao. Dùng **cùng** bộ hiển thị với trang quản trị để hai nơi không lệch.
      return <RichText text={block.text} className="leading-[1.75]" fileMap={fileMap} />;

    case "strongParagraph":
      return (
        <p>
          <strong className="font-semibold">{block.label}</strong> {block.text}
        </p>
      );

    case "ordered":
      return (
        <ol className="list-decimal space-y-2 pl-5 leading-[1.75]">
          <ListItems items={block.items} />
        </ol>
      );

    case "unordered":
      return (
        <ul className="list-disc space-y-2 pl-5 leading-[1.75]">
          <ListItems items={block.items} />
        </ul>
      );

    case "citation":
      return <CitationBlock block={block} />;

    case "files":
      return <FileList items={block.items} />;
  }
}

/** Câu trả lời của trợ lý: avatar, tên, rồi các khối nội dung. */
const DISLIKE_REASONS = [
  "Không chính xác hoặc chưa đầy đủ",
  "Không đúng điều tôi yêu cầu",
  "Chậm hoặc bị lỗi",
  "Nguồn tham khảo không phù hợp",
  "Nội dung khó hiểu",
  "Khác",
];

export default function MessageAnswer({ message }: { message: AssistantMessage }) {
  const [feedback, setFeedback] = useState<AnswerFeedback | null>(message.feedback ?? null);
  const [feedbackReasons, setFeedbackReasons] = useState<string[]>(message.feedbackReasons ?? []);
  const [feedbackComment, setFeedbackComment] = useState(message.feedbackComment ?? "");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");

  const persistFeedback = async (
    next: AnswerFeedback | null,
    reasons: string[] = [],
    comment = "",
  ): Promise<boolean> => {
    if (!message.messageId) {
      setFeedbackError("Chưa thể lưu đánh giá cho câu trả lời này.");
      return false;
    }
    setFeedbackSaving(true);
    setFeedbackError("");
    try {
      await saveAnswerFeedback(message.messageId, {
        feedback: next,
        reasons,
        comment,
      });
      setFeedback(next);
      if (next === null) {
        setFeedbackReasons([]);
        setFeedbackComment("");
      } else {
        setFeedbackReasons(reasons);
        setFeedbackComment(comment);
      }
      return true;
    } catch {
      setFeedbackError("Không gửi được đánh giá. Vui lòng thử lại.");
      return false;
    } finally {
      setFeedbackSaving(false);
    }
  };

  const toggleReason = (reason: string) => {
    setFeedbackReasons((current) =>
      current.includes(reason)
        ? current.filter((item) => item !== reason)
        : [...current, reason],
    );
  };

  const submitDislike = async () => {
    const ok = await persistFeedback("dislike", feedbackReasons, feedbackComment);
    if (ok) setFeedbackOpen(false);
  };

  // Chưa có chữ nào thì cũng chưa nên mời đánh giá.
  const coChu = message.blocks.some((block) =>
    "text" in block
      ? block.text.trim().length > 0
      : block.kind === "citation" || block.kind === "files",
  );

  const fileMap: Record<string, ProcedureDocument> = {};
  for (const block of message.blocks) {
    if (block.kind !== "files") continue;
    for (const file of block.items) {
      for (const id of file.file_ids ?? (file.file_id ? [file.file_id] : [])) {
        fileMap[id] = file;
      }
    }
  }

  return (
    <article className="flex w-full flex-col gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border-color bg-white text-primary shadow-sm">
          {message.icon === "logo" ? (
            <img src="/logo.png" alt="Logo ChatTTHC" className="h-full w-full rounded-lg object-cover" />
          ) : (
            <span className="material-symbols-outlined text-[18px]">{message.icon}</span>
          )}
        </div>
        <div className="flex flex-col">
          <span className="flex items-center gap-1.5 text-[14px] font-medium text-text-primary">
            {message.author}
            {message.phase ? (
              // Vòng xoay **và nhãn** nằm cạnh tên trợ lý: người dùng biết hệ thống đang ở bước
              // nào, thay vì chỉ thấy một vòng xoay không nói gì.
              <span className="flex items-center gap-1.5" role="status">
                <span className="material-symbols-outlined animate-spin text-[15px] text-primary">
                  progress_activity
                </span>
                <span className="text-[12px] font-normal text-text-secondary">
                  {message.phase === "searching"
                    ? "Đang tìm kiếm thông tin…"
                    : "Chuẩn bị câu trả lời…"}
                </span>
              </span>
            ) : null}
          </span>
          {message.authorNote ? (
            <span className="text-[12px] text-text-secondary">{message.authorNote}</span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-3 pl-2 sm:pl-10">
        {message.blocks.map((block, index) => (
          <Block key={`${message.id}-${block.kind}-${index}`} block={block} fileMap={fileMap} />
        ))}

        {message.phase || !coChu ? null : (
        <div className="flex items-center gap-1 pt-1 text-text-secondary" aria-label="Đánh giá câu trả lời">
          <button
            type="button"
            title={feedback === "like" ? "Bỏ đánh giá hữu ích" : "Câu trả lời hữu ích"}
            aria-label={feedback === "like" ? "Bỏ đánh giá hữu ích" : "Thích câu trả lời"}
            aria-pressed={feedback === "like"}
            disabled={!message.messageId || feedbackSaving}
            onClick={() => void persistFeedback(feedback === "like" ? null : "like")}
            className={`flex size-8 cursor-pointer items-center justify-center rounded-full transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 ${feedback === "like" ? "text-primary" : ""}`}
          >
            <span
              className="material-symbols-outlined text-[18px]"
              style={{
                fontVariationSettings:
                  feedback === "like" ? "'FILL' 1, 'wght' 500" : "'FILL' 0",
              }}
            >
              thumb_up
            </span>
          </button>
          <button
            type="button"
            title={feedback === "dislike" ? "Bỏ đánh giá không hữu ích" : "Câu trả lời chưa hữu ích"}
            aria-label={feedback === "dislike" ? "Bỏ đánh giá không hữu ích" : "Không thích câu trả lời"}
            aria-pressed={feedback === "dislike"}
            disabled={!message.messageId || feedbackSaving}
            onClick={() => {
              if (feedback === "dislike") {
                void persistFeedback(null);
                return;
              }
              setFeedbackOpen(true);
            }}
            className={`flex size-8 cursor-pointer items-center justify-center rounded-full transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 ${feedback === "dislike" ? "text-primary" : ""}`}
          >
            <span
              className="material-symbols-outlined text-[18px]"
              style={{
                fontVariationSettings:
                  feedback === "dislike" ? "'FILL' 1, 'wght' 500" : "'FILL' 0",
              }}
            >
              thumb_down
            </span>
          </button>
          <button
            type="button"
            title="Nghe câu trả lời (sắp có)"
            aria-label="Nghe câu trả lời"
            aria-disabled="true"
            className="flex size-8 cursor-default items-center justify-center rounded-full text-text-secondary/70"
          >
            <span className="material-symbols-outlined text-[18px]">volume_up</span>
          </button>
        </div>
        )}

        {feedbackOpen ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="feedback-title"
            onMouseDown={() => setFeedbackOpen(false)}
          >
            <section
              className="w-full max-w-lg rounded-xl border border-border-color bg-card-surface p-5 shadow-xl"
              onMouseDown={(event) => event.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 id="feedback-title" className="text-lg font-bold text-text-primary">
                    Chia sẻ góp ý
                  </h3>
                  <p className="mt-1 text-sm text-text-secondary">
                    Điều gì chưa ổn ở câu trả lời này?
                  </p>
                </div>
                <button
                  type="button"
                  aria-label="Đóng góp ý"
                  onClick={() => setFeedbackOpen(false)}
                  className="rounded-md px-2 py-1 text-xl leading-none text-text-secondary hover:bg-secondary-surface"
                >
                  ×
                </button>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {DISLIKE_REASONS.map((reason) => (
                  <button
                    key={reason}
                    type="button"
                    aria-pressed={feedbackReasons.includes(reason)}
                    onClick={() => toggleReason(reason)}
                    className={[
                      "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                      feedbackReasons.includes(reason)
                        ? "border-primary bg-primary-soft text-primary"
                        : "border-border-color text-text-secondary hover:border-primary/50",
                    ].join(" ")}
                  >
                    {reason}
                  </button>
                ))}
              </div>

              <label className="mt-4 block text-xs font-semibold text-text-secondary">
                Chia sẻ chi tiết (không bắt buộc)
                <textarea
                  value={feedbackComment}
                  maxLength={1000}
                  onChange={(event) => setFeedbackComment(event.target.value)}
                  placeholder="Mô tả thêm để admin hiểu vấn đề…"
                  className="mt-1.5 min-h-20 w-full resize-y rounded-lg border border-border-color bg-card-surface px-3 py-2 text-sm font-normal text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary-soft"
                />
              </label>

              {feedbackError ? (
                <p className="mt-2 text-xs font-semibold text-danger">{feedbackError}</p>
              ) : null}

              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setFeedbackOpen(false)}
                  className="rounded-md px-3 py-1.5 text-sm font-semibold text-text-secondary hover:bg-secondary-surface"
                >
                  Hủy
                </button>
                <button
                  type="button"
                  disabled={feedbackSaving}
                  onClick={() => void submitDislike()}
                  className="rounded-md bg-primary px-4 py-1.5 text-sm font-semibold text-white hover:bg-primary-hover disabled:opacity-50"
                >
                  {feedbackSaving ? "Đang gửi…" : "Gửi"}
                </button>
              </div>
            </section>
          </div>
        ) : null}

      </div>
    </article>
  );
}
