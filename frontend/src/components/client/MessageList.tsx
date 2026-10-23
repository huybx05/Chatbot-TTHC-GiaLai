import type { ChatMessage } from "../../data/chatTypes";
import MessageAnswer, { UserBubble } from "./MessageAnswer";

/**
 * Cột tin nhắn: bong bóng người dùng và câu trả lời của trợ lý.
 *
 * **Không** còn vòng xoay riêng ở cuối danh sách: trạng thái đang soạn nằm trong chính tin
 * nhắn của trợ lý (cạnh tên), nên nó đi theo đúng câu trả lời thay vì trôi ở đáy trang.
 */
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
