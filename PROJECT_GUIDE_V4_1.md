# PROJECT GUIDE V5.1 — TTHC Gia Lai Chatbot

> **Cập nhật:** 2026-11-05
> **Phạm vi:** mã nguồn, dữ liệu, kiến trúc, vận hành và triển khai production hiện tại.
> **Nguồn chuẩn:** PostgreSQL là SSOT; các kho tìm kiếm/đồ thị chỉ là chỉ mục phái sinh.

## Đề tài

**Ứng dụng RAG và Knowledge Graph để xây dựng Chatbot AI hỗ trợ tra cứu Thủ tục hành chính tại tỉnh Gia Lai.**

---

# 0. TÓM TẮT ĐIỀU HÀNH

## 0.1. Mục tiêu

Hệ thống hỗ trợ người dân:

- tra cứu thông tin TTHC bằng tiếng Việt;
- biết hồ sơ, trình tự, thời hạn, phí, kết quả, căn cứ pháp lý;
- nhận câu trả lời có nguồn (`detail_url`), không bịa khi thiếu dữ liệu;
- tra cứu quan hệ thủ tục – cơ quan – văn bản pháp lý qua Knowledge Graph;
- quản trị dữ liệu, FAQ, hội thoại, chi phí AI và tình trạng dịch vụ tại `/admin`.

## 0.2. Quy mô dữ liệu hiện tại

| Hạng mục | Giá trị |
|---|---:|
| Thủ tục trong manifest | **1.874** |
| Thủ tục trong `procedures` | **1.874** |
| File JSON gốc `data/json` | **1.874** |
| File JSON chuẩn hóa `data/json_normalized` | **1.874** |
| File raw API `data/raw/api` | **1.870** |
| Domain group | **15** |
| Source field | **166** |
| Canonical field | **51** |
| Chunk `procedure_sections` / `chunks.jsonl` | **24.512** |
| File đính kèm tham chiếu | **2.450** refs / **2.062** file unique |
| Nhóm chủ đề `procedure_themes` | **247** nhóm (khi build lại toàn bộ) |
| Mốc thời hạn `procedure_time_cases` | **2.312** mốc (khi build lại toàn bộ) |
| Tất cả manifest READY | **1.872** / 1.874 (2 bản ghi cũ còn lỗi hash) |

### Vì sao raw ít hơn 4 file?

Bốn TTHC liên thông không có UUID/raw API riêng:

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

Vì vậy `data/raw/api` có 1.870 file, còn `data/json` và `json_normalized` có 1.874.

## 0.3. Trạng thái nguồn

| Trạng thái nguồn | Số lượng |
|---|---:|
| `UPDATED` | 1.487 |
| `ACTIVE` | 378 |
| `Đã công khai` | 4 |

## 0.4. Nguyên tắc bất biến

```text
1. PostgreSQL là nguồn sự thật duy nhất (SSOT).
2. Elasticsearch, Qdrant, Neo4j là chỉ mục phái sinh — có thể xóa và dựng lại.
3. Mọi câu trả lời phải có detail_url.
4. Không bịa khi dữ liệu thiếu; phân biệt “chưa ghi nhận” và “không có”.
5. Không dựng lại mô hình A0 (procedure_identity/profile/case).
6. Không dùng Qdrant collection ngoài semantic_search/faq_search.
7. Mỗi node/edge Neo4j phải có run_id để tách bộ dữ liệu.
8. Tên biến/hàm mới dùng tiếng Anh; nội dung người dùng dùng tiếng Việt.
9. Không hardcode danh sách từ khóa/route; tín hiệu phải sinh từ dữ liệu.
10. Thay đổi hành vi phải có test tương ứng.
```

---

# 1. KIẾN TRÚC TỔNG THỂ

## 1.1. Sơ đồ luồng

```text
Người dân
  │
  ▼
chat.tthc-gialai.id.vn
  │  Cloudflare Tunnel
  ▼
Nginx frontend (:80)
  ├── /api/chat, /chat/stream ──► FastAPI backend
  ├── /api/v1/* ───────────────► FastAPI backend
  └── SPA React
                                      │
                                      ▼
                             Workflow RAG (FastAPI)
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
  PostgreSQL SSOT              Elasticsearch BM25             Qdrant vector
  procedures/sections/faq      index chatbot_tthc              semantic_search
        │                             │                             │
        └───────────────► RRF fusion ◄┴─────────────────────────────┘
                                      │
                                      ▼
                             Reranker / gate
                                      │
                                      ▼
                             Neo4j Knowledge Graph
                             quan hệ thủ tục/cơ quan/văn bản
                                      │
                                      ▼
                             DeepSeek synthesizer
                                      │
                                      ▼
                             Câu trả lời + citation
                                      │
                                      ▼
                             Cloudflare Tunnel
                                      │
                                      ▼
                             admin.tthc-gialai.id.vn
                             (Nginx admin + FastAPI admin)
```

## 1.2. Thành phần hạ tầng

| Thành phần | Image / phiên bản | Vai trò |
|---|---|---|
| PostgreSQL | `postgres:18-alpine` | SSOT: thủ tục, chunk, FAQ, user, chat, chi phí |
| SeaweedFS | `chrislusf/seaweedfs:4.50` | S3-compatible lưu file PDF/Word |
| Redis | `redis:7-alpine` | Rate limit phân tán, cache ngắn hạn |
| Qdrant | `qdrant/qdrant:v1.19.0` | Vector search |
| Neo4j | `neo4j:5-community` | Knowledge Graph |
| Elasticsearch | `elasticsearch:9.5.4` | BM25 lexical search |
| Backend | FastAPI + Python 3.12 | API, workflow RAG, admin API |
| Frontend | React 19 + Vite + Nginx | Chat client và admin UI |
| Cloudflare Tunnel | `cloudflare/cloudflared:latest` | Public HTTPS, không mở inbound 80/443 |

## 1.3. Mạng Docker

```text
edge:
  - frontend
  - backend
  - cloudflared

data (internal: true):
  - postgres
  - redis
  - qdrant
  - neo4j
  - elasticsearch
  - s3
  - backend
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
│   │   ├── api/            # chat, sessions, procedures, search, admin, docs, faq...
│   │   ├── auth/           # JWT, refresh token, user admin
│   │   ├── cost/           # ghi nhận chi phí LLM
│   │   ├── db/             # engine PostgreSQL
│   │   ├── documents/      # S3 storage, importer, repository
│   │   ├── memory/         # short-term memory, rewrite
│   │   ├── models/         # model client Qwen/DeepSeek
│   │   ├── rag/            # hybrid, graph, themes, time cases, grounding...
│   │   ├── schemas/        # Pydantic response models
│   │   ├── services/       # dịch vụ dùng chung
│   │   ├── workflow/       # LangGraph/state workflow
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── rate_limit.py
│   │   └── security_headers.py
│   ├── tests/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/            # client HTTP + config URL
│   │   ├── components/     # layout, client, admin
│   │   ├── pages/client/   # ChatPage
│   │   ├── pages/admin/    # login, overview, data, FAQ, graph, costs...
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── nginx.conf
│   └── Dockerfile
├── data/
│   ├── raw/api/            # JSON API gốc
│   ├── json/               # JSON đã chuyển đổi
│   ├── json_normalized/    # JSON chuẩn hóa
│   ├── processed/          # manifest, chunks, CSV
│   └── failed/
├── data_pipeline/
│   ├── crawler/
│   ├── processing/
│   └── indexing/
├── scripts/                # prepare, process, load, index, build...
├── db/migrations/          # migration SQL
├── config/schema.sql       # DDL nền
├── docs/                   # hướng dẫn deploy, plan
├── evaluation/             # đánh giá RAG
├── compose.yaml            # môi trường local
├── docker-compose.prod.yml # production
├── .env.example
├── .env                    # không commit
└── PROJECT_GUIDE_V4_1.md   # tài liệu này
```

---

# 3. DỮ LIỆU

## 3.1. Phân bố 15 domain group

| Domain group | Số thủ tục |
|---|---:|
| `THONG_TIN_KHOA_HOC_CONG_NGHE` | 309 |
| `CONG_THUONG_NANG_LUONG` | 238 |
| `TU_PHAP_BO_TRO` | 200 |
| `NONG_LAM_THUY_SAN` | 198 |
| `XAY_DUNG_GIAO_THONG` | 184 |
| `TAI_NGUYEN_MOI_TRUONG` | 154 |
| `VAN_HOA_THE_THAO_DU_LICH` | 121 |
| `LAO_DONG_AN_SINH_XA_HOI` | 119 |
| `Y_TE_SUC_KHOE` | 117 |
| `DOANH_NGHIEP_DAU_TU` | 99 |
| `NOI_VU_TON_GIAO_DAN_TOC` | 68 |
| `GIAO_DUC_DAO_TAO` | 48 |
| `QUOC_PHONG_NGOAI_VU` | 8 |
| `TAI_CHINH_NGAN_SACH` | 7 |
| `AN_NINH_TRAT_TU_CU_TRU` | 4 |
| **Tổng** | **1.874** |

Có **166 source field** được ánh xạ về **51 canonical field**, thuộc 15 domain group.

## 3.2. Chuỗi xử lý dữ liệu

```text
1. Crawl API DVC
   data/raw/api/*.json

2. Chuyển đổi / chuẩn hóa
   data/json/<DOMAIN>/<SOURCE_FIELD>/<code>.json
   data/json_normalized/<DOMAIN>/<SOURCE_FIELD>/<code>.json

3. Sinh manifest + chunk
   data/processed/procedure_manifest.csv
   data/processed/chunks.jsonl

4. Nạp PostgreSQL
   procedures, procedure_agencies, procedure_sections, faq

5. Sinh chỉ mục phái sinh
   Elasticsearch + Qdrant + Neo4j
```

Các lệnh chính:

```bash
uv run python scripts/prepare_data.py
uv run python scripts/process.py
uv run python scripts/build_chunks.py
uv run python scripts/build_manifest.py
uv run python scripts/load_postgres.py
uv run python scripts/index_search_stores.py --target all --recreate
uv run python -m data_pipeline.indexing.neo4j --from-postgres --database neo4j --run-id full --wipe
```

## 3.3. Cấu trúc JSON chuẩn hóa

Một file TTHC có các nhóm trường:

```text
ma_thu_tuc
detail_url
formality_id
ten_thu_tuc
so_quyet_dinh
cap_thuc_hien
loai_thu_tuc
linh_vuc
doi_tuong_thuc_hien
co_quan_co_tham_quyen
dia_chi_tiep_nhan
co_quan_duoc_uy_quyen
co_quan_phoi_hop
thu_tuc_lien_quan
trinh_tu_thuc_hien
cach_thuc_thuc_hien
thanh_phan_ho_so
execution_cases
can_cu_phap_ly
co_quan_thuc_hien
yeu_cau_dieu_kien
ket_qua_xu_ly
co_quan_ban_hanh
ngay_cap_nhat
phi
thoi_han
trang_thai
domain_group
content_hash
ngay_crawl
```

### `execution_cases`

Mỗi case gồm:

```json
{
  "case_order": 1,
  "case_code": "",
  "case_name": "",
  "components": [
    {
      "component_index": 1,
      "profile_component_id": "...",
      "name": "Tên thành phần hồ sơ",
      "original_qty": 1,
      "copy_qty": 0,
      "required": false,
      "has_electronic_form": true,
      "attachments": [],
      "source_path": "executionCases[0].profileComponents[0]"
    }
  ],
  "processing_day": {},
  "source_path": "executionCases[0]"
}
```

### `phi`

```json
{
  "loai": "MIEN_PHI | CO_DINH | THEO_SO_LUONG | CHUA_XAC_DINH",
  "so_tien": null,
  "van_ban": [],
  "mo_ta_goc": "",
  "muc_chi_tiet": []
}
```

### `thoi_han`

```json
{
  "loai": "SO | KHONG_CO | CHUA_XAC_DINH",
  "moc": [{"gia_tri": 2, "don_vi": "WORKING_DAY"}],
  "nhieu_don_vi": false,
  "muc_chi_tiet": [
    {
      "gia_tri": 2,
      "don_vi": "WORKING_DAY",
      "dieu_kien": "Điều kiện áp dụng",
      "hinh_thuc": "Trực tuyến"
    }
  ]
}
```

## 3.4. Sentinel — không được hiểu sai

```text
"Không có thông tin"  → chưa tra được / nguồn không cung cấp
"Không có"            → nguồn khẳng định không có
```

Không được trả lời “không có dữ liệu” khi thực chất chỉ là **chưa tra được**.

Các sentinel/giá trị đặc biệt trong dữ liệu:

```text
Không có thông tin
Không có
CHUA_XAC_DINH
MIEN_PHI
THEO_SO_LUONG
```

## 3.5. Manifest

File:

```text
data/processed/procedure_manifest.csv
```

Các cột quan trọng:

```text
procedure_code
procedure_name
domain_group
source_field
canonical_field
cap_thuc_hien
co_quan_ban_hanh
trang_thai
detail_url
has_formality_id
status
issues
content_hash
ngay_cap_nhat
ngay_crawl
phi_loai
phi_so_tien
thoi_han_loai
```

Hiện tại:

```text
1.874 dòng
status = READY toàn bộ
content_hash unique toàn bộ
```

## 3.6. Chunk

File:

```text
data/processed/chunks.jsonl
```

Hiện tại: **24.512 chunk**.

Mỗi chunk được nạp vào:

- `procedure_sections.section_id`
- Elasticsearch `chatbot_tthc`
- Qdrant `semantic_search`

`section_id` chính là khóa đồng bộ giữa PostgreSQL, Elasticsearch và Qdrant.

## 3.7. File đính kèm

Nguồn metadata:

```text
procedure_documents
```

File thật:

```text
SeaweedFS bucket procedure-documents
object_key = procedures/<procedure_code>/<checksum>.<ext>
```

Thống kê lần import gần nhất:

```text
Attachments: 2.450
File unique: 2.062
File refs (procedure + file_id): 2.450
Thủ tục có file: 1.248
Đã xử lý: 2.450
Upload mới: 2.043
Đã có: 239
Trùng file: 163
Lỗi: 5 (file rỗng từ nguồn)
```

Năm file lỗi thuộc các thủ tục:

```text
1.002982
1.003702
1.004819
2.002770
2.002850
```

Không tạo object rỗng trong SeaweedFS.

## 3.8. Mapping TTHC liên thông

Mapping nguồn:

```text
config/interlinked_components.json
```

Mapping hiện tại:

| Thủ tục cha | Thành phần thật |
|---|---|
| `2.002621` | `1.001193`, `1.014137` (thay `1.002535`), `1.116788` (thay `1.004222`) |
| `2.002622` | `1.000656`, `1.116788` (thay `1.003197`, đã gộp) |
| `1.014475` | `1.001029`, `1.001612`, `3.000243` |
| `2.002804` | `1.000801` |
| `3.000153` | Không có thành phần trên cổng DVC |

Quy tắc:

```text
- Không tạo node ThuTuc rỗng từ tên thành phần.
- Cạnh THANH_PHAN_CUA trỏ tới procedure_code thật.
- Nếu cổng đổi mã, sửa mapping và rebuild Neo4j.
```

---

# 4. POSTGRESQL — SSOT

## 4.1. Bảng nghiệp vụ

| Bảng | Vai trò |
|---|---|
| `procedures` | Thông tin gốc của thủ tục |
| `procedure_agencies` | Cơ quan thực hiện/thẩm quyền/phối hợp/ủy quyền |
| `procedure_sections` | Chunk nội dung; khóa đồng bộ search |
| `faq` | Câu hỏi/đáp đã duyệt hoặc draft |
| `procedure_themes` | Nhóm thủ tục theo 4 từ đầu tên |
| `procedure_time_cases` | Mốc thời hạn kèm điều kiện |
| `procedure_documents` | Metadata file đính kèm |

### `procedures`

Khóa chính:

```text
procedure_code
```

Các cột chính:

```text
procedure_name
domain_group
source_field
canonical_field
administrative_levels
issuing_agency
target_audience
procedure_type
decision_number
requirements
status
can_cu_phap_ly
thu_tuc_lien_quan
ket_qua_xu_ly
formality_id
detail_url
domain_field_code
content_hash
theme_id
created_at/updated_at
```

### `procedure_sections`

```text
section_id       = chunk_id
procedure_code
section_type
title
content
chunk_order
detail_url
metadata JSONB
```

### `procedure_documents`

Các cột quan trọng:

```text
id UUID
procedure_code
profile_component_id
file_id
file_ids
case_order
case_orders
component_index
component_indexes
document_name
file_name
mime_type
size_bytes
checksum_sha256
object_key
source_bucket/source_path/source_url
sort_order/is_active
```

Các cột `file_ids`, `case_orders`, `component_indexes` được thêm bởi migration 013–015.

## 4.2. Bảng xác thực và hội thoại

| Bảng | Vai trò |
|---|---|
| `users` | Tài khoản admin/client, Argon2id |
| `sessions` | Refresh token đã hash, rotation family |
| `chat_sessions` | Cuộc trò chuyện; hỗ trợ guest |
| `chat_messages` | Tin nhắn + metadata citation |
| `chat_session_memory` | Bộ nhớ tóm tắt hội thoại |
| `guest_sessions` | Phiên khách TTL ngắn |
| `audit_logs` | Nhật ký thao tác quản trị |
| `ai_models` | Danh mục model |
| `ai_price_versions` | Phiên bản giá |
| `ai_usage_events` | Sự kiện sử dụng/chi phí |

## 4.3. Migration hiện có

```text
20261023_002_user_roles_client_admin.sql
20261023_003_chat_sessions.sql
20261023_004_fix_chat_session_title_encoding.sql
20261026_005_session_rotation_and_last_seen.sql
20261026_006_chat_messages.sql
20261027_007_procedure_documents.sql
20261027_008_faq_general.sql
20261028_009_chat_session_memory.sql
20261029_010_chat_topic_recall_index.sql
20261030_012_section_metadata.sql
20261030_013_document_case_map.sql
20261030_014_document_case_arrays.sql
20261030_015_document_file_ids.sql
20261030_016_guest_sessions.sql
20261031_017_session_preferred_name.sql
20261031_018_session_soft_delete.sql
20261101_019_ai_costs.sql
```

Lưu ý:

```text
procedure_time_cases không được tạo bởi schema.sql.
Bảng này do scripts/build_time_cases.py tạo.
```

## 4.4. Vai trò DB

Production nên dùng role ít quyền:

```text
chatbot_app
```

Tạo bằng:

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps \
  -e DATABASE_ADMIN_URL="postgresql://postgres:<admin-password>@postgres:5432/chatbot_tthc" \
  -e APP_DB_PASSWORD="<app-password>" \
  backend python scripts/create_app_db_role.py --apply --role chatbot_app
```

Chạy **sau khi restore database**, trước khi start backend.

Có thể dùng `postgres` cho local/demo, nhưng không nên cho production public.

---

# 5. NEO4J — KNOWLEDGE GRAPH

## 5.1. Node label

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
| `THUC_HIEN` | Thủ tục – cơ quan thực hiện |
| `THAM_QUYEN` | Thủ tục – cơ quan có thẩm quyền |
| `PHOI_HOP` | Thủ tục – cơ quan phối hợp |
| `UY_QUYEN` | Thủ tục – cơ quan được ủy quyền |
| `CAN_CU_PHAP_LY` | Thủ tục – văn bản pháp lý |
| `CO_QUYET_DINH` | Thủ tục – quyết định |
| `BAN_HANH_BOI` | Văn bản – cơ quan ban hành |
| `THU_TUC_LIEN_QUAN` | Thủ tục – thủ tục liên quan |
| `THANH_PHAN_CUA` | Quan hệ thành phần của TTHC liên thông |

Một số quan hệ được suy luận từ số hiệu văn bản và đánh dấu:

```text
is_inferred = true
```

Không được coi dữ liệu suy luận là dữ liệu nguồn.

## 5.3. Dựng lại graph

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
```

Kỳ vọng hiện tại:

```text
1869
```

---

# 6. ELASTICSEARCH VÀ QDRANT

## 6.1. Elasticsearch

```text
index: chatbot_tthc
```

Dùng BM25 cho tìm kiếm từ khóa, mapping tiếng Việt và trường `section_type`, `procedure_code`.

## 6.2. Qdrant

```text
semantic_search   # vector chunk TTHC
faq_search        # vector FAQ
```

Vector:

```text
EMBEDDING_DIM=1024
```

Model nhúng phải khớp dimension và model sinh vector.

## 6.3. Dựng lại chỉ mục

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
  python scripts/index_search_stores.py --target all --recreate
```

Lưu ý:

```text
Elasticsearch reindex: không tốn embedding
Qdrant reindex: gọi API embedding, có thể tốn phí
```

Có thể dùng snapshot/copy volume thay vì reindex nếu cùng version và đã stop container.

Kiểm tra Qdrant:

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
  python -c "from backend.app.config import settings; from qdrant_client import QdrantClient; q=QdrantClient(url=settings.qdrant_host); print(q.get_collection('semantic_search').points_count)"
```

---

# 7. BACKEND FASTAPI

## 7.1. Module

```text
api/          # endpoint công khai + admin
auth/         # đăng nhập, JWT, refresh, user admin
cost/         # ghi nhận chi phí AI
db/           # engine PostgreSQL
documents/    # S3, import file
memory/       # short-term memory, rewrite
models/       # Qwen/DeepSeek client
rag/          # hybrid, rerank, graph, themes, time cases, grounding
schemas/      # Pydantic
services/     # dùng chung
workflow/     # workflow RAG
```

## 7.2. API công khai

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

## 7.3. API admin

Tất cả dưới:

```text
/api/admin
```

và yêu cầu role `admin`:

```text
GET  /api/admin/system/status
GET  /api/admin/conversations
GET  /api/admin/conversations/{id}
DELETE /api/admin/conversations/{id}

GET  /api/admin/procedures
GET  /api/admin/procedures/{code}
GET  /api/admin/procedures/{code}/sections

GET  /api/admin/faq/intents
GET  /api/admin/faq
POST /api/admin/faq
PATCH /api/admin/faq/{id}
PATCH /api/admin/faq/{id}/status
DELETE /api/admin/faq/{id}

GET  /api/admin/graph/stats
GET  /api/admin/graph
GET  /api/admin/graph/procedures/{code}

POST /api/admin/workflow/ask
POST /api/admin/retrieval/test

GET  /api/admin/costs/summary
GET  /api/v1/auth/admin/users
PATCH /api/v1/auth/admin/users/{id}
DELETE /api/v1/auth/admin/users/{id}
```

## 7.4. Xác thực

- Mật khẩu: Argon2id.
- Access token: JWT HS256, 30 phút.
- Refresh token: 30 ngày, lưu hash, rotation family.
- Cookie HttpOnly/Secure/SameSite; client và admin tách host.
- Khóa tài khoản sau 5 lần sai trong 15 phút.
- Rate limit: Redis, fallback in-memory.
- Admin API yêu cầu `require_admin`.
- `/docs` và `/openapi.json` tắt ở production.

---

# 8. RAG WORKFLOW

## 8.1. Các bước

```text
1. Chuẩn hóa câu hỏi
2. Memory rewrite (nếu bật)
3. Router/parser xác định loại câu hỏi
4. Grounding thủ tục/danh từ
5. Disambiguation / theme agreement nếu mơ hồ
6. Hybrid retrieval:
   - Elasticsearch BM25
   - Qdrant vector
   - RRF fusion
7. Rerank/gate
8. Graph lookup nếu cần quan hệ
9. Synthesize bằng DeepSeek
10. Citation + confidence + safety
11. Ghi log/workflow_trace, chat_messages, memory
```

## 8.2. Ngưỡng hiện tại

```env
FAQ_CACHE_THRESHOLD=0.76
RRF_K_CONSTANT=60
RRF_KEYWORD_WEIGHT=0.2
RRF_VECTOR_WEIGHT=0.8
HYBRID_BRANCH_K=30
HYBRID_CONTEXT_K=10
RERANKER_GATE_MIN_SCORE=0.60
CHUNK_FILTER_MIN_SCORE=0.0
MAX_RETRY_COUNT=2
```

Không đổi `RRF_KEYWORD_WEIGHT`/`RRF_VECTOR_WEIGHT` thành 50/50: đo trước đây làm giảm độ chính xác mục.

`CHUNK_FILTER_MIN_SCORE` phải để `0.0`; dùng 0.60 sẽ loại âm thầm chunk đúng điểm thấp.

## 8.3. Theme và time case

- `procedure_themes`: nhóm 4 từ đầu tên; chỉ nhóm ≥2 thành viên.
- `canonical_code` chỉ đặt cho nhóm đã rà soát thủ công.
- `procedure_time_cases`: mốc thời hạn kèm điều kiện, dùng để so khớp tình huống.

Build lại:

```bash
uv run python scripts/build_procedure_themes.py --apply
uv run python scripts/build_time_cases.py --apply
```

Hiện tại khi build toàn bộ:

```text
247 theme groups
2.312 time cases
```

Sau khi build, restart backend để xóa cache theme/time case.

---

# 9. FRONTEND

## 9.1. Client

```text
/                 ChatPage
```

Chức năng:

- gửi câu hỏi, streaming;
- lịch sử hội thoại, ghim, đổi tên, xóa;
- guest session;
- FAQ gợi ý;
- citation/detail_url trong câu trả lời;
- feedback.

## 9.2. Admin

```text
/admin                 Tổng quan
/admin/data            Dữ liệu/chunk
/admin/faq             Quản lý FAQ
/admin/graph           Đồ thị tri thức
/admin/retrieval       Kiểm thử retrieval
/admin/conversations   Lịch sử hội thoại
/admin/costs           Chi phí AI
/admin/users           Người dùng
/admin/operations      Vận hành
```

## 9.3. Tách subdomain

```text
chat.tthc-gialai.id.vn   → client
admin.tthc-gialai.id.vn  → admin
```

Cookie là host-only, không dùng `Domain=.tthc-gialai.id.vn`; client và admin là hai phiên riêng.

Điều hướng chéo phải dùng URL tuyệt đối:

```ts
chatHomeUrl()
```

trong:

```text
frontend/src/api/config.ts
frontend/src/components/layout/AdminLayout.tsx
frontend/src/pages/admin/AdminLoginPage.tsx
```

Không dùng `NavLink to="/"` trên admin host.

## 9.4. Nginx

- `chat`: chặn `/api/admin`, chặn `/admin` chuyển sang admin host.
- `admin`: `/` → `/admin`, `X-Robots-Tag: noindex`.
- `absolute_redirect off;` trong server admin.
- Phải có:

```nginx
location = /index.html {
    expires -1;
    try_files $uri =404;
}
```

Nếu thiếu, `/admin` fallback về `/index.html` rồi bị `location /` redirect `/admin` → vòng redirect.

---

# 10. DOCKER VÀ TRIỂN KHAI

## 10.1. Compose production

File:

```text
docker-compose.prod.yml
```

Project name:

```text
tracuutthc
```

Các service:

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

## 10.2. Điểm cấu hình quan trọng

### PostgreSQL 18

```yaml
volumes:
  - postgres-data:/var/lib/postgresql
```

Không dùng `/var/lib/postgresql/data` cho PostgreSQL 18.

### Neo4j

Chỉ dùng:

```yaml
NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
```

Không đặt `NEO4J_PASSWORD` trong `environment` của Neo4j; Neo4j sẽ hiểu là setting `PASSWORD` không hợp lệ và container restart.

Healthcheck:

```yaml
cypher-shell -u neo4j -p "$${NEO4J_AUTH#neo4j/}" 'RETURN 1'
```

### SeaweedFS

```yaml
S3_ENDPOINT_DOCKER: http://s3:8333
S3_BUCKET: procedure-documents
```

File cấu hình:

```text
/opt/seaweedfs/s3.json
```

Access key/secret phải khớp `.env`.

### Cloudflare

```env
CLOUDFLARE_TUNNEL_TOKEN=...
```

Chạy:

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d
```

Public Hostname:

```text
chat.tthc-gialai.id.vn  → http://frontend:80
admin.tthc-gialai.id.vn → http://frontend:80
```

Bắt buộc đặt HTTP Host Header đúng từng subdomain.

Chỉ chạy connector Cloudflare trên VPS; không chạy thêm trên laptop.

## 10.3. Thứ tự deploy

```text
1. SSH root
2. Cài Docker, swap, UFW
3. Clone repo
4. Tạo .env
5. Tạo /opt/seaweedfs/s3.json
6. docker compose build
7. up postgres/redis/qdrant/neo4j/elasticsearch/s3
8. restore PostgreSQL hoặc nạp dữ liệu
9. tạo role chatbot_app (nếu dùng)
10. import procedure_documents / SeaweedFS
11. build theme/time case
12. build Neo4j
13. index Elasticsearch/Qdrant
14. up backend/frontend
15. seed admin
16. bật Cloudflare Tunnel
```

Chi tiết lệnh:

- [deploy_root_simple.md](docs/deploy_root_simple.md) — bản root tối giản.
- [deployment_vps_cloudflare.md](docs/deployment_vps_cloudflare.md) — bản đầy đủ.

## 10.4. Kiểm tra version

```text
PostgreSQL 18
Elasticsearch 9.5.4
Qdrant 1.19.0
Neo4j 5
SeaweedFS 4.50
Redis 7
```

Không dùng volume PostgreSQL 16/Elasticsearch 8/Qdrant 1.15 với các image mới nếu chưa migrate.

---

# 11. VẬN HÀNH

## 11.1. Kiểm tra sức khỏe

```bash
cd /opt/tra_cuu_tthc

docker compose -f docker-compose.prod.yml ps
docker stats --no-stream
df -h
free -h
```

## 11.2. Backup

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

Elasticsearch: dùng snapshot repository hoặc chấp nhận reindex.

SeaweedFS: backup volume hoặc `aws s3 sync`.

## 11.3. Dọn Docker hàng tuần

```bash
cd /opt/tra_cuu_tthc

df -h
docker system df

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

# 12. LỖI THƯỜNG GẶP

## 12.1. Neo4j restart: Unrecognized setting PASSWORD

Nguyên nhân: `NEO4J_PASSWORD` nằm trong environment của service `neo4j`.

Sửa:

```yaml
environment:
  NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:?set NEO4J_PASSWORD in .env}
```

Xóa `NEO4J_PASSWORD` khỏi block `neo4j`.

## 12.2. PostgreSQL 18 restart

Kiểm tra mount:

```yaml
- postgres-data:/var/lib/postgresql
```

Nếu volume cũ tạo với PostgreSQL 16, phải dump/restore hoặc xóa volume mới.

## 12.3. `pg_restore: unsupported version (1.16)`

Dump tạo bởi PostgreSQL 18, container restore là PostgreSQL 16.

Cách xử lý:

- dùng PostgreSQL 18 ở cả hai phía; hoặc
- dump dạng plain SQL (`-Fp`) và restore bằng `psql`.

## 12.4. Admin bị `ERR_TOO_MANY_REDIRECTS`

Kiểm tra Nginx admin:

```nginx
absolute_redirect off;

location = / {
    return 302 /admin;
}

location ^~ /admin {
    try_files $uri $uri/ /index.html;
}

location = /index.html {
    try_files $uri =404;
}

location / {
    return 302 /admin;
}
```

Nếu thiếu `location = /index.html`, `/admin` fallback `/index.html` rồi bị `location /` redirect `/admin` vòng.

Sau sửa:

```bash
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d --force-recreate frontend
```

## 12.5. Admin hiện cảnh báo “không hỗ trợ kết nối bảo mật”

Kiểm tra:

```bash
curl -I https://admin.tthc-gialai.id.vn
```

Nếu `location: http://...`:

- Nginx còn redirect tuyệt đối HTTP;
- thiếu `absolute_redirect off`;
- hoặc request đi vào connector cũ (Windows).

Kiểm tra Cloudflare chỉ còn 1 connector VPS.

## 12.6. Bấm “Giao diện chatbot” vẫn ở admin

Kiểm tra frontend đã build code mới:

```bash
grep -n "chatHomeUrl" frontend/src/components/layout/AdminLayout.tsx
```

Build lại:

```bash
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d --force-recreate frontend
```

## 12.7. S3 lỗi xác thực

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python -c "from backend.app.documents.storage import S3Storage; S3Storage.from_settings().ensure_bucket(); print('S3 OK')"
```

Nếu `InvalidAccessKeyId`/`SignatureDoesNotMatch`, đối chiếu `.env` với `/opt/seaweedfs/s3.json`.

## 12.8. Cloudflare Tunnel không chạy

```bash
docker compose -f docker-compose.prod.yml ps -a | grep cloudflared
docker compose -f docker-compose.prod.yml --profile tunnel up -d
docker compose -f docker-compose.prod.yml logs --tail=100 cloudflared
```

Profile `tunnel` không tự bật nếu chạy `up` không có `--profile tunnel`.

---

# 13. KIỂM THỬ VÀ KIỂM CHỨNG

## Backend

```bash
uv run ruff check backend scripts
uv run pytest -q
```

## Frontend

```bash
cd frontend
npm run typecheck
npm run build
```

## Compose

```bash
docker compose -f docker-compose.prod.yml config
```

## Kiểm tra dữ liệu

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d chatbot_tthc -c "SELECT count(*) FROM procedures;"
```

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d chatbot_tthc -c "SELECT count(*) FROM procedure_sections;"
```

Kỳ vọng:

```text
procedures: 1869
procedure_sections: 24428
```

## Kiểm tra web

```bash
curl -I -H "Host: chat.tthc-gialai.id.vn" http://127.0.0.1:8080/health
curl -I -H "Host: admin.tthc-gialai.id.vn" http://127.0.0.1:8080/admin
```

Sau Cloudflare:

```bash
curl -I https://chat.tthc-gialai.id.vn
curl -I https://admin.tthc-gialai.id.vn
```

---

# 14. NHỮNG KHOẢNG TRỐNG VÀ LƯU Ý

## 14.1. File đính kèm

- 5 file nguồn rỗng, không thể upload.
- Cần kiểm tra lại từ cổng DVC nếu muốn bổ sung.
- Không tạo file rỗng trong SeaweedFS.

## 14.2. Theme/time case

- `procedure_themes` và `procedure_time_cases` phải build lại sau khi thay đổi `procedures`.
- Nếu DB đang có 6 theme cũ, đó là dữ liệu từ phạm vi 49 thủ tục trước đây; build lại sẽ có 247 nhóm.

## 14.3. Search store

- Nếu Qdrant/Elasticsearch trống, RAG vẫn có thể trả lời bằng PostgreSQL nhưng giảm recall.
- Reindex Qdrant tốn embedding; ưu tiên snapshot nếu cùng version.
- Không copy volume khi container đang chạy.

## 14.4. Cloudflare

- Chỉ một connector VPS.
- `admin` phải Proxied, không dùng A record trỏ IP VPS.
- Host Header phải đúng từng subdomain.
- Xóa Access nếu không dùng; Access không bắt buộc.

## 14.5. Tài nguyên

- 8GB RAM / 4–6 vCPU / 80GB SSD là cấu hình khuyến nghị.
- 6GB RAM cần giảm memory limit và thêm swap.
- Docker log đã giới hạn 10MB × 3 file mỗi container.

---

# 15. PHỤ LỤC LỆNH NHANH

## 15.1. Chạy local

```bash
docker compose -f compose.yaml up -d
uv run uvicorn backend.app.main:app --reload
cd frontend && npm run dev
```

## 15.2. Build production

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

## 15.3. Restore PostgreSQL

```bash
docker compose -f docker-compose.prod.yml cp \
  chatbot_tthc_full.dump postgres:/tmp/chatbot_tthc_full.dump

docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U postgres -d chatbot_tthc \
  --clean --if-exists --no-owner --no-privileges \
  /tmp/chatbot_tthc_full.dump
```

## 15.4. Import file đính kèm

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps \
  -v "$PWD/data/raw/api:/app/data/raw/api:ro" \
  backend python scripts/import_procedure_documents.py \
  --from-db --apply --delay 0.3
```

## 15.5. Tạo admin

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python scripts/seed_user.py --username admin --role admin --ask-password
```

## 15.6. Kiểm tra Cloudflare

```bash
docker compose -f docker-compose.prod.yml ps cloudflared
docker compose -f docker-compose.prod.yml logs --tail=100 cloudflared
```

---

# 16. KẾT LUẬN

Dự án hiện tại là hệ thống **chatbot TTHC Gia Lai** với:

```text
1.874 thủ tục
24.512 chunk
15 domain group
51 canonical field
PostgreSQL SSOT
Elasticsearch BM25
Qdrant vector
Neo4j knowledge graph
FastAPI RAG workflow
React admin/client
Cloudflare Tunnel
SeaweedFS object storage
```

Nguyên tắc vận hành:

```text
PostgreSQL là nguồn chuẩn.
Search/graph là chỉ mục có thể dựng lại.
Mọi câu trả lời phải có nguồn.
Không bịa khi thiếu dữ liệu.
Không commit .env, s3.json, dump, backup.
```
