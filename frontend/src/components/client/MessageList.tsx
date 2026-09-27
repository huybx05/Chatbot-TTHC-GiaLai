import type { ChatMessage } from "../../data/chatTypes";
import MessageAnswer, { UserBubble } from "./MessageAnswer";

/** Cột tin nhắn: bong bóng người dùng và câu trả lời của trợ lý. */
export default function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="relative flex w-full flex-col">
      <div className="flex w-full flex-col gap-6">
        {messages.map((message) =>
          message.role === "user" ? (
            <UserBubble key={message.id} message={message} />
          ) : (
            <MessageAnswer key={message.id} message={message} />
          ),
        )}
      </div>
    </div>
  );
}
