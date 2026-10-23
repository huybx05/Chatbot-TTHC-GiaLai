import { useState } from "react";
import { RichText } from "../RichText";

import type {
  AnswerBlock,
  AssistantMessage,
  ListItem,
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
          <span className="material-symbols-outlined text-[13px]">done_all</span>
        </div>
      </div>
    </div>
  );
}

function CitationBlock({ block }: { block: Extract<AnswerBlock, { kind: "citation" }> }) {
  return (
    <div className="flex flex-col gap-1.5 pt-2 text-sm">
      <span className="font-semibold text-text-primary">Nguồn tham khảo:</span>
      <ul className="flex flex-col gap-1 pl-1 text-text-secondary">
        {block.items.map((item) => (
          <li key={item.title} className="flex flex-col gap-0.5">
            <span className="flex items-center gap-1.5">
              <span>{item.title}</span>
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline"
                >
                  — Xem nguồn
                  <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                </a>
              ) : null}
            </span>
            {item.note ? <span className="text-[12px]">{item.note}</span> : null}
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

function Block({ block }: { block: AnswerBlock }) {
  switch (block.kind) {
    case "heading":
      return <h4 className="text-[16px] font-bold text-text-primary">{block.text}</h4>;

    case "paragraph":
      // Câu trả lời của mô hình có `**in đậm**` và gạch đầu dòng; hiện nguyên văn thì người dân
      // thấy cả dấu sao. Dùng **cùng** bộ hiển thị với trang quản trị để hai nơi không lệch.
      return <RichText text={block.text} className="leading-[1.75]" />;

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
  }
}

/** Câu trả lời của trợ lý: avatar, tên, rồi các khối nội dung. */
export default function MessageAnswer({ message }: { message: AssistantMessage }) {
  const [feedback, setFeedback] = useState<"like" | "dislike" | null>(null);

  // Chưa có chữ nào thì cũng chưa nên mời đánh giá.
  const coChu = message.blocks.some((block) =>
    "text" in block ? block.text.trim().length > 0 : block.kind === "citation",
  );

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
          <Block key={`${message.id}-${block.kind}-${index}`} block={block} />
        ))}

        {message.phase || !coChu ? null : (
        <div className="flex items-center gap-1 pt-1 text-text-secondary" aria-label="Đánh giá câu trả lời">
          <button
            type="button"
            title="Câu trả lời hữu ích"
            aria-label="Thích câu trả lời"
            aria-pressed={feedback === "like"}
            onClick={() => setFeedback((current) => current === "like" ? null : "like")}
            className={`flex size-8 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-primary-soft hover:text-primary ${feedback === "like" ? "bg-primary-soft text-primary" : ""}`}
          >
            <span className="material-symbols-outlined text-[18px]">thumb_up</span>
          </button>
          <button
            type="button"
            title="Câu trả lời chưa hữu ích"
            aria-label="Không thích câu trả lời"
            aria-pressed={feedback === "dislike"}
            onClick={() => setFeedback((current) => current === "dislike" ? null : "dislike")}
            className={`flex size-8 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-primary-soft hover:text-primary ${feedback === "dislike" ? "bg-primary-soft text-primary" : ""}`}
          >
            <span className="material-symbols-outlined text-[18px]">thumb_down</span>
          </button>
        </div>
        )}
      </div>
    </article>
  );
}
