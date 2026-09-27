# Giao diện client — ghi chú chuyển đổi

Chuyển 3 màn hình HTML/CSS (Tailwind CDN) sang Tailwind 4 bản build + component React,
**không đổi màu sắc và bố cục**. Tài liệu này ghi những chỗ buộc phải quyết định.

## Nguồn

| Màn hình | File gốc | Trạng thái trong code |
|---|---|---|
| Chưa chat | màn 1 | `messages.length === 0` → `WelcomeView` |
| Đang chat | màn 2 | có tin nhắn → `MessageList` + `MessageInput` cố định dưới |
| Menu ba chấm + xác nhận xóa | màn 3 | `ContextMenu` + `DeleteDialog` |

## Bộ token

Lấy nguyên giá trị màu từ **màn 2** (màn đầy đủ token nhất, khớp `design.md`) và áp dụng
thống nhất cho cả 3 màn hình. Định nghĩa ở `src/styles/global.css` trong khối `@theme`
của Tailwind 4, nên dùng được trực tiếp dưới dạng utility (`bg-main-bg`, `text-primary`…).

```text
main-bg #FAF7F2   sidebar-bg #F2ECE4   card-surface #FFFDF9   secondary-surface #F7F1EA
primary #A54E2D   primary-hover #8F4225   primary-soft #F0DDD2   secondary-accent #D4A23A
text-primary #2E2E2E   text-secondary #6A625B
border-color #E6DDD2   border-strong #D8CEC3
user-bubble #F3EDE6   hover-item #ECE3D9
danger #B2463B   danger-hover #96382E   danger-surface #FBEFED
```

## Ba màn hình gốc không thống nhất — cách xử lý

Bản gốc có 3 bảng token khác nhau cho cùng một sản phẩm. Đã thống nhất theo màn 2; các
điểm dưới đây là chỗ giá trị gốc của màn 1 hoặc màn 3 bị thay bằng giá trị tương ứng
của màn 2. **Không có màu nào bị đổi sang màu khác về mặt thị giác.**

| Chỗ | Màn 1 / màn 3 ghi | Đã dùng (theo màn 2) | Ghi chú |
|---|---|---|---|
| Nền hover item sidebar | `#ECE3D9` (m1) / `#EAE2D7` (m3) | `#ECE3D9` | Lệch 1 sắc độ giữa hai bản gốc |
| Bong bóng người dùng | `#F0EAE1` (m3) | `#F3EDE6` | |
| Item đang chọn | `border-l-4` (m1) / `border` (m3) | `border` | |
| Nút gửi | tròn (m1, m2) / vuông (m3) | tròn | m3 lệch so với hai màn kia |
| Icon header | `verified` (m1, m3) / `account_balance` (m2) | `verified` | Giữ icon của màn 1 và 3 vì đây là header |
| Branding sidebar | "Trợ lý Hành chính" (m1) / "Dịch vụ công AI" (m3) | "Trợ lý Thủ tục hành chính" | Theo màn 2 |

## Quyết định khác

1. **Icon nhúng local.** Dùng gói `material-symbols` (font biến thiên nằm trong
   `node_modules`, Vite copy vào `dist`). Không gọi Google Fonts cho icon. Chữ Be Vietnam
   Pro vẫn nạp từ Google Fonts như bản gốc.
2. **Nội dung disclaimer lấy theo màn 2**: "…đối chiếu với văn bản quy phạm pháp luật
   hiện hành và Cổng Dịch vụ công Quốc gia." Màn 1 ghi khác đôi chữ.
3. **Menu ba chấm dùng portal + đo vị trí.** Bản gốc đặt cứng `top-[228px] left-[250px]`,
   chỉ đúng với một dòng cụ thể. Bản mới neo theo nút được bấm nên đúng ở mọi dòng.
4. **Drawer mobile.** Bản gốc có nút hamburger nhưng sidebar vẫn `fixed w-[260px]` và nội
   dung `pl-[260px]`, nên trên điện thoại sidebar đè lên nội dung. Bản mới: dưới `md`
   sidebar trượt ra kèm lớp phủ mờ, đóng bằng nút phủ, chọn xong cuộc trò chuyện, hoặc
   phím Esc. Từ `md` trở lên giữ nguyên bố cục gốc.
5. **Chưa làm chế độ tối.** Bản gốc khai báo `darkMode: "class"` nhưng không màn hình nào
   có bảng màu tối. Không tự bịa để tránh đổi giao diện. Sẽ bổ sung khi có thiết kế.
6. **Thêm `text-[13px]` cho phụ đề sidebar** (màn 1 ghi 13px, màn 2 ghi 12px) — lấy 12px
   theo màn 2.

## Mức độ khớp đã kiểm chứng

So nội dung text render thật giữa bản gốc và bản viết lại (Chrome headless, đối chiếu DOM):

```text
Màn 2 (đang chat): 48 dòng text ở bản gốc
  khác biệt còn lại: 5, tất cả đều hợp lý
    - "more_vert"      : icon, không phải nội dung
    - "—" tách node    : chỉ khác cách chia text node
    - disclaimer       : cố ý lấy theo màn 2
    - 1 dòng           : tiêu đề section trong file nguồn, không thuộc trang
```

Trong quá trình so đã phát hiện và sửa một lỗi thật: bản đầu làm **mất chữ in đậm** ở
nhãn các mục danh sách (bản gốc bọc `<strong>`). Đã tách `ListItem` thành
`label` / `text` / `legal` để giữ đúng định dạng.

## Chưa kiểm chứng

- **Màn 3 (menu + hộp thoại xóa)**: mới kiểm tra mã nguồn, chưa đối chiếu bằng ảnh render
  vì cần thao tác bấm. Nên xem lại bằng mắt.
- **Màn 1 (màn chào)**: đã đối chiếu cấu trúc nhưng lần so cuối bị dừng giữa đường.
- **Chế độ tối**: chưa làm.

## Chạy

```powershell
npm install
npm run dev        # http://localhost:5173
npm run typecheck
npm run build
```
