# tra-cuu-tthc

Chatbot AI hỗ trợ tư vấn, tra cứu Thủ tục hành chính trên Cổng Dịch vụ công Quốc gia.

Kiến trúc, cấu trúc repository, data contract và thứ tự triển khai được chốt trong
`PROJECT_GUIDE_TTHC_AI_CHATBOT_v3.md`. Đọc file đó trước khi sửa code.

## Cấu trúc

```text
backend/        FastAPI API, services, DB clients, RAG, LangGraph workflow
data_pipeline/  Ingest PDF → parse → normalize → validate → chunk → index
frontend/       React + Vite + TypeScript
notebooks/      Google Colab orchestration cho xử lý offline
data/           samples, processed, failed (raw corpus nằm trên Google Drive)
config/         field_mapping, retrieval, models
evaluation/     Dataset và entrypoint đo retrieval / answer quality
scripts/        Entrypoint mỏng: prepare_data, process, index
docs/           architecture, data_schema
```

Nguồn dữ liệu: PDF TTHC tải từ Cổng DVCQG bằng tool riêng, lưu trên Google Drive
theo `<domain folder>/<source_field folder>/<procedure_code>.pdf`. Không commit raw corpus.

## Chạy

```powershell
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run uvicorn backend.app.main:app --reload
```

`GET /health` trả `{"status": "ok"}`.

## Cấu hình

Copy `.env.example` thành `.env` rồi điền. Backend không hard-code secret.
LLM chỉ dùng hai biến `BASE_URL` và `API_KEY`. `DATA_ROOT` trỏ vào cây PDF
(`./data` khi chạy local, đường dẫn Drive khi chạy Colab).

## Trạng thái

Đang ở PHASE 1 — Repository Bootstrap. Backend mới có app, config loader và `/health`.
Crawler, HTML parser và BeautifulSoup **không** thuộc dự án này.
