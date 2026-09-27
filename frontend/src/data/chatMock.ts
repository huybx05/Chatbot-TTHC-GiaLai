import type { ChatMessage, Conversation, SuggestedQuestion } from "./chatTypes";

/**
 * Dữ liệu mẫu, chép nguyên nội dung từ bản thiết kế HTML gốc.
 *
 * Tách khỏi phần trình bày để sau này nối API chỉ cần đổi chỗ truyền prop.
 */

export const SIDEBAR_PINNED: Conversation[] = [
  { id: "lam-ho-chieu", title: "Làm hộ chiếu phổ thông", pinned: true, path: "lam-ho-chieu", messages: [] },
  {
    id: "dang-ky-khai-sinh",
    title: "Đăng ký khai sinh lưu động",
    pinned: true,
    path: "dang-ky-khai-sinh",
    messages: [],
  },
];

export const SIDEBAR_RECENT: Conversation[] = [
  {
    id: "cap-lai-cccd",
    title: "Cấp đổi, cấp lại thẻ Căn cước",
    pinned: false,
    path: "cap-lai-cccd",
    messages: [
      {
        id: "m1",
        role: "user",
        text: "Cho tôi hỏi hồ sơ và trình tự làm lại thẻ Căn cước công dân (bị mất) gồm những giấy tờ gì và làm ở đâu?",
        time: "09:42",
      },
      {
        id: "m2",
        role: "assistant",
        author: "Trợ lý Thủ tục Hành chính Quốc gia",
        authorNote: "Căn cứ Luật Căn cước số 26/2023/QH15",
        icon: "logo",
        blocks: [
          {
            kind: "paragraph",
            text: "Theo quy định mới nhất có hiệu lực từ ngày 01/07/2024, khi thực hiện thủ tục cấp lại thẻ Căn cước do bị mất, công dân có thể nộp hồ sơ trực tuyến hoặc trực tiếp tại cơ quan quản lý căn cước.",
          },
          {
            kind: "infoCards",
            title: "Hồ sơ & Thủ tục chuẩn bị",
            icon: "assignment_turned_in",
            cards: [
              {
                label: "Hồ sơ cần nộp",
                value: "Phiếu yêu cầu cấp lại thẻ Căn cước",
                description:
                  "Điền trực tiếp trên Cổng Dịch vụ công hoặc tờ khai tại nơi tiếp nhận hồ sơ. Không yêu cầu xuất trình sổ hộ khẩu giấy.",
              },
              {
                label: "Thời hạn giải quyết",
                value: "Tối đa 07 ngày làm việc",
                description:
                  "Kể từ ngày nhận đủ hồ sơ hợp lệ theo quy định của cơ quan Công an có thẩm quyền.",
              },
            ],
          },
          {
            kind: "citation",
            items: [
              {
                title: "[1] Cổng Dịch vụ công Quốc gia - Mã TTHC: 1.002847",
                note: "Cập nhật theo Nghị định 70/2024/NĐ-CP",
              },
            ],
          },
        ],
      },
    ],
  },
  { id: "sang-ten-xe-may", title: "Thủ tục sang tên xe máy", pinned: false, path: "sang-ten-xe-may", messages: [] },
  {
    id: "dang-ky-kinh-doanh",
    title: "Đăng ký hộ kinh doanh cá thể",
    pinned: false,
    path: "dang-ky-kinh-doanh",
    messages: [],
  },
];

/** Cuộc trò chuyện hoàn chỉnh dùng cho màn hình "đang chat". */
export const PASSPORT_CONVERSATION: ChatMessage[] = [
  {
    id: "p1",
    role: "user",
    text: "Làm hộ chiếu phổ thông lần đầu cần chuẩn bị những giấy tờ gì và nộp ở đâu?",
    time: "09:42",
  },
  {
    id: "p2",
    role: "assistant",
    author: "Trợ lý Dịch vụ công Quốc gia",
    icon: "auto_awesome",
    blocks: [
      {
        kind: "paragraph",
        text: "Chào bạn, theo quy định hiện hành về cấp hộ chiếu phổ thông trong nước cho công dân Việt Nam, bạn cần chuẩn bị hồ sơ và thực hiện như sau:",
      },
      {
        kind: "heading",
        text: "Hồ sơ cần chuẩn bị:",
      },
      {
        kind: "ordered",
        items: [
          {
            label: "Tờ khai đề nghị cấp hộ chiếu (Mẫu TK01):",
            text: "Điền đầy đủ thông tin hoặc hoàn thiện kê khai trực tuyến qua Cổng Dịch vụ công.",
          },
          {
            label: "Thẻ Căn cước công dân (CCCD):",
            text: "Loại có gắn chip điện tử hoặc Căn cước hiện hành, còn nguyên giá trị sử dụng.",
          },
          {
            label: "02 ảnh chân dung 4x6 cm:",
            text: "Phông nền trắng, chụp không quá 6 tháng (nộp file số nếu làm online).",
          },
          {
            label: "Bản sao Giấy khai sinh hoặc trích lục khai sinh:",
            text: "Chỉ áp dụng đối với người dưới 14 tuổi chưa có CCCD.",
          },
        ],
      },
      {
        kind: "heading",
        text: "Nơi nộp hồ sơ:",
      },
      {
        kind: "unordered",
        items: [
          {
            label: "Nộp trực tuyến (Khuyến nghị):",
            text: "Thực hiện trên Cổng Dịch vụ công Quốc gia hoặc Cổng Dịch vụ công Bộ Công an bằng tài khoản VNeID cấp độ 2.",
          },
          {
            label: "Nộp trực tiếp:",
            text: "Tại Phòng Quản lý xuất nhập cảnh Công an tỉnh/thành phố trực thuộc Trung ương nơi bạn thường trú hoặc tạm trú.",
          },
        ],
      },
      {
        kind: "strongParagraph",
        label: "Thời hạn giải quyết:",
        text: "08 ngày làm việc kể từ ngày cơ quan có thẩm quyền tiếp nhận đủ hồ sơ hợp lệ.",
      },
      {
        kind: "strongParagraph",
        label: "Lệ phí:",
        text: "160.000 đồng (đang áp dụng giảm 20% khi nộp hồ sơ trực tuyến theo quy định).",
      },
      {
        kind: "citation",
        items: [
          { title: "[1] Cổng Dịch vụ công Quốc gia", note: "" },
          { title: "[2] Luật Xuất cảnh, nhập cảnh của công dân Việt Nam", note: "" },
        ],
      },
    ],
  },
];

export const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  { id: "q1", text: "Làm hộ chiếu phổ thông lần đầu cần chuẩn bị những giấy tờ gì?" },
  { id: "q2", text: "Thủ tục cấp lại thẻ Căn cước công dân trực tuyến như thế nào?" },
  { id: "q3", text: "Hồ sơ và quy trình đăng ký khai sinh lưu động gồm những gì?" },
  { id: "q4", text: "Lệ phí và thủ tục sang tên xe máy hiện nay ra sao?" },
];
