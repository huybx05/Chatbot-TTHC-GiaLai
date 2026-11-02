# AGENTS.md — Quy tắc làm việc trong repo `tra_cuu_tthc`

> Đây là **bộ nhớ quy tắc** của repo. Đọc file này trước khi bắt đầu một task.
> Thứ tự ưu tiên khi có xung đột:
> **chỉ dẫn trực tiếp của người dùng → quy tắc dự án trong file này → hướng dẫn trong từng skill.**

---

## 1. Bộ kỹ năng của repo

Toàn bộ skill nằm ở:

```text
SKILLS/agent_skills/<tên-skill>/SKILL.md
```

Quy tắc dùng skill:

- **Đọc `SKILL.md` của skill trước khi làm**, không đoán nội dung từ tên.
- Script trong skill dùng đường dẫn **tương đối so với thư mục chứa `SKILL.md`**, không phải so với repo.
- Không tự tạo skill mới khi chưa được yêu cầu; nếu cần, dùng `writing-skills`.
- Khi một task khớp skill, nói ngắn một câu kiểu: *“Đang dùng skill `writing-plans` để lập kế hoạch.”* rồi làm theo.
- `SKILLS/AGENTS.md` (Ponytail mode) có phạm vi **chỉ trong thư mục `SKILLS/`**. Toàn repo vẫn ưu tiên quy tắc dự án ở file này.

### Chọn skill theo tình huống

| Tình huống | Skill | Ghi chú |
|---|---|---|
| Ý tưởng mới, tính năng mới, thay đổi hành vi | `brainstorming` | Bắt buộc trước khi viết code; làm rõ ý định, ràng buộc, tiêu chí thành công; chốt thiết kế với người dùng |
| Task nhiều bước đã có yêu cầu/spec | `writing-plans` | Lập kế hoạch từng bước, mỗi bước có kiểm chứng; lưu `docs/superpowers/plans/YYYY-MM-DD-<tên>.md` |
| Thực thi kế hoạch trong phiên hiện tại | `executing-plans` | Tự làm từng task, dùng ledger, TDD, không dừng hỏi giữa các task |
| Thực thi kế hoạch bằng subagent | `subagent-driven-development` | Mỗi task một implementer mới + review từng task + review cuối nhánh |
| Viết code mới hoặc sửa lỗi | `test-driven-development` | Viết test trước, **phải thấy test đỏ**, rồi code tối thiểu cho xanh |
| Gặp bug, test fail, hành vi lạ | `systematic-debugging` | Tìm root cause trước, **không sửa triệu chứng** |
| Trước khi nói “xong / đã sửa / pass” | `verification-before-completion` | Chạy lệnh kiểm chứng mới, đọc output, chỉ kết luận khi có bằng chứng |
| Sau task lớn, trước khi merge | `requesting-code-review` | Gửi reviewer subagent đúng context; kèm BASE/HEAD SHA |
| Khi nhận feedback review | `receiving-code-review` | Kiểm chứng trước khi sửa; phản hồi kỹ thuật, không đồng ý hình thức |
| 2+ việc độc lập có thể chạy song song | `dispatching-parallel-agents` | Một agent cho mỗi nhóm lỗi/việc độc lập |
| Cần không gian làm việc tách biệt | `using-git-worktrees` | Kiểm tra isolation trước; ưu tiên công cụ native, fallback git worktree |
| Kết thúc nhánh phát triển | `finishing-a-development-branch` | Test xanh → chọn cách tích hợp → dọn dẹp |
| Điều tra vì sao một phiên làm việc hỏng | `diagnosing-superpowers` | Chỉ báo cáo, không tự sửa; mọi phát hiện phải có `path:line` |
| Tạo/sửa skill | `writing-skills` | TDD cho tài liệu: chạy tình huống gốc trước, viết skill, kiểm lại |
| Nội dung thương hiệu, giọng điệu, tài sản brand | `brand` | Chỉ dùng khi task thật sự liên quan brand |
| Design token, component spec, slide | `design-system` | Token 3 lớp; chỉ dùng khi làm design system/slide |
| Giao diện shadcn/ui + Tailwind + canvas | `ui-styling` | Component accessible, responsive, dark mode |
| Thiết kế/review UI/UX tổng quát | `ui-ux-pro-max` | Tra cứu style, palette, typography, UX guideline; bỏ qua nếu thuần backend |

---

## 2. Quy trình chuẩn cho một task

```text
1. Brainstorm (nếu là tính năng/thay đổi hành vi)
   → hiểu ý định, ràng buộc, tiêu chí thành công
   → viết lại thiết kế ngắn, chờ người dùng chốt

2. Lập kế hoạch (nếu task nhiều bước)
   → file kế hoạch có: mục tiêu, file sẽ sửa, từng task, test cho từng task
   → mỗi task là một đơn vị tự kiểm chứng được

3. Thực thi
   → TDD: test đỏ → code tối thiểu → test xanh
   → sửa đúng phạm vi, không refactor ngoài kế hoạch
   → ghi ledger/ghi chú để không quên quyết định

4. Review
   → tự review diff trước
   → task lớn: gửi reviewer subagent
   → nhận feedback: kiểm chứng rồi mới sửa

5. Kiểm chứng trước khi báo xong
   → chạy full test + lint
   → đọc output, đếm lỗi
   → chỉ nói “pass” khi có output thật
```

---

## 3. Quy tắc dự án (bắt buộc)

### Phạm vi và dữ liệu

- **Không dựng lại A0**: không tạo bảng `procedure_identity`, `procedure_profile`, `procedure_case`; Qdrant chỉ dùng collection `semantic_search`.
- Phạm vi hiện tại là **49 thủ tục**; không tự nạp 1.909 thủ tục khi chưa được chốt.
- Dữ liệu chuẩn hoá nằm ở `data/json_normalized/`; PostgreSQL là nguồn sự thật (SSOT) cho thủ tục.
- Không thêm bảng mới nếu chưa được người dùng đồng ý.

### Câu trả lời

- Mọi câu trả lời phải có **`detail_url`**.
- Không dùng ký hiệu `[1]`, `[2]` trong nội dung câu trả lời.
- **“Chưa ghi nhận” khác “không có”**: không được báo “không có dữ liệu” khi thực chất là chưa tra được.
- Câu trả lời phải phân biệt rõ: trả lời được / cần hỏi lại / từ chối.

### Mã nguồn

- Tên biến, hàm, lớp mới dùng **tiếng Anh**; giao diện và thông báo cho người dùng dùng **tiếng Việt**.
- **Không hardcode danh sách từ khoá/route**. Tín hiệu phải sinh từ dữ liệu (IDF, nhóm thủ tục, điều kiện thời hạn…).
- Không thêm dependency mới nếu stdlib hoặc dependency đã có làm được.
- Ưu tiên sửa nhỏ, đúng file; không viết lại file lớn nếu chỉ cần sửa vài dòng.
- Không giữ code chết, import thừa, hàm trùng.
- Mọi thay đổi hành vi phải có test tương ứng.

### Chi phí và đo lường

- Không chạy benchmark lớn hoặc gọi LLM tràn lan khi chưa cần.
- Khi báo cáo kết quả, nêu **số đo thật** (số câu đúng/tổng, thời gian, token) — không ước lượng bằng cảm giác.
- Không tuyên bố “đã cải thiện” nếu chưa đo lại trên cùng bộ câu hỏi.

### Ghi log và chẩn đoán

- Mỗi lượt hỏi qua giao diện phải ghi một dòng vào `logs/workflow_trace.jsonl`.
- Log phải đủ để trả lời: câu hỏi đi qua bước nào, dừng ở đâu, vì sao.
- Ghi log không bao giờ được làm hỏng lượt trả lời.

---

## 4. Quy tắc “Ponytail” (áp dụng toàn repo)

Trước khi viết code, dừng ở bậc đầu tiên đã đủ:

1. Việc này có cần tồn tại không? → không: bỏ qua (YAGNI).
2. Đã có trong codebase chưa? → tái sử dụng, không viết lại.
3. Stdlib làm được không? → dùng stdlib.
4. Tính năng native của nền tảng? → dùng native.
5. Dependency đã cài? → dùng dependency đó.
6. Một dòng là đủ? → một dòng.
7. Chỉ khi đó: viết mức tối thiểu chạy được.

**Không bao giờ cắt**: validation, xử lý lỗi, bảo mật, khả năng truy cập (accessibility).

---

## 5. Lệnh kiểm tra

```powershell
# Backend
uv run ruff check backend scripts
uv run pytest -q

# Frontend
cd frontend
npm run typecheck
npm run build
```

Chỉ được báo “pass” sau khi đã chạy lệnh và đọc output thật.

---

## 6. Ghi chú về từng skill (tóm tắt nhanh)

- **brainstorming**: phân loại mức độ cần thiết; hỏi một câu trọng tâm khi thiếu thông tin; viết lại hiểu biết để người dùng sửa; chốt thiết kế trước khi code.
- **writing-plans**: kế hoạch cho người chưa biết codebase; nêu rõ file, tên hàm, chữ ký, test; chia task nhỏ; mỗi bước có kiểm chứng.
- **executing-plans**: thực thi tuần tự, ledger là bộ nhớ, TDD là cổng từng task, review cuối nhánh; không dừng hỏi giữa các task.
- **subagent-driven-development**: mỗi task một implementer mới + reviewer riêng; reviewer cuối toàn nhánh; ghi ruling khi gặp mâu thuẫn.
- **test-driven-development**: test trước, thấy đỏ, code tối thiểu, thấy xanh; không viết test sau khi code.
- **systematic-debugging**: điều tra root cause trước; không sửa triệu chứng; có pha điều tra, giả thuyết, kiểm chứng.
- **verification-before-completion**: chỉ kết luận khi có output mới; không dùng “should/probably”; chạy đủ lệnh.
- **requesting-code-review**: reviewer subagent nhận context tự chứa, kèm BASE/HEAD SHA; review sớm và thường xuyên.
- **receiving-code-review**: đọc hết, hiểu, kiểm chứng, đánh giá kỹ thuật, phản hồi, sửa từng mục.
- **dispatching-parallel-agents**: một agent cho mỗi nhóm lỗi độc lập; không chia việc phụ thuộc nhau.
- **using-git-worktrees**: kiểm tra đang ở worktree chưa; ưu tiên công cụ native; fallback git worktree.
- **finishing-a-development-branch**: test xanh trước; đưa lựa chọn tích hợp; dọn dẹp sau khi chọn.
- **using-superpowers**: nếu có dù chỉ 1% khả năng skill áp dụng, đọc và dùng skill trước khi trả lời.
- **writing-skills**: viết skill cũng theo TDD; chạy tình huống gốc trước khi viết.
- **diagnosing-superpowers**: chỉ báo cáo sự cố phiên; mọi kết luận phải có `path:line`; không tự sửa.
- **brand**: giọng điệu, nhận diện, tài sản thương hiệu; chỉ dùng khi task liên quan brand.
- **design-system**: token 3 lớp primitive → semantic → component; component spec; slide generation.
- **ui-styling**: shadcn/ui + Tailwind + canvas; ưu tiên accessible, responsive, dark mode.
- **ui-ux-pro-max**: tra cứu style/palette/typography/UX guideline; không dùng cho backend thuần.

---

## 7. Khi nào cập nhật file này

Cập nhật `AGENTS.md` khi:

- Thêm/bớt skill trong `SKILLS/agent_skills/`.
- Thay đổi quy trình bắt buộc (ví dụ bắt buộc review trước merge).
- Thay đổi quy tắc dự án (phạm vi dữ liệu, định dạng câu trả lời, lệnh kiểm tra).

Không cần cập nhật cho từng task nhỏ; chỉ ghi quy tắc ổn định, có giá trị lâu dài.
