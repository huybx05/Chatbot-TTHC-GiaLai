import { useMemo, useState } from "react";

import ChatHeader from "../../components/client/ChatHeader";
import ChatSidebar from "../../components/client/ChatSidebar";
import ContextMenu from "../../components/client/ContextMenu";
import DeleteDialog from "../../components/client/DeleteDialog";
import MessageInput from "../../components/client/MessageInput";
import MessageList from "../../components/client/MessageList";
import WelcomeView from "../../components/client/WelcomeView";
import {
  SIDEBAR_PINNED,
  SIDEBAR_RECENT,
  SUGGESTED_QUESTIONS,
} from "../../data/chatMock";
import type { ChatMessage, Conversation } from "../../data/chatTypes";

interface DeleteTarget {
  id: string;
  title: string;
  /** Chuỗi mô tả: ngày tạo và số tin nhắn. */
  meta: string;
}

const DELETE_META = "Tạo ngày 24/10/2024 • 2 tin nhắn";

function currentTime(): string {
  return new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Giao diện người dân.
 *
 * Hiện dùng dữ liệu mẫu ở src/data. Chưa nối API chat.
 */
export default function ChatPage() {
  const [pinned, setPinned] = useState<Conversation[]>(SIDEBAR_PINNED);
  const [recent, setRecent] = useState<Conversation[]>(SIDEBAR_RECENT);
  const [activeId, setActiveId] = useState("cap-lai-cccd");  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prefill, setPrefill] = useState("");
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [menu, setMenu] = useState<{ id: string; anchor: HTMLElement } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const allConversations = useMemo(() => [...pinned, ...recent], [pinned, recent]);
  const menuConversation = menu ? allConversations.find((item) => item.id === menu.id) : undefined;

  const closeSidebar = () => setMobileSidebarOpen(false);

  const handleNewConversation = () => {
    setActiveId("");
    setMessages([]);
    setPrefill("");
    setMenu(null);
    closeSidebar();
  };

  const handleSelectConversation = (id: string) => {
    setActiveId(id);
    setMenu(null);
    const conversation = allConversations.find((item) => item.id === id);
    setMessages(conversation?.messages ?? []);
  };

  const handleSend = (text: string) => {
    setMessages((previous) => [
      ...previous,
      { id: `u-${Date.now()}`, role: "user", text, time: currentTime() },
    ]);
    setPrefill("");
  };

  const handleTogglePin = (targetId?: string) => {
    const id = targetId ?? menu?.id;
    if (!id) return;
    const item = allConversations.find((conversation) => conversation.id === id);
    if (!item) return;

    const next = { ...item, pinned: !item.pinned };
    setPinned((previous) =>
      next.pinned ? [...previous, next] : previous.filter((conversation) => conversation.id !== id),
    );
    setRecent((previous) =>
      next.pinned ? previous.filter((conversation) => conversation.id !== id) : [...previous, next],
    );
    setMenu(null);
  };

  const handleRequestDelete = () => {
    if (!menu) return;
    const item = allConversations.find((conversation) => conversation.id === menu.id);
    if (!item) return;

    setDeleteTarget({ id: item.id, title: item.title, meta: DELETE_META });
    setMenu(null);
  };

  const handleConfirmDelete = () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    setPinned((previous) => previous.filter((conversation) => conversation.id !== id));
    setRecent((previous) => previous.filter((conversation) => conversation.id !== id));
    if (activeId === id) {
      setActiveId("");
      setMessages([]);
    }
    setDeleteTarget(null);
  };

  return (
    <div className="min-h-screen bg-main-bg font-sans text-text-primary antialiased">
      <ChatSidebar
        pinned={pinned}
        recent={recent}
        activeId={activeId}
        menuForId={menu?.id ?? null}
        mobileOpen={mobileSidebarOpen}
        onClose={closeSidebar}
        onSelect={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onTogglePin={handleTogglePin}
        onOpenMenu={(id, anchor) => setMenu({ id, anchor })}
      />

      <div className="md:pl-[260px]">
        <ChatHeader onOpenSidebar={() => setMobileSidebarOpen(true)} />

        {messages.length === 0 ? (
          <main className="relative flex min-h-[calc(100vh-64px)] flex-col justify-between pt-16">
            <WelcomeView
              suggestions={SUGGESTED_QUESTIONS}
              prefill={prefill}
              onPickSuggestion={setPrefill}
              onSend={handleSend}
            />
          </main>
        ) : (
          <>
            <main className="relative min-h-[calc(100vh-140px)] pb-36 pt-16">
              <div className="mx-auto max-w-[840px] px-6 py-8">
                <MessageList messages={messages} />
              </div>
            </main>

            <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-border-color bg-main-bg/90 px-4 pb-4 pt-3 backdrop-blur-md md:left-[260px] md:px-8">
              <div className="mx-auto max-w-[840px]">
                <MessageInput
                  prefill={prefill}
                  placeholder="Nhập câu hỏi về thủ tục hành chính (ví dụ: hồ sơ cấp lại CCCD, lệ phí làm hộ chiếu)..."
                  onSend={handleSend}
                />
                <p className="mt-2 text-center text-[12px] text-text-secondary">
                  Trợ lý AI cung cấp thông tin tham khảo. Vui lòng đối chiếu với văn bản quy phạm pháp
                  luật hiện hành và Cổng Dịch vụ công Quốc gia.
                </p>
              </div>
            </div>
          </>
        )}
      </div>

      {menu && menuConversation ? (
        <ContextMenu
          anchor={menu.anchor}
          pinned={menuConversation.pinned}
          onTogglePin={handleTogglePin}
          onDelete={handleRequestDelete}
          onClose={() => setMenu(null)}
        />
      ) : null}

      {deleteTarget ? (
        <DeleteDialog
          conversationTitle={deleteTarget.title}
          meta={deleteTarget.meta}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleConfirmDelete}
        />
      ) : null}
    </div>
  );
}
