# Frontend — Client + Admin

Một app React + Vite + TypeScript phục vụ **hai giao diện**, tách theo route:

```text
/                  → giao diện người dân
/admin             → tổng quan monitoring
/admin/data-quality
/admin/retrieval
/admin/pipeline
```

## Cấu trúc

```text
src/
├── main.tsx                     entry: BrowserRouter + App
├── App.tsx                      khai báo route cho cả 2 giao diện
├── vite-env.d.ts
│
├── api/                         tầng gọi backend, dùng chung
│   ├── config.ts                base URL, timeout, app mode
│   ├── http.ts                  fetch wrapper + ApiError
│   ├── chat.ts                  POST /chat
│   ├── procedures.ts            GET /search, GET /procedures/{code}
│   └── admin.ts                 GET /api/admin/* (backend chưa có)
│
├── components/
│   ├── client/                  giao diện người dân
│   │   ├── ChatSidebar.tsx      danh sách cuộc trò chuyện + drawer mobile
│   │   ├── ConversationItem.tsx một dòng cuộc trò chuyện
│   │   ├── ChatHeader.tsx       header có nút hamburger (mobile)
│   │   ├── WelcomeView.tsx      màn chào + câu hỏi gợi ý + ô nhập
│   │   ├── MessageList.tsx      cột tin nhắn
│   │   ├── MessageAnswer.tsx    bong bóng user, câu trả lời, thẻ thông tin, citation
│   │   ├── MessageInput.tsx     ô nhập tự giãn
│   │   ├── ContextMenu.tsx      menu ba chấm (Ghim/Bỏ ghim, Xóa)
│   │   └── DeleteDialog.tsx     hộp thoại xác nhận xóa
│   ├── ui/                      component nhỏ dùng chung
│   │   ├── Placeholder.tsx
│   │   ├── States.tsx
│   │   └── ThemeToggle.tsx
│   └── layout/
│       ├── ClientLayout.tsx     lớp ngoài rỗng cho vùng người dân
│       └── AdminLayout.tsx      sidebar điều hướng admin
│
├── data/                        dữ liệu mẫu, tách khỏi phần trình bày
│   ├── chatTypes.ts
│   └── chatMock.ts
│
├── hooks/
│   └── useTheme.ts
│
├── pages/
│   ├── client/
│   │   └── ChatPage.tsx
│   └── admin/
│       ├── OverviewPage.tsx
│       ├── DataQualityPage.tsx
│       ├── RetrievalPage.tsx
│       └── PipelinePage.tsx
│
├── types/
│   ├── chat.ts
│   ├── procedure.ts
│   └── admin.ts
│
└── styles/
    └── global.css               @import tailwind + font icon + @theme token
```

## Chạy

```powershell
npm install
npm run dev        # http://localhost:5173
npm run typecheck  # tsc --noEmit
npm run build      # typecheck + vite build
```

Dev server chuyển tiếp `/chat`, `/search`, `/procedures`, `/api/admin`, `/health`
sang backend `http://127.0.0.1:8000`:

```powershell
uv run uvicorn backend.app.main:app --reload
```

## Quy ước bắt buộc

### 1. `/admin` là route UI, API monitoring nằm ở `/api/admin`

Không đưa `/admin` vào danh sách proxy trong `vite.config.ts`. Nếu đưa vào, request
`GET /admin` của người dùng sẽ bị đẩy sang backend và trang admin trả 502.

### 2. File nằm trực tiếp trong thư mục depth-1 dưới `src/` không được lùi ≥2 cấp

Resolver của môi trường hiện tại xử lý sai đường dẫn tương đối lùi nhiều cấp **khi file
nằm ngay trong một thư mục con cấp 1 của `src/`**:

```text
src/components/ThemeToggle.tsx   import "../../hooks/useTheme"   ❌ TS2307
src/components/layout/X.tsx      import "../ui/ThemeToggle.tsx"  ✅
src/components/ui/X.tsx          import "../../hooks/useTheme"   ✅
src/pages/admin/X.tsx            import "../../components/..."   ✅
```

Vì vậy: **mọi file trong `src/<dir>/` phải nằm trong một thư mục con**, không đặt trực
tiếp. Đây là lý do `src/components/ui/` và `src/components/client/` tồn tại.

`src/api/`, `src/data/`, `src/hooks/`, `src/types/`, `src/styles/` giữ file trực tiếp được
vì chúng chỉ import thư viện ngoài hoặc lùi 1 cấp. Nếu một file trong đó cần lùi ≥2 cấp,
phải chuyển nó vào thư mục con.

## Giao diện

- **Người dân**: chuyển từ 3 màn hình HTML/CSS sang Tailwind 4 + React. Chi tiết bộ
  token, các chỗ phải thống nhất giữa 3 màn hình, và mức độ khớp đã kiểm chứng nằm ở
  `docs/client_ui.md` (root dự án).
- **Admin**: mới có cấu trúc, chưa có UI. Ngoài V3 — xem `docs/decisions.md`.

## Chưa làm

- Chưa nối API chat. Nội dung đang lấy từ `src/data/chatMock.ts`.
- Chưa có chế độ tối: bản thiết kế khai báo `darkMode: "class"` nhưng không màn hình nào
  có bảng màu tối, nên chưa có gì để dựng.
- Chưa có backend endpoint cho admin — `src/api/admin.ts` gọi các path chưa tồn tại.
- Chưa có test frontend.
