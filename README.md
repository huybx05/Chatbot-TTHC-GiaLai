# tra-cuu-tthc

Chatbot AI hỗ trợ tra cứu Thủ tục hành chính tỉnh Gia Lai.

## Đọc trước khi sửa code

Nguồn định hướng hiện tại:

- `PROJECT_GUIDE_V4_1.md` — **PROJECT GUIDE V6.0**, cập nhật 2026-11-08.
- `AGENTS.md` — quy tắc làm việc, skill, TDD và các lệnh kiểm tra.
- `docs/generate_faqs.md` — tạo FAQ hàng loạt bằng LLM local và import Excel.
- `docs/procedure_export.md` — xuất báo cáo TTHC từ `/admin/data`.
- `docs/faq_global.md` — FAQ toàn cục và collection Qdrant `faq_global`.

`README.md` này chỉ là điểm vào nhanh; chi tiết kiến trúc, dữ liệu, RAG/GraphRAG,
deploy và trạng thái dự án nằm trong `PROJECT_GUIDE_V4_1.md`.

## Trạng thái hiện tại

```text
Dữ liệu:        1.874 thủ tục / 24.512 chunk
Backend:        FastAPI + workflow RAG + GraphRAG
Tìm kiếm:       PostgreSQL + Elasticsearch + Qdrant
Đồ thị:         Neo4j (THANH_PHAN_CUA, quan hệ thủ tục)
Hồ sơ:          trả đủ case, có Lưu ý
Feedback:       like/dislike cho assistant response
Test:           1038 passed, 1 skipped
Phase 6:        chưa đánh giá chính thức
Phase 7:        chưa triển khai
```

## Cấu trúc

```text
backend/        FastAPI, auth, RAG/GraphRAG, workflow, tests
data_pipeline/  crawl/normalize/chunk/index
frontend/       React 19 + Vite + Nginx
scripts/        prepare, load, index, build graph/themes/time cases
config/         schema.sql, interlinked_components.json
data/           raw / json / json_normalized / processed
docs/           deploy, plan, hướng dẫn
evaluation/     đánh giá RAG
```

## Chạy nhanh

```powershell
uv sync
uv run pytest -q
uv run ruff check backend scripts

cd frontend
npm run typecheck
npm run build
```

Chạy backend local:

```powershell
uv run uvicorn backend.app.main:app --reload
```

`GET /health` trả `{"status": "ok"}`.

## Cấu hình

Copy `.env.example` thành `.env` rồi điền giá trị thật. Không commit `.env`,
dữ liệu thô, log hoặc secret.

## Nguyên tắc bất biến

```text
PostgreSQL là SSOT.
Elasticsearch / Qdrant / Neo4j là chỉ mục phái sinh.
Mọi câu trả lời phải có detail_url.
"Chưa ghi nhận" khác "không có".
Không hardcode danh sách thủ tục / từ khóa / route.
Không dùng LLM viết Cypher.
Thay đổi hành vi phải có test.
```
