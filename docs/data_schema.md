# Data Schema — TTHC AI Chatbot (V3)

> Nguồn: `PROJECT_GUIDE_TTHC_AI_CHATBOT_v3.md`.
> Tài liệu này chốt hình dạng dữ liệu trước khi parse toàn corpus.

## 1. Nguồn dữ liệu

```text
Cổng DVCQG → tool tải PDF có sẵn → Google Drive → PDF TTHC
```

Raw PDF **không** commit vào Git. Code ở GitHub, raw + offline output ở Google Drive,
dữ liệu phục vụ truy vấn ở PostgreSQL / Elasticsearch / Qdrant / Neo4j.

## 2. Cấu trúc folder → metadata

```text
<domain folder>/<source_field folder>/<procedure_code>.pdf
```

| Thành phần | Ví dụ | Trở thành |
|---|---|---|
| Folder lớn | `02. Tư pháp - Tòa án` | `domain_group = TU_PHAP_TOA_AN` |
| Folder con | `Hộ tịch` | `source_field = "Hộ tịch"` |
| Tên file PDF | `1.001234.pdf` | `procedure_code = "1.001234"` |

Folder chỉ dùng để **khởi tạo** metadata. Sau bước ingest, pipeline không phụ thuộc
tên folder nữa. Không dùng LLM để đoán giá trị đã lấy chắc chắn được từ path.

## 3. `procedure_manifest.csv`

Sinh bởi `data_pipeline/ingest.py`. Bắt buộc trước khi parse toàn corpus.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `procedure_code` | text | từ tên file PDF |
| `procedure_name` | text \| null | bổ sung sau nếu chưa có |
| `domain_group` | text | từ folder lớn |
| `source_field` | text | từ folder con, giữ nguyên bản |
| `pdf_path` | text | đường dẫn trong `DATA_ROOT` |
| `source_url` | text \| null | **không tạo URL giả** |
| `file_size` | int | byte |
| `content_hash` | text | SHA-256 |
| `ingest_status` | enum | xem §6 |
| `parse_status` | enum | xem §6 |
| `validation_status` | enum | xem §6 |

## 4. Taxonomy 3 lớp

```text
source_field  →  canonical_field  →  domain_group
"Hộ tịch"     →  HO_TICH          →  TU_PHAP_TOA_AN
```

`source_field` **luôn được giữ nguyên**. Một procedure có thể thuộc nhiều
`canonical_field`. Mapping nằm ở `config/field_mapping.csv`.

## 5. Chunk schema

Chunk là đơn vị tìm kiếm chung cho Elasticsearch và Qdrant — hai store **phải dùng
cùng `chunk_id`**.

```json
{
  "chunk_id": "1.001234:REQUIRED_DOCUMENTS:0",
  "procedure_code": "1.001234",
  "procedure_name": "Đăng ký lại khai sinh",
  "domain_group": "TU_PHAP_TOA_AN",
  "source_field": "Hộ tịch",
  "canonical_field": "HO_TICH",
  "section_type": "REQUIRED_DOCUMENTS",
  "section_title": "Thành phần hồ sơ",
  "chunk_order": 0,
  "content": "...",
  "agency": "...",
  "administrative_level": "...",
  "province": null,
  "source_url": "...",
  "source_file": "1.001234.pdf",
  "page_number": 3,
  "version": 1,
  "is_active": true
}
```

Các field procedure-level (`procedure_code`, `procedure_name`, `domain_group`,
`source_field`, `canonical_field`, `agency`, `administrative_level`, `province`,
`source_url`, `version`) được **kế thừa** xuống mọi chunk. Không classify lại từng
chunk bằng LLM.

## 6. Section types

```text
GENERAL_INFO
PROCEDURE_STEPS
REQUIRED_DOCUMENTS
SUBMISSION_METHOD
PROCESSING_TIME
FEE
REQUIREMENTS
RESULT
LEGAL_BASIS
OTHER
```

Ưu tiên section-aware chunking. Section ngắn: 1 section = 1 chunk. Section dài:
1 section = nhiều chunk. Không mặc định fixed 500-token cho toàn corpus.

## 7. Trạng thái

```text
ingest_status      : PENDING | DONE | DUPLICATE | ERROR
parse_status       : PENDING | DONE | PARSE_ERROR
validation_status  : READY | NEED_REVIEW | MISSING_DATA | DUPLICATE
```

Chỉ `READY` được đi tiếp vào chunking và indexing.

## 8. PostgreSQL schema

```text
procedures
fields
procedure_fields
procedure_sections
procedure_documents
legal_documents
procedure_legal_basis
```

PostgreSQL là source of truth sau normalize + validate.
