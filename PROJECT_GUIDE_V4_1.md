# HƯỚNG DẪN KIẾN TRÚC & TRIỂN KHAI DỰ ÁN TOÀN DIỆN (PROJECT GUIDE V4.1)
> **Cập nhật trạng thái: 2026-10-22.** Đọc §0.5 trước khi sửa mã.
## Đề tài: Ứng dụng RAG và Knowledge Graph để xây dựng Chatbot AI hỗ trợ tra cứu Thủ tục hành chính tại tỉnh Gia Lai

---

## 0. BỐI CẢNH, MỤC TIÊU, PHẠM VI & TRẠNG THÁI

Phần này mô tả **dự án cần làm gì** và **đang ở đâu**. Các mục 0.1–0.4 là bối cảnh; **0.5 là trạng thái hiện tại** và là phần phải đọc trước khi sửa mã.

### 0.1. Mục tiêu của đề tài

Xây dựng chatbot tiếng Việt tra cứu **thủ tục hành chính (TTHC) tỉnh Gia Lai**, kết hợp:

* **RAG** cho nội dung hướng dẫn (hồ sơ, trình tự, thời hạn, phí, kết quả, căn cứ pháp lý);
* **Knowledge Graph** cho quan hệ (cơ quan ban hành/thực hiện/phối hợp/ủy quyền, cấp, lĩnh vực, văn bản);
* **Workflow tất định** để quyết định tra gì, không để mô hình tự do chọn công cụ.

Mục tiêu chất lượng: trả lời **đúng nguồn, có `detail_url`**, và **không bịa** khi dữ liệu không có.

### 0.2. Phạm vi dữ liệu hiện tại

| Hạng mục | Hiện tại (2026-10-22) |
|---|---|
| Danh mục mục tiêu | 1.955 TTHC áp dụng tại Gia Lai (168 lĩnh vực nguồn, 15 nhóm) |
| Bộ đang nạp và đo | **49 TTHC** (dùng để phát triển, đo và làm luận văn) |
| Nguồn | API công khai Cổng Dịch vụ công Quốc gia (JSON), **không dùng PDF/OCR** |
| Lưu trữ | PostgreSQL (SSOT) · Neo4j (đồ thị) · Elasticsearch (BM25) · Qdrant (vector) |

> Mở rộng lên 1.955 TTHC là việc dữ liệu, không phải viết lại kiến trúc. Mọi ngưỡng phải đo trên
> bộ đang có và ghi rõ quy mô khi báo cáo.

### 0.3. Nguyên tắc thiết kế

1. **Tất định ở phần quyết định.** LLM chỉ làm hai việc: hiểu câu hỏi thành `QuestionFrame`, và
   viết câu trả lời từ bằng chứng. Router/planner/executor là mã nguồn.
2. **Bằng chứng trước câu chữ.** Không có evidence thì không trả lời; mỗi khẳng định phải truy
   ngược được về một mục ngữ cảnh và `detail_url`.
3. **Ba trạng thái thiếu phải khác nhau:** `không có dữ liệu` ≠ `nguồn đang lỗi` ≠ `chưa hỗ trợ`.
4. **Ưu tiên không trả lời hơn trả lời sai.** Hỏi lại chỉ khi có lựa chọn thật; từ chối phải nói
   rõ thiếu gì.
5. **Không hardcode cụm từ để định tuyến/phân loại.** Ngưỡng và từ phân biệt phải suy ra từ dữ
   liệu (score, IDF, df) hoặc từ schema.
6. **Không dựng lại A0** (identity/profile/case) — đã đo là tệ hơn và đã gỡ.

### 0.4. Chính sách độ tin cậy dữ liệu

Phí/lệ phí được phân thành **5 loại** và trả lời khác nhau; sentinel `"Không có thông tin"` nghĩa
là **chưa đăng**, không phải **không có**. Chi tiết và bảng nhận biết ở **§1.2b**; đây là chính
sách bắt buộc cho bước sinh câu trả lời.

### 0.5. TRẠNG THÁI HIỆN TẠI — cập nhật 2026-10-22 (đọc trước khi sửa bất kỳ file nào)

Đây là phần **bắt buộc đọc đầu tiên** đối với Coding Agent. Nó thay thế các mô tả cũ ở Giai đoạn 13/14 khi hai mục đó khác với mã hiện có.

#### 0.5.1. Hệ thống đang chạy theo kiến trúc nào

Luồng hiện tại (mặc định, đã nối vào `/chat`, `/chat/stream` và `/api/admin/workflow/ask`):

```text
normalize
  → ① mã thủ tục bằng regex + PostgreSQL
  → ② từ điển văn bản pháp lý (RAM)
  → ③ thực thể đóng (cơ quan / lĩnh vực / cấp / nhóm)
  → ④ cổng nội dung (hybrid + reranker)
  → ⑤ Graph phân loại
  → ⑥ nhúng lười (tối đa một lần mỗi câu)
  → ⑦ resolver tên thủ tục
  → ⑧ router (adapter từ QuestionFrame)
  → ⑨ grounding từng subject mention
  → ⑩ planner tất định (capability matrix)
  → ⑪ executor: chạy task song song + coverage từng ý + fallback tối đa 1 lần
  → ⑫ answer contract + kiểm chứng hậu sinh + retry 1 lần + fallback tất định
  → ⑬ tổng hợp câu trả lời
```

**Điểm khác biệt cốt lõi so với V4.1 gốc:** không còn "router đoán một nhánh rồi nhánh đó tự quyết định". Hiểu câu hỏi được tách thành ba tầng tất định:

1. **QuestionFrame** — LLM semantic parser trả JSON có schema, không trả nhãn nhánh.
2. **Grounding + Planner** — mã nguồn quyết định subject nào đã xác định, ý nào hỗ trợ được, dùng tool nào.
3. **Executor** — chạy đúng plan, gắn bằng chứng theo từng ý, tính coverage, không để lỗi một nguồn làm mất nguồn khác.

#### 0.5.2. File nào là "mã mới" của Giai đoạn 13

| File | Vai trò |
|---|---|
| `backend/app/workflow/question_frame.py` | Schema `QuestionFrame` v1.0: `QuestionScope`, `SubjectType`, `RequestOperation`, `Facet` (20 giá trị), `ConstraintType`, `AmbiguityKind`; `SubjectMention`, `QuestionRequest`, `QuestionFrame`. |
| `backend/app/workflow/question_parser.py` | Gọi LLM sinh frame + validate JSON + cache + `to_router_decision()` (adapter frame → 3 nhánh cũ). |
| `backend/app/rag/grounding.py` | `ground_frame()`: mã đã xác thực → mã không tồn tại → đại từ → resolver (tên chính xác/vector) → từ điển văn bản → thực thể đóng. Trạng thái `resolved/ambiguous/not_found/context_required`. |
| `backend/app/workflow/planner.py` | `plan_retrieval()`: capability matrix đóng (facet × operation × subject) → `Task(tool, intent, expected_types, constraints, procedure_codes)`. Không hỗ trợ thì ghi `unsupported`, không đoán. |
| `backend/app/workflow/executor.py` | `execute_plan()`: chạy task song song, timeout từng tool, coverage từng request, fallback tối đa một lần, single-flight embedding, lỗi hạ tầng → `failed` (không phải `empty`). |
| `backend/app/workflow/answer.py` | Answer contract: khối "CÁC Ý CẦN TRẢ LỜI", context nhóm theo ý, chọn evidence công bằng theo request, `verify_contract()`, `build_fallback_answer()`. |
| `backend/app/workflow/graph.py` | Thêm node `THUC_THI`; plan có task **hoặc** unsupported đều đi qua executor; bỏ `BO_SUNG_MUC` khi executor đã phủ. |
| `backend/app/workflow/run.py` | `RunResult.to_dict()` xuất `question_frame`, `groundings`, `plan`, `coverage`, `verification`, `grounding_ms`. |

Các file cũ vẫn tồn tại và **vẫn dùng** cho đường legacy khi parser tắt/lỗi: `nodes.py`, `router_rules.py`, `resolve.py`, `hybrid.py`, `graph_query.py`, `sections.py`, `fact_lookup.py`.

#### 0.5.3. Trạng thái dữ liệu và hạ tầng (đo ngày 2026-10-22)

```text
PostgreSQL  chatbot_tthc: procedures (49), procedure_sections, procedure_agencies
Neo4j       đồ thị tri thức của 49 thủ tục
Qdrant      chỉ còn collection semantic_search: 541 point, 1024 chiều
Elasticsearch  chỉ mục từ khoá của procedure_sections
Model       router/parser qwen3.7-flash · synthesizer deepseek-flash
            embedding qwen3.7-text-embedding · reranker qwen3-rerank
```

**Đã gỡ hoàn toàn A0** (identity/profile/case). Không được dựng lại:
- ba bảng `procedure_identity`, `procedure_profile`, `procedure_case` đã drop;
- code `identity.py`, `cases.py`, `resolver` dùng identity, `data/case_overrides.csv`, script `build_procedure_*` đã xoá;
- lý do: đo được **tệ hơn** baseline (subject 24/51 so với 32/51; false clarify 27 so với 12).

#### 0.5.4. Số đo hiện tại

**Bộ 60 câu — baseline 2026-10-21 (trước kiến trúc mới):**

```text
32/51 đúng thủ tục (63%) · 21/31 đúng con số · 43/60 đúng kết cục
12 hỏi lại oan · 2 từ chối oan · 1 câu trả lời rác
```

**Nhóm A (10 câu người dùng, thủ tục 1.115362) — đo lại 2026-10-22 sau Giai đoạn 3 + 4:**

```text
8/10 đúng (A1–A4, A6, A8–A10); A5 và A7 chỉ đúng một phần
A1  đúng: 1.115362, 17,5 ngày          (gỡ rối bằng điều kiện thời hạn)
A2  đúng: 1.115362, 14 ngày            (sửa lỗi chọn 1.115351 "Xóa đăng ký thuê")
A3  đúng: 1.115362, 15 ngày            (benchmark chấp nhận 15 hoặc 25)
A4  đúng: 1.115362, 18 ngày
A5  trả lời được 3 hình thức nộp; dữ liệu không có "Bộ phận Một cửa" nên chưa khớp kỳ vọng
A6  đúng: Trực tiếp / Trực tuyến / Bưu chính
A7  trả lời một phần: nói rõ chưa ghi nhận điều kiện (benchmark muốn từ chối)
A8  đúng: Mẫu số 18
A9  đúng: văn bản thỏa thuận cấp chung + Mẫu 18
A10 đúng: danh sách giấy chứng nhận
```

Nguyên nhân cũ và cách đã sửa:

1. Resolver chỉ trả 3 lựa chọn và lấy vector top-1 → **đã sửa**: top-10 ứng viên + gỡ rối bằng điều kiện thời hạn.
2. Câu chung khớp nhiều biến thể → **đã sửa**: nhóm thủ tục + đồng thuận/đại diện.
3. Parser gán sai loại mention → **đã sửa**: fallback `document → procedure`.
4. Câu điều kiện pháp lý (A7) → còn một phần: trả lời "chưa ghi nhận" thay vì từ chối dứt khoát.

#### 0.5.5. Việc tiếp theo, theo thứ tự ưu tiên

```text
P1  Resolver: rerank đối chiếu bằng IDF (dữ liệu sinh ra từ kho tên thủ tục,
    KHÔNG dùng danh sách từ khoá cứng) → sửa A1, A2.
P1  Grounding: fallback loại mention document ↔ procedure → sửa A8.
P1  Luật theo operation: check + requirements + subject chưa xác định → abstain
    (không clarify) → sửa A7.
P2  Đồng thuận giữa các biến thể: nếu top-2/3 cùng giá trị cho facet được hỏi
    thì trả lời một lần kèm ghi chú; khác nhau thì clarify → A5, A6, A9, A10.
P2  (chỉ khi P2 trên thất bại) nhóm canonical suy ra từ dữ liệu, không viết tay.
P3  Đo lại toàn bộ 60 câu; cập nhật bảng kết quả trong docs/benchmark_60_cau.md.
P3  Giai đoạn 6.3 (rollout mặc định): người dùng đã chọn áp dụng mặc định,
    nên bỏ điều kiện chuyển đổi; vẫn phải đo trước khi tuyên bố cải thiện.
P3  Alias section_type trong SQL (dữ liệu hiện sạch, chưa có ca thật).
P3  Hybrid fail-open khi reranker lỗi: chỉ thêm metric, chưa đổi chính sách.
```

#### 0.5.6. Ràng buộc không được vi phạm

```text
1. KHÔNG dựng lại A0 (identity/profile/case) dưới bất kỳ tên khác.
2. KHÔNG hardcode danh sách cụm từ/từ khoá để định tuyến hay phân loại.
   Mọi ngưỡng/từ phân biệt phải suy ra từ dữ liệu (IDF, df, score) hoặc từ schema.
3. Tên hàm/biến mới dùng tiếng Anh; không dùng tiếng Việt có dấu trong định danh.
4. Mỗi câu trả lời phải kèm `detail_url`; không đánh số nguồn `[n]` trong câu chữ.
5. Không trả lời khi bằng chứng rỗng. "Không có dữ liệu" khác "nguồn đang lỗi"
   khác "chưa hỗ trợ" — ba trạng thái phải hiện khác nhau.
6. Hậu kiểm phải CHẶN câu vi phạm hợp đồng, không chỉ ghi log. Đường stream
   không thể rút chữ đã gửi — đây là giới hạn đã biết, không được che.
7. Sau mọi thay đổi: `uv run ruff check backend scripts` và `uv run pytest -q`.
```

#### 0.5.7. Lệnh chạy và kiểm

```powershell
uv run uvicorn backend.app.main:app --reload   # backend + /docs
uv run pytest -q                               # 702 test (2026-10-22)
uv run ruff check backend scripts
cd frontend; npm run dev                       # giao diện người dân + quản trị
```

API liên quan:

```text
POST /chat                    → một lần, dùng cho đo/so sánh
POST /chat/stream             → SSE, giao diện người dân
POST /api/admin/workflow/ask  → chạy cả luồng, trả trace đầy đủ
POST /api/admin/retrieval/test→ chạy một engine (playground, cố ý tách khỏi luồng)
```

#### 0.5.8. Bảng trạng thái 16 giai đoạn

| GĐ | Nội dung | Trạng thái |
|---|---|---|
| 1 | Khởi tạo dự án, môi trường, config | ✅ xong |
| 2 | Taxonomy 15 nhóm / 49 lĩnh vực, hợp đồng dữ liệu | ✅ xong |
| 3 | Crawl API cổng DVC | ✅ xong |
| 4 | Chuẩn hoá & kiểm định dữ liệu | ✅ xong |
| 5 | Chunking theo section | ✅ xong |
| 6 | PostgreSQL (SSOT) | ✅ xong |
| 7 | Neo4j Knowledge Graph | ✅ xong |
| 8 | Elasticsearch BM25 | ✅ xong |
| 9 | Qdrant vector | ✅ xong |
| 10 | Cache TTL (thay semantic FAQ cache) | 🚧 có TTL, không có FAQ cache |
| 11 | Hybrid + RRF + reranker | ✅ xong |
| 12 | Graph Query Engine | ✅ xong |
| 13 | Hiểu câu hỏi + planner + executor | 🚧 xong kiến trúc, chất lượng chưa đạt |
| 14 | Answer contract + kiểm chứng | 🚧 xong phần lớn |
| 15 | Đóng gói API + Docker Compose | 🚧 API có; compose mới có ES/Qdrant |
| 16 | Đánh giá RAG chuyên sâu + bảo vệ | ⏳ chưa làm |

#### 0.5.9. Hợp đồng hai lớp: `discovery` và `verified_evidence`

Từ 2026-10-22, kết quả truy xuất được chia làm hai lớp **không thể lẫn**:

```text
discovery          ứng viên + điểm + lý do tìm thấy — là GIẢ THUYẾT, không dùng để trả lời
verified_evidence  chỉ sinh sau khi ứng viên đã neo vào mã thủ tục/thực thể thật,
                   rồi truy xuất bằng section theo mã, Graph theo neo, hoặc fact theo mã
```

- Code: `backend/app/rag/contracts.py`; mỗi mục bằng chứng có `result_kind`, `verified`,
  `verification` (lý do).
- Ứng viên từ grounding/resolver nằm ở trace `discovery`, **không** nằm trong `evidence`;
  `answer.build_context` có hàng rào bỏ qua mục `kind="candidate"`.
- Đoạn văn hybrid **chưa neo** vào mã đã xác thực được đánh dấu `verified=False`
  (`chunk_search_without_anchor`); chỉ khi task có mã đã xác thực mới được nâng lên
  `hybrid_with_verified_code`.
- Nguyên tắc lấy từ *Deterministic Legal Agents* (SAT-Graph API): tìm kiếm chỉ là **hạt
  giống** để đi định vị, không phải chân lý cuối cùng.

#### 0.5.10. Trường `scenario` — tình huống của từng ý hỏi

Mỗi `requests[*]` có thêm `scenario`: **nguyên văn cụm mô tả tình huống** người dùng nêu
(ví dụ "cho thuê lại trong dự án", "bán tài sản gắn liền với đất thuê trả tiền hàng năm").
Rỗng nếu câu không nêu tình huống.

- Chỉ **ghi lại**, không gán mã thủ tục, không sinh `case_key`, không đưa vào `constraints`.
- Tối đa 500 ký tự, cắt ở ranh giới từ; trường tuỳ chọn nên mô hình quên không làm hỏng frame.
- Giai đoạn 4 sẽ dùng trường này để xếp hạng ứng viên, lọc bằng chứng và buộc hỏi lại khi
  cùng thủ tục có nhiều thời hạn theo tình huống. Hiện tại **chưa dùng để quyết định**.

#### 0.5.11. Nhãn nguồn lực `plan_class` (Giai đoạn 2)

Sau khi hiểu câu hỏi và định vị chủ thể, mã nguồn tự gán **một trong 6 nhãn** (không gọi mô
hình), để biết lượt này cần loại nguồn lực nào:

| Nhãn | Nghĩa |
|---|---|
| `direct` | 1 ý, đã xác định thủ tục/thực thể → tra tối thiểu |
| `composed` | ≥ 2 ý, tất cả xử lý được → chạy song song |
| `discovery` | chưa có chủ thể, phải tìm thủ tục trước → mới dùng hybrid |
| `clarify` | chủ thể mơ hồ / cần tiền ngữ → hỏi lại kèm lựa chọn |
| `unsupported` | operation/facet chưa có công cụ, hoặc câu điều kiện pháp lý mà dữ liệu TTHC không trả lời được |
| `out_of_scope` | ngoài TTHC / smalltalk → không truy xuất |

- Thứ tự ưu tiên khi gán nhãn lượt: `out_of_scope > unsupported > clarify > composed > discovery > direct`.
- Mỗi lượt cũng ghi **nhãn riêng cho từng ý** (`request_plan_class`) để không mất chi tiết.
- Trace: `plan_class`, `plan_class_reason`, `request_plan_class`.
- Đây **không** phải nhãn nhánh cũ của router LLM; nhãn này chỉ mô tả nguồn lực, không thay
  quyết định truy xuất. Hiện chưa dùng để đổi hành vi.

#### 0.5.12. Nhóm thủ tục `procedure_themes` (Giai đoạn 3)

Câu chung như "đăng ký biến động đất đai" khớp nhiều thủ tục là biến thể của nhau. Bảng
`procedure_themes` (sinh từ tên, 4 từ đầu) + `procedures.theme_id` gom chúng lại:

```text
dang_ky_bien_dong   6 thủ tục   đại diện 1.115362
dang_ky_cap_giay    6
cap_giay_phep_xay   2
dang_ky_dat_dai     2
dieu_chinh_quyet_dinh 2
giao_dat_cho_thue   2
```

Khi resolver trả về nhiều ứng viên:

1. mọi thành viên **cùng nội dung** cho khía cạnh được hỏi → trả lời một lần;
2. khác nội dung + nhóm có `canonical_code` → trả lời theo đại diện, ghi rõ theo nhóm;
3. nhóm chiếm đa số (≥ một nửa ứng viên) → dùng nhóm đó;
4. còn lại → hỏi lại như cũ.

Code: `backend/app/rag/themes.py`, `backend/app/rag/theme_agreement.py`; script
`scripts/build_procedure_themes.py --dry-run/--apply`. Kết quả CSV:
`data/processed/procedure_themes.csv`.

#### 0.5.13. Gỡ rối bằng điều kiện thời hạn (Giai đoạn 4)

Resolver trả **top-10 ứng viên** (`ProcedureResolution.candidates`). Với câu hỏi **thời hạn**,
hệ thống so **tình huống** (`scenario`, hoặc mention nếu scenario rỗng) với
`procedure_time_cases.dieu_kien` — bảng sinh từ `thoi_han.muc_chi_tiet` của JSON (78 mốc / 49
thủ tục).

```text
điểm = vector + 0,25 × độ_phủ_IDF(tình huống, điều kiện)
ghi đè nếu: chênh ≥ 0,03 · độ phủ mới ≥ 0,5 · độ phủ cũ thấp hơn ≥ 0,2
```

Kết quả thật: A1 → 1.115362 (17,5 ngày); A2 → 1.115362 (14 ngày, sửa lỗi chọn 1.115351);
A3 → 15 ngày; A4 → 18 ngày. Fallback `document → procedure` sửa A8. Code:
`backend/app/rag/disambiguation.py`, `time_cases.py`, `grounding.py`; script
`scripts/build_time_cases.py`.

#### 0.5.14. Trace log `logs/workflow_trace.jsonl` (v2)

Mỗi lượt ghi **một dòng JSON** (kể cả lượt stream, ghi sau khi stream xong), gồm:
`question_frame`, `groundings` (kèm `candidates`), `discovery`, `plan_class`,
`request_plan_class`, `plan`, `coverage`, `evidence` (kèm `verified`), `verification`, `answer`,
`thieu`, `timings`, `tokens`, `source` (`chat`/`chat_stream`/`admin`/`api`), `phase`
(`final`/`error`/`cache`); lỗi có thêm `error_detail` (traceback, tối đa 4.000 ký tự).

Ghi log không bao giờ làm hỏng lượt trả lời; lỗi ghi file bị nuốt. Muốn đổi đường dẫn:
biến môi trường `WORKFLOW_TRACE_JSONL_PATH`.

> **Quy ước đọc tài liệu:** các mục Giai đoạn 1–12 và 15–16 vẫn đúng như mô tả. Riêng **Giai đoạn 13 và 14** đã được hiện thực khác cấu trúc file ghi trong kế hoạch gốc — luôn đối chiếu §0.5 trước.

---

## MỤC LỤC TỔNG QUAN
0. **Bối cảnh, Mục tiêu, Phạm vi & Trạng thái hiện tại**
   * **0.5. TRẠNG THÁI HIỆN TẠI (2026-10-22)** — kiến trúc, file, số đo, việc tiếp theo, ràng buộc, bảng trạng thái 16 giai đoạn
1. **Tuyên ngôn Kiến trúc, Phạm vi Dữ liệu & Nguyên tắc Ràng buộc**
2. **Chuẩn hóa Phân loại Nghiệp vụ (15 Domain Groups & 49 Canonical Fields)**
3. **Cấu trúc Không gian Lưu trữ & Thư mục Đồng bộ (Google Drive & Repository Skeleton)**
4. **Quy chuẩn Hợp đồng Dữ liệu (Data Contract, PostgreSQL DDL & Neo4j Graph Schema)**
5. **Kiến trúc Hệ thống Hiện tại** (luồng hiểu câu hỏi → executor → answer contract; mô hình hai tầng chân lý)
6. **Lộ trình Triển khai Chi tiết 16 Giai đoạn (Phase 1 – Phase 16)**
7. **Khung Biện luận & Trả lời Phản biện trước Hội đồng Chấm thi**
   * **Phụ lục A:** Ánh xạ 168 lĩnh vực nguồn về 15 nhóm lĩnh vực

> **Trạng thái tài liệu:** V4.1 là **SOURCE OF TRUTH DUY NHẤT** về kiến trúc, cấu trúc repository, luồng dữ liệu, schema CSDL, dependency và thứ tự triển khai. Coding Agent phải đọc kỹ trước khi tạo, sửa hoặc refactor bất kỳ file mã nguồn nào. Nếu skeleton hoặc chiến lược dữ liệu thay đổi, phải cập nhật tài liệu này **đồng thời** với code.


---

## 1. TUYÊN NGÔN KIẾN TRÚC, PHẠM VI DỮ LIỆU & NGUYÊN TẮC RÀNG BUỘC

### 1.1. Phạm vi Dữ liệu Nghiệp vụ (Data Scope Definition)
* **Khái niệm chuẩn xác về tập dữ liệu:** Hệ thống sử dụng **Bộ dữ liệu Thủ tục hành chính (TTHC) công bố trên Cổng Dịch vụ công Quốc gia, áp dụng thực thi theo thẩm quyền phân cấp trên địa bàn tỉnh Gia Lai**.
* **Nguồn dữ liệu:** Hai API công khai của Cổng Dịch vụ công Quốc gia (`dichvucong.gov.vn`), **không cần đăng nhập**:
  * `POST /api/v1/submitting/formality/list-all-public-formality-by-citizen` — tra mã thủ tục, trả về UUID và cơ quan ban hành.
  * `POST /api/v1/configuring/formality/get-formality-by-citizen` — lấy toàn bộ nội dung chi tiết theo UUID.
* **Nguyên tắc xác định phạm vi:** Danh mục **1.955 mã TTHC** trong file `danh_sach_tthc_bo_tinh_xa_edit.xlsx` là **nguồn quyết định cần crawl những gì**. API chỉ là công cụ lấy nội dung. Khi một mã trả về nhiều bản, chọn bản `ACTIVE` có `updatedAt` mới nhất.
* **Quy mô tập dữ liệu thực tế:** Gồm **1.955 TTHC**, bao phủ **168 lĩnh vực nguồn**, trong đó **47 TTHC do UBND tỉnh Gia Lai ban hành** (bổ sung ở giai đoạn sau, thuộc hai nhóm Tài nguyên–Môi trường và Xây dựng–Giao thông). Danh mục gốc có 19 cơ quan ban hành cấp Trung ương (Bộ Nông nghiệp và Môi trường: 357, Bộ Công Thương: 247, Bộ Khoa học và Công nghệ: 247, Bộ Tư pháp: 198, Bộ Xây dựng: 193, Bộ Văn hóa, Thể thao và Du lịch: 165...). Về cấp thực hiện, dữ liệu ghi nhận 13 giá trị phân cấp và nhiều thủ tục thực hiện đồng thời ở nhiều cấp: **1.462 TTHC đúng cấp tỉnh**, **257 TTHC đúng cấp xã**, **370 TTHC có thực hiện ở cấp xã** (kể cả thủ tục đa cấp). Dữ liệu **không có cấp huyện** — phù hợp với mô hình hành chính hiện hành chỉ còn cấp tỉnh và cấp xã.

> **Trạng thái 2026-10-22:** danh mục mục tiêu là 1.955 TTHC, nhưng bộ **đang nạp và đo** là **49 TTHC** (xem §0.5.3). Mọi số liệu trong tài liệu phải ghi rõ quy mô đo; không trộn số của 1.955 với số của 49.
* **Chuẩn hóa nghiệp vụ:** 168 lĩnh vực nguồn được quy hoạch gọn gàng về **49 Lĩnh vực chuẩn hóa (Canonical Fields)** thuộc **15 Nhóm Lĩnh vực lớn (Domain Groups)**.

### 1.2. Tuyên ngôn Về Độ chính xác & Triệt tiêu Ảo giác (Hallucination Policy)
Hệ thống thiết lập nguyên tắc kiểm soát ảo giác theo **Mô hình Hai Tầng Chân lý (Two-Tier Truth Model)**:
1. **Tầng Chân lý Tuyệt đối (Deterministic Metadata Truth - 100%):** Đối với các thuộc tính định danh (Mã TTHC, Tên TTHC, Cấp thực hiện, Cơ quan ban hành, Số/Ngày Quyết định), hệ thống **triệt tiêu hoàn toàn ảo giác (Zero Hallucination - 100%)** bằng cơ chế truy vấn trực diện cơ sở dữ liệu quan hệ (PostgreSQL Fact Lookup), không qua tầng sinh của LLM.
2. **Tầng Chân lý Trích xuất (Extracted Content Truth - Mục tiêu Faithfulness ≥ 0.98):** Đối với nội dung hướng dẫn chi tiết khai thác từ API cổng DVC (Thành phần hồ sơ, Thời hạn giải quyết, Phí/Lệ phí, Trình tự thực hiện), hệ thống sử dụng Retrieval-Augmented Generation (RAG) với cơ chế **Trích dẫn bắt buộc (Strict Provenance)**: Mọi câu trả lời sinh ra bởi LLM đều phải kèm trích dẫn số quyết định công bố, mã thủ tục và đường dẫn nguồn (`detail_url`); mục tiêu định lượng đo lường bằng Ragas là **Độ trung thực (Faithfulness) ≥ 0.98** và **Độ liên quan (Answer Relevance) ≥ 0.95**.

### 1.2b. Chính sách Trả lời theo Độ tin cậy Dữ liệu (Data Reliability Policy)
Vì chất lượng dữ liệu khác nhau giữa các trường, hệ thống phân loại độ tin cậy và có chính sách trả lời riêng. Đây là điểm khác biệt giữa hệ thống **trung thực** và hệ thống **giả vờ biết**:

> **Phân loại này được gán ngay ở Giai đoạn 3 (crawl), lưu vào trường `phi` có cấu trúc** (mục 4.1b). Trường `phi.loai` nhận đúng 5 giá trị dưới đây, và `phi.mo_ta_goc` giữ nguyên văn nguồn để luôn đối chiếu ngược được. Các tầng sau (chunking, generation) **đọc** nhãn này, không phân loại lại — tránh hai nơi cùng quyết định một việc.

**Về PHÍ/LỆ PHÍ — 5 loại, trả lời khác nhau:**

| `phi.loai` | Cách trả lời | Dấu hiệu nhận biết trong API |
|---|---|---|
| `SO_TIEN` | "Lệ phí: 160.000 đồng" | `value > 0` |
| `MIEN_PHI` | "Thủ tục này miễn phí" | `fees` **có** mục, `value = 0`, mô tả rỗng |
| `THEO_VAN_BAN` | "Theo Thông tư X" + link tra cứu | `value = 0` + mô tả có số hiệu văn bản |
| `THEO_QUY_DINH_CHUNG` | "Theo quy định hiện hành" — nếu mọi mục đều không có số tiền thì nêu **cả** nhãn cổng hiển thị (xem ghi chú dưới bảng) | `value = 0` + mô tả có chữ (viện dẫn chung) |
| `CHUA_XAC_DINH` | "Chưa có thông tin lệ phí" (từ chối) | `fees` **rỗng hoàn toàn** ở mọi cách thức |

**Hai chỗ tuyệt đối không được suy diễn — đã kiểm chứng trực tiếp trên cổng:**

1. **`fees: []` KHÔNG phải miễn phí.** Cổng không đăng ký mục phí nào thì không có cơ sở kết luận, và cổng cũng hiển thị *"không có thông tin"*. Kiểm chứng: thủ tục `3.000242`.
2. **`value = 0` kèm mô tả KHÔNG phải miễn phí.** Phải đọc mô tả; có thể là *"Thực hiện theo quy định tại Thông tư số 10/2024/TT-BTC"*.

**Trường phân biệt "miễn phí" với "không có thông tin" là SỐ PHẦN TỬ của `fees`**, không phải giá trị `value`. Kiểm chứng: thủ tục `1.013314` có `fees: [{value: 0, description: ""}]` → cổng ghi *"miễn phí"*; thủ tục `3.000242` có `fees: []` → cổng ghi *"không có thông tin"*.

**Cảnh báo thứ ba — cổng có thể tự ghi "Miễn phí" dù API không có chữ đó.**

Cổng DVC hiển thị nhãn *"Miễn phí"* dựa trên logic giao diện của chính nó khi mọi mục phí có `value = 0`. Chữ "miễn phí" **không hề có trong response API** — kiểm chứng trên `2.000115`: tìm `"miễn phí"`, `"miễn"`, `"free"`, `feeType` trong toàn bộ response đều **0 lần**; API chỉ trả `value = 0` kèm mô tả *"Theo quy định của Bộ tài chính"*.

Nghĩa là **cổng hiển thị "Miễn phí" nhưng ta phân loại `THEO_QUY_DINH_CHUNG`** — hai câu khác nhau cho cùng một thủ tục. Đây là **giới hạn của dữ liệu API**, không phải lỗi phân loại: không có trường nào trong API nói cổng sẽ gắn nhãn gì.

**Chính sách đã chốt — không sửa dữ liệu, ràng buộc cách diễn đạt.** Giữ nguyên `THEO_QUY_DINH_CHUNG` và để Giai đoạn 14 xử lý khi trả lời:

```text
Nếu phi.loai = THEO_QUY_DINH_CHUNG và MỌI mục trong muc_chi_tiet đều so_tien = null:
  → trả lời nêu cả hai nguồn thông tin:
    "Cổng DVC ghi thủ tục này miễn phí; đồng thời hồ sơ có ghi 'theo quy định
     của Bộ Tài chính'. Bạn xem chi tiết tại <detail_url>."
```

Nhờ vậy **không mâu thuẫn với những gì người dân thấy trên cổng**, mà vẫn trung thực với dữ liệu API (không tự bịa ra chữ "miễn phí"). Chunk `FEE` đã chứa mô tả *"Theo quy định của Bộ tài chính"* để LLM dẫn lại được.

**Về THỜI HẠN GIẢI QUYẾT — 3 loại:**

| Nhãn | Ý nghĩa | Cách dùng |
|---|---|---|
| `SO` | Lấy được từ trường số | Trả lời trực tiếp |
| `TRONG_TEXT` | Trường số rỗng, phải trích từ mô tả | Trả lời kèm trích nguyên văn |
| `CHUA_XAC_DINH` | Không xác định được | Từ chối trả lời |

**Cảnh báo quan trọng:** nếu thủ tục có **nhiều mốc với đơn vị khác nhau** (ví dụ vừa "15 Ngày" vừa "1 Giờ"), **không được trả lời bằng một con số duy nhất** — phải liệt kê đầy đủ các mốc. Không cộng dồn các mốc, vì dữ liệu thật cho thấy cùng một thời hạn của cả thủ tục bị ghi lặp ở nhiều bước.


### 1.3. Nguyên tắc Lưu trữ Đa hệ (Polyglot Persistence) & SSOT
* **PostgreSQL là Nguồn chân lý duy nhất (Single Source of Truth - SSOT):** Mọi thực thể có cấu trúc, quan hệ phân cấp, metadata và các phân đoạn văn bản khai thác từ API cổng DVC đều được lưu trữ tập trung tại PostgreSQL.
* **Các CSDL còn lại là các phép chiếu chỉ mục (Projections / Auxiliary Search Indexes):**
  * **Elasticsearch:** Chỉ mục tra cứu từ khóa chính xác BM25 (Số quyết định, Mã TTHC, tên viết tắt, cụm từ chuyên ngành).
  * **Qdrant:** Chỉ mục vector phục vụ tìm kiếm ngữ nghĩa (`semantic_search`).
  * **Neo4j:** Đồ thị tri thức biểu diễn liên kết đa chiều giữa Thủ tục - Cơ quan thụ lý - Cơ quan thẩm quyền - Cơ quan phối hợp - Cấp thực hiện.

### 1.4. Ràng buộc Hạ tầng Vận hành
* Toàn bộ hệ thống được tối ưu hóa để vận hành bền bỉ trên môi trường đồ án sinh viên: **VPS Ubuntu (16 – 32GB RAM, 4 – 8 vCPU, 50 – 100GB SSD)**.
* Toàn bộ dịch vụ hạ tầng (PostgreSQL, Elasticsearch, Qdrant, Neo4j, backend API, frontend) được container hóa và điều phối bằng một tệp `compose.yaml` duy nhất với hạn mức RAM (Memory Limits) chặt chẽ cho từng container.
* **Không dùng Redis, Kafka, RabbitMQ, Celery hay Kubernetes** ở giai đoạn này. Dự án ưu tiên tính ổn định và dễ giải thích trước Hội đồng hơn là thêm hạ tầng chưa có use-case chứng minh.

---

## 2. CHUẨN HÓA PHÂN LOẠI NGHIỆP VỤ (15 DOMAIN GROUPS & 49 CANONICAL FIELDS)

Toàn bộ 168 lĩnh vực nguồn được quy nạp thành 15 Domain Groups. Mảng Cư trú/Xuất nhập cảnh (ngành dọc Công an) được tách biệt hoàn toàn khỏi mảng Quốc phòng/Ngoại vụ để tối ưu hóa không gian vector và phản ánh đúng thẩm quyền hành chính địa phương.

Cột **Số Lĩnh Vực Nguồn** dưới đây là kết quả phân nhóm trực tiếp từ dữ liệu gốc và **cộng đúng 168**; danh sách đầy đủ 168 dòng nằm ở **Phụ lục A** và tệp `config/field_mapping.csv` (49 Canonical Fields):

| STT | Mã Thư mục (`Domain_Group`) | Tên Nhóm Lĩnh Vực Lớn | Số Lĩnh Vực Nguồn | Cơ quan Quản lý / Thụ lý chính | Lĩnh vực Nguồn Tiêu biểu |
|:---:|---|---|:---:|---|---|
| 1 | `01. AN_NINH_TRAT_TU_CU_TRU` | An ninh trật tự, Cư trú & Xuất nhập cảnh | 2 | Công an tỉnh Gia Lai, Công an Xã/Phường | Đăng ký quản lý cư trú (thường trú, tạm trú, nơi ở); Quản lý xuất nhập cảnh (Thẻ ABTC, hộ chiếu)... |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Công nghiệp, Năng lượng, Thương mại & Thị trường | 25 | Sở Công Thương | Xuất nhập khẩu, Thương mại điện tử, Điện lực, Năng lượng tái tạo, Dầu khí, Khí đốt, Hóa chất, Vật liệu nổ, An toàn thực phẩm... |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Đăng ký Doanh nghiệp, Hợp tác xã & Đầu tư | 12 | Sở KH&ĐT, Ban QL Khu kinh tế | Đăng ký DN, Hộ kinh doanh, Hợp tác xã, Đầu tư trong/ngoài nước, ODA, KCN, KKT... |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục, Đào tạo & Giáo dục nghề nghiệp | 11 | Sở Giáo dục & Đào tạo | Mầm non, Tiểu học, Trung học, GDTX, Giáo dục nghề nghiệp, Tuyển sinh, Văn bằng chứng chỉ... |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Lao động, Việc làm, Người có công & An sinh | 14 | Sở Lao động - TB&XH | Việc làm, Tiền lương, Người có công, Bảo trợ xã hội, An toàn vệ sinh lao động, Trẻ em, BHXH... |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Cán bộ công chức, Tôn giáo, Dân tộc & Thi đua | 8 | Sở Nội vụ, Ban Dân tộc | Cán bộ công chức, Tổ chức hội quỹ, Thi đua khen thưởng, Văn thư lưu trữ, Tín ngưỡng tôn giáo, Công tác dân tộc... |
| 7 | `07. NONG_LAM_THUY_SAN` | Nông nghiệp, Lâm nghiệp, Thủy sản & PTNT | 11 | Sở Nông nghiệp và Môi trường | Trồng trọt, BVTV, Chăn nuôi, Thú y, Lâm nghiệp, Kiểm lâm, Thủy sản, Thủy lợi, Đê điều... |
| 8 | `08. QUOC_PHONG_NGOAI_VU` | Quốc phòng, Ngoại vụ & Sự cố đặc thù | 4 | Bộ CHQS tỉnh Gia Lai, Sở Ngoại vụ | Quản lý vùng trời (phương tiện bay không người lái), Sự cố tràn dầu BQP, Hội nghị quốc tế, Hợp tác quốc tế... |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Tài chính, Giá cả, Thuế, Phí & Công sản | 6 | Sở Tài chính, Cục Thuế, Hải quan | Quản lý giá, Quản lý công sản, Tài chính đất đai, Thuế, Phí lệ phí, Hải quan... |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Tài nguyên, Đất đai, Khoáng sản & Môi trường | 10 | Sở Nông nghiệp và Môi trường | Đất đai, Đo đạc bản đồ, Môi trường, Biến đổi khí hậu, Địa chất khoáng sản, Tài nguyên nước... |
| 11 | `11. TU_PHAP_BO_TRO` | Tư pháp, Hộ tịch & Bổ trợ tư pháp | 19 | Sở Tư pháp | Hộ tịch, Quốc tịch, Chứng thực, Công chứng, Luật sư, Đấu giá tài sản, Thừa phát lại, Giám định tư pháp... |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Khoa học, Công nghệ, Bưu chính & Viễn thông | 14 | Sở KH&CN, Sở TT&TT | Khoa học công nghệ, Sở hữu trí tuệ, Tiêu chuẩn đo lường, Bưu chính, Viễn thông, Tần số, Báo chí, Xuất bản... |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Văn hóa, Di sản, Thể thao & Du lịch | 14 | Sở Văn hóa, Thể thao & Du lịch | Di sản văn hóa, Nghệ thuật biểu diễn, Mỹ thuật triển lãm, Quảng cáo, Thể dục thể thao, Du lịch, Gia đình... |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Xây dựng, Nhà ở, Quy hoạch & GTVT | 11 | Sở Xây dựng, Sở GTVT | Hoạt động xây dựng, Nhà ở, BĐS, Quy hoạch đô thị, Hạ tầng kỹ thuật, Đường bộ, Đường sắt, Đăng kiểm... |
| 15 | `15. Y_TE_SUC_KHOE` | Y tế, Khám chữa bệnh, Dược phẩm & Mỹ phẩm | 8 | Sở Y tế | Khám bệnh, chữa bệnh, Phòng bệnh, Y dược cổ truyền, Dược phẩm, Mỹ phẩm, Thiết bị y tế... |
| **Tổng** | **15 Nhóm Lĩnh Vực Lớn** | **Toàn bộ TTHC áp dụng tại Gia Lai** | **168** | **Đầy đủ 49 Lĩnh vực chuẩn hóa (Canonical Fields)** | |

> **Tên 15 nhóm và `domain_group` lấy từ tên sheet của file Excel**, do người dùng đặt theo đúng thứ tự của cổng — không phải phân loại tự đặt. Cột "Số Lĩnh Vực Nguồn" cộng lại đúng **168** dòng `(domain_group, source_field)` đã crawl. Lĩnh vực *An toàn thực phẩm* nằm ở **cả nhóm 02 và nhóm 15** nhưng với **các mã TTHC khác nhau**; đã kiểm chứng **không mã nào thuộc hai nhóm**.

---

## 3. CẤU TRÚC KHÔNG GIAN LƯU TRỮ & THƯ MỤC ĐỒNG BỘ

Để bảo đảm tính tương thích tuyệt đối giữa hệ thống lưu trữ Google Drive, mã nguồn pipeline và Admin UI, toàn bộ tên đường dẫn và artifact được đồng bộ hóa thống nhất:

### 3.1. Cấu trúc Quản trị Dữ liệu (`DATA/`)
```text
DATA/
├── 00_DANH_MUC/                                            <-- Metadata & danh mục
│   ├── Taxonomy_TTHC_Gia_Lai_168_Linh_Vuc_15_Groups.xlsx   <-- Bảng ánh xạ 168 lĩnh vực về 15 nhóm
│   ├── danh_sach_tthc_bo_tinh_xa.json                      <-- File JSON danh mục chủ gốc (1.955 bản ghi)
│   ├── danh_sach_tthc_bo_tinh_xa_edit.xlsx                 <-- File Excel danh mục: 15 sheet = 15 nhóm, lọc sẵn bằng AutoFilter
│   ├── procedure_manifest.csv                              <-- Bảng kiểm soát tiến độ crawl & hash nội dung
│   └── validation_report.csv                               <-- Báo cáo kiểm định chất lượng
│
├── 01_RESPONSE_API/                                        <-- Response API thô, chia theo nhóm
│   └── <DOMAIN_GROUP>/
│       └── <SOURCE_FIELD>/
│           ├── 1.000172.json                               <-- BẢO HIỂM: giữ nguyên để parse lại khi sửa logic
│           └── ...
│
├── 02_KET_QUA_CHUAN_HOA/                                   <-- JSON đã chuẩn hóa, cùng cấu trúc thư mục
│   └── <DOMAIN_GROUP>/<SOURCE_FIELD>/<procedure_code>.json
│
└── 03_DU_LIEU_LOI/                                         <-- Bản ghi cần xem lại
    └── <DOMAIN_GROUP>/<SOURCE_FIELD>/<procedure_code>.json <-- Kèm trường "van_de" nêu lý do
```

**Vì sao chia theo `<DOMAIN_GROUP>/<SOURCE_FIELD>/`:** với 1.955 thủ tục, để phẳng một
thư mục sẽ rất khó tìm và khó kiểm tra bằng mắt xem thủ tục có nằm đúng nhóm không.
Chia hai tầng cho phép kiểm tra trực quan từng nhóm, và tránh ghi nhầm thủ tục sang nhóm khác.

**Vì sao lưu cả response thô lẫn JSON chuẩn hóa:** response thô là **nguồn bất biến**. Khi sửa logic transform (phân loại phí, trích thời hạn, khử trùng lặp), chỉ cần đọc lại file thô để sinh lại JSON chuẩn hóa trong vài giây, **không phải crawl lại 1,6 giờ**. Tương đương vai trò "PDF thô bất biến" ở hướng cũ.

### 3.1b. Chuỗi Xử lý 4 Bước (thay cho pipeline PDF)
```text
[API cổng DVC]  →  [Chuẩn hóa]  →  [Kiểm định]  →  [PostgreSQL SSOT]
                                                        ↓
                                          [Section-aware Chunking]
                                                        ↓
                                    ┌───────────────────┼───────────────────┐
                                    ▼                   ▼                   ▼
                            [Elasticsearch]         [Qdrant]            [Neo4j]
```

### 3.2. Cấu trúc Mã nguồn Dự án (`tthc-ai-chatbot/`)
```text
tthc-ai-chatbot/
├── .env.example
├── pyproject.toml
├── uv.lock
├── compose.yaml
├── index.html
├── README.md
│
├── config/
│   ├── crawler.yaml                                        <-- Cấu hình crawl (base URL, delay, đường dẫn)
│   ├── field_mapping.csv                                   <-- Ánh xạ 168 source_field -> 49 canonical -> 15 group
│   ├── retrieval.yaml                                      <-- Trọng số BM25/Vector, Top-K, RRF
│   └── models.yaml                                         <-- Cấu hình embedding và reranker
│
├── data/                                                   <-- Thư mục làm việc cục bộ (đồng bộ với Drive)
│   ├── raw/api/                                            <-- Response API thô, chia <domain_group>/<source_field>/
│   ├── json/                                               <-- JSON chuẩn hóa, cùng cấu trúc thư mục.
│   │                                                           **Bản gốc crawl về — KHÔNG BAO GIỜ SỬA.**
│   ├── json_normalized/                                    <-- Giai đoạn 4: bản đã chuẩn hóa khoảng trắng +
│   │                                                           content_hash tính lại. **Giai đoạn 5 đọc từ đây.**
│   │                                                           Giữ nguyên cây thư mục, đủ 1.955 bản ghi.
│   ├── processed/                                          <-- procedure_manifest.csv, chunks.jsonl
│   └── failed/                                             <-- Bản ghi NEED_REVIEW
│
├── data_pipeline/
│   ├── __init__.py
│   ├── main.py                                             <-- Điều phối pipeline
│   ├── crawler/                                            <-- GIAI ĐOẠN 3: khai thác API cổng DVC
│   │   ├── __init__.py                                     <-- Hằng số endpoint, timeout, retry
│   │   ├── api_client.py                                   <-- Client httpx gọi 2 API
│   │   ├── catalog.py                                      <-- Đọc danh mục 1.955 mã + sheet CCPL từ Excel
│   │   ├── config.py                                       <-- Đọc config/crawler.yaml
│   │   ├── transform.py                                    <-- API -> JSON chuẩn hóa
│   │   ├── validator.py                                    <-- Chấm READY / NEED_REVIEW
│   │   └── run.py                                          <-- CLI, checkpoint resume, sinh manifest
│   ├── processing/
│   │   ├── normalizer.py                                   <-- Làm sạch, chuẩn hóa số tiền & ngày
│   │   ├── validator.py                                    <-- Kiểm tra trường bắt buộc trước khi nạp
│   │   └── chunker.py                                      <-- GIAI ĐOẠN 5: section-aware chunking
│   └── indexing/
│       ├── postgres.py                                     <-- GIAI ĐOẠN 6: nạp PostgreSQL
│       ├── elasticsearch.py                                <-- GIAI ĐOẠN 8
│       ├── qdrant.py                                       <-- GIAI ĐOẠN 9
│       └── neo4j.py                                        <-- GIAI ĐOẠN 7: dựng đồ thị
│
├── backend/                                                <-- Dịch vụ trực tuyến
│   ├── app/
│   │   ├── main.py                                         <-- FastAPI app, CORS, lifespan, /health
│   │   ├── config.py                                       <-- Pydantic BaseSettings đọc .env
│   │   ├── text_norm.py                                    <-- Chuẩn hoá tiếng Việt dùng chung
│   │   ├── api/
│   │   │   ├── chat.py                                     <-- POST /chat, POST /chat/stream (SSE)
│   │   │   ├── search.py                                   <-- GET /search (debug retrieval)
│   │   │   ├── procedures.py                               <-- GET /procedures/{code}
│   │   │   └── admin.py                                    <-- Admin UI + /workflow/ask + /retrieval/test
│   │   ├── auth/                                           <-- Đăng nhập quản trị, session
│   │   ├── services/
│   │   │   ├── chat_service.py
│   │   │   ├── search_service.py
│   │   │   └── procedure_service.py
│   │   ├── db/
│   │   │   ├── postgres.py
│   │   │   ├── elasticsearch.py
│   │   │   ├── qdrant.py
│   │   │   └── neo4j.py
│   │   ├── rag/
│   │   │   ├── retrieval.py                                <-- Vào luồng workflow
│   │   │   ├── resolve.py                                  <-- Định danh mã/tên thủ tục, vector
│   │   │   ├── resolver.py                                 <-- Resolver tên (exact/vector)
│   │   │   ├── grounding.py                                <-- Grounding subject mention
│   │   │   ├── hybrid.py                                   <-- BM25 + vector + RRF + rerank
│   │   │   ├── reranker.py
│   │   │   ├── sections.py                                 <-- Đọc mục nội dung PostgreSQL
│   │   │   ├── fact_lookup.py                              <-- Thuộc tính định danh
│   │   │   ├── graph_query.py                              <-- Cypher Template cố định
│   │   │   ├── graph_shapes.py
│   │   │   ├── evidence.py                                 <-- Chuẩn hoá bằng chứng
│   │   │   ├── embeddings.py
│   │   │   ├── scope.py
│   │   │   ├── types.py
│   │   │   ├── generation.py                               <-- PLACEHOLDER: chưa dùng
│   │   │   └── prompts.py                                  <-- PLACEHOLDER: chưa dùng
│   │   ├── workflow/                                       <-- LangGraph + hiểu câu hỏi
│   │   │   ├── state.py
│   │   │   ├── question_frame.py                           <-- Schema QuestionFrame v1.0
│   │   │   ├── question_parser.py                          <-- LLM → frame + adapter router
│   │   │   ├── planner.py                                  <-- Capability matrix → Task
│   │   │   ├── executor.py                                 <-- Chạy task + coverage + fallback
│   │   │   ├── answer.py                                   <-- Contract + verify + fallback text
│   │   │   ├── nodes.py                                    <-- Node truy xuất legacy
│   │   │   ├── router_rules.py
│   │   │   ├── graph.py                                    <-- StateGraph, node THUC_THI
│   │   │   ├── run.py                                      <-- RunResult + trace
│   │   │   └── trace_log.py
│   │   ├── models/
│   │   └── schemas/
│   ├── tests/                                              <-- pytest (679 test ngày 2026-10-22)
│   ├── migrations/
│   └── Dockerfile
│
├── frontend/                                               <-- React + Vite + TypeScript + Tailwind
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── client/                                     <-- Giao diện người dân
│   │   │   ├── layout/
│   │   │   └── ui/
│   │   ├── data/
│   │   ├── hooks/
│   │   ├── pages/
│   │   │   ├── client/                                     <-- ChatPage
│   │   │   └── admin/                                      <-- Trang monitoring
│   │   ├── styles/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
├── notebooks/
│   └── process_tthc_colab.ipynb                            <-- Chỉ orchestration
│
├── evaluation/
│   ├── dataset/
│   │   └── eval_testset.jsonl                              <-- Bộ test giấu mặt (Blind Evaluation)
│   ├── evaluate_retrieval.py                               <-- Recall@K, MRR, nDCG
│   └── evaluate_rag.py                                     <-- Faithfulness, Groundedness (Ragas)
│
├── scripts/
│   ├── prepare_data.py                                     <-- Gọi crawler sinh manifest
│   ├── process.py                                          <-- Normalize -> validate -> chunk
│   └── index.py                                            <-- Nạp PostgreSQL / ES / Qdrant / Neo4j
│
└── docs/
    ├── architecture.md
    ├── crawler.md                                          <-- Hướng dẫn chạy crawler
    ├── data_schema.md                                      <-- Data contract
    ├── client_ui.md                                        <-- Ghi chú chuyển đổi giao diện
    └── decisions.md                                        <-- Nhật ký quyết định kỹ thuật
```

**Nguyên tắc tách biệt:** `backend/app/api/` chỉ nhận request và gọi service; `backend/app/services/` chứa nghiệp vụ; `backend/app/db/` chỉ nói chuyện với cơ sở dữ liệu; `backend/app/workflow/` điều phối luồng. Không tầng nào vượt ranh giới của tầng khác.

---

## 4. QUY CHUẨN HỢP ĐỒNG DỮ LIỆU & LƯỢC ĐỒ CSDL (DATA CONTRACTS & SCHEMAS)

### 4.1. Hợp đồng Bảng kiểm soát (`procedure_manifest.csv`)
Tệp CSV quản lý tiến độ crawl, **13 cột**, làm việc trực tiếp với Admin UI. Sinh bởi `data_pipeline/crawler/run.py`:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `procedure_code` | VARCHAR | mã TTHC, ví dụ `"1.013314"` |
| `procedure_name` | TEXT | tên thủ tục |
| `domain_group` | VARCHAR | 1 trong 15 nhóm, **suy trực tiếp từ tên sheet** của file Excel |
| `source_field` | VARCHAR | lĩnh vực nguồn nguyên bản |
| `administrative_level` | VARCHAR | cấp thực hiện |
| `co_quan_ban_hanh` | TEXT | cơ quan ban hành, **lấy từ API** (nguồn chân lý) |
| `detail_url` | TEXT | URL trang chi tiết — **nguồn trích dẫn** |
| `fee_note` | TEXT | phí, trích từ trường có cấu trúc `phi` |
| `status` | VARCHAR | `READY` \| `NEED_REVIEW` |
| `issues` | TEXT | lý do cần xem lại, phân tách bằng `;` |
| `content_hash` | CHAR(64) | SHA-256 của **nội dung nghiệp vụ**, phát hiện thủ tục thay đổi |
| `crawled_at` | TIMESTAMP | thời điểm crawl |
| `raw_path` | TEXT | đường dẫn file response thô để parse lại |

**Vì sao manifest lấy `co_quan_ban_hanh` từ API, không từ Excel.** Cột `Cơ quan ban hành` của Excel trộn hai khái niệm: cấp Bộ (`Bộ Công thương`) và đơn vị soạn thảo (`Văn phòng Bộ`, `Cục Công nghiệp công nghệ thông tin`, `Vụ Đánh giá và Thẩm định công nghệ`...). **20 mã bị ảnh hưởng.** Đối chiếu theo cột đó sinh cờ đỏ giả — ví dụ `1.014967` có quyết định `1213/QĐ-BCT` (Bộ Công Thương ban hành) nhưng Excel ghi `Văn phòng Bộ`. API luôn trả tên cấp Bộ nên là nguồn chính xác hơn. Chi tiết ở `docs/crawler.md`.

**`canonical_field` chưa có trong manifest.** Cột này cần `config/field_mapping.csv` (168 → 43 → 15) — sản phẩm của Giai đoạn 2.

**Lưu ý về `content_hash`:** băm **nội dung nghiệp vụ**, bỏ các trường phiên bản (`ngay_crawl`, `ngay_cap_nhat`, `content_hash`). Mục đích: phát hiện thủ tục đã thay đổi để bỏ qua chunking và embedding cho phần không đổi.

**Ghi chú về `validation_report.csv`:** là báo cáo tổng hợp sinh từ cột `status` và `issues` của manifest, không phải file nhập tay. Admin UI đọc cả hai.

**Lưu ý về font khi mở manifest:** file là UTF-8 chuẩn. Nếu mở bằng Excel bị lỗi tiếng Việt, dùng `Data > From Text/CSV` và chọn encoding UTF-8 — file không hỏng, chỉ là Excel đoán sai encoding.

### 4.1b. Hợp đồng JSON chuẩn hóa (`data/json/<domain_group>/<source_field>/<procedure_code>.json`)
Mỗi thủ tục một file, **29 trường**. Bộ trường gồm 23 trường bám sát file mẫu `1.115368.json` (bỏ `raw_text`), cộng **6 trường bổ sung** chia hai mức. Tên trường **tiếng Việt không dấu, ngăn bằng gạch dưới**.

**Quy tắc bắt buộc: KHÔNG tự thêm/bớt trường.** Bộ trường là hợp đồng dữ liệu với tầng sau. Test `test_transform_tra_dung_29_truong` chặn mọi thay đổi âm thầm; muốn nâng cấp phải sửa đồng thời `transform.py`, file test, tài liệu này và `docs/crawler.md`.

| # | Trường | Kiểu | Ghi chú |
|---|---|---|---|
| 1 | `ma_thu_tuc` | text | mã TTHC — **duy nhất**, dùng được làm khóa chính |
| 2 | `detail_url` | text | URL trang chi tiết — **nguồn trích dẫn** |
| 3 | `formality_id` | text | UUID trên cổng. **Rỗng** với 4 TTHC liên thông (cổng không công bố UUID) |
| 4 | `ten_thu_tuc` | text | tên thủ tục |
| 5 | `so_quyet_dinh` | text | số quyết định công bố |
| 6 | `cap_thuc_hien` | text | `"Cấp tỉnh, Cấp xã"` — nối bằng `", "` |
| 7 | `loai_thu_tuc` | text | nhãn tiếng Việt từ danh mục Excel |
| 8 | `linh_vuc` | text | lĩnh vực nguồn (nhãn) |
| 9 | `doi_tuong_thuc_hien` | text | đối tượng thực hiện |
| 10 | `co_quan_co_tham_quyen` | text | cơ quan có thẩm quyền |
| 11 | `dia_chi_tiep_nhan` | text | địa chỉ tiếp nhận hồ sơ |
| 12 | `co_quan_duoc_uy_quyen` | text | cơ quan được ủy quyền |
| 13 | `co_quan_phoi_hop` | text | cơ quan phối hợp |
| 14 | `thu_tuc_lien_quan` | text | `"Không có thông tin"` nếu không có. Nếu có: **tên các thủ tục, ngăn bằng `", "`**, giữ nguyên thứ tự cổng liệt kê (xem ghi chú ngữ nghĩa bên dưới) |
| 15 | `trinh_tu_thuc_hien` | text | trình tự các bước |
| 16 | `cach_thuc_thuc_hien` | text | **bảng có tab**: Hình thức nộp / Thời gian / Phí, lệ phí / Mô tả |
| 17 | `thanh_phan_ho_so` | text | **bảng có tab**: Tên giấy tờ / Mẫu đơn / Số lượng |
| 18 | `can_cu_phap_ly` | text | **bảng có tab**: Tên văn bản / Mã văn bản |
| 19 | `co_quan_thuc_hien` | text | cơ quan thực hiện |
| 20 | `yeu_cau_dieu_kien` | text | `"Không có thông tin"` nếu API trả `"Không"` |
| 21 | `ket_qua_xu_ly` | text | kết quả nhận được |
| 22 | `co_quan_ban_hanh` | text | **Mức 1** — 1 trong 19 cơ quan ban hành |
| 23 | `ngay_cap_nhat` | text | **Mức 1** — ISO 8601 UTC, đổi từ `updatedAt` |
| 24 | `content_hash` | text | **Mức 1** — SHA-256 của nội dung, dùng incremental load |
| 25 | `ngay_crawl` | text | **Mức 1** — ISO 8601 UTC |
| 26 | `phi` | object | **Mức 2** — `loai`, `so_tien`, `van_ban`, `mo_ta_goc`, `muc_chi_tiet` |
| 27 | `thoi_han` | object | **Mức 2** — `loai`, `moc`, `nhieu_don_vi`, `muc_chi_tiet` |
| 28 | `trang_thai` | text | `ACTIVE` / `UPDATED` / ... |
| 29 | `domain_group` | text | nhóm lĩnh vực, suy từ tên sheet Excel |

**Vì sao bỏ `raw_text`:** đây là DOM text do crawler HTML cũ sinh ra. Hướng API không có khái niệm DOM nên không tái tạo trung thực được. Bỏ hẳn thay vì giữ một trường luôn rỗng.

### 4.1c. Ngữ nghĩa `thu_tuc_lien_quan` — đọc kỹ trước khi dùng

Trường này chứa tên các thủ tục trong **cùng một quy trình liên thông**. Portal hiển thị ở tab
*"TTHC liên thông"* của trang chi tiết thủ tục.

**Quan hệ này nghĩa là "thành phần của một quy trình liên thông", KHÔNG phải "thủ tục tiên quyết".**

Ví dụ thủ tục `1.014475` (liên thông cấp Giấy phép kinh doanh dịch vụ karaoke) có
`thu_tuc_lien_quan = "Thủ tục cấp giấy phép đủ điều kiện kinh doanh dịch vụ karaoke, Đăng ký thành
lập hộ kinh doanh, Cấp mới Giấy chứng nhận đủ điều kiện về an ninh, trật tự (thực hiện tại cấp xã)"`.

Ba thủ tục đó là **ba giai đoạn của cùng một hồ sơ** — người dân **nộp một lần**, không phải làm
xong cái này mới sang cái kia. Vì vậy **không được** để chatbot trả lời *"bạn phải làm thủ tục đăng
ký hộ kinh doanh trước"* — sai nghiệp vụ.

**Ba quy tắc lưu trữ:**

1. **Giữ nguyên tên**, không tra mã TTHC rồi tạo khóa ngoại. Portal chỉ cung cấp tên, không có mã.
   Tra tên dễ khớp sai — "Thủ tục đăng ký khai sinh" ứng với nhiều mã khác nhau.
2. **Giữ nguyên thứ tự cổng liệt kê.** Thứ tự phản ánh trình tự các giai đoạn trong quy trình.
3. **Kiểu `text`, ngăn bằng `", "`** — giống quy ước nối chuỗi của API. Không đổi sang mảng, vì
   1.951 bản ghi khác cũng dùng kiểu này.

**Quan hệ Neo4j (Giai đoạn 7):** dùng cạnh `(:ThuTuc)-[:THU_TUC_LIEN_QUAN]->(:ThuTuc)` (tên cạnh trùng tên trường JSON), **không** dùng
`[:TIEN_QUYET]`. Đặt tên sai sẽ dẫn Router tới kết luận sai. **Lưu ý:** cạnh này chỉ có **3/1.955 bản ghi** — cạnh trục của đồ thị là `[:CAN_CU_PHAP_LY]`, xem §4.3c.

### 4.1d. Giá trị sentinel — `"Không có thông tin"` KHÁC `"Không có"`

Cổng DVC dùng một số cụm từ để **đánh dấu mục chưa ghi nhận** thay vì để trống. Chúng **không phải
nội dung nghiệp vụ**. Bộ giá trị đã chốt (`EMPTY_SENTINELS` trong `normalizer.py`):

```text
"Không"   "không"   "Không có thông tin"   "Không quy định"   "không quy định"
```

**Phân biệt hai câu KHÁC NHAU về nghĩa — đây là điểm dễ sai nhất:**

```text
"Không có thông tin"  = cổng CHƯA GHI NHẬN mục này
"Không có"            = khẳng định CHẮC CHẮN không có
```

**Độ phủ thật đo trên 1.955 bản ghi (2026-10):**

| Trường | Có giá trị thật | Sentinel | Rỗng |
|---|---:|---:|---:|
| `thu_tuc_lien_quan` | **3** | 1.952 | 0 |
| `yeu_cau_dieu_kien` | 887 | 187 | 881 |
| `dia_chi_tiep_nhan` | 232 | 3 | 1.720 |
| `ket_qua_xu_ly` | 1.947 | 2 | 6 |

**Vì sao phải quan tâm:** `thu_tuc_lien_quan` có độ phủ "100%" nếu chỉ đếm "trường không rỗng" —
nhưng thực tế **chỉ 3 bản ghi** có dữ liệu. Vì vậy báo cáo Giai đoạn 4 **tách 3 cột** (`giá trị
thật` / `sentinel` / `rỗng`), và luận văn phải trích **cột "giá trị thật"**.

**Ba quy tắc xử lý — nhất quán ở mọi giai đoạn:**

1. **Không đổi giá trị gốc khi lưu trữ.** Giữ nguyên `"không quy định"` viết thường nếu cổng viết
   thường — dữ liệu phải sát nguồn. Việc nhận diện sentinel dùng `is_sentinel()` (nhận cả hoa/thường).
2. **Không bỏ trường khi chunk (Giai đoạn 5).** Người dùng hỏi *"thủ tục A có liên quan tới thủ tục
   nào không?"* — nếu bỏ trường thì LLM không có nguồn và sẽ trả lời *"không có thủ tục liên quan"*,
   một **khẳng định sai**. Bỏ dữ liệu khiến LLM không phân biệt được *chưa có dữ liệu* với *không có*.
3. **Đổi cách diễn đạt khi render:** sentinel → *"cổng chưa ghi nhận thông tin"*. Kèm luật prompt ở
   Giai đoạn 14: **không được** nói *"không có X"* khi dữ liệu ghi *"chưa ghi nhận X"*.

**Ngoại lệ:** `phi` và `thoi_han` có cờ cấu trúc riêng (`CHUA_XAC_DINH`) nên **không sinh chunk**
khi rơi vào trạng thái đó, thay vì render thành câu văn bản.

**Một điểm đã kiểm chứng:** 3 tên trong `thu_tuc_lien_quan` của `2.002621` (*"Thủ tục đăng ký khai
sinh"*, *"Cấp thẻ bảo hiểm y tế"*, *"Đăng ký thường trú"*) **không khớp thủ tục nào** trong 1.955 mã
đã crawl. Chúng là **tên thành phần bên trong quy trình liên thông**, không phải thủ tục độc lập
trong danh mục. Đây là lý do thứ hai để không tra mã cho các tên đó.


**Vì sao thêm 4 trường Mức 1.** Ba vấn đề đã kiểm chứng bằng dữ liệu thật:
* **`co_quan_ban_hanh`** — JSON bản trước **không có** cơ quan ban hành (chỉ manifest có). Thiếu nó là mất 19 cơ quan, mất JOIN vào `procedures.issuing_agency`, mất phép kiểm chứng chéo với Excel, và mất quan hệ Neo4j `(:CoQuan)-[:BAN_HANH]->(:ThuTuc)`.
* **`ngay_cap_nhat`** — không có thì không có versioning, không biết bản ghi cũ hay mới.
* **`content_hash`** — dùng incremental load: hash không đổi thì **bỏ qua chunking và embedding**, tiết kiệm lớn khi crawl lại 1.955 thủ tục. Băm **nội dung nghiệp vụ**, bỏ các trường phiên bản (`ngay_crawl`, `ngay_cap_nhat`, `content_hash`); nếu băm cả chúng thì hash đổi mỗi lần crawl và incremental load vô nghĩa.
* **`ngay_crawl`** — audit và tái lập kết quả thực nghiệm Chương 4.

**Vì sao thêm 2 trường Mức 2.** Phí và thời hạn là hai câu hỏi phổ biến nhất của người dân, nhưng ở bản trước chúng bị chôn trong bảng text nên **không truy vấn được bằng index**. Có cấu trúc rồi mới làm được:
```sql
WHERE (phi->>'so_tien')::int < 500000
WHERE (thoi_han->'moc'->0->>'gia_tri')::int <= 3
```
Chi tiết 5 loại phí và 3 loại thời hạn ở mục 1.2b.

**Quy ước giá trị:** trường API không trả → `""` (không bỏ trường đi); API trả `"Không"` → `"Không có thông tin"`; trường nhiều giá trị → nối bằng `", "`. Không trường text nào trả `None`; riêng `phi.so_tien` là `null` khi không có số tiền — **cố ý**, để phân biệt "không có số tiền" với "0 đồng".

**Quy tắc `phi` và `thoi_han` — điểm quan trọng nhất.** Cả hai đều phải giữ **CẶP (giá trị, điều kiện)**, không chỉ giá trị:

* `phi.muc_chi_tiet` — mảng `{so_tien, dieu_kien}`. Thủ tục `1.004376` có **8 mức phí** cho 8 trường hợp; `1.014257` có **10 mức**. `so_tien` là `null` khi cổng ghi *"theo quy định…"* mà không nêu số tiền (thủ tục `2.000115`).
* `thoi_han.muc_chi_tiet` — mảng `{gia_tri, don_vi, dieu_kien, hinh_thuc}`. Thủ tục `2.000115` có nhiều mốc **cùng `3 Ngày làm việc`** nhưng **điều kiện khác nhau**; `3.000242` có **6 mốc** khác đơn vị.

**Vì sao phải giữ cặp:** đo trên 1.955 bản ghi, **442 bản ghi có mô tả phí nhưng mô tả KHÔNG chứa số tiền nào**. Chỉ lưu một con số thì câu hỏi *"trường hợp của TÔI đóng bao nhiêu / mất bao lâu?"* — câu hỏi phổ biến nhất — **không trả lời được**.

**Khử trùng theo CẶP, không theo giá trị.** Ở `1.004376` có hai mục **cùng 21.500.000** ứng với hai điều kiện khác nhau; ở `3.000242` có hai mục **cùng 5 Ngày làm việc** ứng với hai điều kiện khác nhau. Khử theo giá trị sẽ **mất một mức**.

**`dieu_kien` ĐƯỢC PHÉP rỗng khi có số tiền.** Cổng có đăng ký phí mà không kèm điều kiện — **35/1909 bản ghi** ở đúng ca đó (`1.006468` 20.000đ Hải quan, `2.000635` 8.000đ Hộ tịch, `1.013836` 500.000đ Công chứng…). Không phải thiếu dữ liệu mà là **không có điều kiện nào để mô tả**. Validator **không** chấm lỗi; chỉ bắt buộc có điều kiện khi `so_tien = null` (lúc đó điều kiện là thông tin duy nhất).

**Quy tắc render chunk `FEE` — tránh dấu gạch treo:**

```text
so_tien có + dieu_kien rỗng  →  "- 20.000 đồng"          (KHÔNG in "— ")
                                 kèm dòng "Mức phí phổ biến, không kèm điều kiện riêng."
so_tien có + dieu_kien có    →  "- 34.500.000 đồng — Quốc tế chiều đi, cấp lần đầu"
so_tien null + dieu_kien có  →  "- Theo quy định của Bộ Tài chính"
```

**`nhieu_don_vi = true`** nghĩa là thủ tục có nhiều mốc với **đơn vị khác nhau** (ví dụ `3.000242` có `Ngày`, `Giờ` và `Ngày làm việc`) — khi đó **không được trả lời bằng một con số duy nhất**.

**KHÔNG có `tom_tat`** (đã bỏ). Trường đó lấy giá trị lớn nhất theo từng đơn vị, tạo ra câu *"20 ngày, 1 giờ, 5 ngày làm việc"* — đọc lên như thể **cộng dồn**, trong khi thực tế là các tình huống **loại trừ nhau**. Không code nào đọc nó. Chunk `PROCESSING_TIME` render từ `muc_chi_tiet`.

**`ma_thu_tuc` là duy nhất.** Kiểm chứng trên danh mục gốc (sheet `TTHC`): **1.955 dòng, 1.955 mã duy nhất, không mã nào lặp** — đếm trực tiếp từ dữ liệu đã crawl (`data/json/`). Khóa chính là `ma_thu_tuc`.

**Phân biệt hai chuyện khác nhau — đừng gộp:** *danh mục gốc* có mã duy nhất, còn *ranh giới nhóm* là việc một **lĩnh vực** về mặt từ ngữ có thể hợp lý với hai nhóm. Đó là chuyện cấu hình filter, không phải mã trùng.

**Trường hợp `An toàn thực phẩm` nằm ở hai nhóm:** lĩnh vực này xuất hiện ở **nhóm `02. CONG_THUONG_NANG_LUONG`** và **nhóm `15. Y_TE_SUC_KHOE`**.

**Mã `1.006424` thuộc nhóm `15. Y_TE_SUC_KHOE`.** Trước đây mã này còn sót lại ở nhóm `02. CONG_THUONG_NANG_LUONG` do **chưa xóa khỏi file Excel** — nay đã xóa. Việc cùng một tên lĩnh vực nằm ở hai nhóm là **đúng với dữ liệu cổng**, và **mỗi mã chỉ thuộc một nhóm**.

### 4.2. Cấu trúc Cơ sở Dữ liệu PostgreSQL (SSOT DDL)
Khắc phục triệt để vấn đề cấp hành chính đa cấp và cơ quan tham gia đa vai trò:

```sql
-- 1. Bảng Thủ tục Hành chính Gốc (Metadata Master SSOT)
CREATE TABLE procedures (
    procedure_code VARCHAR(50) PRIMARY KEY,
    procedure_name TEXT NOT NULL,
    domain_group VARCHAR(100) NOT NULL,
    source_field VARCHAR(255) NOT NULL,
    canonical_field VARCHAR(255) NOT NULL,
    administrative_levels TEXT[] NOT NULL,     -- Lưu mảng đa cấp: ARRAY['Cấp tỉnh', 'Cấp xã']
    issuing_agency TEXT NOT NULL,              -- Cơ quan ban hành, từ JSON `co_quan_ban_hanh` (API)
    target_audience TEXT,                      -- Đối tượng thực hiện (Công dân, Doanh nghiệp...)
    procedure_type VARCHAR(100),               -- Loại thủ tục hành chính
    decision_number VARCHAR(100),              -- Số quyết định công bố
    decision_date VARCHAR(50),                 -- Ngày ban hành quyết định
    requirements TEXT,                         -- Yêu cầu, điều kiện thực hiện
    status VARCHAR(50) DEFAULT 'Đã công khai',
    formality_id TEXT,                         -- UUID của bản ghi trên cổng DVC. Để TEXT chứ không UUID vì:
                                               -- (1) 4 TTHC liên thông không có UUID — cổng dùng ID số, để NULL
                                               -- (2) cổng đã đổi định dạng định danh một lần rồi, TEXT chịu được cả hai
                                               -- Không phải trường bắt buộc; khóa đồng bộ là procedure_code
    detail_url TEXT,                           -- URL trang chi tiết, dùng cho citation
    domain_field_code VARCHAR(50),             -- Mã lĩnh vực do cổng cấp (ví dụ G13-TN02)
    content_hash CHAR(64) NOT NULL,            -- SHA-256 của response API thô
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tạo GIN Index hỗ trợ tìm kiếm mảng cấp thực hiện cực nhanh
CREATE INDEX idx_procedures_levels ON procedures USING GIN (administrative_levels);
CREATE INDEX idx_procedures_domain ON procedures(domain_group);
CREATE INDEX idx_procedures_canonical ON procedures(canonical_field);
CREATE UNIQUE INDEX idx_procedures_formality ON procedures(formality_id);

-- 2. Bảng nối Cơ quan tham gia đa vai trò (Giải quyết Cơ quan phối hợp, Ủy quyền, Thụ lý)
CREATE TABLE procedure_agencies (
    id SERIAL PRIMARY KEY,
    procedure_code VARCHAR(50) NOT NULL REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    agency_name TEXT NOT NULL,
    role VARCHAR(50) NOT NULL,                -- 'THUC_HIEN', 'THAM_QUYEN', 'PHOI_HOP', 'UY_QUYEN'
    is_inferred BOOLEAN DEFAULT FALSE,        -- TRUE nếu cơ quan được suy luận bù khuyết
    CONSTRAINT chk_agency_role CHECK (role IN ('THUC_HIEN', 'THAM_QUYEN', 'PHOI_HOP', 'UY_QUYEN'))
);

CREATE INDEX idx_proc_agencies_code ON procedure_agencies(procedure_code);
CREATE INDEX idx_proc_agencies_name_role ON procedure_agencies(agency_name, role);

-- 3. Bảng phân đoạn nghiệp vụ chức năng
CREATE TABLE procedure_sections (
    section_id VARCHAR(120) PRIMARY KEY,       -- Cấu trúc: {procedure_code}:{section_type}:{chunk_order}
    procedure_code VARCHAR(50) NOT NULL REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    section_type VARCHAR(50) NOT NULL,         -- 'REQUIRED_DOCUMENTS', 'PROCESSING_TIME', 'FEE', 'STEPS', 'LEGAL_BASIS'...
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,                     -- nội dung chunk; bảng biểu giữ dạng text có tab
    chunk_order INT NOT NULL DEFAULT 0,        -- thứ tự chunk trong cùng một section
    detail_url TEXT,                           -- URL nguồn để trích dẫn
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sections_procedure_code ON procedure_sections(procedure_code);
CREATE INDEX idx_sections_type ON procedure_sections(section_type);
```

**Ghi chú về `formality_id` (quan trọng):** đây là **trường tùy chọn**, không phải bắt buộc. Nó là UUID của bản ghi trên Cổng DVC Quốc gia, dùng **duy nhất** ở khâu crawl (gọi API chi tiết). **Không code nào downstream đọc nó để truy xuất** — khóa đồng bộ giữa bốn CSDL là `procedure_code` (PostgreSQL, Neo4j) và `chunk_id` (Elasticsearch, Qdrant).

**4 TTHC liên thông** (`3.000153`, `2.002621`, `2.002622`, `1.014475`) **không có UUID**: cổng dùng đường dẫn `/thu-tuc-hanh-chinh-lien-thong/<ID số>` và endpoint chi tiết của nhóm này bị WAF chặn. Chúng vẫn có `detail_url` thật nên **trích dẫn hoạt động bình thường**. Cột khai `TEXT` (không `UUID`) để chứa được cả UUID của 1.951 bản ghi kia lẫn `NULL` của 4 bản ghi này — `NULL` nhiều dòng vẫn hợp lệ với `UNIQUE INDEX`.

**Khi nạp:** đổi chuỗi rỗng thành `NULL` — `NULLIF(record->>'formality_id', '')`.

**Không được tự sinh UUID** cho 4 bản ghi này để lấp chỗ trống: làm vậy là tuyên bố cổng có bản ghi mang UUID đó, và khi sau này lấy được UUID thật thì incremental load sẽ hiểu nhầm thành bản ghi khác và tạo bản trùng.

**Ghi chú về trích dẫn nguồn (Strict Provenance):** hướng PDF cũ dùng `page_number` để truy vết vị trí trong tài liệu. Hướng API **không có khái niệm trang**, nên trường `page_number` đã được bỏ; thay bằng `detail_url` trỏ tới trang chi tiết thủ tục trên cổng. Đây là trích dẫn **mạnh hơn** vì người dân bấm được và thấy đúng nội dung chính thức, trong khi số trang PDF chỉ có nghĩa khi mở đúng file.

### 4.3. Lược đồ Đồ thị Tri thức Neo4j (Knowledge Graph Schema)

**Nguyên tắc đặt tên:** mọi cạnh đặt tên **trùng với tên trường JSON** (viết HOA). Nhờ vậy truy vết được ngay một cạnh trong đồ thị sinh ra từ trường nào trong `data/json/`, và ngược lại. Đây là điều kiện để kiểm chứng đồ thị khớp dữ liệu.

#### 4.3a. Đỉnh (Node Labels)

| Nhãn | Khóa | Sinh từ trường |
|---|---|---|
| `(:ThuTuc)` | `ma_thu_tuc` | `ma_thu_tuc`, `ten_thu_tuc` |
| `(:CoQuan)` | `name` | `co_quan_ban_hanh`, `co_quan_thuc_hien`, `co_quan_co_tham_quyen`, `co_quan_phoi_hop`, `co_quan_duoc_uy_quyen` |
| `(:DomainGroup)` | `name` | `domain_group` (15 nhóm) |
| `(:LinhVuc)` | `name` | `linh_vuc` (168 lĩnh vực nguồn) |
| `(:CapHanhChinh)` | `name` | `cap_thuc_hien` — 5 giá trị: `Cấp bộ`, `Cấp tỉnh`, `Cấp xã`, `Cơ quan khác`, `Chưa xác định`. **Không có `Cấp huyện`** vì mô hình hành chính hiện hành đã bỏ cấp này. |
| `(:DoiTuong)` | `name` | `doi_tuong_thuc_hien` |
| `(:KetQua)` | `name` | `ket_qua_xu_ly` |
| `(:VanBanPhapLy)` | `ma_van_ban` | `can_cu_phap_ly` |
| `(:TrangThai)` | `name` | `trang_thai` |

#### 4.3b. Mười hai cạnh (Relationships) — kèm độ phủ thật

Độ phủ đo trực tiếp trên **1.955 bản ghi** trong `data/json/`.

**Nhóm A — quan hệ với cơ quan (4 cạnh, 4 vai trò tách biệt):**

| Cạnh | Sinh từ trường | Đỉnh đích | Độ phủ |
|---|---|---|---|
| `[:BAN_HANH_BOI]` | `co_quan_ban_hanh` | `:CoQuan` | 1.951/1.955 (99,8%) |
| `[:CO_THAM_QUYEN]` | `co_quan_co_tham_quyen` | `:CoQuan` | 505/1.955 (25,8%) |
| `[:PHOI_HOP]` | `co_quan_phoi_hop` | `:CoQuan` | 42/1.955 (2,1%) |
| `[:DUOC_UY_QUYEN]` | `co_quan_duoc_uy_quyen` | `:CoQuan` | 12/1.955 (0,6%) |

> **Ưu thế của hướng API:** bốn vai trò cơ quan được tách thành bốn trường riêng, nên dựng được bốn loại cạnh. Hướng PDF chỉ có một trường text lẫn lộn, không tách được.
>
> **Cảnh báo về hai cạnh thưa:** `[:PHOI_HOP]` (2,1%) và `[:DUOC_UY_QUYEN]` (0,6%) chỉ cho **42** và **12** cạnh. Truy vấn dựa vào chúng sẽ trả về gần như rỗng — **không nên** đặt kỳ vọng "tra cứu thủ tục phối hợp liên ngành" lên hai cạnh này trong tiêu chuẩn nghiệm thu.

**Nhóm B — quan hệ phân loại (4 cạnh):**

| Cạnh | Sinh từ trường | Đỉnh đích | Độ phủ |
|---|---|---|---|
| `[:DOMAIN_GROUP]` | `domain_group` | `:DomainGroup` | 1.955/1.955 (100%) |
| `[:LINH_VUC]` | `linh_vuc` | `:LinhVuc` | 1.955/1.955 (100%) |
| `[:CAP_THUC_HIEN]` | `cap_thuc_hien` | `:CapHanhChinh` | 1.951/1.955 (99,8%) |
| `[:TRANG_THAI]` | `trang_thai` | `:TrangThai` | 1.955/1.955 (100%) |

> `[:CAP_THUC_HIEN]` nối **một thủ tục tới nhiều đỉnh** nếu là thủ tục đa cấp — ví dụ nối cả `Cấp tỉnh` và `Cấp xã`.

**Nhóm C — hai quan hệ còn lại (2 cạnh):**

| Cạnh | Sinh từ trường | Đỉnh đích | Độ phủ |
|---|---|---|---|
| `[:DOI_TUONG_THUC_HIEN]` | `doi_tuong_thuc_hien` | `:DoiTuong` | 1.951/1.955 (99,8%) |
| `[:KET_QUA_XU_LY]` | `ket_qua_xu_ly` | `:KetQua` | 1.949/1.955 (99,7%) |

**Nhóm D — hai cạnh liên thủ tục:**

| Cạnh | Sinh từ trường | Đỉnh đích | Độ phủ |
|---|---|---|---|
| **`[:CAN_CU_PHAP_LY]`** | `can_cu_phap_ly` | `:VanBanPhapLy` | **1.929/1.955 (98,7%)** |
| `[:THU_TUC_LIEN_QUAN]` | `thu_tuc_lien_quan` | `:ThuTuc` | **3/1.955 (0,15%)** |

#### 4.3c. `[:CAN_CU_PHAP_LY]` là cạnh trục, không phải `[:THU_TUC_LIEN_QUAN]`

Đây là điểm dễ thiết kế sai nhất. Trường `thu_tuc_lien_quan` có **1.952/1.955 bản ghi ghi `"Không có thông tin"`** — chỉ 3 bản ghi có dữ liệu thật, cho khoảng **8 cạnh**. Lấy nó làm trục dựng đồ thị thì đồ thị gần như rỗng.

**Cạnh trục phải là `[:CAN_CU_PHAP_LY]`**, vì nó cho **hơn 5.000 cạnh** (1.929 bản ghi × trung bình 2,6 văn bản mỗi bản ghi). Cơ chế:

```cypher
(:ThuTuc)-[:CAN_CU_PHAP_LY]->(:VanBanPhapLy)<-[:CAN_CU_PHAP_LY]-(:ThuTuc)
```

**Hai thủ tục cùng viện dẫn một văn bản pháp lý thì liên quan về mặt pháp lý** — quan hệ này **suy trực tiếp từ dữ liệu có thật**, độ phủ 98,7%.

**Kiểm chứng bằng dữ liệu thật:** hai thủ tục `2.002621` và `2.002622` cùng viện dẫn `63/2024/NĐ-CP` (Nghị định quy định liên thông điện tử 02 nhóm thủ tục khai sinh và khai tử). Đồ thị **tự phát hiện** chúng liên quan mà **không cần** trường `thu_tuc_lien_quan`. Nghĩa là: **quan hệ pháp lý bù đắp được quan hệ liên thông khi trường kia rỗng.**

Vì vậy:

* `[:THU_TUC_LIEN_QUAN]` **giữ lại nhưng là cạnh phụ** — dùng làm ví dụ minh họa và để đối chiếu chéo với `[:CAN_CU_PHAP_LY]`.
* **Không được suy đoán** quan hệ liên thủ tục từ **tên** thủ tục. Trường `thu_tuc_lien_quan` chỉ có tên, không có mã; khớp theo tên dễ tạo cạnh sai. Mọi cạnh nối theo tên phải đánh cờ `is_inferred: true`.

#### 4.3d. Quy tắc bù khuyết thẩm quyền

`co_quan_co_tham_quyen` trống ở **1.450/1.955 bản ghi (74,2%)**. Với các bản ghi đó, hệ thống gán mặc định thẩm quyền theo **cấp hành chính cao nhất** thụ lý thủ tục (ví dụ TTHC cấp tỉnh → *"Ủy ban nhân dân cấp tỉnh"*), đồng thời đánh dấu `is_inferred: true` trên cạnh `[:CO_THAM_QUYEN]` để phân biệt với thẩm quyền công bố tường minh (`is_inferred: false`).

#### 4.3e. Bất nhất cần xử lý khi nạp

`co_quan_thuc_hien` (độ phủ 67,1%) chứa **nhiều cơ quan ngăn bằng `"; "`** trong một chuỗi:

```text
"Bảo hiểm xã hội cấp huyện; Sở Lao động Thương binh và Xã hội; Phòng Lao động TBXH; ..."
```

Trong khi `co_quan_co_tham_quyen`, `co_quan_phoi_hop`, `co_quan_duoc_uy_quyen` **đã là mảng sẵn** (API trả `departmentsAuthority`, `departmentsCoordinating`...). Khi nạp **phải tách `co_quan_thuc_hien` theo `"; "`**, nếu để nguyên chuỗi thì không lọc được theo cơ quan.

`co_quan_thuc_hien` dùng chính nhãn **`:CoQuan`** làm đỉnh — không tạo cạnh riêng, vì trong DDL nó là cột của bảng `procedures`, không phải bảng nối.


---

## 5. KIẾN TRÚC HỆ THỐNG HIỆN TẠI

```text
[Người dùng]
     │
     ▼
[Chuẩn hoá câu hỏi]
     │
     ├─① mã thủ tục (regex) → PostgreSQL xác thực
     ├─② văn bản pháp lý → từ điển RAM
     ├─③ thực thể đóng (cơ quan/lĩnh vực/cấp/nhóm)
     └─④ nếu chưa đủ → semantic parser → QuestionFrame
                │
                ▼
        [Grounding từng subject mention]
        mã đã xác thực · mã sai · đại từ · resolver tên · từ điển văn bản · thực thể
                │
                ▼
        [Planner tất định — capability matrix]
        facet × operation × subject → Task(tool, intent, expected_types, constraints)
        ngoài ma trận → unsupported (không đoán)
                │
                ▼
        [Executor — song song, timeout từng tool]
        section_lookup · graph · hybrid · fact_lookup
        coverage từng ý: covered / empty / failed / unsupported / ambiguous
        fallback tối đa 1 lần/ý; lỗi hạ tầng ≠ thiếu dữ liệu
                │
                ▼
        [Answer contract]
        khối "CÁC Ý CẦN TRẢ LỜI" · context nhóm theo ý · kiểm chứng hậu sinh
        vi phạm → retry 1 lần → vẫn vi phạm → câu trả lời tất định từ evidence
                │
                ▼
        [Synthesizer] → câu trả lời + citations + detail_url
```

### 5.1. Những phương pháp đã bỏ — không dùng lại

| Cách cũ (đã bỏ) | Vấn đề | Cách hiện tại |
|---|---|---|
| Router LLM chọn 1 trong 3 nhánh `FACT_LOOKUP / HYBRID_SEARCH / GRAPH_QUERY` | Câu nhiều ý bị ép vào một nhánh; router đoán sai thì mất ý | `QuestionFrame` tách từng ý, planner chọn tool cho **từng** ý |
| Nhánh tự quyết định có trả lời được không | Không có chỗ nào tính độ phủ; mục thiếu bị bỏ im lặng | Executor tính `coverage` từng request, trả lời một phần và nêu rõ phần thiếu |
| Semantic FAQ cache trên Qdrant | Không triển khai; Qdrant chỉ còn `semantic_search` | Cache TTL trong tiến trình (Phase 10) |
| `verification.py` riêng | Chưa từng tồn tại trong mã | `answer.verify_contract()` + `node_sinh` |
| Để LLM viết Cypher | Không kiểm soát được | `graph_query.py` chỉ dùng Cypher Template cố định |

### 5.2. Mô hình hai tầng chân lý vẫn giữ

1. **Chân lý tuyệt đối** — thuộc tính định danh lấy trực tiếp PostgreSQL (mã, tên, cấp, cơ quan,
   số quyết định), không qua LLM.
2. **Chân lý trích xuất** — nội dung hướng dẫn lấy từ RAG/Graph, mọi khẳng định phải có evidence
   và `detail_url`; mục tiêu Faithfulness ≥ 0.98 (đo ở Giai đoạn 16).

## 6. LỘ TRÌNH TRIỂN KHAI CHI TIẾT 16 GIAI ĐOẠN (PHASE 1 – PHASE 16)

---

### GIAI ĐOẠN 1: KHỞI TẠO DỰ ÁN & MÔI TRƯỜNG PHÁT TRIỂN (PHASE 1)
* **Mục tiêu:** Thiết lập khung xương dự án chuẩn mực, kiểm soát toàn diện dependencies bằng công cụ hiện đại, cấu hình logging và biến môi trường sẵn sàng cho container hóa.
* **Các công việc thực hiện:**
  1. Khởi tạo repository `tthc-ai-chatbot` với `git`.
  2. Sử dụng trình quản lý gói `uv` để tạo môi trường ảo và file `pyproject.toml` tại **thư mục gốc** (một file duy nhất cho toàn dự án).
  3. Cài đặt các thư viện lõi: `fastapi[standard]`, `uvicorn`, `pydantic>=2.0`, `pydantic-settings`, `httpx`, `openpyxl`, `pyyaml`, `langgraph`, `qdrant-client`, `elasticsearch[async]`, `psycopg[binary]`, `neo4j`, `sqlalchemy`, `alembic`, `pandas`, `pytest`, `ruff`.
  4. Tạo file cấu hình môi trường `.env.example` chuẩn hóa. **LLM chỉ dùng 2 biến `BASE_URL` và `API_KEY`**, không thêm `provider`, `model`, `sdk_type`.
  5. Xây dựng module `backend/app/config.py` đọc cấu hình bằng Pydantic BaseSettings.
* **Tiêu chuẩn nghiệm thu (Acceptance Criteria):** Chạy `uv run ruff check .` và `uv run pytest` đều sạch; `uv run uvicorn backend.app.main:app` khởi động và endpoint `/health` trả HTTP 200.
* **Ghi chú:** không tạo `src/tra_cuu_tthc/`; không có `docker-compose.yml` riêng lẻ mà dùng `compose.yaml`.

---

### GIAI ĐOẠN 2: CHUẨN HÓA TAXONOMY & HỢP ĐỒNG DỮ LIỆU (PHASE 2)
* **Mục tiêu:** Áp dụng mô hình **15 Domain Groups** và **49 Canonical Fields** vào hệ thống lưu trữ và cấu hình.
* **Các công việc thực hiện:**
  1. Xuất tệp `Taxonomy_TTHC_Gia_Lai_168_Linh_Vuc_15_Groups.xlsx` và đưa vào `data/metadata/`.
  2. Sinh `config/field_mapping.csv` với đủ **168 dòng** ánh xạ `source_field → canonical_field → domain_group`, kèm cột `review_status` để đánh dấu dòng cần xem lại.
  3. Kiểm tra tổng ba cột `domain_group` khớp đúng **1.955 TTHC** và **168 lĩnh vực nguồn**.
  4. Sinh `config/crawler.yaml` (base URL, delay, đường dẫn đầu ra) và `config/retrieval.yaml` (trọng số, Top-K, RRF), `config/models.yaml` (embedding, reranker — để `TBD` cho tới Giai đoạn 9).
* **Tiêu chuẩn nghiệm thu:** `config/field_mapping.csv` phủ **100%** 168 lĩnh vực nguồn; mọi dòng hoặc có đủ 3 tầng, hoặc được đánh `NEED_REVIEW`; không mất giá trị `source_field` gốc.
* **Ghi chú về 3 cặp lĩnh vực gần trùng tên:** *An toàn vệ sinh lao động* / *An toàn, vệ sinh lao động*; *Thi đua – Khen thưởng* / *Thi đua, khen thưởng*; *Giáo dục nghề nghiệp* / *Giáo dục nghề nghiệp (G07-LĐ06)*. **Đây là giá trị do Cổng Dịch vụ công Quốc gia trả về, không phải lỗi Excel — KHÔNG đổi tên trong Excel**, vì đổi tên sẽ làm crawler đối chiếu sai và lấy về dữ liệu không đúng. Mỗi biến thể có **một dòng riêng** trong `field_mapping.csv`, cùng `canonical_field` và `domain_group` với biến thể kia. Tầng `canonical_field` gom chúng lại ở tầng truy vấn.

---

### GIAI ĐOẠN 3: KHAI THÁC DỮ LIỆU QUA API CỔNG DVC (PHASE 3)
* **Mục tiêu:** Thu thập nội dung thủ tục qua API công khai, lưu **response thô** làm nguồn bất biến và sinh **JSON chuẩn hóa** sẵn sàng cho chunking.
* **Cơ chế chọn nhóm lĩnh vực (Domain Group):** File Excel danh mục có **15 sheet, mỗi sheet là một Domain Group**, và mỗi sheet đã được **lọc sẵn bằng AutoFilter trên cột `Lĩnh vực`**. Crawler **chỉ lấy những hàng đang hiện**, bỏ qua hàng bị filter ẩn. Mặc định mỗi lần chạy chỉ xử lý **một nhóm** để kiểm soát và tránh ghi sai thư mục.
* **Cảnh báo kỹ thuật bắt buộc tuân thủ:** `openpyxl` **đọc cả hàng bị AutoFilter ẩn**. Nếu không xử lý filter, mỗi sheet sẽ trả về **đủ 1.955 thủ tục** thay vì chỉ nhóm của nó, và crawler sẽ ghi cùng một thủ tục vào nhiều thư mục nhóm. Cách xử lý đúng:
  1. Đọc vùng lọc từ `worksheet.auto_filter.ref` (ví dụ `G1:G1914`) để lấy **cột bắt đầu** của vùng.
  2. `filterColumn[].colId` là chỉ số **tương đối trong vùng lọc**, không phải chỉ số cột tuyệt đối — phải cộng `min_col - 1` mới ra cột thật.
  3. Một hàng đang hiện khi **mọi** cột được lọc đều khớp giá trị giữ lại.
* **Các công việc thực hiện:**
  1. Viết module `data_pipeline/crawler/api_client.py` gọi 2 endpoint, có retry giới hạn (3 lần, backoff tăng dần) và nghỉ giữa request (mặc định 1,5s) để không gây tải cho cổng.
  2. Viết `data_pipeline/crawler/catalog.py`:
     * Liệt kê 15 sheet nhóm theo đúng thứ tự trong file.
     * Suy ra mã nhóm từ tên sheet (`"2.CONG_THUONG_NANG_LUONG"` → `"02. CONG_THUONG_NANG_LUONG"`).
     * Đọc **chỉ các hàng đang hiện** theo AutoFilter.
     * Đọc sheet `CCPL` (1.049 văn bản) để ghép link tra cứu.
  3. Viết `data_pipeline/crawler/transform.py` chuyển response API thành JSON chuẩn hóa **29 trường** theo mục 4.1b. Năm quy tắc bắt buộc:
     * **Không tự thêm/bớt trường.** Bộ trường là hợp đồng dữ liệu; sửa phải cập nhật đồng thời `transform.py`, file test, mục 4.1b và `docs/crawler.md`.
     * **Trường rỗng để `""`**, không bỏ trường đi. API trả `"Không"` thì ghi `"Không có thông tin"`.
     * **Phí — gán 5 loại** (`SO_TIEN`, `MIEN_PHI`, `THEO_VAN_BAN`, `THEO_QUY_DINH_CHUNG`, `CHUA_XAC_DINH`) vào `phi.loai`, kèm `phi.so_tien` dạng **số** và `phi.mo_ta_goc` nguyên văn. **Tuyệt đối không suy diễn `fees` rỗng hoặc `value = 0` thành miễn phí** — khảo sát cho thấy phần lớn thủ tục trên cổng không công bố mức phí.
     * **Phí phải giữ CẶP (số tiền, điều kiện) trong `phi.muc_chi_tiet`.** API trả mỗi mục phí kèm `description` nói điều kiện áp dụng. Thủ tục `1.004376` có **8 mức phí** cho 8 trường hợp; `1.014257` có **10 mức**. Nếu chỉ lưu một số tiền thì **không trả lời được** *"trường hợp của tôi đóng bao nhiêu?"* — mà đó là câu hỏi phổ biến nhất về phí. Đo trên 1.955 bản ghi: **442 bản ghi có mô tả phí nhưng mô tả KHÔNG chứa số tiền nào**.
       * Khử trùng theo **cặp `(value, description)`**, KHÔNG theo `value`: ở `1.004376` có hai mục **cùng 21.500.000** ứng với hai điều kiện khác nhau, khử theo số tiền sẽ mất một mức.
       * **Giữ mục `value = 0` khi CÓ mô tả.** `2.000115` có mọi mục phí `value = 0` kèm mô tả *"Theo quy định của Bộ tài chính"* — bỏ hết thì `muc_chi_tiet` rỗng và chunk `FEE` không còn gì để nói. Ngược lại `value = 0` **không mô tả** (thủ tục `1.013314`) là nhãn `MIEN_PHI` thuần → bỏ, `phi.loai` đã nói đủ.
     * **Thời hạn — gán 3 loại** (`SO`, `TRONG_TEXT`, `CHUA_XAC_DINH`) vào `thoi_han.loai`. Ưu tiên trường số; nếu `processingTimeUnit = OTHER` hoặc `value = 0` thì trích mốc từ mô tả bằng regex. Đánh dấu `nhieu_don_vi` khi có nhiều đơn vị.
     * **Thời hạn cũng phải giữ CẶP** trong `thoi_han.muc_chi_tiet` — mảng `{gia_tri, don_vi, dieu_kien, hinh_thuc}`. Thủ tục `2.000115` có **nhiều mốc `3 Ngày làm việc` với điều kiện khác nhau**; `3.000242` có **6 mốc** khác đơn vị. **KHÔNG có trường `mo_ta` tự sinh** — bản đầu tôi lưu `mo_ta = "3 Ngày làm việc"` nên các mốc cùng số ngày nhìn giống hệt nhau và mất hết thông tin phân biệt.
     * **Khử trùng bằng `_khoa_mo_ta`** — bỏ khác biệt khoảng trắng, dấu câu, hoa/thường, chỉ lấy **dòng đầu** (cổng có lúc cắt cụt mô tả). Nhờ vậy `2.000115` gộp từ 9 mục xuống **7**. Dấu câu **thay bằng khoảng trắng** chứ không xoá thẳng, để `17/2020/NĐ-CP` vẫn khác `17/2020NĐCP`. Giá trị lưu vẫn **nguyên văn** lần gặp đầu.
     * **KHÔNG có `tom_tat`.** Đã bỏ hẳn: nó lấy max theo từng đơn vị, tạo câu *"20 ngày, 1 giờ, 5 ngày làm việc"* đọc như cộng dồn trong khi các tình huống **loại trừ nhau**. Không code nào đọc.
     * **`content_hash` băm nội dung**, bỏ các trường phiên bản (`ngay_crawl`, `ngay_cap_nhat`, `content_hash`). Nếu băm cả chúng thì hash đổi mỗi lần crawl và incremental load vô nghĩa.
  4. Viết `data_pipeline/crawler/validator.py` chấm `READY` / `NEED_REVIEW`. Hai lưu ý:
     * **Không** coi `thanh_phan_ho_so` rỗng là lỗi — phần lớn thủ tục để trống trường này.
     * **Không** coi `formality_id` rỗng là lỗi — 4 TTHC liên thông không có UUID (cổng dùng ID số cho nhóm này). Trường bắt buộc là `ma_thu_tuc`, `ten_thu_tuc`, `detail_url`.
  5. Viết `data_pipeline/crawler/run.py` làm CLI với các lựa chọn: `--list-sheets`, `--sheet <tên|số|all>`, `--limit`, `--codes`, `--test`, `--redo`, `--delay`. Có checkpoint resume và sinh `procedure_manifest.csv`.
  6. **Lưu kết quả theo cấu trúc `<domain_group>/<source_field>/`** cho cả `data/raw/api/`, `data/json/` và `data/failed/`. `domain_group` giữ dạng `"15. Y_TE_SUC_KHOE"`; `source_field` đổi sang **tiếng Việt không dấu, ngăn bằng gạch dưới** (`"Đăng ký, quản lý cư trú"` → `Dang_ky_quan_ly_cu_tru`) để đường dẫn an toàn trên mọi hệ điều hành.
  7. Chạy theo thứ tự: `--list-sheets` → `--test` → từng nhóm một hoặc `--sheet all`.
* **Tiêu chuẩn nghiệm thu:**
  * Mỗi lần chạy chỉ đọc đúng một nhóm; log ghi rõ *"Đọc nhóm X: N thủ tục (bỏ qua M hàng không khớp filter)"*.
  * Cấu trúc thư mục đầu ra là `<domain_group>/<source_field slug>/<procedure_code>.json`.
  * Mỗi file JSON có **đúng 29 trường** nêu ở mục 4.1b, không thiếu không thừa.
  * `procedure_manifest.csv` có cột `domain_group`, `status`, `issues`; **không** bản ghi nào mang nội dung giả khi thiếu dữ liệu.
  * Tổng số bản ghi crawl của 15 nhóm là **1.955** — đếm trực tiếp từ dữ liệu đã crawl, khớp với tổng số hàng đang hiện.
* **Hiệu năng (đo thật, 2026-10):** API cổng rất nhanh — **2 request hết 0,10 giây**. Nút cổ chai duy nhất là **đọc file Excel danh mục**: `load_workbook(read_only=False)` tốn **22,5 giây** cho file thật (1.930 hàng + nhiều sheet phụ lớn), còn `read_only=True` chỉ 0,28 giây nhưng **`ReadOnlyWorksheet` không có `auto_filter`** nên không dùng được.
  * **Vì vậy phải mở workbook MỘT LẦN rồi dùng lại cho mọi nhóm** (`load_catalog(..., workbook=wb)`). Mở lại theo từng nhóm: 17 × 22s ≈ **383 giây** khởi động. Mở một lần: **22 giây**. Nhanh **17 lần**.
  * Thời gian crawl thật ≈ **3,1 giây/thủ tục** (2 request 0,1s + 2 lần delay 1,5s) → 1.955 thủ tục ≈ **101 phút**. Con số này **không phụ thuộc** số thủ tục được chọn — chọn 2 thủ tục vẫn mất ~22s khởi động.

* **Ghi chú về 4 mã không được crawl — đúng thiết kế:** `1.000758`, `1.000799`, `1.002968` (lĩnh vực *Thương mại điện tử*) và `2.000046` (lĩnh vực *Chất lượng sản phẩm hàng hóa*), đều thuộc Bộ Công thương, **không khớp filter ở bất kỳ sheet nào nên không được crawl**. Đã kiểm tra: **4 thủ tục này bị bãi bỏ**, nên việc bỏ qua chúng là **đúng** — không bổ sung hai giá trị lĩnh vực trên vào AutoFilter.
* **Ghi chú về lĩnh vực nằm ở hai nhóm:** lĩnh vực *An toàn thực phẩm* xuất hiện ở nhóm `02. CONG_THUONG_NANG_LUONG` **và** nhóm `15. Y_TE_SUC_KHOE`. Đây là đúng với dữ liệu cổng, và **mỗi mã chỉ thuộc một nhóm** — mã `1.006424` thuộc nhóm `15. Y_TE_SUC_KHOE`.
* **Vì vậy tổng là 1.955 bản ghi**, **mỗi mã đúng một lần** — khớp với số file trong `data/json/`.
* **Bổ sung 47 TTHC của UBND tỉnh Gia Lai** vào hai nhóm `10. TAI_NGUYEN_MOI_TRUONG` (43 TTHC lĩnh vực *Đất đai*) và `14. XAY_DUNG_GIAO_THONG` (4 TTHC lĩnh vực *Đường bộ*) — đã crawl xong.
* **21 mã bãi bỏ đã được xóa khỏi danh mục** sau khi crawl: `1.000892`, `1.000940`, `1.007949`, `1.009445`, `1.009458`, `1.009788`, `1.011675`, `2.000378`, `2.001116`, `2.001998` (nhóm Xây dựng–Giao thông), `1.011325`, `1.013809`, `1.013811`, `1.013813`, `3.000215` (nhóm Nông lâm thủy sản), `1.005132`, `1.013727`, `1.013728`, `1.013729` (nhóm Lao động–An sinh), `2.002253`, `3.000474` (nhóm Thông tin–KHCN). Xác nhận: **không mã nào trong 21 mã này còn trong dữ liệu crawl.**

---

### GIAI ĐOẠN 4: CHUẨN HÓA & KIỂM ĐỊNH DỮ LIỆU (PHASE 4)
* **Mục tiêu:** Làm sạch và xác nhận toàn vẹn dữ liệu trước khi nạp vào PostgreSQL — nguồn chân lý duy nhất.
* **Nguyên tắc bất di bất dịch:** dữ liệu thô crawl từ cổng trong `data/json/` **KHÔNG BAO GIỜ BỊ SỬA**. Chuẩn hóa ghi ra `data/json_normalized/` với **cùng cây thư mục**. Nhờ vậy luôn đối chiếu được bản gốc với bản đã chuẩn hóa, và crawl lại không làm mất công chuẩn hóa. **Giai đoạn 5 đọc từ `data/json_normalized/`.**
* **Các công việc thực hiện:**
  1. `data_pipeline/processing/normalizer.py`: chuẩn hóa Unicode **NFC** và khoảng trắng. Ba quy tắc khoảng trắng, cố ý tách riêng:
     * Nhiều space liền nhau → một space; space thừa quanh tab → bỏ
     * **Từ ba dòng trống liên tiếp trở lên → còn hai.** Không gộp xuống dòng về một: chunker cắt theo ranh giới đoạn nên phải giữ cấu trúc dòng.
     * **KHÔNG BAO GIỜ gộp cụm tab.** `\t\t` là **một ô rỗng** trong bảng (`thanh_phan_ho_so`, `cach_thuc_thuc_hien`, `can_cu_phap_ly`); gộp lại sẽ **dịch cột** và làm sai dữ liệu. Đã gặp thật ở `1.013314` (cột "Mẫu đơn" rỗng) — có test chốt hành vi này.
     * Định nghĩa `EMPTY_SENTINELS` = {`khong`, `khong co`, `khong co thong tin`, `khong quy dinh`} (đã chuẩn hóa, không dấu) và hàm `is_sentinel()`. Xem §4.1c.
  2. `data_pipeline/processing/validator.py`: kiểm **cấu trúc** (đúng 29 trường, đúng tên, **đúng thứ tự**), kiểu dữ liệu, ràng buộc giá trị (`phi.loai`, `thoi_han.loai`), `content_hash` khớp nội dung, và **kiểm định liên file** (trùng `ma_thu_tuc`, `content_hash` dùng chung, thư mục lệch `domain_group`).
  3. Trạng thái: `READY` | `NEED_REVIEW`. **Chỉ `READY` được đi tiếp.** (`MISSING_DATA` và `DUPLICATE` gộp vào `NEED_REVIEW` kèm lý do cụ thể — tránh hai nhãn cùng nghĩa.)
  4. `scripts/build_manifest.py` — CLI, **mặc định chỉ đọc**:
     * `--normalize --write` → sinh `data/json_normalized/` (đủ 1.955 bản ghi, `content_hash` tính lại cho mọi bản ghi)
     * `--write` → sinh `data/processed/procedure_manifest.csv` (`utf-8-sig` để Excel mở đúng tiếng Việt)
     * `--report <đường dẫn>` → báo cáo markdown
     * `--dry-run` → xem trước, không ghi
  5. Báo cáo gồm 9 mục: lỗi theo loại · cảnh báo · **độ phủ 29 trường tách 3 cột** (`giá trị thật` / `sentinel` / `rỗng`) · phân bố 5 loại phí · phân bố 3 loại thời hạn · phân bố 15 nhóm · lĩnh vực thiếu mapping · chuẩn hóa khoảng trắng · lỗi liên file.
* **Vì sao độ phủ phải tách 3 cột:** `thu_tuc_lien_quan` có độ phủ "100%" nhưng thực tế chỉ **3** bản ghi có dữ liệu — 1.952 bản ghi còn lại là chuỗi `"Không có thông tin"` do cổng đánh dấu chưa ghi nhận. Báo cáo không tách thì tưởng 1.955 thủ tục đều có thủ tục liên quan.
* **Kết quả đo được (2026-10):** 1.955/1.955 `READY`, 0 lỗi, 0 lỗi liên file; 1.548 bản ghi có khoảng trắng cần chuẩn hóa; 407 bản ghi đã sạch. Toàn bộ dữ liệu **đã ở dạng NFC** nên không có giá trị nào phải đổi Unicode.
* **Tiêu chuẩn nghiệm thu:** Chỉ bản ghi `READY` vào pipeline; `data/json/` không đổi; `data/json_normalized/` đủ 1.955 bản ghi và chạy lại chuẩn hóa là **no-op**; mọi bản ghi lỗi có lý do cụ thể trong báo cáo.

---

### GIAI ĐOẠN 5: PHÂN ĐOẠN SECTION & CHUẨN BỊ NẠP CSDL (PHASE 5)
* **Đầu vào:** `data/json_normalized/` — **KHÔNG** đọc `data/json/` (đó là bản gốc crawl, có khoảng trắng thừa).
* **Mục tiêu:** Chia nội dung thủ tục thành các phân đoạn nghiệp vụ có ý nghĩa tra cứu, gán `chunk_id` ổn định, sẵn sàng cho cả PostgreSQL, Elasticsearch và Qdrant.
* **Điểm khác biệt so với hướng PDF:** nội dung **đã được API phân loại sẵn** thành các trường riêng biệt. Vì vậy **không cần dùng regex để dò tiêu đề** như hướng PDF — việc gán `section_type` trở thành **ánh xạ tất định** từ tên trường, loại bỏ hẳn một tầng sai số.
* **Bảng ánh xạ trường → `section_type`:**

  | Trường trong JSON chuẩn hóa | `section_type` | Tiêu đề hiển thị |
  |---|---|---|
  | `trinh_tu_thuc_hien` | `STEPS` | Trình tự thực hiện |
  | `cach_thuc_thuc_hien` | `SUBMISSION_METHOD` | Cách thức thực hiện |
  | `thanh_phan_ho_so` | `REQUIRED_DOCUMENTS` | Thành phần, số lượng hồ sơ |
  | `can_cu_phap_ly` | `LEGAL_BASIS` | Căn cứ pháp lý |
  | `ket_qua_xu_ly` | `RESULT` | Kết quả xử lý |
  | `yeu_cau_dieu_kien` | `REQUIREMENTS` | Yêu cầu, điều kiện thực hiện |
  | `phi` (trường có cấu trúc) | `FEE` | Phí, lệ phí |
  | `thoi_han` (trường có cấu trúc) | `PROCESSING_TIME` | Thời hạn giải quyết |
  | các trường định danh còn lại | `GENERAL_INFO` | Thông tin chung |

* **Các công việc thực hiện:**
  1. Viết `data_pipeline/processing/chunker.py` thực hiện **section-aware chunking** hai tầng:
     * **Tầng 1 — theo trường:** ánh xạ tất định 29 trường → 9 `section_type`. Một section **ngắn vẫn là một chunk riêng**, không gộp sang section khác. Đây là phần "nhận biết ngữ nghĩa" — ranh giới chunk trùng ranh giới nghiệp vụ do cổng đã phân loại sẵn, **không dò tiêu đề bằng regex**.
     * **Tầng 2 — trong section dài:** cắt theo **thứ tự ưu tiên ranh giới**, không cắt theo số ký tự:
       1. Đánh số bước (`* Bước 1`, `Bước 2`, `a)`, `b)`) — 512/1.955 bản ghi (26,2%) có dạng này
       2. Ranh giới **hàng** (với bảng) hoặc **đoạn** `\n`
       3. Ranh giới **câu** (`". "`, `"; "`)
       4. Ranh giới **mệnh đề** (`", "`) — chỉ khi câu đơn vẫn quá dài
     * **Trần cứng 4.500 ký tự** mỗi chunk. Con số này lấy từ giới hạn thật của reranker: `qwen3-rerank` cho **4.000 token mỗi document** và **trả HTTP 400 chứ không cắt bớt** nếu vượt ([tài liệu Alibaba Cloud](https://www.alibabacloud.com/help/en/model-studio/text-rerank-api)). Tiếng Việt ≈ 3 ký tự/token → 4.500 ký tự ≈ 1.500 token, còn biên an toàn.
     * **Biên mềm:** vượt trần nhưng chỉ do **một đơn vị cuối** thì **giữ nguyên, không tách**. Nhờ vậy bảng 2.256 ký tự vẫn là **một chunk**.
     * **Hàng là ĐƠN VỊ CẮT, không phải đơn vị chunk.** Đo trên 1.955 bản ghi: nếu 1 hàng = 1 chunk thì 3 trường bảng sinh **33.410 chunk** (so với 7.509 khi gộp) và **74,3% số hàng ngắn hơn 200 ký tự** — sinh ra hàng chục nghìn chunk chỉ chứa `"Lưu ý"`. Tệ hơn: câu hỏi *"cần nộp những gì?"* cần **cả danh sách**, chia nhỏ sẽ trả lời **thiếu**.
     * **Bảng phải ghép CẶP dòng — không cắt từng ô.** `can_cu_phap_ly`, `thanh_phan_ho_so` và `cach_thuc_thuc_hien` là bảng dùng **tab phân cách cột**. Cắt theo từng dòng thì mỗi ô thành một chunk riêng: `Luật Bảo hiểm xã hội` một chunk và `58/2014/QH13` một chunk — dòng thứ hai **vô nghĩa khi đứng một mình**. Đo trên dữ liệu thật: `LEGAL_BASIS` có **3.171/10.192 dòng ngắn hơn 40 ký tự** (31%), `REQUIRED_DOCUMENTS` có **4.558**. Vì vậy mỗi **hàng** được làm phẳng thành một dòng bằng cách nối các ô với ` · `, bỏ tab phân cách (tab chỉ có nghĩa khi còn cấu trúc bảng). Dòng tiêu đề cột (`Tên giấy tờ · Mẫu đơn, tờ khai · Số lượng`) bị bỏ vì lặp lại nhiều lần và không trả lời câu hỏi nào.
     * **Trần phải tính CẢ header.** `text = header + "\n" + thân`, mà header 200–300 ký tự. Áp trần chỉ cho thân là **bug thật đã gặp**: chunk `PROCESSING_TIME` của `1.014257` dài **67.651 ký tự** — gấp 15 lần trần, reranker sẽ trả HTTP 400. Hàm `ngan_sach_than()` trừ header trước khi giao ngân sách cho phần cắt.
     * **`GENERAL_INFO` cũng phải tôn trọng trần.** 2/1909 thủ tục (`1.115362` tên ~4.700 ký tự, `1.115369` ~5.900 ký tự) có tên dài tới mức riêng phần định danh đã vượt trần.
     * **`RESULT` ngắn phải có tiền tố ngữ cảnh.** 1.666/1.903 `RESULT` ngắn hơn 200 ký tự, nhiều cái chỉ 14 ký tự (`"Giấy khai sinh"`). Vector của một cụm 14 ký tự trơ trọi rất yếu, nên chunk được chèn câu dẫn — **cố định của ta, không bịa nội dung**: `Kết quả người dân nhận được khi hoàn thành thủ tục: <nguyên văn>.`
  2. Gán `chunk_id` ổn định theo định dạng **`{procedure_code}:{section_type}:{chunk_order}`** — ổn định nghĩa là cùng nội dung thì cùng ID giữa các lần chạy.
  3. Kế thừa **100% metadata cấp thủ tục** xuống mọi chunk: `domain_group`, `canonical_field`, `source_field`, `cap_thuc_hien`, `co_quan_thuc_hien`, `detail_url`. Không phân loại lại từng chunk bằng LLM.
  4. **Chunk `FEE` render từ `phi.muc_chi_tiet`, chunk `PROCESSING_TIME` render từ `thoi_han.muc_chi_tiet`** — KHÔNG đọc `so_tien` đơn lẻ, KHÔNG đọc `moc` phẳng. Hai trường đó là kết quả sửa ở Giai đoạn 3 để giữ **cặp (giá trị, điều kiện)**; render từ chúng mới trả lời được *"trường hợp của tôi đóng bao nhiêu / mất bao lâu?"*. Định dạng đơn vị tiếng Việt (`WORKING_DAY` → `Ngày làm việc`). Nếu bỏ bước này thì truy vấn `section_type = 'FEE'` sẽ **trả về rỗng** dù dữ liệu vẫn tồn tại.
  5. **Luật sentinel — bắt buộc, không được bỏ qua.** Với trường mang giá trị sentinel (§4.1d), **GIỮ trường trong chunk** nhưng **đổi cách diễn đạt** thành *"cổng chưa ghi nhận thông tin"*:
     * **KHÔNG bỏ trường** khỏi chunk. Người dùng hỏi *"thủ tục A có liên quan tới thủ tục nào không?"* — nếu bỏ trường thì LLM không có nguồn nào, và sẽ trả lời *"không có thủ tục liên quan"*, một **khẳng định sai** vì dữ liệu có ghi (chỉ là ghi "chưa có"). Bỏ dữ liệu khiến LLM không phân biệt được *chưa có dữ liệu* với *không có*.
     * **KHÔNG để nguyên** `"Không có thông tin"`. Câu đó LLM dễ đọc thành *"không có"* — khác nghĩa. Cổng ghi *chưa ghi nhận*, không khẳng định *không tồn tại*.
     * Áp cho `thu_tuc_lien_quan` (1.906), `yeu_cau_dieu_kien` (250), `dia_chi_tiep_nhan` (3), `ket_qua_xu_ly` (4).
     * **Nhận diện sentinel theo DẠNG ĐÃ CHUẨN HÓA, không liệt kê nguyên văn.** Cổng ghi cùng một ý với **9 biến thể** khác nhau về dấu câu, hoa/thường và khoảng trắng: `Không có thông tin` · `Không quy định` · `Không quy định.` · `Không có` · `không có` · `không quy định` · `Không.` · `không có.` · `Không có.`. Liệt kê tay từng biến thể là cách làm sai — cổng chỉ cần thêm một dấu chấm nữa là sót. Hàm `is_sentinel` chuẩn hóa giá trị về không dấu, không dấu câu rồi tra trong tập đóng `EMPTY_SENTINELS` = `{khong, khong co, khong co thong tin, khong quy dinh}`. **Giá trị gốc không bị đổi** — chỉ dùng để nhận diện.
     * **Ba cụm KHÔNG được coi là sentinel** dù bắt đầu bằng "không có", vì chúng là **khẳng định có nghĩa nghiệp vụ**: `Không có yêu cầu, điều kiện` (thủ tục không đòi điều kiện), `Không có kết quả`, `Không có văn bản trả lời`. Gộp chúng vào sentinel thì chunk nói *"cổng chưa ghi nhận"* trong khi cổng đã KHẲNG ĐỊNH — **sai hướng**. Vì vậy dùng tập ĐÓNG, **không dùng tiền tố** `"không có"`.
     * **Riêng `FEE` và `PROCESSING_TIME` thì KHÔNG sinh chunk** khi `phi.loai == 'CHUA_XAC_DINH'` / `thoi_han.loai == 'CHUA_XAC_DINH'` — hai trường này đã có cờ cấu trúc riêng, không cần câu văn bản.
  6. **Luật tab:** không được gộp cụm `\t` khi render bảng. `\t\t` là ô rỗng — gộp lại sẽ dịch cột.
  7. **Header mỗi chunk gồm 4 dòng** và `ten_thu_tuc` lấy **y nguyên**, không viết hoa lại, không cắt ngắn:
     ```text
     Tên thủ tục: <ten_thu_tuc nguyên văn>
     Lĩnh vực: <linh_vuc> · Cấp thực hiện: <cap_thuc_hien>
     Nguồn: <detail_url>
     ---
     ```
     Chunk tiếp theo của cùng section dùng header gọn (chỉ `procedure_code` + tên) để tiết kiệm ký tự, vì chunk đầu đã có `detail_url`.
  8. Xuất `data/processed/chunks.jsonl`. Script: `scripts/build_chunks.py` (tách khỏi `build_manifest.py` để chạy lại chunking không phải chạy lại chuẩn hóa).
  9. **Chuẩn hóa phải đi cả vào `muc_chi_tiet`.** `normalizer.py` phải chuẩn hóa `phi.muc_chi_tiet[].dieu_kien`, `thoi_han.muc_chi_tiet[].dieu_kien` và `hinh_thuc[]` — **không chỉ** `mo_ta_goc`. Bug thật đã gặp: 37/49 file test giữ **Unicode dạng NFD** (`'ơ'` + dấu huyền = 2 ký tự) trong `dieu_kien` vì normalizer bỏ qua `muc_chi_tiet`; chuỗi NFD **không bằng** NFC khi so sánh nên tìm kiếm sẽ trượt. Cùng lúc đó, **không** được đụng vào `so_tien`, `gia_tri`, `don_vi`, `moc`, `nhieu_don_vi` — chúng là số và mã.
* **Lệnh chạy:**
  ```powershell
  # Thử nhanh trên bộ test (49 bản ghi)
  uv run python scripts/build_chunks.py --test --out data/processed/chunks_test.jsonl --force

  # Kiểm định trên toàn bộ, KHÔNG ghi file
  uv run python scripts/build_chunks.py --dry-run

  # Sinh thật + báo cáo
  uv run python scripts/build_chunks.py --report docs/phase5_report.md
  ```
  Script **từ chối ghi** nếu có chunk vượt trần hoặc `chunk_id` trùng, và **từ chối ghi đè** file đích đã tồn tại (trừ khi thêm `--force`).
* **Tiêu chuẩn nghiệm thu:**
  * Mỗi thủ tục sinh ra **tối thiểu 4 section** chính; mọi chunk truy ngược được về thủ tục, section và `detail_url`.
  * Tồn tại chunk `section_type = 'FEE'` cho mọi thủ tục có `phi.loai != 'CHUA_XAC_DINH'`; tương tự với `PROCESSING_TIME` khi `thoi_han.loai != 'CHUA_XAC_DINH'`.
  * **Chunk `FEE` chứa ĐỦ mọi mức trong `phi.muc_chi_tiet`, mỗi mức kèm điều kiện.** Thủ tục `1.004376` phải có đủ **8 mức**, `1.014257` đủ **10 mức**. Chunk `PROCESSING_TIME` của `3.000242` phải có đủ **6 mốc** với hình thức nộp.
  * **Không chunk nào vượt 4.500 ký tự** (trần reranker).
  * Cùng một `chunk_id` dùng thống nhất cho cả Elasticsearch và Qdrant.
  * **Mọi thủ tục đều có chunk chứa `thu_tuc_lien_quan`** (kể cả khi giá trị là sentinel) — không được thiếu, để câu hỏi về quan hệ luôn có nguồn.
  * `chunk_id` **không trùng** trong toàn tập (mã thủ tục đã kiểm: **0 mã trùng / 1.909**).
* **Kết quả đo được (1.909 bản ghi, phiên bản chunker `5.0`):**

  | Chỉ số | Giá trị |
  |---|---:|
  | Chunk sinh ra | **16.735** |
  | Chunk vượt 4.500 ký tự | **0** |
  | `chunk_id` trùng | **0** |
  | Thủ tục dưới 4 section | **0** |
  | Độ dài: min / trung vị / max | 153 / 724 / 4.500 |

  Số chunk theo section: `REQUIRED_DOCUMENTS` 2.197 · `STEPS` 2.150 · `SUBMISSION_METHOD` 2.060 · `GENERAL_INFO` 1.911 · `RESULT` 1.903 · `LEGAL_BASIS` 1.884 · `PROCESSING_TIME` 1.842 · `FEE` 1.657 · `REQUIREMENTS` 1.131.

---

### GIAI ĐOẠN 6: KHỞI TẠO CƠ SỞ DỮ LIỆU GỐC POSTGRESQL (SSOT) (PHASE 6)
* **Mục tiêu:** Thiết lập cơ sở dữ liệu quan hệ PostgreSQL đóng vai trò Nguồn chân lý duy nhất (SSOT), bảo đảm tính toàn vẹn dữ liệu ở cấp độ cao nhất.
* **Các công việc thực hiện:**
  1. Khởi chạy PostgreSQL thông qua Docker Compose.
  2. Thực thi script DDL tạo bảng `procedures`, `procedure_agencies` và `procedure_sections` kèm các ràng buộc Khóa chính, Khóa ngoại và GIN Index.
  3. Viết script `data_pipeline/indexing/postgres.py`:
     * Đọc `data/json/*.json` (JSON chuẩn hóa) và nạp thuộc tính hành chính vào bảng `procedures` (chuyển đổi chuỗi cấp hành chính thành mảng `TEXT[]`, ví dụ `"Cấp bộ, Cấp tỉnh"` → `ARRAY['Cấp bộ','Cấp tỉnh']`).
     * Phân tách cơ quan thực hiện, thẩm quyền, phối hợp, ủy quyền vào bảng `procedure_agencies` với cờ `is_inferred`.
     * Đọc `data/processed/chunks.jsonl` để nạp nội dung chi tiết vào bảng `procedure_sections`.
  4. Thiết lập trigger tự động cập nhật trường `updated_at`.
  5. Viết `backend/app/services/procedure_service.py` tra cứu fact theo mã thủ tục, không dùng LLM.
* **Tiêu chuẩn nghiệm thu:** Lệnh kiểm tra `SELECT COUNT(*) FROM procedures;` phản ánh đúng số lượng bản ghi nạp vào; truy vấn tìm kiếm theo mảng `administrative_levels @> ARRAY['Cấp xã']` đạt thời gian dưới 5ms.

---

### GIAI ĐOẠN 7: DỰNG ĐỒ THỊ TRI THỨC TRÊN NEO4J (PHASE 7)
* **Mục tiêu:** Chuyển hóa các quan hệ quản lý hành chính phức tạp (Cơ quan ban hành, Thẩm quyền quyết định, Đơn vị thụ lý, Cơ quan phối hợp, Cấp hành chính) thành một Knowledge Graph liên kết đa chiều.
* **Các công việc thực hiện:**
  1. Khởi chạy instance Neo4j Community Edition (qua Docker).
  2. Thiết lập ràng buộc duy nhất (Unique Constraints) trên các đỉnh: `(:ThuTuc {ma_thu_tuc})`, `(:CoQuan {name})`, `(:DomainGroup {name})`, `(:LinhVuc {name})`, `(:CapHanhChinh {name})`, `(:DoiTuong {name})`, `(:KetQua {name})`, `(:VanBanPhapLy {ma_van_ban})`, `(:TrangThai {name})`.
  3. Viết script `data_pipeline/indexing/neo4j.py` đọc dữ liệu từ PostgreSQL. **Đặt tên cạnh TRÙNG với tên trường JSON** để truy vết được cạnh nào sinh từ trường nào — xem §4.3b cho danh sách đầy đủ kèm độ phủ.
     * Tạo 9 nhãn đỉnh theo §4.3a.
     * Tạo **12 cạnh**: `[:BAN_HANH_BOI]`, `[:CO_THAM_QUYEN]`, `[:PHOI_HOP]`, `[:DUOC_UY_QUYEN]`, `[:DOMAIN_GROUP]`, `[:LINH_VUC]`, `[:CAP_THUC_HIEN]`, `[:TRANG_THAI]`, `[:DOI_TUONG_THUC_HIEN]`, `[:KET_QUA_XU_LY]`, `[:CAN_CU_PHAP_LY]`, `[:THU_TUC_LIEN_QUAN]`.
     * **Ưu tiên cạnh `[:CAN_CU_PHAP_LY]`** (98,7% độ phủ, hơn 5.000 cạnh) — đây là **cạnh trục** nối các thủ tục cùng viện dẫn một văn bản pháp lý. **Không** lấy `[:THU_TUC_LIEN_QUAN]` làm trục: nó chỉ có **3/1.955 bản ghi**, cho khoảng 8 cạnh.
     * `[:THU_TUC_LIEN_QUAN]` là cạnh phụ. Nguồn chỉ có **tên** thủ tục, không có mã, nên phải **khớp theo tên** và đánh cờ `is_inferred: true`. Quan hệ này nghĩa là *thành phần của cùng một quy trình liên thông*, **không phải** thủ tục tiên quyết — xem §4.1c.
     * Tách `co_quan_thuc_hien` theo `"; "` trước khi nạp (xem §4.3e).
     * Thực hiện quy tắc bù khuyết thẩm quyền, đánh cờ `is_inferred: true` trên cạnh `[:CO_THAM_QUYEN]` cho các bản ghi bị khuyết (xem §4.3d).
* **Tiêu chuẩn nghiệm thu (đã hiệu chỉnh theo độ phủ thật):**
  * Tra cứu **cấp xã** qua `[:CAP_THUC_HIEN]` — độ phủ 99,8%, chạy tốt.
  * Tra cứu **thủ tục cùng khung pháp lý** qua `[:CAN_CU_PHAP_LY]` — độ phủ 98,7%, chạy tốt.
  * Tra cứu **cơ quan ban hành** qua `[:BAN_HANH_BOI]` — độ phủ 99,8%, chạy tốt.
  * **Không** đặt tiêu chuẩn "tra cứu thủ tục phối hợp liên ngành" lên `[:PHOI_HOP]` (2,1% = 42 cạnh) hay `[:DUOC_UY_QUYEN]` (0,6% = 12 cạnh) — hai cạnh này sẽ trả về gần như rỗng. Nêu rõ trong báo cáo đây là **giới hạn của nguồn dữ liệu**, không phải lỗi hệ thống.

---

### GIAI ĐOẠN 8: ĐÁNH CHỈ MỤC TÌM KIẾM TỪ KHÓA TRÊN ELASTICSEARCH (PHASE 8)
* **Mục tiêu:** Xây dựng bộ tìm kiếm từ khóa chính xác (Lexical BM25 Search) được tối ưu riêng cho đặc thù văn bản hành chính tiếng Việt.
* **Các công việc thực hiện:**
  1. Khởi chạy cụm Elasticsearch.
  2. Cấu hình Index `tthc_lexical` với bộ phân tích tiếng Việt (`vi_analyzer` hoặc bộ phân tích chuẩn hóa lowercase, asciifolding, n-gram).
  3. Định nghĩa mapping chi tiết:
     * `procedure_code`: kiểu `keyword` (tìm chính xác).
     * `procedure_name`: kiểu `text` (kèm sub-field `keyword`).
     * `requirements`, `content`: kiểu `text` (đánh chỉ mục toàn văn).
     * `domain_group`, `administrative_levels`: kiểu `keyword` (phục vụ lọc).
  4. Viết script `data_pipeline/indexing/elasticsearch.py` đồng bộ chunk từ `data/processed/chunks.jsonl` sang Elasticsearch. Bảo đảm trường `chunk_id` **trùng khớp tuyệt đối** với Qdrant.
* **Tiêu chuẩn nghiệm thu:** Thực hiện các truy vấn gõ tắt không dấu, tìm mã số quyết định hoặc cụm từ viết tắt hành chính đều trả về đúng thủ tục mong muốn với điểm BM25 cao nhất.

---

### GIAI ĐOẠN 9: ĐÁNH CHỈ MỤC TÌM KIẾM NGỮ NGHĨA TRÊN QDRANT (PHASE 9)
* **Mục tiêu:** Xây dựng chỉ mục tìm kiếm vector ngữ nghĩa (Dense Vector Search) để hiểu được các câu hỏi diễn đạt tự nhiên của người dân khi không dùng thuật ngữ chuyên môn.
* **Các công việc thực hiện:**
  1. Khởi chạy cụm cơ sở dữ liệu vector Qdrant.
  2. Tạo Collection `procedure_semantic` với khoảng cách Cosine, kích thước vector 1024 chiều (tương ứng mô hình `bge-m3`).
  3. Viết script `data_pipeline/indexing/qdrant.py`:
     * Ghép nối ngữ cảnh: `[Tên TTHC] + [Lĩnh vực] + [Tên Section] + [Nội dung chi tiết]`.
     * Tạo vector nhúng thông qua mô hình Embedding.
     * Nạp vector vào Qdrant kèm theo trường `payload` đầy đủ: `{procedure_code, domain_group, canonical_field, administrative_levels, section_type}`.
  4. Tạo Payload Index trên Qdrant cho trường `domain_group` và `administrative_levels` để hỗ trợ lọc trước khi tìm kiếm vector (Pre-filtering).
* **Tiêu chuẩn nghiệm thu:** Tìm kiếm câu hỏi ngôn ngữ đời thường (ví dụ: *"làm giấy tờ cho con mới sinh cần gì"*) tìm ra đúng thủ tục Đăng ký khai sinh trong top 3 kết quả.

---

### GIAI ĐOẠN 10: CACHE TTL TRONG TIẾN TRÌNH (PHASE 10)

> **TRẠNG THÁI 2026-10-22:** đã làm **cache TTL**, không làm semantic FAQ cache. Collection
> `faq_cache` trên Qdrant **không tồn tại**; Qdrant chỉ còn `semantic_search`.

* **Mục tiêu:** câu hỏi lặp lại trả về ngay, không tốn token và không chạy lại workflow.
* **Cách làm hiện tại** (`backend/app/api/chat.py`):
  1. Chuẩn hoá câu hỏi (lowercase, gộp khoảng trắng) làm khoá.
  2. `_lay_cache()` trả câu trả lời đã lưu nếu còn hạn; `_cat_cache()` ghi sau khi trả lời.
  3. TTL cấu hình bằng `CACHE_TTL_S`; cache nằm trong tiến trình, mất khi restart.
  4. Đường stream phát lại câu cache theo từng mẩu `delta`, kèm cờ `cached: true` để client và bộ
     đo phân biệt với câu mới.
* **Không dùng:** không nhúng câu hỏi để so cosine, không có ngưỡng 0.90, không có tập FAQ nạp
  sẵn.
* **Tiêu chuẩn nghiệm thu:** câu lặp lại phản hồi dưới 100 ms và không gọi mô hình.

### GIAI ĐOẠN 11: TÌM KIẾM LAI + RERANKER (PHASE 11)

> **TRẠNG THÁI 2026-10-22:** đã hoàn thành.

* **Mục tiêu:** kết hợp BM25 (khớp từ khoá) và vector (ngữ nghĩa) bằng RRF, rồi xếp hạng lại.
* **File:** `backend/app/rag/hybrid.py`, `backend/app/rag/reranker.py`, `backend/app/rag/embeddings.py`.
* **Cách làm:**
  1. Chạy song song Elasticsearch (BM25) và Qdrant (cosine), lọc theo mã thủ tục nếu đã xác thực.
  2. Hợp nhất theo `chunk_id` bằng RRF:

$$\text{RRF\_Score}(d) = \frac{1}{60 + \text{Rank}_{BM25}(d)} + \frac{1}{60 + \text{Rank}_{Vector}(d)}$$

  3. Rerank bằng `qwen3-rerank`; giữ `rerank_used` / `rerank_error` để UI và bộ đo biết câu trả
     lời có thực sự qua rerank hay không.
  4. Cổng từ chối dùng điểm rerank cao nhất trong vài tài liệu đầu; reranker lỗi thì **fail-open**
     (đã ghi nhận là trade-off, xem §0.5.5).
* **Tiêu chuẩn nghiệm thu:** Hit Rate@3 ≥ 95% trên bộ đánh giá; mọi câu trả lời có cờ rerank rõ
  ràng.

### GIAI ĐOẠN 12: ĐỘNG CƠ TRUY VẤN ĐỒ THỊ (PHASE 12)

> **TRẠNG THÁI 2026-10-22:** đã hoàn thành.

* **Mục tiêu:** trả lời câu hỏi về quan hệ mà tìm kiếm văn bản không làm được: cơ quan ban
  hành/thực hiện/phối hợp/ủy quyền, cấp, lĩnh vực, nhóm, đối tượng, văn bản căn cứ.
* **File:** `backend/app/rag/graph_query.py`, `backend/app/rag/graph_shapes.py`.
* **Cách làm:**
  1. **Cypher Template cố định** theo `Shape`; LLM **không** viết Cypher.
  2. `AGENCY` trả 4 vai trò (`BAN_HANH_BOI`, `CO_THAM_QUYEN`, `PHOI_HOP`, `DUOC_UY_QUYEN`) kèm cột
     `vai_tro`; `CLASSIFY` trả `CAP_THUC_HIEN`, `LINH_VUC`, `DOMAIN_GROUP`, `TRANG_THAI`;
     `AUDIENCE`, `LEGAL_BASIS_OF_PROCEDURE` trả quan hệ trực tiếp.
  3. Intent ngược `PROCEDURES_BY_AGENCY/LEVEL/FIELD/GROUP` cho câu liệt kê/đếm theo thực thể.
  4. Khi planner yêu cầu, Graph chỉ chạy đúng `intent` trong allowlist và lọc dòng theo
     `expected_types` (ví dụ `implementing_agency` chỉ giữ `CO_THAM_QUYEN`) — không rơi về
     `classify(question)` theo từ khoá.
  5. Lỗi Neo4j trả `failed=True`, executor ghi `failed` chứ không phải `empty`.
* **Tiêu chuẩn nghiệm thu:** câu quan hệ trả đúng loại, dưới 50 ms, 0 token.

### GIAI ĐOẠN 13: HIỂU CÂU HỎI & ĐIỀU PHỐI TẤT ĐỊNH (PHASE 13)

> **TRẠNG THÁI 2026-10-22:** đã hiện thực, **chưa đạt** chất lượng mong muốn. Kiến trúc chi tiết
> ở §0.5; số đo nhóm A ở §0.5.4.

* **Mục tiêu:** thay router "đoán một nhánh" bằng chuỗi **hiểu → định vị → lập kế hoạch → thực
  thi**; mỗi bước là mã nguồn hoặc LLM có schema, không có nhánh nào tự quyết định thay planner.
* **Đã làm:**
  1. `question_frame.py` + `question_parser.py`: LLM trả `QuestionFrame` v1.0 (scope, subject
     mentions, requests, constraints, ambiguity), validate JSON, cache, timeout.
  2. `grounding.py`: xác định từng subject mention (`resolved/ambiguous/not_found/context_required`).
  3. `planner.py`: capability matrix đóng; task có `tool`, `intent`, `expected_types`,
     `constraints`; ngoài ma trận → `unsupported`.
  4. `executor.py`: chạy song song, timeout, coverage từng request, fallback tối đa một lần,
     single-flight embedding.
  5. `graph.py`: node `THUC_THI`; mọi plan do parser sinh (kể cả rỗng/unsupported) đi qua executor.
  6. `run.py`: trace `question_frame/groundings/plan/coverage/verification`.
* **Chưa làm / đang sai:**
  * Resolver chưa kiểm tra từ phân biệt của tên thủ tục → câu A2 chọn sai thủ tục.
  * Mention chung khớp nhiều biến thể → clarify oan (A1, A5, A6, A8, A9, A10).
  * Parser gán sai loại mention (A8) và coi cụm hành vi là tên thủ tục (A7).
  * Chưa có cơ chế trả lời cho nhóm biến thể cùng câu trả lời.
* **Tiêu chuẩn nghiệm thu (cập nhật):** đo trên bộ 60 câu, không dùng "routing accuracy 98%" cũ.
  Mục tiêu trước mắt: **giảm false clarify**, không tăng câu trả lời sai; mọi câu trả lời phải
  truy được về evidence.

### GIAI ĐOẠN 14: TỔNG HỢP CÂU TRẢ LỜI, TRÍCH DẪN & HÀNG RÀO AN TOÀN (PHASE 14)

> **TRẠNG THÁI 2026-10-22:** đã làm phần lớn, **khác cấu trúc file** ghi trong kế hoạch cũ.
> `rag/generation.py` và `rag/prompts.py` chỉ là placeholder, **không được dùng**. Toàn bộ logic
> nằm ở `backend/app/workflow/answer.py` và `node_sinh` trong `graph.py`.

* **Mục tiêu:** câu trả lời tiếng Việt, đúng thứ tự ý, chỉ dùng bằng chứng, có nguồn, không bịa.
* **Đã làm:**
  1. **Answer contract** (`answer.py`):
     * khối `CÁC Ý CẦN TRẢ LỜI` theo đúng thứ tự, kèm trạng thái từng ý;
     * context nhóm theo ý (`### Ý n — <khía cạnh>`), chọn evidence công bằng theo request;
     * luật: ý `covered` không được nói "chưa ghi nhận"; ý `failed` nói nguồn lỗi, không nói thiếu
       dữ liệu; ý `unsupported` nói chưa hỗ trợ; ý `ambiguous` phải hỏi lại.
  2. **Kiểm chứng hậu sinh** (`verify_contract()`): bắt `empty_answer`,
     `denies_available_evidence`, `omits_missing_data` bằng luật tất định (không gọi mô hình).
  3. **Retry một lần** với chỉ dẫn sửa; nếu vẫn vi phạm → **chặn** câu của mô hình và dựng câu
     trả lời tất định từ evidence (`build_fallback_answer()`), hoặc trả `answer_error` nếu không
     có evidence.
  4. **Trích dẫn:** `build_citations()` dùng cùng bộ chọn với context; mỗi nguồn có `detail_url`;
     không đánh số `[n]` trong câu chữ.
* **Chính sách nội dung vẫn giữ:**
  * Phí: 5 loại ở §1.2b; không suy `fees: []` thành "miễn phí"; `THEO_VAN_BAN` thì nêu số hiệu,
    không đoán số tiền.
  * Thời hạn: nhiều mốc thì liệt kê đủ, không gộp.
  * **"Chưa ghi nhận" ≠ "không có"**: sentinel nghĩa là cổng chưa đăng, không phải pháp luật
    không quy định. Đặc biệt với `yeu_cau_dieu_kien` và `thu_tuc_lien_quan`.
* **Giới hạn đã biết:** đường stream không thể rút chữ đã gửi; kiểm chứng chỉ ghi log/cache, không
  retry. Muốn chặn tuyệt đối phải buffer (đánh đổi streaming).
* **Tiêu chuẩn nghiệm thu:** 100% câu trả lời có nguồn hợp lệ; không có câu `answered` nào chứa
  khẳng định vượt quá evidence; Faithfulness ≥ 0.98 (đo ở Giai đoạn 16).

### GIAI ĐOẠN 15: ĐÓNG GÓI API VÀ ORCHESTRATION DOCKER COMPOSE (PHASE 15)

> **TRẠNG THÁI 2026-10-22:** API đã có (`/chat`, `/chat/stream`, `/api/admin/*`, `/health`). `compose.yaml` hiện chỉ có **Elasticsearch + Qdrant**; PostgreSQL/Neo4j đang dùng ngoài compose. Chưa đủ 6 service như mô tả dưới đây.
* **Mục tiêu:** Đóng gói toàn bộ hệ sinh thái dịch vụ thành một khối thống nhất, dễ dàng triển khai, demo và bảo trì trên bất kỳ máy chủ nào chỉ với một câu lệnh.
* **Các công việc thực hiện:**
  1. Xây dựng ứng dụng FastAPI trong `backend/app/api/` với các endpoint chuẩn:
     * `POST /chat`: Tiếp nhận câu hỏi và trả về câu trả lời kèm siêu dữ liệu trích dẫn (Metadata Citations).
     * `GET /procedures/{code}`: Tra cứu thông tin chi tiết một thủ tục trực tiếp từ PostgreSQL.
     * `GET /search`: Endpoint debug retrieval (lexical / semantic / hybrid).
     * `GET /api/admin/*`: Cung cấp số liệu cho Admin UI, đọc từ `procedure_manifest.csv` và `validation_report.csv`.
       **Lưu ý:** tiền tố là `/api/admin` chứ **không phải** `/admin`, vì `/admin` đã là route giao diện phía frontend — dùng chung sẽ khiến proxy của Vite nuốt luôn trang admin.
     * `GET /health`: Kiểm tra tình trạng kết nối tới các cơ sở dữ liệu.
  2. Viết file `Dockerfile` đa tầng (Multi-stage build) để tối ưu kích thước image backend.
  3. Hoàn thiện file `compose.yaml` điều phối toàn bộ cụm dịch vụ:

     * Service `postgres` (Cổng 5432)
     * Service `neo4j` (Cổng 7474, 7687)
     * Service `elasticsearch` (Cổng 9200)
     * Service `qdrant` (Cổng 6333)
     * Service `backend` (Cổng 8000)
     * Service `frontend` (Cổng 5173 khi dev, Nginx khi production)
  4. Cấu hình giới hạn bộ nhớ (Memory Limits) cho từng container để đảm bảo hệ thống vận hành ổn định trên VPS 16 – 32GB RAM.
  5. Thêm healthcheck cho service `backend` gọi endpoint `/health`, để Docker biết container còn sống.
* **Tiêu chuẩn nghiệm thu:** Chạy lệnh `docker compose up -d`, toàn bộ dịch vụ khởi động thành công và vượt qua bài kiểm tra Healthcheck trong vòng 60 giây.

---

### GIAI ĐOẠN 16: ĐÁNH GIÁ ĐỘ ĐO RAG CHUYÊN SÂU & CHUẨN BỊ BẢO VỆ (PHASE 16)
* **Mục tiêu:** Thực hiện đánh giá định lượng hệ thống theo tiêu chuẩn học thuật quốc tế (khung đánh giá RAG Triad / Ragas) để đưa số liệu thuyết phục vào báo cáo tốt nghiệp.
* **Các công việc thực hiện:**
  1. Dùng bộ **60 câu hiện có** trong `docs/benchmark_60_cau.md` (đã có đáp án mong đợi và kết quả baseline), mở rộng dần lên 150 câu nếu còn thời gian. Bộ câu hỏi chia theo nhóm: nêu mã, nêu tên chính thức, mô tả trường hợp, nhiều ý, không dấu/viết tắt, ngoài phạm vi, cần tiền ngữ. **Không** dùng chính tập đã nạp cache để đánh giá.
  2. Đo lường các chỉ số cốt lõi:
     * **Faithfulness (Độ trung thực):** Đảm bảo câu trả lời không chứa thông tin nằm ngoài ngữ cảnh (Mục tiêu ≥ 0.98).
     * **Answer Relevance (Độ liên quan của câu trả lời):** Đánh giá mức độ trả lời đúng trọng tâm câu hỏi của dân (Mục tiêu ≥ 0.95).
     * **Context Precision & Recall:** Đánh giá chất lượng của bộ tìm kiếm lai Hybrid Search (Mục tiêu ≥ 0.90).
     * **Abstention Accuracy:** Tỷ lệ từ chối đúng khi thiếu bằng chứng — đo riêng trên nhóm câu hỏi không có đáp án.
     * **End-to-End Latency:** Đo lường thời gian phản hồi trung bình (Cache hit < 100ms; Hybrid search < 1.5s).
  3. **Báo cáo riêng độ phủ dữ liệu lệ phí** theo phân loại 5 loại ở mục 1.2b, tính trên toàn bộ 1.955 thủ tục (không phải mẫu nhỏ). Đây là số liệu quan trọng để biện luận rằng hệ thống từ chối trả lời là do **giới hạn nguồn dữ liệu**, không phải do yếu kém của hệ thống.
  4. Chụp ảnh các đồ thị, sơ đồ kiến trúc, biểu đồ thời gian phản hồi để đưa vào Chương 4 (Thực nghiệm & Đánh giá) của quyển báo cáo.
* **Tiêu chuẩn nghiệm thu:** Hoàn thành bảng thống kê số liệu thực nghiệm đầy đủ, tự tin trình diễn demo trực tiếp trước Hội đồng chấm thi.

---

## 7. KHUNG BIỆN LUẬN & TRẢ LỜI PHẢN BIỆN TRƯỚC HỘI ĐỒNG

Khi bảo vệ đồ án, các thầy cô trong Hội đồng thường tập trung xoáy sâu vào **tính hợp lý của các quyết định kỹ thuật** và **tính khả thi của hệ thống**. Dưới đây là 5 câu hỏi trọng điểm và câu trả lời mẫu chuẩn mực:

#### Câu hỏi 1: Tại sao không dùng 1 CSDL duy nhất (như Postgres pgvector) mà phải dùng tới 4 hệ thống (Postgres, Elastic, Qdrant, Neo4j) cho phức tạp?
* **Lập luận trả lời:**
  > *"Hệ thống áp dụng triết lý thiết kế **Polyglot Persistence** (sử dụng đúng công cụ cho đúng bản chất dữ liệu) để tối ưu hóa hiệu năng và độ chính xác:
  > - **PostgreSQL** đảm bảo tính toàn vẹn dữ liệu chuẩn hóa cấp chính quyền và là Nguồn chân lý duy nhất (SSOT).
  > - **Elasticsearch** giải quyết bài toán tìm kiếm từ khóa chính xác tuyệt đối (Mã TTHC, số hiệu quyết định, tên viết tắt cơ quan) thông qua thuật toán BM25 và bộ phân tích tiếng Việt.
  > - **Qdrant** chuyên biệt hóa cho tìm kiếm vector ngữ nghĩa với tốc độ cao và hỗ trợ lọc dữ liệu theo Payload rất mạnh.
  > - **Neo4j** biểu diễn các mối liên kết đa chiều giữa các cơ quan hành chính liên thông, cho phép tra cứu cây thẩm quyền chỉ bằng 1 câu lệnh Cypher thay vì phải JOIN 4-5 bảng SQL phức tạp.
  > Sự phân tách này giúp mỗi thành phần hoạt động đúng sở trường, giảm tải CPU và tăng tốc độ phản hồi tổng thể dưới 1.5 giây."*

#### Câu hỏi 2: Tại sao không dùng router LLM chọn một trong ba nhánh như thiết kế ban đầu?

* **Lập luận trả lời:**
  > *"Vì router đoán nhánh chỉ đúng khi câu hỏi chỉ có một ý. Với câu nhiều ý — ví dụ 'cần hồ sơ gì,
  > bao lâu và đơn vị nào xử lý' — router buộc phải chọn một nhánh, hai ý còn lại bị bỏ. Ngoài ra,
  > router không có chỗ nào tính được **ý nào đã trả lời, ý nào chưa**, nên không thể trả lời một
  > phần và nói rõ phần thiếu.
  >
  > Kiến trúc hiện tại tách câu hỏi thành `QuestionFrame` (từng ý, từng subject), rồi planner chọn
  > công cụ cho **từng ý** và executor chạy song song, tính coverage. Router vẫn còn, nhưng chỉ là
  > **adapter** từ frame sang quyết định, không tự đoán nội dung.*

#### Câu hỏi 3: Làm thế nào hệ thống đảm bảo Chatbot không bịa đặt thông tin (Hallucination) khi hướng dẫn thủ tục?
* **Lập luận trả lời:**
  > *"Hệ thống kiểm soát ảo giác qua Mô hình Hai Tầng Chân lý (Two-Tier Truth Model):
  > 1. Đối với thông tin thuộc tính định danh (Mã, Cấp, Cơ quan, Quyết định), hệ thống triệt tiêu hoàn toàn ảo giác (Zero Hallucination) bằng cách truy vấn trực diện PostgreSQL, bỏ qua LLM sinh từ.
  > 2. Đối với nội dung chi tiết khai thác từ API cổng DVC (hồ sơ, trình tự, lệ phí), mô hình ngôn ngữ bị ràng buộc chặt chẽ trong Context, bắt buộc trích dẫn số quyết định công bố và đường dẫn nguồn `detail_url` trỏ về trang chi tiết thủ tục trên cổng.
  > 3. Hệ thống có **kiểm chứng hậu sinh tất định** (`verify_contract`): bắt câu trả lời rỗng, câu phủ nhận bằng chứng đang có, câu bỏ sót ý thiếu. Nếu sai, sinh lại một lần với chỉ dẫn; vẫn sai thì **chặn câu của mô hình** và dựng câu trả lời trực tiếp từ bằng chứng. Đường stream không thể rút chữ đã gửi — giới hạn này được ghi rõ, không che."*

#### Câu hỏi 4: Vì sao hiện tại chỉ có 49 thủ tục mà không phải 1.955?

* **Lập luận trả lời:**
  > *"49 thủ tục là **bộ đang nạp và đo** để phát triển, kiểm thử và làm luận văn; danh mục mục
  > tiêu vẫn là 1.955 TTHC theo file danh mục. Việc mở rộng là thay dữ liệu đầu vào, không phải
  > viết lại kiến trúc: pipeline crawl → chuẩn hoá → chunk → nạp PostgreSQL/Neo4j/Elasticsearch/
  > Qdrant đã chạy đúng trên 49 thủ tục.
  >
  > Điều quan trọng là **không trộn quy mô khi báo cáo**: mọi ngưỡng, số đo, tỷ lệ phải ghi rõ đo
  > trên 49 hay 1.955. Khi mở rộng, các ngưỡng phải đo lại vì phân bố dữ liệu đổi.*

#### Câu hỏi 5: Vì sao không dùng Semantic FAQ Cache như thiết kế ban đầu?

* **Lập luận trả lời:**
  > *"Semantic FAQ cache yêu cầu một tập câu hỏi–đáp án đã thẩm định và một collection vector
  > riêng. Dự án **không triển khai** phần này: Qdrant hiện chỉ có `semantic_search` cho nội dung
  > thủ tục. Thay vào đó là **cache TTL trong tiến trình** theo khoá câu hỏi đã chuẩn hoá — đơn
  > giản, không cần dữ liệu thẩm định, và không tạo thêm một nguồn "chân lý" thứ hai.
  >
  > Hệ quả học thuật: không có số liệu "40% câu hỏi lặp lại" để trích dẫn; nếu cần, phải đo trên
  > log thật. Cache TTL chỉ tiết kiệm chi phí cho câu lặp lại, không được coi là cơ chế trả lời.*

#### Câu hỏi 6: Vì sao nhiều câu hỏi về lệ phí hệ thống không trả lời được con số cụ thể? Đây có phải là điểm yếu của hệ thống?
* **Lập luận trả lời:**
  > *"Đây là **giới hạn của nguồn dữ liệu**, không phải điểm yếu của hệ thống, và nhóm đã đo lường được giới hạn đó. Khảo sát trên dữ liệu Cổng Dịch vụ công Quốc gia cho thấy chỉ khoảng 10% thủ tục công bố mức phí cụ thể; khoảng 60% chỉ **viện dẫn sang văn bản pháp lý khác** (ví dụ 'Thực hiện theo quy định tại Thông tư số 10/2024/TT-BTC'); khoảng 30% hoàn toàn không có dữ liệu phí. Nhóm xử lý bằng **chính sách trả lời theo độ tin cậy dữ liệu**: phí có số tiền thì trả lời số tiền; phí viện dẫn thì trả lời đúng số hiệu văn bản kèm link tra cứu; phí không có dữ liệu thì **từ chối trả lời** và nói rõ chưa có thông tin. Điều nhóm **không làm** là suy diễn '0 đồng' thành 'miễn phí' — vì như vậy mới là bịa đặt và mới là điểm yếu thật sự. Hệ thống chọn trung thực với dữ liệu nguồn thay vì tạo cảm giác luôn biết câu trả lời."*

---

#### Câu hỏi 7: Dữ liệu thiếu cơ quan có thẩm quyền thì hệ thống xử lý thế nào?

* **Lập luận trả lời:**
  > *"Trong danh mục mục tiêu 1.955 TTHC, trường `co_quan_co_tham_quyen` trống ở **1.450 bản ghi
  > (74,2%)** — đây là đặc thù của nguồn, không phải lỗi crawl. Hệ thống bù có kiểm soát: gán thẩm
  > quyền theo cấp hành chính cao nhất thụ lý và đánh dấu `procedure_agencies.is_inferred = true`,
  > để truy vấn không bị đứt nhưng vẫn phân biệt được **dữ liệu công bố** với **dữ liệu suy luận**.
  > Bộ 49 thủ tục đang dùng cũng theo cùng cơ chế; khi mở rộng lên 1.955, tỷ lệ này phải được đo lại
  > và báo cáo riêng."*

## PHỤ LỤC A — ÁNH XẠ 168 LĨNH VỰC NGUỒN VỀ 15 NHÓM LĨNH VỰC

Bảng dưới đây là kết quả phân nhóm trực tiếp từ cột `Lĩnh vực` của `danh_sach_tthc_bo_tinh_xa.json` (168 giá trị duy nhất, 1.955 TTHC). Cột `canonical_field` là lớp chuẩn hóa trung gian giữa `source_field` và `domain_group`, được nạp vào `config/field_mapping.csv`.

### A.1. Tổng hợp theo 15 Nhóm Lĩnh vực

| STT | Mã Thư mục (`Domain_Group`) | Tên Nhóm Lĩnh Vực Lớn | Số Lĩnh vực Nguồn | Số Canonical Fields | Số TTHC |
|:---:|---|---|:---:|:---:|:---:|
| 1 | `01. AN_NINH_TRAT_TU_CU_TRU` | An ninh trật tự, Cư trú & Xuất nhập cảnh | 2 | 2 | 2 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Công nghiệp, Năng lượng, Thương mại & Thị trường | 25 | 5 | 239 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Đăng ký Doanh nghiệp, Hợp tác xã & Đầu tư | 12 | 3 | 99 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục, Đào tạo & Giáo dục nghề nghiệp | 11 | 2 | 89 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Lao động, Việc làm, Người có công & An sinh | 15 | 4 | 124 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Cán bộ công chức, Tôn giáo, Dân tộc & Thi đua | 8 | 2 | 68 |
| 7 | `07. NONG_LAM_THUY_SAN` | Nông nghiệp, Lâm nghiệp, Thủy sản & PTNT | 11 | 4 | 198 |
| 8 | `08. QUOC_PHONG_NGOAI_VU` | Quốc phòng, Ngoại vụ & Sự cố đặc thù | 4 | 2 | 8 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Tài chính, Giá cả, Thuế, Phí & Công sản | 6 | 2 | 7 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Tài nguyên, Đất đai, Khoáng sản & Môi trường | 10 | 3 | 192 |
| 11 | `11. TU_PHAP_BO_TRO` | Tư pháp, Hộ tịch & Bổ trợ tư pháp | 19 | 6 | 200 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Khoa học, Công nghệ, Bưu chính & Viễn thông | 14 | 5 | 309 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Văn hóa, Di sản, Thể thao & Du lịch | 14 | 4 | 120 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Xây dựng, Nhà ở, Quy hoạch & GTVT | 11 | 3 | 185 |
| 15 | `15. Y_TE_SUC_KHOE` | Y tế, Khám chữa bệnh, Dược phẩm & Mỹ phẩm | 8 | 3 | 115 |
| **Tổng** | **15 nhóm** | **Bao phủ toàn bộ dữ liệu** | **169** | **49** | **1955** |

> **Số ở cột "Số TTHC" đếm trực tiếp từ dữ liệu đã crawl** (`data/json/`), khớp tổng **1.955**; cột "Số Lĩnh vực Nguồn" cộng lại đúng **169** cặp `(domain_group, source_field)` — gồm **168 lĩnh vực nguồn**, trong đó *An toàn thực phẩm* nằm ở 2 nhóm. Khớp hoàn toàn với `config/field_mapping.csv`.

### A.2. Danh sách 168 lĩnh vực nguồn đã phân nhóm

> Bảng này **sinh trực tiếp từ dữ liệu đã crawl** (`data/json/`) — mỗi dòng là một cặp
> `(domain_group, source_field)` có thật, kèm `canonical_field` và số TTHC đếm được.
> Khớp `config/field_mapping.csv`.
>
> **`domain_group` lấy từ tên sheet của file Excel** (do người dùng đặt theo đúng thứ tự
> của cổng), không phải phân loại tự đặt. Danh sách 15 nhóm, theo đúng thứ tự trong file:
> `01. AN_NINH_TRAT_TU_CU_TRU`, `02. CONG_THUONG_NANG_LUONG`, `03. DOANH_NGHIEP_DAU_TU`,
> `04. GIAO_DUC_DAO_TAO`, `05. LAO_DONG_AN_SINH_XA_HOI`, `06. NOI_VU_TON_GIAO_DAN_TOC`,
> `07. NONG_LAM_THUY_SAN`, `08. QUOC_PHONG_NGOAI_VU`, `09. TAI_CHINH_NGAN_SACH`,
> `10. TAI_NGUYEN_MOI_TRUONG`, `11. TU_PHAP_BO_TRO`, `12. THONG_TIN_KHOA_HOC_CONG_NGHE`,
> `13. VAN_HOA_THE_THAO_DU_LICH`, `14. XAY_DUNG_GIAO_THONG`, `15. Y_TE_SUC_KHOE`.
>
> **Tổng: 169 dòng, 168 lĩnh vực nguồn duy nhất, 49 canonical, 1.955 TTHC.**
> Lĩnh vực *An toàn thực phẩm* xuất hiện ở **hai nhóm** (02 và 15) nhưng với **các mã TTHC
> khác nhau** — đã kiểm chứng **không mã nào thuộc hai nhóm**.
>
> **3 cặp lĩnh vực gần trùng tên KHÔNG được gộp:** *An toàn vệ sinh lao động* / *An toàn, vệ
> sinh lao động*; *Thi đua – Khen thưởng* / *Thi đua, khen thưởng*; *Giáo dục nghề nghiệp* /
> *Giáo dục nghề nghiệp (G07-LĐ06)*. Đây là **giá trị do Cổng Dịch vụ công Quốc gia trả về**,
> không phải lỗi Excel — đổi tên sẽ làm crawler đối chiếu sai. Mỗi biến thể có dòng riêng,
> cùng `canonical_field` với biến thể kia.

| # | Mã Thư mục (`Domain_Group`) | Lĩnh vực Nguồn (`source_field`) | Canonical Field | Số TTHC |
|:---:|---|---|---|:---:|
| 1 | `01. AN_NINH_TRAT_TU_CU_TRU` | Quản lý xuất nhập cảnh | `XUAT_NHAP_CANH` | 1 |
| 1 | `01. AN_NINH_TRAT_TU_CU_TRU` | Đăng ký, quản lý cư trú | `CU_TRU` | 1 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | An toàn thực phẩm | `PHONG_BENH_AN_TOAN_THUC_PHAM` | 11 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | An toàn đập, hồ chứa thuỷ điện | `THUY_LOI_DE_DIEU_PCTT` | 9 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Công nghiệp hỗ trợ | `CONG_NGHIEP` | 3 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Công nghiệp tiêu dùng | `CONG_NGHIEP` | 8 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Cụm Công nghiệp | `CONG_NGHIEP` | 1 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Dầu khí | `NANG_LUONG` | 1 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Giám định thương mại | `THUONG_MAI_NOI_DIA_SO` | 2 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Hóa chất | `HOA_CHAT_VAT_LIEU_NO` | 31 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Kinh doanh khí | `NANG_LUONG` | 10 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Lưu thông hàng hóa trong nước | `THUONG_MAI_NOI_DIA_SO` | 9 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Nghề thủ công mỹ nghệ | `CONG_NGHIEP` | 1 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Quản lý bán hàng đa cấp | `THUONG_MAI_NOI_DIA_SO` | 6 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Sở giao dịch hàng hóa | `THUONG_MAI_NOI_DIA_SO` | 4 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Thương mại biên giới và miền núi | `THUONG_MAI_QUOC_TE` | 1 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Thương mại quốc tế | `THUONG_MAI_QUOC_TE` | 26 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Thương mại điện tử | `THUONG_MAI_NOI_DIA_SO` | 6 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Tài sản kết cấu hạ tầng chợ do Nhà nước đầu tư, quản lý | `TAI_CHINH_NGAN_SACH_CONG_SAN` | 3 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Vận chuyển hàng hóa nguy hiểm | `HOA_CHAT_VAT_LIEU_NO` | 6 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Vật liệu nổ công nghiệp, tiền chất thuốc nổ | `HOA_CHAT_VAT_LIEU_NO` | 14 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Xuất nhập khẩu | `THUONG_MAI_QUOC_TE` | 53 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Xúc tiến thương mại | `THUONG_MAI_NOI_DIA_SO` | 15 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | bảo vệ quyền lợi người tiêu dùng | `THUONG_MAI_NOI_DIA_SO` | 2 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Điện | `NANG_LUONG` | 9 |
| 2 | `02. CONG_THUONG_NANG_LUONG` | Điện lực | `NANG_LUONG` | 8 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Hỗ trợ doanh nghiệp nhỏ và vừa | `DOANH_NGHIEP` | 7 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Hỗ trợ tổ hợp tác, hợp tác xã, liên hiệp hợp tác xã | `HOP_TAC_XA_TO_HOP_TAC` | 1 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Quản lý chương trình mục tiêu quốc gia | `TAI_CHINH_NGAN_SACH_CONG_SAN` | 1 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Quản lý doanh nghiệp | `DOANH_NGHIEP` | 1 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Quản lý nhà nước về khu công nghiệp, khu kinh tế | `DAU_TU_KCN_KKT` | 3 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Thành lập và hoạt động của doanh nghiệp | `DOANH_NGHIEP` | 30 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Thành lập và hoạt động của tổ hợp tác không đăng ký | `HOP_TAC_XA_TO_HOP_TAC` | 2 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Thành lập và hoạt động của tổ hợp tác, hợp tác xã, liên hiệp hợp tác xã | `HOP_TAC_XA_TO_HOP_TAC` | 19 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Thành lập và hoạt động doanh nghiệp (hộ kinh doanh) | `DOANH_NGHIEP` | 7 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Thành lập và hoạt động doanh nghiệp xã hội | `DOANH_NGHIEP` | 2 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Đầu tư bằng vốn hỗ trợ phát triển chính thức (ODA) và viện trợ không hoàn lại không thuộc hỗ trợ phát triển chính thức | `DAU_TU_KCN_KKT` | 1 |
| 3 | `03. DOANH_NGHIEP_DAU_TU` | Đầu tư tại Việt nam | `DAU_TU_KCN_KKT` | 25 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Các cơ sở giáo dục khác | `GIAO_DUC_PHO_THONG` | 1 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục mầm non | `GIAO_DUC_PHO_THONG` | 9 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục nghề nghiệp | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | 8 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục nghề nghiệp (G07-LĐ06) | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | 5 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục thường xuyên | `GIAO_DUC_PHO_THONG` | 12 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục tiểu học | `GIAO_DUC_PHO_THONG` | 4 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục trung học | `GIAO_DUC_PHO_THONG` | 10 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục và Đào tạo thuộc hệ thống giáo dục quốc dân | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | 24 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Giáo dục, đào tạo với nước ngoài | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | 4 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Thi, tuyển sinh | `GIAO_DUC_PHO_THONG` | 8 |
| 4 | `04. GIAO_DUC_DAO_TAO` | Văn bằng, chứng chỉ | `GIAO_DUC_PHO_THONG` | 4 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | An toàn vệ sinh lao động | `AN_TOAN_VE_SINH_LAO_DONG` | 2 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | An toàn, vệ sinh lao động | `AN_TOAN_VE_SINH_LAO_DONG` | 4 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Bảo hiểm xã hội | `AN_SINH_XA_HOI` | 1 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Bảo trợ xã hội | `AN_SINH_XA_HOI` | 13 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Giảm nghèo | `AN_SINH_XA_HOI` | 7 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Kiểm định kỹ thuật an toàn lao động | `AN_TOAN_VE_SINH_LAO_DONG` | 2 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Lao động | `LAO_DONG_VIEC_LAM` | 3 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Lao động, tiền lương | `LAO_DONG_VIEC_LAM` | 4 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Lao động, tiền lương và bảo hiểm xã hội | `LAO_DONG_VIEC_LAM` | 1 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Người có công | `NGUOI_CO_CONG` | 52 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Phòng, chống tệ nạn xã hội | `AN_SINH_XA_HOI` | 6 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Quản lý lao động ngoài nước | `LAO_DONG_VIEC_LAM` | 5 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Thu BHXH, BHYT, BHTN, BH tai nạn lao động, BNN | `AN_SINH_XA_HOI` | 1 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Trẻ em | `AN_SINH_XA_HOI` | 7 |
| 5 | `05. LAO_DONG_AN_SINH_XA_HOI` | Việc làm | `LAO_DONG_VIEC_LAM` | 16 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Công chức, viên chức | `NOI_VU_THI_DUA` | 2 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Công tác dân tộc | `TON_GIAO_DAN_TOC_HOI_QUY` | 2 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Công tác thanh niên | `NOI_VU_THI_DUA` | 1 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Quản lý nhà nước về hội, quỹ | `TON_GIAO_DAN_TOC_HOI_QUY` | 28 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Tín ngưỡng, tôn giáo | `TON_GIAO_DAN_TOC_HOI_QUY` | 33 |
| 6 | `06. NOI_VU_TON_GIAO_DAN_TOC` | Văn thư và Lưu trữ nhà nước | `NOI_VU_THI_DUA` | 2 |
| 7 | `07. NONG_LAM_THUY_SAN` | Chăn nuôi | `CHAN_NUOI_THU_Y` | 21 |
| 7 | `07. NONG_LAM_THUY_SAN` | Kinh tế hợp tác và Phát triển nông thôn | `THUY_LOI_DE_DIEU_PCTT` | 7 |
| 7 | `07. NONG_LAM_THUY_SAN` | Kiểm lâm | `LAM_NGHIEP_KIEM_LAM` | 13 |
| 7 | `07. NONG_LAM_THUY_SAN` | Lâm nghiệp và Kiểm lâm | `LAM_NGHIEP_KIEM_LAM` | 27 |
| 7 | `07. NONG_LAM_THUY_SAN` | Quản lý chất lượng nông lâm sản và thủy sản | `LAM_NGHIEP_KIEM_LAM` | 12 |
| 7 | `07. NONG_LAM_THUY_SAN` | Quản lý Đê điều và Phòng, chống thiên tai | `THUY_LOI_DE_DIEU_PCTT` | 3 |
| 7 | `07. NONG_LAM_THUY_SAN` | Thú y | `CHAN_NUOI_THU_Y` | 25 |
| 7 | `07. NONG_LAM_THUY_SAN` | Thủy lợi | `THUY_LOI_DE_DIEU_PCTT` | 34 |
| 7 | `07. NONG_LAM_THUY_SAN` | Thủy sản | `THUY_SAN` | 30 |
| 7 | `07. NONG_LAM_THUY_SAN` | Trồng trọt | `TRONG_TROT_BVTV` | 9 |
| 7 | `07. NONG_LAM_THUY_SAN` | Trồng trọt và Bảo vệ thực vật | `TRONG_TROT_BVTV` | 17 |
| 8 | `08. QUOC_PHONG_NGOAI_VU` | Hội nghị, hội thảo quốc tế | `NGOAI_VU_HOI_NHAP` | 2 |
| 8 | `08. QUOC_PHONG_NGOAI_VU` | Hội nhập kinh tế quốc tế | `NGOAI_VU_HOI_NHAP` | 2 |
| 8 | `08. QUOC_PHONG_NGOAI_VU` | Quản lý vùng trời | `QUOC_PHONG_SU_CO_DAC_THU` | 1 |
| 8 | `08. QUOC_PHONG_NGOAI_VU` | Ứng phó sự cố tràn dầu BQP | `QUOC_PHONG_SU_CO_DAC_THU` | 3 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Hải quan | `THUE_PHI_HAI_QUAN` | 1 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Quản lý công sản | `TAI_CHINH_NGAN_SACH_CONG_SAN` | 1 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Quản lý giá | `TAI_CHINH_NGAN_SACH_CONG_SAN` | 1 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Quản lý thuế, phí, lệ phí và thu khác của ngân sách nhà nước | `THUE_PHI_HAI_QUAN` | 1 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Tài chính đất đai | `TAI_CHINH_NGAN_SACH_CONG_SAN` | 1 |
| 9 | `09. TAI_CHINH_NGAN_SACH` | Đăng ký hoạt động của Ngân hàng Chính sách xã hội | `TAI_CHINH_NGAN_SACH_CONG_SAN` | 2 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Biến đổi khí hậu | `MOI_TRUONG_KHI_HAU` | 7 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Biển và hải đảo | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | 14 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Bảo tồn thiên nhiên và Đa dạng sinh học | `MOI_TRUONG_KHI_HAU` | 9 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Khoáng sản | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | 4 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Khí tượng, thủy văn | `MOI_TRUONG_KHI_HAU` | 4 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Môi trường | `MOI_TRUONG_KHI_HAU` | 4 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Tài nguyên nước | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | 19 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Đo đạc, bản đồ và thông tin địa lý | `MOI_TRUONG_KHI_HAU` | 1 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Đất đai | `DAT_DAI` | 91 |
| 10 | `10. TAI_NGUYEN_MOI_TRUONG` | Địa chất và khoáng sản | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | 39 |
| 11 | `11. TU_PHAP_BO_TRO` | Bồi thường nhà nước | `THI_HANH_AN_BOI_THUONG` | 3 |
| 11 | `11. TU_PHAP_BO_TRO` | Chứng thực | `CHUNG_THUC_CONG_CHUNG` | 12 |
| 11 | `11. TU_PHAP_BO_TRO` | Công chứng | `CHUNG_THUC_CONG_CHUNG` | 28 |
| 11 | `11. TU_PHAP_BO_TRO` | Giám định tư pháp | `GIAM_DINH_BO_TRO_TU_PHAP` | 7 |
| 11 | `11. TU_PHAP_BO_TRO` | Hòa giải thương mại | `GIAM_DINH_BO_TRO_TU_PHAP` | 13 |
| 11 | `11. TU_PHAP_BO_TRO` | Hòa giải ở cơ sở | `GIAM_DINH_BO_TRO_TU_PHAP` | 5 |
| 11 | `11. TU_PHAP_BO_TRO` | Hỗ trợ pháp lý cho doanh nghiệp nhỏ và vừa | `TRO_GIUP_PHAP_LY` | 1 |
| 11 | `11. TU_PHAP_BO_TRO` | Hộ tịch | `HO_TICH_QUOC_TICH` | 41 |
| 11 | `11. TU_PHAP_BO_TRO` | Luật sư | `TRO_GIUP_PHAP_LY` | 20 |
| 11 | `11. TU_PHAP_BO_TRO` | Nuôi con nuôi | `HO_TICH_QUOC_TICH` | 9 |
| 11 | `11. TU_PHAP_BO_TRO` | Quản tài viên | `GIAM_DINH_BO_TRO_TU_PHAP` | 7 |
| 11 | `11. TU_PHAP_BO_TRO` | Quốc tịch | `HO_TICH_QUOC_TICH` | 5 |
| 11 | `11. TU_PHAP_BO_TRO` | Thi hành án dân sự | `THI_HANH_AN_BOI_THUONG` | 1 |
| 11 | `11. TU_PHAP_BO_TRO` | Thừa hành viên | `GIAM_DINH_BO_TRO_TU_PHAP` | 8 |
| 11 | `11. TU_PHAP_BO_TRO` | Trọng tài thương mại | `GIAM_DINH_BO_TRO_TU_PHAP` | 13 |
| 11 | `11. TU_PHAP_BO_TRO` | Trợ giúp pháp lý | `TRO_GIUP_PHAP_LY` | 12 |
| 11 | `11. TU_PHAP_BO_TRO` | Tư vấn pháp luật | `TRO_GIUP_PHAP_LY` | 6 |
| 11 | `11. TU_PHAP_BO_TRO` | Đăng ký biện pháp bảo đảm | `GIAM_DINH_BO_TRO_TU_PHAP` | 5 |
| 11 | `11. TU_PHAP_BO_TRO` | Đấu giá tài sản | `GIAM_DINH_BO_TRO_TU_PHAP` | 4 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | An toàn bức xạ và hạt nhân | `AN_TOAN_BUC_XA_HAT_NHAN` | 24 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Báo chí | `BAO_CHI_XUAT_BAN` | 11 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Bưu chính | `BUU_CHINH_VIEN_THONG` | 14 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Công nghiệp công nghệ số, công nghệ thông tin, điện tử | `BUU_CHINH_VIEN_THONG` | 11 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Hoạt động khoa học và công nghệ | `KHCN_QUAN_LY_KHCN` | 65 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Khoa học và Công nghệ | `KHCN_QUAN_LY_KHCN` | 2 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Phát thanh, truyền hình và thông tin điện tử | `BAO_CHI_XUAT_BAN` | 22 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Sở hữu trí tuệ | `SHTT_TIEU_CHUAN_DO_LUONG` | 17 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Thông tin đối ngoại | `NGOAI_VU_HOI_NHAP` | 1 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Tiêu chuẩn đo lường chất lượng | `SHTT_TIEU_CHUAN_DO_LUONG` | 32 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Tần số vô tuyến điện | `BUU_CHINH_VIEN_THONG` | 49 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Tổng hợp | `NOI_VU_THI_DUA` | 1 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Viễn thông và Internet | `BUU_CHINH_VIEN_THONG` | 48 |
| 12 | `12. THONG_TIN_KHOA_HOC_CONG_NGHE` | Xuất Bản, In và Phát hành | `BAO_CHI_XUAT_BAN` | 12 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Bản quyền tác giả | `SHTT_TIEU_CHUAN_DO_LUONG` | 4 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Di sản văn hóa | `DI_SAN_NGHE_THUAT_VAN_HOA` | 26 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Du lịch | `THE_THAO_DU_LICH_QUANG_CAO` | 22 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Gia đình | `GIA_DINH_DOI_SONG` | 5 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Hoạt động mua bán quốc tế chuyên ngành văn hóa | `GIA_DINH_DOI_SONG` | 2 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Hợp tác quốc tế | `NGOAI_VU_HOI_NHAP` | 3 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Mỹ thuật, nhiếp ảnh, triển lãm | `DI_SAN_NGHE_THUAT_VAN_HOA` | 11 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Nghệ thuật biểu diễn | `DI_SAN_NGHE_THUAT_VAN_HOA` | 4 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Quảng cáo | `THE_THAO_DU_LICH_QUANG_CAO` | 2 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Thi đua – Khen thưởng | `NOI_VU_THI_DUA` | 6 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Thể dục thể thao | `THE_THAO_DU_LICH_QUANG_CAO` | 23 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Văn hóa | `DI_SAN_NGHE_THUAT_VAN_HOA` | 6 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Văn học | `DI_SAN_NGHE_THUAT_VAN_HOA` | 2 |
| 13 | `13. VAN_HOA_THE_THAO_DU_LICH` | Điện ảnh | `DI_SAN_NGHE_THUAT_VAN_HOA` | 4 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Hoạt động xây dựng | `XAY_DUNG_NHA_O_BDS` | 19 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Hàng hải và đường thủy nội địa | `GIAO_THONG_VAN_TAI` | 53 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Hạ tầng kỹ thuật | `QUY_HOACH_HA_TANG` | 1 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Kinh doanh bất động sản | `XAY_DUNG_NHA_O_BDS` | 9 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Nhà ở và công sở | `XAY_DUNG_NHA_O_BDS` | 21 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Quy hoạch đô thị và nông thôn | `QUY_HOACH_HA_TANG` | 5 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Quản lý chất lượng công trình xây dựng | `XAY_DUNG_NHA_O_BDS` | 2 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Vật liệu xây dựng | `XAY_DUNG_NHA_O_BDS` | 2 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Đăng kiểm | `GIAO_THONG_VAN_TAI` | 6 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Đường bộ | `GIAO_THONG_VAN_TAI` | 55 |
| 14 | `14. XAY_DUNG_GIAO_THONG` | Đường sắt | `GIAO_THONG_VAN_TAI` | 12 |
| 15 | `15. Y_TE_SUC_KHOE` | An toàn thực phẩm | `PHONG_BENH_AN_TOAN_THUC_PHAM` | 12 |
| 15 | `15. Y_TE_SUC_KHOE` | Dược phẩm | `DUOC_MY_PHAM_TBYT` | 14 |
| 15 | `15. Y_TE_SUC_KHOE` | Giám định | `GIAM_DINH_BO_TRO_TU_PHAP` | 2 |
| 15 | `15. Y_TE_SUC_KHOE` | Khám bệnh, chữa bệnh | `KHAM_CHUA_BENH` | 23 |
| 15 | `15. Y_TE_SUC_KHOE` | Mỹ phẩm | `DUOC_MY_PHAM_TBYT` | 6 |
| 15 | `15. Y_TE_SUC_KHOE` | Phòng bệnh | `PHONG_BENH_AN_TOAN_THUC_PHAM` | 36 |
| 15 | `15. Y_TE_SUC_KHOE` | Thi đua, khen thưởng | `NOI_VU_THI_DUA` | 3 |
| 15 | `15. Y_TE_SUC_KHOE` | Thiết bị y tế | `DUOC_MY_PHAM_TBYT` | 6 |
| 15 | `15. Y_TE_SUC_KHOE` | Y Dược cổ truyền | `DUOC_MY_PHAM_TBYT` | 11 |
| 15 | `15. Y_TE_SUC_KHOE` | Đào tạo và Nghiên cứu khoa học | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | 2 |

### A.3. Những thay đổi đã áp dụng so với bản trước

**4 lần tách canonical** (nhóm quá rộng, trộn nhiều chủ đề không liên quan):

| Canonical cũ | Số TTHC | Tách thành | Số TTHC |
|---|---|---|---|
| `KHCN_SHTT_TIEU_CHUAN` | 147 | `KHCN_QUAN_LY_KHCN` | 67 |
| | | `SHTT_TIEU_CHUAN_DO_LUONG` | 56 |
| | | `AN_TOAN_BUC_XA_HAT_NHAN` | 24 |
| `LAM_NGHIEP_THUY_SAN_THUY_LOI` | 141 | `LAM_NGHIEP_KIEM_LAM` | 53 |
| | | `THUY_LOI_DE_DIEU_PCTT` | 46 |
| | | `THUY_SAN` | 30 |
| `THUONG_MAI_XTTM` | 109 | `THUONG_MAI_QUOC_TE` | 80 |
| | | `THUONG_MAI_NOI_DIA_SO` | 29 |
| `DI_SAN_VAN_HOA_GIA_DINH` | 55 | `DI_SAN_NGHE_THUAT_VAN_HOA` | 48 |
| | | `GIA_DINH_DOI_SONG` | 7 |
| `MOI_TRUONG_KHI_HAU_DA_DANG` | 25 | `MOI_TRUONG_KHI_HAU` | 25 |

**1 lần chuyển canonical:** lĩnh vực *Nghề thủ công mỹ nghệ* (1 TTHC) chuyển canonical từ `LAM_NGHIEP_THUY_SAN_THUY_LOI` sang `CONG_NGHIEP`, vì đó là ngành nghề công nghiệp chứ không phải nông nghiệp. Về nhóm, dữ liệu cổng xếp lĩnh vực này vào **`02. CONG_THUONG_NANG_LUONG`** — đúng với canonical mới.

**Lưu ý về `domain_group`:** 15 nhóm trong guide này **lấy từ tên sheet Excel**, do người dùng đặt theo đúng thứ tự của cổng. Đây là tầng song song với `canonical_field`: `domain_group` theo nguồn, `canonical_field` theo ngữ nghĩa. Cả hai đều có trong `config/field_mapping.csv`.

**3 cặp lĩnh vực gần trùng tên — GIỮ NGUYÊN, không gộp:**

| Cặp giá trị từ cổng | Số TTHC | Canonical chung | `domain_group` thực tế |
|---|---|---|---|
| `An toàn vệ sinh lao động` / `An toàn, vệ sinh lao động` | 2 / 4 | `AN_TOAN_VE_SINH_LAO_DONG` | cùng `05. LAO_DONG_AN_SINH_XA_HOI` |
| `Thi đua – Khen thưởng` / `Thi đua, khen thưởng` | 6 / 3 | `NOI_VU_THI_DUA` | **khác nhóm**: `13. VAN_HOA_THE_THAO_DU_LICH` / `15. Y_TE_SUC_KHOE` |
| `Giáo dục nghề nghiệp` / `Giáo dục nghề nghiệp (G07-LĐ06)` | 8 / 5 | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | cùng `04. GIAO_DUC_DAO_TAO` |

**Vì sao giữ nguyên:** đây là **giá trị do Cổng Dịch vụ công Quốc gia trả về**, không phải Excel nhập sai. Đổi tên trong Excel sẽ khiến crawler đối chiếu sai và **lấy về dữ liệu không đúng**. Mỗi biến thể được cấp một dòng riêng trong `field_mapping.csv`, cùng `canonical_field` — mapping nhờ đó phủ 100% giá trị thực tế.

**Đây chính là giá trị của tầng `canonical_field`:** cặp *Thi đua* nằm ở **hai `domain_group` khác nhau** (13 và 15) nhưng **cùng canonical** `NOI_VU_THI_DUA`. Truy vấn theo `canonical_field` gom được cả hai; truy vấn theo `domain_group` thì không. Vì vậy **lọc theo `canonical_field` đáng tin hơn lọc theo `domain_group`**.

**Kết quả:** canonical **43 → 49**, lĩnh vực nguồn **168 giữ nguyên** (không gộp). Tổng TTHC **1.955**.

**Cách tính canonical:** 4 canonical bị tách thành 10 canonical mới (3+3+2+2), tức `4 → 10`, **thực tăng +6**; cộng thêm *MOI_TRUONG_KHI_HAU_DA_DANG* chỉ **đổi tên** thành `MOI_TRUONG_KHI_HAU` (không tăng số lượng). Vậy `43 + 6 = 49`.

> **Không cần làm gì với 3 cặp lĩnh vực gần trùng tên.** Chúng là giá trị do Cổng Dịch vụ công Quốc gia trả về, đã được cấp dòng riêng trong `field_mapping.csv` với cùng `canonical_field`. `field_mapping.csv` vì vậy có **168 dòng**, khớp 100% cặp `(domain_group, source_field)` thực tế trong dữ liệu crawl.

