# Decisions — sai lệch so với V3

Ghi lại những quyết định đi ra ngoài `PROJECT_GUIDE_TTHC_AI_CHATBOT_v3.md`, kèm lý do.
V3 yêu cầu: nếu skeleton hoặc kiến trúc thay đổi thì phải cập nhật tài liệu đồng thời
với code, để tài liệu và implementation không lệch nhau.

---

## D1 — Thêm giao diện admin monitoring

**Ngày:** đang thực hiện
**Trạng thái:** đã dựng cấu trúc thư mục, chưa có backend

**V3 nói gì:**

```text
§52: "Không cần login, Redux, admin dashboard ở MVP."
§11: backend/app/api/ chỉ có chat.py, search.py, procedures.py
§56: backend phải ghi log, nhưng không yêu cầu API đọc log
§58: không tự ý thêm service/framework mới
```

**Thực tế:** có yêu cầu làm giao diện admin để monitoring dự án.

**Quyết định:**

1. Frontend: một app, tách theo route. `/` cho người dân, `/admin` cho monitoring.
   Không tạo app thứ hai, không tách repo.
2. Dữ liệu admin lấy từ hai nguồn, cả hai đều **không cần database mới**:
   - **Hướng A** — đọc file pipeline sinh ra: `procedure_manifest.csv`,
     `validation_report.csv`, `chunks.jsonl`.
   - **Hướng C** — đọc report benchmark từ `evaluation/evaluate_retrieval.py`.
3. **Không** làm log realtime (hướng B) ở giai đoạn này.

**Lý do chọn A + C:** cả hai chỉ đọc artifact đã tồn tại trên đĩa. Không thêm bảng,
không thêm middleware vào mọi request, không đụng vào luồng chat. Giữ được tinh thần
"không thêm gì nếu chưa chứng minh cần" của V3.

**Hệ quả cần làm tiếp:**

- Backend cần router admin mới. V3 §11 chưa có chỗ cho nó — phải bổ sung
  `backend/app/api/admin.py` + service tương ứng.
- **API admin dùng tiền tố `/api/admin`, không phải `/admin`.** Lý do: `/admin` là route
  giao diện phía frontend. Nếu API cũng ở `/admin`, proxy của Vite sẽ nuốt luôn trang
  admin và trả 502. Đã kiểm chứng thực tế lỗi này.
- Frontend `src/api/admin.ts` đang gọi 4 path chưa tồn tại:
  `/api/admin/overview`, `/api/admin/data-quality`, `/api/admin/retrieval`,
  `/api/admin/pipeline`.
- Cần cập nhật V3 §11 và §52 cho khớp.

**Rủi ro:** admin UI không có gì để hiển thị cho tới khi pipeline (PHASE 3-7) sinh ra
được manifest, validation report và chunks. Nên thứ tự hợp lý là làm admin **sau**
PHASE 7, không phải trước.

---

## D2 — Thêm `react-router-dom`

**V3 nói gì:** §59 — trước khi thêm package mới phải kiểm `pyproject.toml`/`uv.lock`,
xác định package thiếu, chỉ thêm cái thật cần. (Áp dụng cho Python; frontend chưa có
quy tắc tương ứng.)

**Quyết định:** thêm `react-router-dom` làm dependency frontend.

**Lý do:** hai giao diện cần phân biệt theo route, và admin cần 4 màn. Không dùng
router thì phải tự đọc `window.location.pathname` — được, nhưng sẽ phải viết lại khi
admin tăng số màn. Chọn router ngay từ đầu rẻ hơn.

---

## D3 — Bổ sung file ngoài skeleton V3 §11

| File | Lý do |
|---|---|
| `backend/__init__.py` | V3 §39 chạy `uvicorn backend.app.main:app`. Không có file này thì import theo đường dẫn đó thất bại. |
| `frontend/index.html` | Vite bắt buộc cần entry HTML. |
| `frontend/tsconfig.json` | TypeScript bắt buộc cần. |
| `frontend/src/vite-env.d.ts` | Khai báo `import.meta.env` cho TypeScript. |
| `frontend/src/types/` | Kiểu dữ liệu dùng chung; V3 chưa nói frontend để type ở đâu. |
| `frontend/src/styles/` | Token màu + light/dark; V3 không quy định chỗ đặt CSS. |
| `notebooks/process_tthc_colab.ipynb` | V3 §11 có `notebooks/` nhưng chưa tạo file. |
| `data_pipeline/ingest.py`, `scripts/prepare_data.py` | V3 §11 và §41 yêu cầu. |

---

## D4 — Việc chưa quyết

1. **Admin có cần đăng nhập không?** V3 §52 nói MVP không cần login. Nếu admin public
   trên internet thì cần ít nhất một lớp bảo vệ — basic auth ở Nginx, hoặc chặn theo IP.
   Chưa quyết.
2. **`httpx` đã bị bỏ khỏi dependency trực tiếp.** V3 §38 không liệt kê nó; hiện chỉ
   còn là transitive dep của `openai`. Nếu cần gọi HTTP trực tiếp thì `uv add httpx`.
3. **`PROJECT_GUIDE_TTHC_AI_CHATBOT_v2.md`** đã được xóa vì V3 thay thế.

---

## D5 — Quy ước vị trí file frontend do resolver của môi trường

**Trạng thái:** đang áp dụng, đã kiểm chứng

**Hiện tượng:** file nằm **trực tiếp** trong một thư mục con cấp 1 của `src/` không
import được đường dẫn tương đối lùi từ 2 cấp trở lên.

Bằng chứng từ `tsc --traceResolution`:

```text
Resolving '../../hooks/useTheme' from
  E:/.../frontend/src/components/ThemeToggle.tsx
→ candidate 'E:/.../frontend/hooks/useTheme'        ← thiếu 'src/'
```

Cùng thư mục đó, `../hooks/useTheme` resolve đúng. Cùng độ sâu 2 cấp ở nơi khác
(`src/pages/admin/` import `../../components/...`) cũng resolve đúng.

**Đã loại trừ:** không phải file hỏng (viết lại từ đầu vẫn lỗi), không phải compiler
(TS 7.0.2, 6.0.0-beta, 5.9.3 đều lỗi giống nhau), không phải `include` của tsconfig.

**Quy ước áp dụng:**

```text
src/<dir>/File.tsx        ❌ không đặt file trực tiếp
src/<dir>/<con>/File.tsx  ✅
```

Vì vậy `src/components/ui/` tồn tại. `src/api/`, `src/hooks/`, `src/types/`,
`src/styles/` giữ file trực tiếp được vì chúng chỉ import thư viện ngoài hoặc lùi
1 cấp.

**Nợ kỹ thuật:** quy ước này là hệ quả của môi trường, không phải thiết kế mong muốn.
Khi resolver được sửa, có thể dẹp `ui/` và đặt component trực tiếp dưới `components/`.

---

## D6 — Vite build cần quyền spawn tiến trình con

`npm run build` gọi `child_process.exec` để resolve realpath trên Windows
(`windowsSafeRealPathSync`). Trong sandbox giới hạn, lệnh này chết với `spawn EPERM`.
Đây là ranh giới của sandbox, không phải lỗi dự án — chạy ngoài sandbox thì bình thường.

`npm run typecheck` (`tsc --noEmit`) chạy được trong mọi trường hợp và là bước kiểm
tra chính.

