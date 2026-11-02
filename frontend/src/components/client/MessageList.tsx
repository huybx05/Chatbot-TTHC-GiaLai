import { Fragment } from "react";

import type { ChatMessage, SuggestedQuestion } from "../../data/chatTypes";
import FollowUpQuestions from "./FollowUpQuestions";
import MessageAnswer, { UserBubble } from "./MessageAnswer";

/**
 * Cột tin nhắn: bong bóng người dùng và câu trả lời của trợ lý.
 *
 * Câu hỏi tiếp theo chỉ hiện dưới câu trả lời cuối cùng, khi câu đó đã
 * trả lời xong — không làm rối các câu trả lời cũ.
 */
export default function MessageList({
  messages,
  followUpSuggestions = [],
  onPickSuggestion,
}: {
  messages: ChatMessage[];
  followUpSuggestions?: SuggestedQuestion[];
  onPickSuggestion?: (text: string) => void;
}) {
  const lastAssistantIndex = messages.reduce(
    (last, message, index) =>
      message.role === "assistant" ? index : last,
    -1,
  );

  return (
    <div className="relative flex w-full flex-col">
      <div className="flex w-full flex-col gap-6">
        {messages.map((message, index) => (
          <Fragment key={message.id}>
            {message.role === "user" ? (
              <UserBubble message={message} />
            ) : (
              <MessageAnswer message={message} />
            )}

            {message.role === "assistant" &&
            index === lastAssistantIndex &&
            index === messages.length - 1 &&
            !message.phase &&
            onPickSuggestion ? (
              <FollowUpQuestions
                items={followUpSuggestions}
                onPick={onPickSuggestion}
              />
            ) : null}
          </Fragment>
        ))}
      </div>
    </div>
  );
}
