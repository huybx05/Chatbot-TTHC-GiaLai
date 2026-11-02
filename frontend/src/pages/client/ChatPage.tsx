import { useEffect, useMemo, useRef, useState } from "react";

import { login, logout, register, restoreSession, type AuthUser } from "../../api/auth";
import { askChatStream, type StreamKetQua } from "../../api/chat";
import { getFaqSuggestions } from "../../api/faq";
import { ApiError } from "../../api/http";
import { recordPageVisit } from "../../api/visits";
import {
  createChatSession,
  createGuestSession,
  deleteChatSession,
  deleteGuestSession,
  getChatMessages,
  getChatSessions,
  getGuestSession,
  renameChatSession,
  setChatSessionPinned,
  type ChatMessageRecord,
  type ChatSession,
} from "../../api/chatSessions";
import AuthDialog from "../../components/client/AuthDialog";
import ChatHeader from "../../components/client/ChatHeader";
import ChatSidebar from "../../components/client/ChatSidebar";
import ContextMenu from "../../components/client/ContextMenu";
import DeleteDialog from "../../components/client/DeleteDialog";
import MessageInput from "../../components/client/MessageInput";
import MessageList from "../../components/client/MessageList";
import WelcomeView from "../../components/client/WelcomeView";
import RenameDialog from "../../components/client/RenameDialog";
import { SUGGESTED_QUESTIONS } from "../../data/chatSuggestions";
import type {
  AssistantMessage,
  ChatMessage,
  Conversation,
  SuggestedQuestion,
} from "../../data/chatTypes";
import type { ChatResponse, ClarifyOption } from "../../types/chat";

const ACTIVE_SESSION_KEY = "chat.active-session";

function readStoredSession(): string {
  try {
    const stored = window.sessionStorage.getItem(ACTIVE_SESSION_KEY);
    if (stored) return stored;

    // Tương thích link cũ `?session=...`: đọc một lần rồi xoá khỏi URL.
    const legacy = new URLSearchParams(window.location.search).get("session");
    if (!legacy) return "";

    window.sessionStorage.setItem(ACTIVE_SESSION_KEY, legacy);
    const url = new URL(window.location.href);
    url.searchParams.delete("session");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    return legacy;
  } catch {
    return "";
  }
}

function writeStoredSession(sessionId: string | null): void {
  try {
    if (sessionId) {
      window.sessionStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
    } else {
      window.sessionStorage.removeItem(ACTIVE_SESSION_KEY);
    }
  } catch {
    // Trình duyệt chặn storage — vẫn chạy trong bộ nhớ của trang.
  }
}

interface DeleteTarget {
  id: string;
  title: string;
  /** Chuỗi mô tả: ngày tạo và số tin nhắn. */
  meta: string;
}

interface RenameTarget {
  id: string;
  title: string;
}

function currentTime(): string {
  return new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** Chuyển một message UI thành text để gửi làm history cho guest. */
function asHistoryText(message: ChatMessage): string {
  if (message.role === "user") return message.text;

  return message.blocks
    .map((block) => {
      if ("text" in block) {
        return "label" in block ? `${block.label}: ${block.text}` : block.text;
      }
      if ("items" in block) {
        return block.items
          .map((item) =>
            Object.values(item)
              .filter((value): value is string => typeof value === "string")
              .join(" "),
          )
          .join("\n");
      }
      return "";
    })
    .filter(Boolean)
    .join("\n")
    .trim();
}

function asConversation(session: ChatSession): Conversation {
  return {
    id: session.id,
    title: session.title,
    pinned: session.is_pinned,
    path: session.id,
    messages: [],
    messageCount: session.message_count,
  };
}

function formatMessageTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** Dựng lại đúng cấu trúc tin nhắn từ bản ghi server (để mở lại phiên cũ). */
function asChatMessage(record: ChatMessageRecord): ChatMessage {
  if (record.role === "user") {
    return {
      id: record.id,
      role: "user",
      text: record.content,
      time: formatMessageTime(record.created_at),
    };
  }

  const meta = record.metadata as Partial<ChatResponse>;
  const rawFeedback = record.metadata.feedback;
  const feedback =
    rawFeedback && typeof rawFeedback === "object"
      ? (rawFeedback as { value?: "like" | "dislike"; reasons?: unknown; comment?: unknown })
      : null;
  const response: ChatResponse = {
    answer: record.content,
    citations: meta.citations ?? [],
    documents: meta.documents ?? [],
    procedure: meta.procedure,
    status: meta.status ?? "answered",
    options: meta.options ?? [],
    abstained: meta.abstained ?? false,
  };
  return {
    ...assistantMessage(response),
    id: record.id,
    messageId: record.id,
    feedback:
      feedback && (feedback.value === "like" || feedback.value === "dislike")
        ? feedback.value
        : null,
    feedbackReasons: Array.isArray(feedback?.reasons)
      ? feedback.reasons.filter((item): item is string => typeof item === "string")
      : [],
    feedbackComment: typeof feedback?.comment === "string" ? feedback.comment : "",
  };
}

function assistantMessage(response: ChatResponse): AssistantMessage {
  const blocks: AssistantMessage["blocks"] = [
    { kind: "paragraph", text: response.answer },
  ];

  if (response.documents?.length) {
    blocks.push({
      kind: "files",
      items: response.documents,
    });
  }

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
        ? "Cần bạn mô tả lại"
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
  const [requestedSessionId, setRequestedSessionId] =
    useState(readStoredSession);

  const [pinned, setPinned] = useState<Conversation[]>([]);
  const [recent, setRecent] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const activeIdRef = useRef("");
  const visitRecorded = useRef(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prefill, setPrefill] = useState("");
  const [suggestions, setSuggestions] =
    useState<SuggestedQuestion[]>(SUGGESTED_QUESTIONS);
  const [defaultSuggestions, setDefaultSuggestions] =
    useState<SuggestedQuestion[]>(SUGGESTED_QUESTIONS);
  const [isSending, setIsSending] = useState(false);

  const applySuggestions = (
    items: { id: string; question: string }[] | undefined,
  ) => {
    if (!Array.isArray(items)) return;
    setSuggestions(
      items.map((item) => ({
        id: item.id,
        text: item.question,
      })),
    );
  };

  const lastUserText = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "user") return message.text.trim();
    }
    return "";
  }, [messages]);

  const followUpSuggestions = useMemo(
    () =>
      suggestions
        .filter((item) => item.text.trim() !== lastUserText)
        .slice(0, 5),
    [lastUserText, suggestions],
  );

  useEffect(() => {
    let cancelled = false;

    getFaqSuggestions(6)
      .then((response) => {
        if (cancelled) return;
        const defaults = response.items.map((item) => ({
          id: item.id,
          text: item.question,
        }));
        setDefaultSuggestions(defaults);
        setSuggestions(defaults);
      })
      .catch(() => {
        // Giữ danh sách tĩnh nếu API FAQ chưa sẵn sàng.
      });

    return () => {
      cancelled = true;
    };
  }, []);
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authRestoring, setAuthRestoring] = useState(true);
  const [menu, setMenu] = useState<{ id: string; anchor: HTMLElement } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [renameTarget, setRenameTarget] = useState<RenameTarget | null>(null);

  const allConversations = useMemo(() => [...pinned, ...recent], [pinned, recent]);
  const menuConversation = menu ? allConversations.find((item) => item.id === menu.id) : undefined;

  useEffect(() => {
    if (!cuonDenLuotMoi.current) return;
    cuonDenLuotMoi.current = false;
    cuoiTrang.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  useEffect(() => {
    if (visitRecorded.current) return;
    visitRecorded.current = true;
    void recordPageVisit().catch(() => {
      // Lỗi đếm lượt truy cập không được ảnh hưởng tới chat.
    });
  }, []);

  useEffect(() => {
    let mounted = true;

    void restoreSession()
      .then((session) => {
        if (!mounted) return;
        setCurrentUser(session.user);
      })
      .catch(() => {
        // Không có phiên: giữ trạng thái khách.
      })
      .finally(() => {
        if (mounted) setAuthRestoring(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const closeSidebar = () => setMobileSidebarOpen(false);

  /**
   * Giữ cuộc trò chuyện đang mở trong sessionStorage.
   *
   * Nhờ vậy F5 vẫn mở lại đúng phiên, nhưng ID không nằm trên URL
   * (không lọt vào history, Referer hay log proxy).
   */
  const setActiveSession = (sessionId: string | null) => {
    writeStoredSession(sessionId);
    setRequestedSessionId(sessionId ?? "");
  };

  const loadSessions = async () => {
    const { items } = await getChatSessions();
    const conversations = items.map(asConversation);
    setPinned(conversations.filter((item) => item.pinned));
    setRecent(conversations.filter((item) => !item.pinned));
  };

  useEffect(() => {
    if (!currentUser) return;
    void loadSessions();
  }, [currentUser]);

  useEffect(() => {
    if (authRestoring || currentUser) return;
    let mounted = true;
    getGuestSession()
      .then((guest) => {
        if (!mounted || guest.messages.length === 0) return;
        activeIdRef.current = guest.session_id;
        setActiveId(guest.session_id);
        setMessages(guest.messages.map(asChatMessage));
      })
      .catch(() => {
        // Chưa có phiên khách hoặc phiên đã hết hạn: chờ câu hỏi đầu tiên.
      });
    return () => {
      mounted = false;
    };
  }, [authRestoring, currentUser]);

  const handleDeleteGuestConversation = async () => {
    try {
      await deleteGuestSession();
    } catch {
      // Cookie/phiên đã hết hạn thì cũng coi như xoá xong.
    }
    resetTemporaryConversation();
    setActiveSession(null);
  };

  const resetTemporaryConversation = () => {
    activeIdRef.current = "";
    setPinned([]);
    setRecent([]);
    setActiveId("");
    setMessages([]);
    setPrefill("");
    setPendingOptions([]);
    setSuggestions(defaultSuggestions);
    setMenu(null);
    setDeleteTarget(null);
    setRenameTarget(null);
    closeSidebar();
  };

  const handleAuthenticate = async (
    mode: "login" | "register",
    username: string,
    password: string,
  ) => {
    const session = mode === "login" ? await login(username, password) : await register(username, password);
    if (!currentUser) {
      try {
        await deleteGuestSession();
      } catch {
        // Phiên khách đã hết hạn thì không cần xoá nữa.
      }
    }
    resetTemporaryConversation();
    setActiveSession(null);
    setCurrentUser(session.user);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      setCurrentUser(null);
      setActiveSession(null);
      resetTemporaryConversation();
    }
  };

  const handleNewConversation = async () => {
    if (isSending) return;

    const session = await createChatSession();
    const conversation = asConversation(session);
    setPinned((previous) => session.is_pinned ? [conversation, ...previous] : previous);
    setRecent((previous) => session.is_pinned ? previous : [conversation, ...previous]);
    activeIdRef.current = session.id;
    setActiveId(session.id);
    setActiveSession(session.id);
    setMessages([]);
    setPrefill("");
    setPendingOptions([]);
    setSuggestions(defaultSuggestions);
    setMenu(null);
    closeSidebar();
  };

  const handleSelectConversation = async (id: string) => {
    activeIdRef.current = id;
    setActiveId(id);
    setActiveSession(id);
    setMenu(null);
    setPendingOptions([]);

    const conversation = allConversations.find((item) => item.id === id);
    setMessages(conversation?.messages ?? []);

    // Phiên tạm (chưa đăng nhập) chỉ có trong bộ nhớ; không gọi API.
    if (!currentUser) return;

    try {
      const { items } = await getChatMessages(id);
      if (activeIdRef.current !== id) return;

      const loaded = items.map(asChatMessage);
      setMessages(loaded);
      const update = (conversations: Conversation[]) =>
        conversations.map((item) =>
          item.id === id ? { ...item, messages: loaded, messageCount: loaded.length } : item,
        );
      setPinned(update);
      setRecent(update);

      // Khôi phục nút hỏi lại nếu tin nhắn cuối cùng là một câu hỏi làm rõ.
      const last = items[items.length - 1];
      const meta = last?.metadata as Partial<ChatResponse> | undefined;
      if (last?.role === "assistant" && meta?.status === "clarify") {
        setPendingOptions([]);
      }
    } catch (error) {
      // Session đã bị xoá hoặc không còn thuộc user: bỏ khỏi URL để F5 không lặp lỗi.
      if (error instanceof ApiError && error.status === 404 && activeIdRef.current === id) {
        activeIdRef.current = "";
        setActiveId("");
        setMessages([]);
        setActiveSession(null);
      }
      // Lỗi mạng: giữ tin nhắn đang có trong bộ nhớ, không làm trắng khung chat.
    }
  };

  // F5: sau khi biết user, mở lại phiên đang lưu trong sessionStorage
  // và tải tin nhắn. Effect chạy lại khi user hoặc session đang mở đổi.
  useEffect(() => {
    if (!currentUser || !requestedSessionId) return;
    if (activeIdRef.current === requestedSessionId) return;
    void handleSelectConversation(requestedSessionId);
    // `handleSelectConversation` là hàm trong cùng render; các phụ thuộc thật
    // là user hiện tại và id phiên đang lưu.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser, requestedSessionId]);

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
      items.map((item) => {
        if (item.id !== id) return item;
        const previousCount = item.messageCount ?? item.messages.length;
        const title =
          message.role === "user" && previousCount === 0
            ? message.text.length > 48
              ? `${message.text.slice(0, 47)}…`
              : message.text
            : item.title;
        return {
          ...item,
          title,
          messages: [...item.messages, message],
          messageCount: previousCount + 1,
        };
      });
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
    let conversationId = activeId;
    let hasServerSession = Boolean(activeId);
    if (!conversationId) {
      const session = currentUser ? await createChatSession() : await createGuestSession();
      conversationId = "id" in session ? session.id : session.session_id;
      hasServerSession = true;
      const title = text.length > 48 ? `${text.slice(0, 47)}…` : text;
      setRecent((previous) => [
        {
          id: conversationId,
          title,
          pinned: false,
          path: conversationId,
          messages: [userMessage],
          messageCount: 1,
        },
        ...previous,
      ]);
      activeIdRef.current = conversationId;
      setActiveId(conversationId);
    } else {
      appendToConversation(conversationId, userMessage);
    }
    if (hasServerSession) setActiveSession(conversationId);
    setMessages((previous) => [...previous, userMessage]);
    setPrefill("");
    setPendingOptions([]);
    setIsSending(true);

    const requestPayload = hasServerSession
      ? {
          question: text,
          session_id: conversationId,
        }
      : {
          question: text,
          history: messages
            .map((message) => ({
              role: message.role,
              content: asHistoryText(message),
            }))
            .filter((message) => message.content.length > 0)
            .slice(-6),
        };

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
        requestPayload,
        {
          onDelta: (manh) => {
            gom += manh;
            hangDoi += manh;
          },
          onMeta: (meta) => {
            setPendingOptions([]);
            applySuggestions(meta.suggestions);
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
        documents: ket_qua.meta?.documents ?? [],
        procedure: ket_qua.meta?.procedure ?? undefined,
        status: ket_qua.meta?.status ?? "answered",
        options: ket_qua.meta?.options ?? [],
        abstained: (ket_qua.meta?.status ?? "answered") !== "answered",
        suggestions: ket_qua.meta?.suggestions ?? [],
      };
      replaceMessage(conversationId, {
        ...assistantMessage(cuoi),
        id: dangTraLoi.id,
        messageId: ket_qua.meta?.message_id,
      });
      if (cuoi.status === "clarify") setPendingOptions([]);

    } catch (error) {
      const thong_diep =
        error instanceof Error ? error.message : "Không thể kết nối tới máy chủ.";
      if (error instanceof ApiError && error.status === 401 && !currentUser) {
        resetTemporaryConversation();
        setActiveSession(null);
      }
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

  const handleTogglePin = async (targetId?: string) => {
    const id = targetId ?? menu?.id;
    if (!id) return;
    const item = allConversations.find((conversation) => conversation.id === id);
    if (!item) return;

    const updated = await setChatSessionPinned(id, !item.pinned);
    const next = { ...item, pinned: updated.is_pinned };
    setPinned((previous) =>
      next.pinned ? [next, ...previous.filter((conversation) => conversation.id !== id)] : previous.filter((conversation) => conversation.id !== id),
    );
    setRecent((previous) =>
      next.pinned ? previous.filter((conversation) => conversation.id !== id) : [next, ...previous.filter((conversation) => conversation.id !== id)],
    );
    setMenu(null);
  };

  const handleRequestDelete = () => {
    if (!menu) return;
    const item = allConversations.find((conversation) => conversation.id === menu.id);
    if (!item) return;

    setDeleteTarget({
      id: item.id,
      title: item.title,
      meta: `${item.messageCount ?? item.messages.length} tin nhắn`,
    });
    setMenu(null);
  };

  const handleRequestRename = () => {
    if (!menu) return;
    const item = allConversations.find((conversation) => conversation.id === menu.id);
    if (!item) return;

    setRenameTarget({ id: item.id, title: item.title });
    setMenu(null);
  };

  const handleConfirmRename = async (title: string) => {
    if (!renameTarget) return;
    const updated = await renameChatSession(renameTarget.id, title);
    const replace = (items: Conversation[]) =>
      items.map((item) => (item.id === updated.id ? { ...item, title: updated.title } : item));
    setPinned(replace);
    setRecent(replace);
    setRenameTarget(null);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    await deleteChatSession(id);
    setPinned((previous) => previous.filter((conversation) => conversation.id !== id));
    setRecent((previous) => previous.filter((conversation) => conversation.id !== id));
    if (activeId === id) {
      activeIdRef.current = "";
      setActiveId("");
      setMessages([]);
      setActiveSession(null);
      setSuggestions(defaultSuggestions);
    }
    setDeleteTarget(null);
  };

  if (authRestoring) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-main-bg text-text-secondary"
        aria-busy="true"
        aria-label="Đang khôi phục phiên đăng nhập"
      >
        <span className="material-symbols-outlined animate-spin text-[24px]">progress_activity</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-main-bg font-sans text-text-primary antialiased">
      {currentUser ? (
        <ChatSidebar
          pinned={pinned}
          recent={recent}
          activeId={activeId}
          menuForId={menu?.id ?? null}
          mobileOpen={mobileSidebarOpen}
          collapsed={sidebarCollapsed}
          onClose={closeSidebar}
          onToggleCollapsed={() => setSidebarCollapsed((collapsed) => !collapsed)}
          onSelect={handleSelectConversation}
          onNewConversation={handleNewConversation}
          onTogglePin={handleTogglePin}
          onOpenMenu={(id, anchor) => setMenu({ id, anchor })}
        />
      ) : null}

      <div className={currentUser && !sidebarCollapsed ? "md:pl-[260px]" : ""}>
        <ChatHeader
          onOpenAuth={() => setAuthOpen(true)}
          onLogout={handleLogout}
          onDeleteGuestConversation={
            currentUser === null && messages.length > 0
              ? () => void handleDeleteGuestConversation()
              : undefined
          }
          onOpenSidebar={() => setMobileSidebarOpen(true)}
          onToggleSidebar={() => setSidebarCollapsed((collapsed) => !collapsed)}
          showSidebar={currentUser !== null}
          sidebarCollapsed={sidebarCollapsed}
          username={currentUser?.username ?? null}
        />

        {messages.length === 0 ? (
          <main className="relative flex min-h-[calc(100vh-64px)] flex-col justify-between pt-16">
            <WelcomeView
              suggestions={suggestions.slice(0, 5)}
              prefill={prefill}
              onPickSuggestion={(text) => {
                setPrefill(text);
                void handleSend(text);
              }}
              onSend={handleSend}
              isSending={isSending}
            />
          </main>
        ) : (
          <>
            <main className="relative min-h-[calc(100vh-140px)] pb-36 pt-16">
              <div className="mx-auto max-w-[840px] px-6 py-8">
                <MessageList
                  messages={messages}
                  followUpSuggestions={isSending ? [] : followUpSuggestions}
                  onPickSuggestion={(text) => {
                    setPrefill(text);
                    void handleSend(text);
                  }}
                />
                <div ref={cuoiTrang} />
              </div>
            </main>

            <div
              className={[
                "fixed bottom-0 left-0 right-0 z-40 border-t border-border-color bg-main-bg/90 px-4 pb-4 pt-3 backdrop-blur-md md:px-8",
                currentUser && !sidebarCollapsed ? "md:left-[260px]" : "",
              ].join(" ")}
            >
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
          onRename={handleRequestRename}
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

      {renameTarget ? (
        <RenameDialog
          conversationTitle={renameTarget.title}
          onCancel={() => setRenameTarget(null)}
          onConfirm={handleConfirmRename}
        />
      ) : null}

      {authOpen ? (
        <AuthDialog
          onAuthenticate={handleAuthenticate}
          onClose={() => setAuthOpen(false)}
        />
      ) : null}
    </div>
  );
}
