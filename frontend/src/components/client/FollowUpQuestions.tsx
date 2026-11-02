import type { SuggestedQuestion } from "../../data/chatTypes";

export default function FollowUpQuestions({
  items,
  onPick,
}: {
  items: SuggestedQuestion[];
  onPick: (text: string) => void;
}) {
  if (items.length === 0) return null;

  return (
    <div className="mt-3 border-t border-border-color/70 pt-3">
      <p className="mb-2 text-[12px] font-bold uppercase tracking-wide text-text-secondary">
        Câu hỏi gợi ý
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onPick(item.text)}
            className="rounded-full border border-border-color bg-card-surface px-3 py-1.5 text-left text-[13px] text-text-primary transition-colors hover:border-primary/50 hover:bg-primary-soft"
          >
            {item.text}
          </button>
        ))}
      </div>
    </div>
  );
}
