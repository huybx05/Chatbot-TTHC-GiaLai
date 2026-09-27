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

function InfoCardsBlock({ block }: { block: Extract<AnswerBlock, { kind: "infoCards" }> }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border-color bg-card-surface p-4 shadow-sm">
      <div className="flex items-center gap-2 text-[15px] font-semibold text-primary">
        <span className="material-symbols-outlined text-[20px]">{block.icon}</span>
        <span>{block.title}</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {block.cards.map((card) => (
          <div
            key={card.label}
            className="flex flex-col gap-1 rounded-lg border border-border-color/70 bg-main-bg p-3"
          >
            <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">
              {card.label}
            </span>
            <span className="text-[13.5px] font-medium text-text-primary">{card.value}</span>
            <p className="text-[13px] leading-relaxed text-text-secondary">{card.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function CitationBlock({ block }: { block: Extract<AnswerBlock, { kind: "citation" }> }) {
  return (
    <div className="flex flex-col gap-1.5 border-t border-border-color pt-4 text-sm">
      <span className="font-semibold text-text-primary">Nguồn tham khảo:</span>
      <ul className="flex flex-col gap-1 pl-1 text-text-secondary">
        {block.items.map((item) => (
          <li key={item.title} className="flex flex-col gap-0.5">
            <span className="flex items-center gap-1.5">
              <span>{`${item.title} —`}</span>
              <a
                href="#"
                className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline"
              >
                Xem nguồn
                <span className="material-symbols-outlined text-[14px]">open_in_new</span>
              </a>
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
      return <p className="leading-[1.75]">{block.text}</p>;

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

    case "infoCards":
      return <InfoCardsBlock block={block} />;

    case "citation":
      return <CitationBlock block={block} />;
  }
}

/** Câu trả lời của trợ lý: avatar, tên, rồi các khối nội dung. */
export default function MessageAnswer({ message }: { message: AssistantMessage }) {
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
          <span className="text-[14px] font-medium text-text-primary">{message.author}</span>
          {message.authorNote ? (
            <span className="text-[12px] text-text-secondary">{message.authorNote}</span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-3 pl-2 sm:pl-10">
        {message.blocks.map((block, index) => (
          <Block key={`${message.id}-${block.kind}-${index}`} block={block} />
        ))}
      </div>
    </article>
  );
}
