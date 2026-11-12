# PROJECT GUIDE V6.0 — TTHC Gia Lai Chatbot

> **Cập nhật:** 2026-11-08  
> **Phạm vi:** mã nguồn, dữ liệu, kiến trúc, RAG/GraphRAG, vận hành và triển khai production.  
> **Nguồn chuẩn:** PostgreSQL là SSOT; Elasticsearch, Qdrant, Neo4j chỉ là chỉ mục phái sinh.

## Đề tài

**Ứng dụng RAG và Knowledge Graph để xây dựng Chatbot AI hỗ trợ tra cứu Thủ tục hành chính tại tỉnh Gia Lai.**

---

# 0. ĐỌC NHANH — DỰ ÁN ĐANG Ở ĐÂU

## 0.1. Trạng thái tổng thể

| Hạng mục | Trạng thái |
|---|---|
| Dữ liệu 1.874 TTHC | ✅ Đã nạp PostgreSQL |
| Chunk + tìm kiếm hybrid | ✅ PostgreSQL + Elasticsearch + Qdrant |
| Knowledge Graph | ✅ Neo4j `run_id=full` |
| Workflow RAG | ✅ FastAPI + LangGraph-style workflow |
| GraphRAG thành phần/liên thông | ✅ Đã triển khai |
| Trả lời hồ sơ đầy đủ theo case | ✅ Đã triển khai |
| FAQ: chọn gợi ý, bulk, import/export Excel | ✅ Đã triển khai |
| FAQ toàn cục: Qdrant `faq_global` + auto-match | ✅ Đã triển khai |
| Báo cáo TTHC Excel từ /admin/data | ✅ Đã triển khai |
| Like/dislike mọi câu trả lời | ✅ Đã triển khai |
| Phase 6 — đánh giá chính thức | ⏳ Chưa làm đầy đủ; có test hồi quy + kiểm tra log thủ công |
| Phase 7 — ToG/PCST/community summary | ⏳ Chưa triển khai; chỉ làm khi có nhu cầu thực tế |

## 0.2. Các mốc đã hoàn thành

```text
Phase 0  ✅  Fixture hồi quy quan hệ thành phần
Phase 1  ✅  Facet components / parent_interlinked
Phase 2  ✅  Capability + planner routing
Phase 3  ✅  Graph shape THANH_PHAN_CUA
Phase 4  ✅  Edge metadata + source_code + alias mã cũ
Phase 5  ✅  Evidence fusion + metadata thành phần
Phase 6  ⏳  Đánh giá/roll-out chính thức chưa làm đầy đủ
Phase 7  ⏳  Nâng cao có điều kiện, chưa làm
```

## 0.3. Các sửa đổi quan trọng sau Phase 5

```text
1. "liên quan" / "liên thông" dùng chung facet procedure_relations
   - Graph đi hai chiều THANH_PHAN_CUA
   - related_procedures cũ được fallback sang procedure_relations

2. Hồ sơ chung trả đủ tất cả case
   - Không tóm tắt bằng LLM
   - Giữ nguyên nội dung, gồm cả case "Lưu ý"

3. Hỏi riêng "Lưu ý" dùng facet notes
   - Chỉ trả case Lưu ý
   - Không lẫn giấy tờ phải nộp/xuất trình

4. Case resolver
   - Chỉ dùng case_name để chọn case
   - Không dùng block_heading
   - Dùng câu hỏi gốc, không dùng câu rewrite đã chèn tên thủ tục

5. Câu từ chối theo trạng thái
   - FACET_NOT_RECORDED
   - TOOL_UNAVAILABLE
   - UNSUPPORTED_FACET
   - INSUFFICIENT_EVIDENCE
   - Không còn câu chung "dữ liệu chưa đủ" khi đã biết mã thủ tục

6. Feedback
   - Clarify/abstained/cached cũng có message_id
   - Nút like/dislike hoạt động cho mọi assistant response được lưu
```

## 0.4. Quy mô dữ liệu hiện tại

| Hạng mục | Giá trị |
|---|---:|
| `procedures` | **1.874** |
| `procedure_sections` | **24.512** |
| `procedure_documents` | **2.043** |
| `procedure_themes` | **247** nhóm |
| Thủ tục có `theme_id` | **1.458 / 1.874** |
| `procedure_time_cases` | **2.312** |
| `faq` | **0** hiện tại |
| `chat_messages` | **163** tại thời điểm cập nhật |

Nguồn dữ liệu:

```text
data/raw/api              ~1.870 JSON API gốc
data/json                 1.874 JSON đã chuyển đổi
data/json_normalized      1.874 JSON chuẩn hóa
data/processed/chunks.jsonl  24.512 chunk
```

Bốn TTHC liên thông không có raw API riêng:

```text
3.000153
2.002621
2.002622
1.014475
```

Chúng được dựng bổ sung bằng:

```text
scripts/build_interlinked_procedures.py
scripts/normalize_interlinked_procedures.py
```

---

# 1. KIẾN TRÚC TỔNG THỂ

## 1.1. Luồng production

```text
Người dân / Quản trị viên
        │ HTTPS
        ▼
Cloudflare Edge
  DNS · TLS · WAF · rate limiting
        │ Cloudflare Tunnel
        ▼
cloudflared (VPS, profile tunnel)
        │ HTTP nội bộ
        ▼
Nginx Frontend
  chat.tthc-gialai.id.vn  → React SPA
  admin.tthc-gialai.id.vn → React Admin SPA
        │ /chat, /chat/stream, /api/*
        ▼
FastAPI Backend
  API · xác thực · workflow · retrieval · citation
        │
        ├── PostgreSQL 18       SSOT
        ├── Redis 7             cache / rate limit
        ├── Elasticsearch 9.5.4 keyword index
        ├── Qdrant 1.19.0       vector index
        ├── Neo4j 5             knowledge graph
        ├── SeaweedFS 4.50      S3 files
        └── External AI APIs    LLM / embedding / reranker
```

## 1.2. Thành phần hạ tầng

| Thành phần | Image / phiên bản | Vai trò |
|---|---|---|
| PostgreSQL | `postgres:18-alpine` | SSOT: thủ tục, chunk, chat, user, feedback, chi phí |
| SeaweedFS | `chrislusf/seaweedfs:4.50` | S3-compatible lưu PDF/Word |
| Redis | `redis:7-alpine` | Cache, rate limit phân tán |
| Qdrant | `qdrant/qdrant:v1.19.0` | Vector search |
| Neo4j | `neo4j:5-community` | Knowledge Graph |
| Elasticsearch | `elasticsearch:9.5.4` | BM25/keyword search |
| Backend | FastAPI + Python 3.12 | API, workflow, retrieval, admin API |
| Frontend | React 19 + Vite + Nginx | Chat client + admin UI |
| Cloudflare Tunnel | `cloudflare/cloudflared:latest` | Public HTTPS, không mở inbound 80/443 |

## 1.3. Docker network

```text
edge:
  frontend
  backend
  cloudflared

data (internal: true):
  postgres
  redis
  qdrant
  neo4j
  elasticsearch
  s3
  backend
```

Chỉ frontend publish:

```text
127.0.0.1:8080:80
```

Không publish PostgreSQL, Redis, Neo4j, Elasticsearch, Qdrant, SeaweedFS ra Internet.

---

# 2. CẤU TRÚC THƯ MỤC

```text
tra_cuu_tthc/
├── backend/
│   ├── app/
│   │   ├── api/            # chat, chat_sessions, feedback, admin, procedures...
│   │   ├── auth/           # JWT, refresh token, user admin
│   │   ├── cost/           # ghi nhận chi phí LLM
│   │   ├── db/             # engine PostgreSQL
│   │   ├── documents/      # S3 storage, importer, repository
│   │   ├── memory/         # short-term memory, rewrite
│   │   ├── models/         # model client Qwen/DeepSeek
│   │   ├── rag/            # hybrid, graph, themes, grounding, evidence...
│   │   ├── schemas/        # Pydantic models
│   │   ├── services/       # dịch vụ dùng chung
│   │   ├── workflow/       # state graph, parser, planner, executor, answer
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── rate_limit.py
│   │   └── security_headers.py
│   ├── tests/              # 105 file test
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/            # client HTTP, SSE, feedback
│   │   ├── components/     # layout, client, admin
│   │   ├── pages/client/   # ChatPage
│   │   ├── pages/admin/    # login, overview, data, FAQ, graph, costs...
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── nginx.conf
│   └── Dockerfile
├── data/
│   ├── raw/api/
│   ├── json/
│   ├── json_normalized/
│   ├── processed/
│   └── failed/
├── data_pipeline/
│   ├── crawler/
│   ├── processing/
│   └── indexing/
├── scripts/                # prepare, process, load, index, build, generate_faqs...
├── config/
│   ├── schema.sql
│   └── interlinked_components.json
├── docs/                   # deploy, plan, hướng dẫn
├── evaluation/             # đánh giá RAG
├── compose.yaml            # local
├── docker-compose.prod.yml # production
├── .env.example
├── .env                    # KHÔNG commit
└── PROJECT_GUIDE_V4_1.md   # tài liệu này (tên file giữ để tương thích)
```

---

# 3. DỮ LIỆU VÀ PIPELINE

## 3.1. Nguyên tắc dữ liệu

```text
PostgreSQL = SSOT
Elasticsearch / Qdrant / Neo4j = chỉ mục phái sinh, có thể xóa và dựng lại
Không tạo bảng A0: procedure_identity / procedure_profile / procedure_case
Không dùng Qdrant collection ngoài semantic_search / faq_search / faq_global
Mỗi node/edge Neo4j phải có run_id
Không hardcode danh sách thủ tục / từ khóa / route
```

## 3.2. Pipeline

```text
1. Crawl API DVC
   data/raw/api/*.json

2. Chuẩn hóa
   data/json/<DOMAIN>/<SOURCE_FIELD>/<code>.json
   data/json_normalized/<DOMAIN>/<SOURCE_FIELD>/<code>.json

3. Manifest + chunk
   data/processed/procedure_manifest.csv
   data/processed/chunks.jsonl

4. Nạp PostgreSQL
   procedures, procedure_agencies, procedure_sections, procedure_documents

5. Sinh chỉ mục
   Elasticsearch + Qdrant + Neo4j
```

Lệnh chính:

```bash
uv run python scripts/prepare_data.py
uv run python scripts/process.py
uv run python scripts/build_chunks.py
uv run python scripts/build_manifest.py
uv run python scripts/load_postgres.py
uv run python scripts/index_search_stores.py --target all --recreate
uv run python -m data_pipeline.indexing.neo4j --from-postgres --database neo4j --run-id full --wipe
```

Tạo FAQ hàng loạt (đọc PostgreSQL, gọi LLM local, xuất Excel):

```bash
uv run python scripts/generate_faqs.py --procedures 300 --per-domain 20 \
  --model gemini-3.8-flash-tiered --reasoning-effort none \
  --max-tokens 8192 --output data/faq_generated/faq_900.xlsx
```

Chi tiết: [docs/generate_faqs.md](docs/generate_faqs.md).

Báo cáo TTHC: xem [docs/procedure_export.md](docs/procedure_export.md).
Nếu `decision_date` còn trống, chạy:

```bash
uv run python scripts/backfill_decision_dates.py --apply
```

FAQ toàn cục: xem [docs/faq_global.md](docs/faq_global.md).
Seed/index:

```bash
uv run python scripts/seed_global_faqs.py --apply
uv run python scripts/index_global_faqs.py
```

## 3.3. Sentinel cần phân biệt

```text
"Không có thông tin"  → chưa tra được / nguồn không cung cấp
"Không có"            → nguồn khẳng định không có
CHUA_XAC_DINH         → chưa xác định
MIEN_PHI              → miễn phí
THEO_SO_LUONG         → theo số lượng
```

Không được trả lời "không có dữ liệu" khi thực chất chỉ là **chưa tra được**.

## 3.4. `procedure_themes`

Bảng nhóm thủ tục theo 4 từ đầu của tên:

```text
procedure_themes(theme_id, label, canonical_code)
procedures.theme_id → procedure_themes.theme_id
```

Mục đích:

```text
- Gom các thủ tục biến thể của cùng một nhóm
- Giảm clarify khi nhiều thủ tục cùng nhóm có cùng nội dung
- Nếu nhóm đã rà soát, dùng canonical_code làm đại diện
```

Hiện tại:

```text
247 nhóm
1.458 / 1.874 thủ tục được gán
chỉ 1 canonical_code: dang_ky_bien_dong → 1.115362
```

Build lại:

```bash
uv run python scripts/build_procedure_themes.py --apply
```

Hạn chế: heuristic 4 từ đầu còn thô; phải build lại khi dữ liệu đổi.

## 3.5. `procedure_time_cases`

Bảng mốc thời hạn kèm điều kiện:

```bash
uv run python scripts/build_time_cases.py --apply
```

Hiện tại: **2.312** mốc.

Bảng này **không được tạo bởi `schema.sql`**; do script tạo. Khi rebuild trên VPS phải mount đủ dữ liệu:

```bash
-v "$PWD/data:/app/data:ro"
```

---

# 4. POSTGRESQL — SSOT

## 4.1. Bảng nghiệp vụ

| Bảng | Vai trò |
|---|---|
| `procedures` | Thông tin gốc thủ tục |
| `procedure_agencies` | Cơ quan thực hiện/thẩm quyền/phối hợp/ủy quyền |
| `procedure_sections` | Chunk nội dung; khóa đồng bộ search |
| `procedure_documents` | Metadata file đính kèm |
| `procedure_themes` | Nhóm thủ tục |
| `procedure_time_cases` | Mốc thời hạn kèm điều kiện |

## 4.2. Bảng xác thực / hội thoại

| Bảng | Vai trò |
|---|---|
| `users` | Tài khoản admin/client, Argon2id |
| `sessions` | Refresh token đã hash, rotation family |
| `chat_sessions` | Cuộc trò chuyện; hỗ trợ guest |
| `chat_messages` | Tin nhắn + metadata citation + feedback |
| `chat_session_memory` | Bộ nhớ tóm tắt hội thoại |
| `guest_sessions` | Phiên khách TTL ngắn |
| `audit_logs` | Nhật ký thao tác quản trị |
| `ai_models` | Danh mục model |
| `ai_price_versions` | Phiên bản giá |
| `ai_usage_events` | Sự kiện sử dụng/chi phí |

## 4.3. Feedback

Lưu trong:

```text
chat_messages.metadata.feedback
```

Dạng:

```json
{
  "value": "like",
  "reasons": [],
  "comment": "",
  "updated_at": "..."
}
```

API:

```text
POST /chat/messages/{message_id}/feedback
```

Quy tắc:

```text
- like / dislike / null
- user chỉ sửa feedback của mình
- guest chỉ sửa message thuộc guest session
- admin xem được qua /api/admin/conversations
```

---

# 5. NEO4J — KNOWLEDGE GRAPH

## 5.1. Node labels

```text
ThuTuc
CoQuan
VanBanPhapLy
QuyetDinh
DomainGroup
LinhVuc
CapHanhChinh
TrangThai
DoiTuong
KetQua
```

Mỗi node có tối thiểu:

```text
run_id
key
ten
```

## 5.2. Quan hệ

| Quan hệ | Ý nghĩa |
|---|---|
| `BAN_HANH_BOI` | Thủ tục → cơ quan ban hành |
| `CO_THAM_QUYEN` | Thủ tục → cơ quan thực hiện |
| `PHOI_HOP` | Thủ tục → cơ quan phối hợp |
| `DUOC_UY_QUYEN` | Thủ tục → cơ quan được ủy quyền |
| `CAN_CU_PHAP_LY` | Thủ tục → văn bản pháp lý |
| `CO_QUYET_DINH` | Thủ tục → quyết định |
| `CAP_THUC_HIEN` | Thủ tục → cấp thực hiện |
| `LINH_VUC` | Thủ tục → lĩnh vực |
| `DOMAIN_GROUP` | Thủ tục → nhóm |
| `TRANG_THAI` | Thủ tục → trạng thái |
| `DOI_TUONG_THUC_HIEN` | Thủ tục → đối tượng |
| `KET_QUA_XU_LY` | Thủ tục → kết quả |
| `THANH_PHAN_CUA` | Thủ tục cha → thành phần |
| `THU_TUC_LIEN_QUAN` | Quan hệ thủ tục liên quan thông thường; hiện 0 cạnh |

## 5.3. Thành phần liên thông

Mapping:

```text
config/interlinked_components.json
```

Hiện tại:

| Thủ tục cha | Thành phần thật |
|---|---|
| `2.002621` | `1.001193`, `1.014137`, `1.116788` |
| `2.002622` | `1.000656`, `1.116788` |
| `1.014475` | `1.001029`, `1.001612`, `3.000243` |
| `2.002804` | `1.000801` |
| `3.000153` | Không có thành phần trên cổng DVC |

Edge `THANH_PHAN_CUA` có:

```text
component_name
source_code
source_url
note
is_inferred
```

Alias mã cũ → mới:

```text
1.002535 → 1.014137
1.004222 → 1.116788
1.003197 → 1.116788
```

Alias nằm trong `config/interlinked_components.json`, không hardcode trong code.

## 5.4. Rebuild graph

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
  python -m data_pipeline.indexing.neo4j \
  --from-postgres \
  --database neo4j \
  --run-id full \
  --wipe
```

Kiểm tra:

```cypher
MATCH (p:ThuTuc {run_id:"full"}) RETURN count(p);
MATCH ()-[r:THANH_PHAN_CUA {run_id:"full"}]->() RETURN count(r);
```

Lần rebuild gần nhất: **1.874 ThuTuc**, **9 cạnh THANH_PHAN_CUA**, **0 cạnh THU_TUC_LIEN_QUAN**.

---

# 6. ELASTICSEARCH VÀ QDRANT

## 6.1. Elasticsearch

```text
index: chatbot_tthc
```

BM25 cho từ khóa, có `section_type`, `procedure_code`.

## 6.2. Qdrant

```text
semantic_search   # vector chunk TTHC
faq_search        # vector FAQ
faq_global        # 3 FAQ toàn cục auto-match trước RAG
```

Vector:

```text
EMBEDDING_DIM=1024
```

## 6.3. Rebuild

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
  python scripts/index_search_stores.py --target all --recreate
```

Lưu ý:

```text
Elasticsearch reindex: không tốn embedding
Qdrant reindex: gọi API embedding, có thể tốn phí
```

---

# 7. BACKEND VÀ WORKFLOW

## 7.1. Module chính

```text
api/          endpoint công khai + admin
auth/         JWT, refresh, user admin
cost/         chi phí AI
db/           PostgreSQL engine
documents/    S3, import file
memory/       short-term memory, rewrite
models/       client Qwen/DeepSeek
rag/          hybrid, graph, themes, grounding, evidence
schemas/      Pydantic
services/     dùng chung
workflow/     state graph, parser, planner, executor, answer
```

## 7.2. Luồng RAG hiện tại

```text
1. Chuẩn hóa câu hỏi
2. Memory rewrite nếu là follow-up
3. LLM parser → QuestionFrame
4. Grounding thủ tục / văn bản / thực thể
5. Disambiguation / theme agreement nếu mơ hồ
6. Planner chọn tool:
   - section_lookup
   - graph
   - hybrid
   - fact_lookup
7. Executor chạy song song
8. Evidence fusion
9. Trả lời:
   - hồ sơ/Lưu ý: câu trả lời tất định từ evidence
   - nội dung khác: LLM tổng hợp có citation
10. Kiểm chứng + ghi trace
```

## 7.3. QuestionFrame / facet

Các facet quan trọng:

```text
required_documents
notes
components
parent_interlinked
procedure_relations
related_procedures
```

Quy ước:

```text
components          → hỏi rõ "gồm thủ tục con/thành phần nào"
parent_interlinked  → hỏi rõ "thuộc thủ tục cha nào"
procedure_relations → "liên quan/liên thông" nói chung, Graph tự trả cả hai chiều
notes               → chỉ phần Lưu ý của hồ sơ
related_procedures  → fallback về procedure_relations nếu có mã thủ tục
```

## 7.4. Hồ sơ đầy đủ

Câu hỏi hồ sơ **không dùng LLM để tóm tắt**. Hàm:

```python
build_required_documents_answer()
```

trong:

```text
backend/app/workflow/answer.py
```

Nguyên tắc:

```text
- nhóm theo case_order
- giữ nguyên nội dung
- không cắt 400 ký tự
- không bỏ "Lưu ý"
- chỉ trả case Lưu ý khi facet notes
```

## 7.5. Case resolver

File:

```text
backend/app/workflow/case_resolver.py
```

Quy tắc:

```text
- Chỉ dùng case_name để chọn case
- Không dùng block_heading (vì chứa tên thủ tục)
- Dùng câu hỏi gốc, không dùng câu rewrite
```

Ví dụ:

```text
"Hồ sơ ... gồm gì?"           → trả tất cả case
"Giấy tờ phải xuất trình?"     → chỉ case 2
"Lưu ý của thủ tục?"           → chỉ case 3
```

## 7.6. Từ chối theo trạng thái

File:

```text
backend/app/workflow/refusals.py
```

Các trạng thái:

```text
FACET_NOT_RECORDED
TOOL_UNAVAILABLE
UNSUPPORTED_FACET
INSUFFICIENT_EVIDENCE
```

Ví dụ đúng:

```text
"Hiện dữ liệu tra cứu chưa ghi nhận thời hạn giải quyết
của thủ tục 1.004873 — ..."
```

Không dùng:

```text
"Dữ liệu hiện có chưa đủ... hãy nêu mã hoặc tên thủ tục"
```

khi đã biết mã.

## 7.7. FAQ — chọn gợi ý; FAQ toàn cục auto-match

```text
Người dùng gõ câu hỏi
  ├─ bấm FAQ gợi ý → frontend gửi faq_id
  │    → find_ready_faq_by_id(faq_id)
  │    → chỉ chấp nhận status = ready
  │    → trả ngay câu trả lời FAQ, không gọi RAG
  │
  ├─ không bấm FAQ, câu hỏi khớp FAQ toàn cục
  │    → rewrite follow-up bằng memory
  │    → exact/Qdrant semantic trên `faq_global`
  │    → trả FAQ, không RAG
  │
  └─ còn lại → RAG bình thường
```

Đã bỏ `find_ready_faq(payload.question)` khỏi `/chat` và `/chat/stream`.
FAQ có `procedure_code` phải trả citation/detail_url của thủ tục.

FAQ **gắn thủ tục** không auto-match; chỉ xuất hiện dạng gợi ý sau RAG.
FAQ **toàn cục** (`procedure_code` rỗng) được auto-match; xem
[docs/faq_global.md](docs/faq_global.md).

FAQ **không gắn thủ tục** vẫn được gợi ý sau câu trả lời RAG khi câu hỏi
không xác định được thủ tục. Cách chọn:

```text
- lọc status = ready
- procedure_code rỗng
- bỏ các intent đã hỏi trong lượt hiện tại
- ưu tiên priority, updated_at
- tối đa 3 câu
```

Không dùng so khớp token/threshold cho gợi ý FAQ thủ tục.
Ví dụ câu hỏi địa chỉ trung tâm có thể gợi ý FAQ giờ làm việc của trung tâm.

Trang `/admin/faq` hỗ trợ:

```text
- checkbox nhiều dòng, chọn tất cả trong tab đang lọc
- bulk đổi trạng thái / xóa, all-or-nothing
- import .xlsx tối đa 5 MB / 1.000 dòng
- export lọc all/ready/draft/theo thủ tục
- file mẫu có dropdown Danh mục và Trạng thái
```

---

# 8. GRAPHRAG ĐÃ LÀM

## 8.1. Capability và shape

```text
COMPONENTS_OF_PROCEDURE   → thủ tục cha → thành phần
PROCEDURES_BY_COMPONENT   → thành phần → thủ tục cha
PROCEDURE_RELATIONS       → hai chiều THANH_PHAN_CUA
```

Shape `PROCEDURE_RELATIONS` dùng quan hệ không định hướng:

```cypher
MATCH (p:ThuTuc {run_id: $run_id, key: $code})
      -[e1:THANH_PHAN_CUA]-
      (x)
```

Trả về:

```text
vai_tro: cha / con
ma, ten
component_name
source_code
source_url
detail_url
```

## 8.2. Evidence

`EvidenceItem` có thêm:

```text
component_name
source_code
source_url
```

`from_graph` map đúng:

```text
thành phần → procedure_code = mã con
thủ tục cha → procedure_code = mã cha
```

Fusion:

```text
deduplicate_evidence()
- cùng procedure_code
- cùng section_type
- cùng content
- cùng component_name
- cùng part_index
```

## 8.3. Router/planner

```text
related_procedures → PROCEDURE_RELATIONS
procedure_relations → PROCEDURE_RELATIONS
components → COMPONENTS_OF_PROCEDURE
parent_interlinked → PROCEDURES_BY_COMPONENT
```

## 8.4. Test hồi quy

```text
backend/tests/fixtures/graph_components_regression.json
backend/tests/test_graph_components_regression.py
backend/tests/test_graph_components_query.py
backend/tests/test_procedure_relations.py
backend/tests/test_graph_evidence_contract.py
backend/tests/test_evidence_fusion.py
```

---

# 9. API

## 9.1. Public

```text
POST /chat
POST /chat/stream
POST /chat/guest-session
GET  /chat/guest-session
DELETE /chat/guest-session

GET  /api/v1/chat-sessions
POST /api/v1/chat-sessions
PATCH /api/v1/chat-sessions/{id}
PATCH /api/v1/chat-sessions/{id}/pin
DELETE /api/v1/chat-sessions/{id}
GET  /api/v1/chat-sessions/{id}/messages

GET  /api/v1/procedures/{procedure_code}/documents
GET  /api/v1/documents/{document_id}/download
GET  /api/v1/faq/intents
GET  /api/v1/faq/suggestions
POST /chat/messages/{message_id}/feedback
POST /api/v1/visits
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

## 9.2. Admin

```text
/api/admin/*
```

Yêu cầu role `admin`.

Các nhóm chính:

```text
system/status
conversations
procedures
faq
faq/import        # .xlsx, tối đa 5 MB / 1.000 dòng, all-or-nothing
faq/export        # lọc status=all|ready|draft, procedure_code
faq/template      # file mẫu có dropdown Danh mục/Trạng thái
faq/bulk/status
faq/bulk/delete
procedures/export   # báo cáo Excel: mỗi TTHC một dòng
graph
workflow/ask
retrieval/test
costs/summary
auth/admin/users
```

## 9.3. Streaming và feedback

`POST /chat/stream` phát:

```text
start → meta → delta* → done
```

`done` phải có:

```text
message_id
```

Frontend dùng `message_id` để gửi like/dislike.

Các trường hợp đã có message_id:

```text
answered
clarify
abstained
cached
FAQ
```

Lỗi mạng/HTTP trước khi có message thì không thể đánh giá.

---

# 10. FRONTEND

## 10.1. Client

```text
/ → ChatPage
```

Chức năng:

```text
- chat streaming
- lịch sử hội thoại, ghim, đổi tên, xóa
- guest session
- FAQ gợi ý
- citation/detail_url
- like/dislike cho mọi assistant message
- hiển thị file mẫu
```

## 10.2. Admin

```text
/admin
/admin/data
/admin/faq
/admin/graph
/admin/retrieval
/admin/conversations
/admin/costs
/admin/users
/admin/operations
```

## 10.3. Subdomain

```text
chat.tthc-gialai.id.vn
admin.tthc-gialai.id.vn
```

Cookie host-only, không dùng `Domain=.tthc-gialai.id.vn`.

Điều hướng chéo dùng URL tuyệt đối `chatHomeUrl()`.

## 10.4. Nginx

```text
chat host:
  chặn /api/admin
  /admin → redirect admin host

admin host:
  / → /admin
  X-Robots-Tag: noindex
  absolute_redirect off
  location = /index.html { try_files $uri =404; }
```

---

# 11. DOCKER VÀ TRIỂN KHAI

## 11.1. Compose production

```text
docker-compose.prod.yml
project name: tracuutthc
```

Services:

```text
postgres
s3
redis
qdrant
neo4j
elasticsearch
backend
frontend
cloudflared (profile tunnel)
```

Volumes:

```text
postgres-data
redis-data
qdrant-data
neo4j-data
neo4j-logs
elasticsearch-data
app-logs
seaweedfs-data
```

## 11.2. Điểm cấu hình quan trọng

### PostgreSQL 18

```yaml
volumes:
  - postgres-data:/var/lib/postgresql
```

Không dùng `/var/lib/postgresql/data`.

### Neo4j

```yaml
environment:
  NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
```

Không đặt `NEO4J_PASSWORD` trực tiếp trong environment Neo4j.

### SeaweedFS

```text
/opt/seaweedfs/s3.json
S3_ENDPOINT_DOCKER=http://s3:8333
S3_BUCKET=procedure-documents
```

### Cloudflare

```env
CLOUDFLARE_TUNNEL_TOKEN=...
```

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d
```

Public hostname:

```text
chat.tthc-gialai.id.vn  → http://frontend:80
admin.tthc-gialai.id.vn → http://frontend:80
```

Phải gửi đúng HTTP Host Header.

## 11.3. Thứ tự deploy

```text
1. SSH root
2. Cài Docker, swap, UFW
3. Clone repo
4. Tạo .env
5. Tạo /opt/seaweedfs/s3.json
6. docker compose build
7. up postgres/redis/qdrant/neo4j/elasticsearch/s3
8. restore PostgreSQL hoặc nạp dữ liệu
9. tạo role chatbot_app nếu dùng
10. import procedure_documents / SeaweedFS
11. build theme/time case
12. build Neo4j
13. index Elasticsearch/Qdrant
14. up backend/frontend
15. seed admin
16. bật Cloudflare Tunnel
```

Chi tiết:

```text
docs/deploy_root_simple.md
docs/deployment_vps_cloudflare.md
```

## 11.4. Version

```text
PostgreSQL 18
Elasticsearch 9.5.4
Qdrant 1.19.0
Neo4j 5
SeaweedFS 4.50
Redis 7
```

Không dùng volume cũ với image mới nếu chưa migrate.

---

# 12. VẬN HÀNH

## 12.1. Kiểm tra sức khỏe

```bash
cd /opt/tra_cuu_tthc

docker compose -f docker-compose.prod.yml ps
docker stats --no-stream
df -h
free -h
```

## 12.2. Backup

PostgreSQL:

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres -d chatbot_tthc -Fc \
  > /opt/backups/chatbot_tthc_$(date +%F).dump
```

Neo4j:

```bash
docker compose -f docker-compose.prod.yml exec -T neo4j \
  neo4j-admin database dump neo4j --to-path=/data/backups
```

Qdrant:

```bash
curl -X POST http://127.0.0.1:6333/collections/semantic_search/snapshots
```

Elasticsearch: snapshot repository hoặc reindex.

SeaweedFS: backup volume hoặc `aws s3 sync`.

## 12.3. Dọn Docker

```bash
docker container prune -f
docker image prune -f
docker builder prune -f
docker network prune -f
journalctl --vacuum-time=7d
```

Không chạy:

```bash
docker volume prune
docker system prune --volumes
```

---

# 13. LỖI THƯỜNG GẶP

## 13.1. Neo4j restart: Unrecognized setting PASSWORD

`NEO4J_PASSWORD` nằm trong environment Neo4j. Sửa:

```yaml
environment:
  NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
```

## 13.2. PostgreSQL 18 restart

Kiểm tra:

```yaml
- postgres-data:/var/lib/postgresql
```

## 13.3. `pg_restore: unsupported version (1.16)`

Dump từ PostgreSQL 18, restore bằng PostgreSQL 16.

Sửa:

```text
- dùng PostgreSQL 18 cả hai phía; hoặc
- dump plain SQL (-Fp) và restore bằng psql
```

## 13.4. Admin `ERR_TOO_MANY_REDIRECTS`

Kiểm tra Nginx:

```nginx
absolute_redirect off;

location = / { return 302 /admin; }
location ^~ /admin { try_files $uri $uri/ /index.html; }
location = /index.html { try_files $uri =404; }
location / { return 302 /admin; }
```

Thiếu `location = /index.html` sẽ tạo vòng redirect.

## 13.5. S3 lỗi xác thực

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python -c "from backend.app.documents.storage import S3Storage; S3Storage.from_settings().ensure_bucket(); print('S3 OK')"
```

Đối chiếu `.env` với `/opt/seaweedfs/s3.json`.

---

# 14. TEST VÀ CHẤT LƯỢNG

## 14.1. Lệnh kiểm tra

```bash
uv run pytest -q
uv run ruff check backend scripts

cd frontend
npm run typecheck
npm run build
```

## 14.2. Trạng thái gần nhất

```text
Backend: 1038 passed, 1 skipped
Ruff: All checks passed
Frontend typecheck: passed
Frontend build: passed
```

Có **105 file test** trong `backend/tests`.

## 14.3. Nguyên tắc test

```text
- TDD: test đỏ trước, code tối thiểu, test xanh
- Không hardcode mã thủ tục trong production
- Fixture dùng mã cụ thể là dữ liệu test, không phải logic
- Mọi thay đổi hành vi phải có test
- Chạy full suite trước khi báo xong
```

## 14.4. Test đáng chú ý

```text
test_question_parser_components.py
test_procedure_relations.py
test_graph_components_query.py
test_graph_components_regression.py
test_graph_evidence_contract.py
test_evidence_fusion.py
test_case_resolver_generic.py
test_answer_documents_full.py
test_notes_facet.py
test_refusals.py
test_feedback.py
test_chat_api.py
```

---

# 15. GIỚI HẠN VÀ VIỆC TIẾP THEO

## 15.1. Giới hạn hiện tại

```text
- 1.004873 không có thời hạn trong dữ liệu nguồn
  → trả "chưa ghi nhận thời hạn", không bịa
- 3.000153 không có thành phần liên thông
- procedure_themes chỉ có 1 canonical_code
- FAQ hiện đang 0 bản ghi
- Chưa có Phase 6 gold set/evaluation chính thức
- Chưa có Phase 7 ToG/PCST/community summary
- Neo4j local có thể không chạy; production dùng container
```

## 15.2. Việc nên làm tiếp

```text
1. Phase 6 tối thiểu
   - gold set 10–15 câu
   - regression relation + hồ sơ
   - kiểm tra log workflow_trace

2. Nếu cần GraphRAG nâng cao
   - interlinked cluster: cha + anh em + con
   - citation source_code/source_url cho quan hệ
   - "chưa ghi nhận" cho quan hệ rỗng

3. Phase 7 chỉ khi thực sự cần
   - 7.1 ToG: multi-hop không xác định mã
   - 7.2 PCST: subgraph vượt context budget
   - 7.3 community summary: câu hỏi toàn cục
```

## 15.3. Không nên làm

```text
- Không dựng lại A0
- Không hardcode mã/từ khóa vào route
- Không thay PostgreSQL bằng search index
- Không bật ToG/PCST mặc định
- Không xóa volume khi chưa backup
```

---

# 16. DÀNH CHO CODING AGENT

## 16.1. Trước khi sửa

```text
1. Đọc AGENTS.md
2. Đọc guide này
3. Xác định task thuộc tầng nào
4. Tìm test hiện có
5. Viết test đỏ trước
6. Sửa tối thiểu
7. Chạy full test + lint
```

## 16.2. File theo loại task

| Task | File chính |
|---|---|
| Câu hỏi / facet | `question_frame.py`, `question_parser.py` |
| Routing / planner | `planner.py`, `plan_class.py`, `graph.py` |
| Grounding | `grounding.py`, `resolver.py`, `fact_lookup.py` |
| Graph query | `graph_shapes.py`, `graph_query.py`, `graph_capabilities.py` |
| Section / hồ sơ | `sections.py`, `executor.py`, `case_resolver.py` |
| Câu trả lời | `answer.py`, `refusals.py` |
| Evidence | `evidence.py`, `executor.py` |
| Feedback | `api/feedback.py`, `MessageAnswer.tsx` |
| Deploy | `docker-compose.prod.yml`, `nginx.conf` |

## 16.3. Quy tắc bất biến

```text
1. PostgreSQL là SSOT.
2. Search/Graph index là phái sinh, có thể dựng lại.
3. Mọi câu trả lời phải có detail_url.
4. "Chưa ghi nhận" khác "không có".
5. Không hardcode danh sách thủ tục/từ khóa/route.
6. Không dùng LLM viết Cypher.
7. Mọi thay đổi hành vi phải có test.
8. Không commit `.env`, dữ liệu, log.
```

## 16.4. Trạng thái hiện tại

```text
Dữ liệu: 1.874 thủ tục / 24.512 chunk
Backend: FastAPI + workflow RAG + GraphRAG
Graph: thành phần/liên thông đã chạy
Hồ sơ: trả đủ case, có Lưu ý
Feedback: like/dislike mọi assistant response được lưu
Test: 1038 passed, 1 skipped
Phase 6: chưa chính thức
Phase 7: chưa làm
```

---

# 17. TÓM TẮT MỘT CÂU

```text
Đây là hệ thống chatbot TTHC Gia Lai đã chạy production trên VPS + Cloudflare Tunnel,
dùng PostgreSQL làm SSOT, hybrid search Elasticsearch + Qdrant, Knowledge Graph Neo4j,
workflow RAG FastAPI, trả lời có citation, hỗ trợ hồ sơ đầy đủ và feedback like/dislike.
```
