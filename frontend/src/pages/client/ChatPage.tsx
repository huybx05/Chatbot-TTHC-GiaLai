import { useEffect, useMemo, useRef, useState } from "react";

import { askChatStream, type StreamKetQua } from "../../api/chat";
import ChatHeader from "../../components/client/ChatHeader";
import ChatSidebar from "../../components/client/ChatSidebar";
import ContextMenu from "../../components/client/ContextMenu";
import DeleteDialog from "../../components/client/DeleteDialog";
import MessageInput from "../../components/client/MessageInput";
import MessageList from "../../components/client/MessageList";
import WelcomeView from "../../components/client/WelcomeView";
import { SUGGESTED_QUESTIONS } from "../../data/chatSuggestions";
import type { AssistantMessage, ChatMessage, Conversation } from "../../data/chatTypes";
import type { ChatResponse, ClarifyOption } from "../../types/chat";

interface DeleteTarget {
  id: string;
  title: string;
  /** Chuỗi mô tả: ngày tạo và số tin nhắn. */
  meta: string;
}

function currentTime(): string {
  return new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function assistantMessage(response: ChatResponse): AssistantMessage {
  const blocks: AssistantMessage["blocks"] = [{ kind: "paragraph", text: response.answer }];
  if (response.citations.length > 0) {
    blocks.push({
      kind: "citation",
      items: response.citations.map((item, index) => ({
        title: `[${index + 1}] ${item.title}`,
        note: item.section ?? "",
        url: item.url,
      })),
    });
  }

  return {
    id: `assistant-${crypto.randomUUID()}`,
    role: "assistant",
    author: "Gia Lai Chatbot",
    // Không hiện mã TTHC dưới tên trợ lý nữa: mã đã nằm trong danh sách nguồn và trong câu
    // trả lời khi cần. Chỉ giữ ghi chú **về hành động** mà người dùng phải làm.
    authorNote:
      response.status === "clarify"
        ? "Cần bạn chọn"
        : response.status === "abstained"
          ? "Chưa trả lời được"
          : undefined,
    icon: "logo",
    blocks,
  };
}

function errorMessage(message: string): AssistantMessage {
  return {
    id: `assistant-${crypto.randomUUID()}`,
    role: "assistant",
    author: "Gia Lai Chatbot",
    icon: "logo",
    blocks: [{ kind: "paragraph", text: message }],
  };
}

/**
 * Giao diện người dân.
 *
 * Mỗi câu hỏi được gửi tới public chat API và hiển thị câu trả lời từ workflow thật.
 */
export default function ChatPage() {
  const [pinned, setPinned] = useState<Conversation[]>([]);
  const [recent, setRecent] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const activeIdRef = useRef("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prefill, setPrefill] = useState("");
  const [isSending, setIsSending] = useState(false);
  /**
   * Lựa chọn của câu hỏi lại gần nhất.
   *
   * Đây là thứ khác hẳn "câu trả lời": hệ thống **chưa** trả lời được vì tên thủ tục mơ hồ,
   * và đưa ra 2–5 lựa chọn có thật. Vẽ thành nút để người dân bấm một cái, thay vì bắt họ gõ
   * lại mã thủ tục.
   */
  const [pendingOptions, setPendingOptions] = useState<ClarifyOption[]>([]);
  /** Mốc cuối khung chat — chỉ dùng để đưa lượt hỏi mới vào vùng nhìn thấy. */
  const cuoiTrang = useRef<HTMLDivElement>(null);
  const cuonDenLuotMoi = useRef(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [menu, setMenu] = useState<{ id: string; anchor: HTMLElement } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const allConversations = useMemo(() => [...pinned, ...recent], [pinned, recent]);
  const menuConversation = menu ? allConversations.find((item) => item.id === menu.id) : undefined;

  useEffect(() => {
    if (!cuonDenLuotMoi.current) return;
    cuonDenLuotMoi.current = false;
    cuoiTrang.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const closeSidebar = () => setMobileSidebarOpen(false);

  const handleNewConversation = () => {
    activeIdRef.current = "";
    setActiveId("");
    setMessages([]);
    setPrefill("");
    setMenu(null);
    closeSidebar();
  };

  const handleSelectConversation = (id: string) => {
    activeIdRef.current = id;
    setActiveId(id);
    setMenu(null);
    const conversation = allConversations.find((item) => item.id === id);
    setMessages(conversation?.messages ?? []);
  };

  /** Thay một tin nhắn đã có (dùng cho khung trả lời đang chạy chữ). */
  const replaceMessage = (conversationId: string, message: ChatMessage) => {
    const thay = (items: Conversation[]) =>
      items.map((item) =>
        item.id === conversationId
          ? { ...item, messages: item.messages.map((m) => (m.id === message.id ? message : m)) }
          : item,
      );
    setPinned(thay);
    setRecent(thay);
    if (activeIdRef.current === conversationId) {
      // Nếu tin nhắn **chưa** có trong danh sách đang hiển thị thì thêm vào, không im lặng bỏ
      // qua. Đây đúng là lỗi đã xảy ra: khung trả lời được thêm vào danh sách hội thoại mà
      // không vào `messages`, nên chữ chảy vào một tin nhắn không ai nhìn thấy — xoay xong
      // trắng trơn.
      setMessages((previous) =>
        previous.some((m) => m.id === message.id)
          ? previous.map((m) => (m.id === message.id ? message : m))
          : [...previous, message],
      );
    }
  };

  const appendToConversation = (id: string, message: ChatMessage) => {
    const append = (items: Conversation[]) =>
      items.map((item) => item.id === id ? { ...item, messages: [...item.messages, message] } : item);
    setPinned(append);
    setRecent(append);
  };

  const handleSend = async (text: string) => {
    if (isSending) return;

    // Chỉ cuộn một lần khi gửi; các mẩu streaming sau đó không được chiếm quyền cuộn.
    cuonDenLuotMoi.current = true;

    const userMessage: ChatMessage = {
      id: `user-${crypto.randomUUID()}`,
      role: "user",
      text,
      time: currentTime(),
    };
    const conversationId = activeId || `conversation-${crypto.randomUUID()}`;
    if (!activeId) {
      const title = text.length > 48 ? `${text.slice(0, 47)}…` : text;
      setRecent((previous) => [
        { id: conversationId, title, pinned: false, path: conversationId, messages: [userMessage] },
        ...previous,
      ]);
      activeIdRef.current = conversationId;
      setActiveId(conversationId);
    } else {
      appendToConversation(conversationId, userMessage);
    }
    setMessages((previous) => [...previous, userMessage]);
    setPrefill("");
    setPendingOptions([]);
    setIsSending(true);

    // Khung trả lời rỗng, được đổ chữ dần khi máy chủ phát từng mẩu.
    const dangTraLoi: AssistantMessage = {
      id: `assistant-${crypto.randomUUID()}`,
      role: "assistant",
      author: "Gia Lai Chatbot",
      icon: "logo",
      phase: "searching",
      blocks: [{ kind: "paragraph", text: "" }],
    };
    appendToConversation(conversationId, dangTraLoi);
    setMessages((previous) => [...previous, dangTraLoi]);

    /**
     * Chữ hiện **chậm hơn** nhịp máy chủ phát.
     *
     * Server phát ~700 ký tự/giây; hiện thẳng thì chữ bung ra gần như một cục, và mắt không
     * theo kịp. Ở đây giữ một hàng đợi rồi nhả 8 ký tự mỗi 35 ms (~230 ký tự/giây): chậm hơn
     * khoảng ba lần, đủ để đọc theo mà không thành chờ đợi.
     */
    const NHIP_MS = 35;
    const MOI_NHIP = 8;
    let hangDoi = "";
    let daHien = "";
    let gom = "";

    const ve = () => {
      replaceMessage(conversationId, {
        ...dangTraLoi,
        // Chữ đã chạy thì chính dòng chữ là dấu hiệu tiến độ — bỏ vòng xoay cho khỏi rối.
        phase: undefined,
        blocks: [{ kind: "paragraph", text: daHien }],
      });
    };

    const dongHo = window.setInterval(() => {
      if (!hangDoi) return;
      daHien += hangDoi.slice(0, MOI_NHIP);
      hangDoi = hangDoi.slice(MOI_NHIP);
      ve();
    }, NHIP_MS);

    /** Chờ chữ hiện hết hàng đợi rồi mới chốt, để nguồn không hiện trước khi chữ viết xong. */
    const doiHienHet = () =>
      new Promise<void>((resolve) => {
        const kiem = window.setInterval(() => {
          if (!hangDoi) {
            window.clearInterval(kiem);
            resolve();
          }
        }, NHIP_MS);
      });

    try {
      const ket_qua: StreamKetQua = await askChatStream(
        { question: text },
        {
          onDelta: (manh) => {
            gom += manh;
            hangDoi += manh;
          },
          onMeta: (meta) => {
            setPendingOptions(meta.status === "clarify" ? meta.options : []);
            // Truy xuất xong, mô hình bắt đầu viết: đổi nhãn để người dùng biết đang ở bước nào.
            replaceMessage(conversationId, { ...dangTraLoi, phase: "answering" });
          },
        },
      );

      await doiHienHet();

      // Chốt lại bằng bản đầy đủ: có nguồn, có mã thủ tục, và chữ đã đồng bộ với `done`.
      const cuoi: ChatResponse = {
        answer: ket_qua.answer || gom,
        citations: ket_qua.meta?.citations ?? [],
        procedure: ket_qua.meta?.procedure ?? undefined,
        status: ket_qua.meta?.status ?? "answered",
        options: ket_qua.meta?.options ?? [],
        abstained: (ket_qua.meta?.status ?? "answered") !== "answered",
      };
      replaceMessage(conversationId, { ...assistantMessage(cuoi), id: dangTraLoi.id });
      if (cuoi.status === "clarify") setPendingOptions(cuoi.options ?? []);
    } catch (error) {
      const thong_diep =
        error instanceof Error ? error.message : "Không thể kết nối tới máy chủ.";
      replaceMessage(conversationId, {
        ...errorMessage(thong_diep),
        id: dangTraLoi.id,
        blocks: daHien
          ? [
              { kind: "paragraph", text: daHien },
              { kind: "paragraph", text: `(${thong_diep})` },
            ]
          : [{ kind: "paragraph", text: thong_diep }],
      });
    } finally {
      window.clearInterval(dongHo);
      setIsSending(false);
    }
  };

  /**
   * Hỏi tiếp theo một lựa chọn của câu hỏi lại.
   *
   * Ghép **nhãn + mã** chứ không gửi mỗi mã: mã trần sẽ bị hiểu là câu hỏi tra thuộc tính,
   * còn "tên thủ tục (mã …)" là câu hỏi đầy đủ mà bộ định danh xử lý được.
   */
  const handlePickOption = (option: ClarifyOption) => {
    if (isSending) return;
    const cau = option.value ? `${option.label} (mã ${option.value})` : option.label;
    void handleSend(cau);
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

    setDeleteTarget({ id: item.id, title: item.title, meta: `${item.messages.length} tin nhắn` });
    setMenu(null);
  };

  const handleConfirmDelete = () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    setPinned((previous) => previous.filter((conversation) => conversation.id !== id));
    setRecent((previous) => previous.filter((conversation) => conversation.id !== id));
    if (activeId === id) {
      activeIdRef.current = "";
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
              isSending={isSending}
            />
          </main>
        ) : (
          <>
            <main className="relative min-h-[calc(100vh-140px)] pb-36 pt-16">
              <div className="mx-auto max-w-[840px] px-6 py-8">
                <MessageList messages={messages} />
                <div ref={cuoiTrang} />
              </div>
            </main>

            <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-border-color bg-main-bg/90 px-4 pb-4 pt-3 backdrop-blur-md md:left-[260px] md:px-8">
              <div className="mx-auto max-w-[840px]">
                {pendingOptions.length > 0 ? (
                  <div className="mb-2 flex flex-wrap gap-2" role="group" aria-label="Chọn thủ tục">
                    {pendingOptions.map((option) => (
                      <button
                        key={`${option.value}-${option.label}`}
                        type="button"
                        onClick={() => handlePickOption(option)}
                        disabled={isSending}
                        className="cursor-pointer rounded-full border border-primary/40 bg-primary-soft px-3 py-1.5 text-left text-[13px] font-semibold text-primary transition-colors hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
                        title={option.hint}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                <MessageInput
                  prefill={prefill}
                  placeholder="Nhập câu hỏi..."
                  onSend={handleSend}
                  disabled={isSending}
                />
                <p className="mt-2 text-center text-[12px] text-text-secondary">
                  Thông tin chỉ mang tính tham khảo và Vui lòng đối chiếu với nguồn chính thức trước khi thực hiện.
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
