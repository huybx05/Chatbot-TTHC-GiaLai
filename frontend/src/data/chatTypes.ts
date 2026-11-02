/** Kiểu dữ liệu cho giao diện client. Khớp nội dung bản thiết kế gốc. */

/**
 * Một mục trong danh sách có thứ tự hoặc không thứ tự.
 *
 * Bản thiết kế gốc in đậm phần nhãn và in nghiêng phần viện dẫn, nên tách
 * thành từng phần thay vì gộp thành một chuỗi.
 */
export interface ListItem {
  /** Phần mở đầu in đậm. */
  label: string;
  /** Phần nội dung còn lại, in thường. */
  text: string;
  /** Phần viện dẫn in nghiêng. */
  legal?: string;
}

/** Một khối nội dung trong câu trả lời của trợ lý. */
export type AnswerBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "strongParagraph"; label: string; text: string }
  | { kind: "ordered"; items: ListItem[] }
  | { kind: "unordered"; items: ListItem[] }
  | { kind: "files"; items: ProcedureDocument[] }
  | { kind: "citation"; items: CitationItem[] };

export interface CitationItem {
  title: string;
  note: string;
  url?: string;
}

export interface UserMessage {
  id: string;
  role: "user";
  text: string;
  /** Giờ hiển thị, ví dụ "09:42". */
  time: string;
}

export interface AssistantMessage {
  id: string;
  /** ID message do backend trả về; dùng để gửi feedback. */
  messageId?: string;
  role: "assistant";
  /** Tên hiển thị cạnh avatar. */
  author: string;
  /** Dòng phụ dưới tên, ví dụ căn cứ pháp lý. */
  authorNote?: string;
  icon: string;
  blocks: AnswerBlock[];
  feedback?: "like" | "dislike" | null;
  feedbackReasons?: string[];
  feedbackComment?: string;
  /**
   * Giai đoạn đang chạy, hiện cạnh tên trợ lý.
   *
   * * `searching` — đang định tuyến và truy xuất (1–6 giây, chưa có chữ nào);
   * * `answering` — đã có bằng chứng, mô hình đang chuẩn bị chữ;
   * * *không có* — chữ đã chạy (hoặc đã xong). Lúc chữ chạy thì chính dòng chữ là dấu hiệu
   *   tiến độ, thêm vòng xoay chỉ làm rối.
   */
  phase?: "searching" | "answering";
}

export type ChatMessage = UserMessage | AssistantMessage;

export interface Conversation {
  id: string;
  title: string;
  pinned: boolean;
  /** Đường dẫn điều hướng trong bản thiết kế gốc. */
  path: string;
  messages: ChatMessage[];
  /** Số tin nhắn phía server; dùng khi chưa tải nội dung tin nhắn. */
  messageCount?: number;
}

/** Icon dùng cho mục gợi ý và các widget nhỏ. */
export interface SuggestedQuestion {
  id: string;
  text: string;
}

/** Dùng cho hiển thị mẫu hồ sơ để tải    */
export interface ProcedureDocument {
  id: string;
  document_name: string;
  file_name: string;
  mime_type: string | null;
  size_bytes: number | null;
  download_url: string;
  case_order?: number;
  component_index?: number;
  case_orders?: number[];
  component_indexes?: number[];
  file_id?: string | null;
  file_ids?: string[];
}