# HƯỚNG DẪN KIẾN TRÚC & TRIỂN KHAI DỰ ÁN TOÀN DIỆN (PROJECT GUIDE V4.1)
## Đề tài: Ứng dụng RAG và Knowledge Graph để xây dựng Chatbot AI hỗ trợ tra cứu Thủ tục hành chính tại tỉnh Gia Lai

---

## MỤC LỤC TỔNG QUAN
1. **Tuyên ngôn Kiến trúc, Phạm vi Dữ liệu & Nguyên tắc Ràng buộc**
2. **Chuẩn hóa Phân loại Nghiệp vụ (15 Domain Groups & 43 Canonical Fields)**
3. **Cấu trúc Không gian Lưu trữ & Thư mục Đồng bộ (Google Drive & Repository Skeleton)**
4. **Quy chuẩn Hợp đồng Dữ liệu (Data Contract, PostgreSQL DDL & Neo4j Graph Schema)**
5. **Kiến trúc Hệ thống Hai Tầng & Mô hình Hai Tầng Chân lý (Two-Tier Truth Model)**
6. **Lộ trình Triển khai Chi tiết 16 Giai đoạn (Phase 1 – Phase 16)**
7. **Khung Biện luận & Trả lời Phản biện trước Hội đồng Chấm thi**

---

## 1. TUYÊN NGÔN KIẾN TRÚC, PHẠM VI DỮ LIỆU & NGUYÊN TẮC RÀNG BUỘC

### 1.1. Phạm vi Dữ liệu Nghiệp vụ (Data Scope Definition)
* **Khái niệm chuẩn xác về tập dữ liệu:** Hệ thống sử dụng **Bộ dữ liệu Thủ tục hành chính (TTHC) công bố trên Cổng Dịch vụ công Quốc gia, áp dụng thực thi theo thẩm quyền phân cấp trên địa bàn tỉnh Gia Lai**.
* **Quy mô tập dữ liệu thực tế:** Gồm **1.929 TTHC**, bao phủ **168 lĩnh vực nguồn**. Toàn bộ 19 cơ quan ban hành gốc là các Bộ, Cục, Ban, Ngành Trung ương (Bộ Nông nghiệp và Môi trường: 357, Bộ Công Thương: 247, Bộ Khoa học và Công nghệ: 247, Bộ Tư pháp: 198, Bộ Xây dựng: 193, Bộ Văn hóa, Thể thao và Du lịch: 165...). Về cấp thực hiện, dữ liệu ghi nhận 13 giá trị phân cấp và nhiều thủ tục thực hiện đồng thời ở nhiều cấp: **1.462 TTHC đúng cấp tỉnh**, **257 TTHC đúng cấp xã**, **370 TTHC có thực hiện ở cấp xã** (kể cả thủ tục đa cấp). Dữ liệu **không có cấp huyện** — phù hợp với mô hình hành chính hiện hành chỉ còn cấp tỉnh và cấp xã.
* **Chuẩn hóa nghiệp vụ:** 168 lĩnh vực nguồn được quy hoạch gọn gàng về **43 Lĩnh vực chuẩn hóa (Canonical Fields)** thuộc **15 Nhóm Lĩnh vực lớn (Domain Groups)**.

### 1.2. Tuyên ngôn Về Độ chính xác & Triệt tiêu Ảo giác (Hallucination Policy)
Hệ thống thiết lập nguyên tắc kiểm soát ảo giác theo **Mô hình Hai Tầng Chân lý (Two-Tier Truth Model)**:
1. **Tầng Chân lý Tuyệt đối (Deterministic Metadata Truth - 100%):** Đối với các thuộc tính định danh (Mã TTHC, Tên TTHC, Cấp thực hiện, Cơ quan ban hành, Số/Ngày Quyết định), hệ thống **triệt tiêu hoàn toàn ảo giác (Zero Hallucination - 100%)** bằng cơ chế truy vấn trực diện cơ sở dữ liệu quan hệ (PostgreSQL Fact Lookup), không qua tầng sinh của LLM.
2. **Tầng Chân lý Trích xuất (Extracted Content Truth - Mục tiêu Faithfulness ≥ 0.98):** Đối với nội dung hướng dẫn chi tiết trích xuất từ văn bản PDF (Thành phần hồ sơ, Thời hạn giải quyết, Phí/Lệ phí, Trình tự thực hiện), hệ thống sử dụng Retrieval-Augmented Generation (RAG) với cơ chế **Trích dẫn bắt buộc (Strict Provenance)**: Mọi câu trả lời sinh ra bởi LLM đều phải kèm trích dẫn số quyết định công bố, mã thủ tục và vị trí tài liệu nguồn; mục tiêu định lượng đo lường bằng Ragas là **Độ trung thực (Faithfulness) ≥ 0.98** và **Độ liên quan (Answer Relevance) ≥ 0.95**.

### 1.3. Nguyên tắc Lưu trữ Đa hệ (Polyglot Persistence) & SSOT
* **PostgreSQL là Nguồn chân lý duy nhất (Single Source of Truth - SSOT):** Mọi thực thể có cấu trúc, quan hệ phân cấp, metadata và các phân đoạn văn bản bóc tách từ PDF đều được lưu trữ tập trung tại PostgreSQL.
* **Các CSDL còn lại là các phép chiếu chỉ mục (Projections / Auxiliary Search Indexes):**
  * **Elasticsearch:** Chỉ mục tra cứu từ khóa chính xác BM25 (Số quyết định, Mã TTHC, tên viết tắt, cụm từ chuyên ngành).
  * **Qdrant:** Chỉ mục vector phục vụ tìm kiếm ngữ nghĩa theo ngôn ngữ tự nhiên và Semantic FAQ Cache.
  * **Neo4j:** Đồ thị tri thức biểu diễn liên kết đa chiều giữa Thủ tục - Cơ quan thụ lý - Cơ quan thẩm quyền - Cơ quan phối hợp - Cấp thực hiện.

### 1.4. Ràng buộc Hạ tầng Vận hành
* Toàn bộ hệ thống được tối ưu hóa để vận hành bền bỉ trên môi trường đồ án sinh viên: **VPS Ubuntu (16 – 32GB RAM, 4 – 8 vCPU, 50 – 100GB SSD)**.
* Toàn bộ dịch vụ hạ tầng (PostgreSQL, Elasticsearch, Qdrant, Neo4j, Redis, Backend API) được container hóa và điều phối bằng một tệp `docker-compose.yml` duy nhất với hạn mức RAM (Memory Limits) chặt chẽ cho từng container.

---

## 2. CHUẨN HÓA PHÂN LOẠI NGHIỆP VỤ (15 DOMAIN GROUPS & 43 CANONICAL FIELDS)

Toàn bộ 168 lĩnh vực nguồn được quy nạp thành 15 Domain Groups. Mảng Cư trú/Xuất nhập cảnh (ngành dọc Công an) được tách biệt hoàn toàn khỏi mảng Quốc phòng/Ngoại vụ để tối ưu hóa không gian vector và phản ánh đúng thẩm quyền hành chính địa phương.

Cột **Số Lĩnh Vực Nguồn** dưới đây là kết quả phân nhóm trực tiếp từ dữ liệu gốc và **cộng đúng 168**; danh sách đầy đủ 168 dòng nằm ở **Phụ lục A** và tệp `config/field_mapping.csv` (43 Canonical Fields):

| STT | Mã Thư mục (`Domain_Group`) | Tên Nhóm Lĩnh Vực Lớn | Số Lĩnh Vực Nguồn | Cơ quan Quản lý / Thụ lý chính | Lĩnh vực Nguồn Tiêu biểu |
|:---:|---|---|:---:|---|---|
| 1 | `01. TU_PHAP_BO_TRO` | Tư pháp, Hộ tịch & Bổ trợ tư pháp | 20 | Sở Tư pháp | Hộ tịch, Quốc tịch, Chứng thực, Công chứng, Luật sư, Đấu giá tài sản, Thừa phát lại, Giám định tư pháp... |
| 2 | `02. TAI_NGUYEN_MOI_TRUONG` | Tài nguyên, Đất đai, Khoáng sản & Môi trường | 10 | Sở Nông nghiệp và Môi trường | Đất đai, Đo đạc bản đồ, Môi trường, Biến đổi khí hậu, Địa chất khoáng sản, Tài nguyên nước... |
| 3 | `03. NONG_LAM_THUY_SAN` | Nông nghiệp, Lâm nghiệp, Thủy sản & PTNT | 13 | Sở Nông nghiệp và Môi trường | Trồng trọt, BVTV, Chăn nuôi, Thú y, Lâm nghiệp, Kiểm lâm, Thủy sản, Thủy lợi, Đê điều... |
| 4 | `04. DOANH_NGHIEP_DAU_TU` | Đăng ký Doanh nghiệp, Hợp tác xã & Đầu tư | 11 | Sở KH&ĐT, Ban QL Khu kinh tế | Đăng ký DN, Hộ kinh doanh, Hợp tác xã, Đầu tư trong/ngoài nước, ODA, KCN, KKT... |
| 5 | `05. CONG_THUONG_NANG_LUONG` | Công nghiệp, Năng lượng, Thương mại & Thị trường | 20 | Sở Công Thương | Xuất nhập khẩu, Thương mại điện tử, Điện lực, Năng lượng tái tạo, Dầu khí, Khí đốt, Hóa chất, Vật liệu nổ... |
| 6 | `06. XAY_DUNG_GIAO_THONG` | Xây dựng, Nhà ở, Quy hoạch & GTVT | 11 | Sở Xây dựng, Sở GTVT | Hoạt động xây dựng, Nhà ở, BĐS, Quy hoạch đô thị, Hạ tầng kỹ thuật, Đường bộ, Đường sắt, Đăng kiểm... |
| 7 | `07. LAO_DONG_AN_SINH_XA_HOI` | Lao động, Việc làm, Người có công & An sinh | 14 | Sở Lao động - TB&XH | Việc làm, Tiền lương, Người có công, Bảo trợ xã hội, An toàn vệ sinh lao động, Trẻ em, BHXH... |
| 8 | `08. Y_TE_SUC_KHOE` | Y tế, Khám chữa bệnh, Dược phẩm & Mỹ phẩm | 7 | Sở Y tế | Khám bệnh, chữa bệnh, Phòng bệnh, Y dược cổ truyền, Dược phẩm, Mỹ phẩm, Thiết bị y tế... |
| 9 | `09. GIAO_DUC_DAO_TAO` | Giáo dục, Đào tạo & Giáo dục nghề nghiệp | 12 | Sở Giáo dục & Đào tạo | Mầm non, Tiểu học, Trung học, GDTX, Giáo dục nghề nghiệp, Tuyển sinh, Văn bằng chứng chỉ... |
| 10 | `10. THONG_TIN_KHOA_HOC_CN` | Khoa học, Công nghệ, Bưu chính & Viễn thông | 14 | Sở KH&CN, Sở TT&TT | Khoa học công nghệ, Sở hữu trí tuệ, Tiêu chuẩn đo lường, Bưu chính, Viễn thông, Tần số, Báo chí, Xuất bản... |
| 11 | `11. VAN_HOA_THE_THAO_DU_LICH` | Văn hóa, Di sản, Thể thao & Du lịch | 11 | Sở Văn hóa, Thể thao & Du lịch | Di sản văn hóa, Nghệ thuật biểu diễn, Mỹ thuật triển lãm, Quảng cáo, Thể dục thể thao, Du lịch, Gia đình... |
| 12 | `12. TAI_CHINH_NGAN_SACH` | Tài chính, Giá cả, Thuế, Phí & Công sản | 8 | Sở Tài chính, Cục Thuế, Hải quan | Quản lý giá, Quản lý công sản, Tài chính đất đai, Thuế, Phí lệ phí, Hải quan... |
| 13 | `13. NOI_VU_TON_GIAO_DAN_TOC` | Cán bộ công chức, Tôn giáo, Dân tộc & Thi đua | 9 | Sở Nội vụ, Ban Dân tộc | Cán bộ công chức, Tổ chức hội quỹ, Thi đua khen thưởng, Văn thư lưu trữ, Tín ngưỡng tôn giáo, Công tác dân tộc... |
| 14 | **`14. AN_NINH_TRAT_TU_CU_TRU`** | **An ninh trật tự, Cư trú & Xuất nhập cảnh** | **2** | **Công an tỉnh Gia Lai, Công an Xã/Phường** | **Đăng ký quản lý cư trú (thường trú, tạm trú, nơi ở); Quản lý xuất nhập cảnh (Thẻ ABTC, hộ chiếu)...** |
| 15 | **`15. QUOC_PHONG_NGOAI_VU`** | **Quốc phòng, Ngoại vụ & Sự cố đặc thù** | **6** | **Bộ CHQS tỉnh Gia Lai, Sở Ngoại vụ** | **Quản lý vùng trời (phương tiện bay không người lái), Sự cố tràn dầu BQP, Hội nghị quốc tế, Hợp tác quốc tế...** |
| **Tổng** | **15 Nhóm Lĩnh Vực Lớn** | **Toàn bộ TTHC áp dụng tại Gia Lai** | **168** | **Đầy đủ 43 Lĩnh vực chuẩn hóa (Canonical Fields)** | |

---

## 3. CẤU TRÚC KHÔNG GIAN LƯU TRỮ & THƯ MỤC ĐỒNG BỘ

Để bảo đảm tính tương thích tuyệt đối giữa hệ thống lưu trữ Google Drive, mã nguồn pipeline và Admin UI, toàn bộ tên đường dẫn và artifact được đồng bộ hóa thống nhất:

### 3.1. Cấu trúc Quản trị Dữ liệu trên Google Drive (`DATA/`)
```text
DATA/
├── 00_DANH_MUC/
│   ├── Taxonomy_TTHC_Gia_Lai_168_Linh_Vuc_15_Groups.xlsx  <-- Bảng ánh xạ 168 lĩnh vực về 15 nhóm
│   ├── danh_sach_tthc_bo_tinh_xa.json                      <-- File JSON danh mục chủ gốc (1.929 bản ghi)
│   ├── procedure_manifest.csv                              <-- Bảng kiểm soát tiến độ bóc tách & hash SHA-256
│   └── validation_report.csv                               <-- Báo cáo kiểm định chất lượng bóc tách
│
├── 01_TAI_LIEU_THO/                                       <-- Lưu trữ toàn bộ PDF thô theo 15 nhóm
│   ├── 01. TU_PHAP_BO_TRO/
│   ├── 02. TAI_NGUYEN_MOI_TRUONG/
│   │   ├── 1.115336.pdf
│   │   └── ...
│   ├── 03. NONG_LAM_THUY_SAN/
│   ├── 04. DOANH_NGHIEP_DAU_TU/
│   ├── 05. CONG_THUONG_NANG_LUONG/
│   │   ├── 1.000172.pdf
│   │   └── ...
│   ├── 06. XAY_DUNG_GIAO_THONG/
│   │   ├── 2.001234.pdf
│   │   └── ...
│   ├── 07. LAO_DONG_AN_SINH_XA_HOI/
│   ├── 08. Y_TE_SUC_KHOE/
│   ├── 09. GIAO_DUC_DAO_TAO/
│   ├── 10. THONG_TIN_KHOA_HOC_CN/
│   ├── 11. VAN_HOA_THE_THAO_DU_LICH/
│   ├── 12. TAI_CHINH_NGAN_SACH/
│   ├── 13. NOI_VU_TON_GIAO_DAN_TOC/
│   ├── 14. AN_NINH_TRAT_TU_CU_TRU/                        <-- Chứa PDF về Cư trú, Thẻ ABTC
│   └── 15. QUOC_PHONG_NGOAI_VU/                            <-- Chứa PDF về Tràn dầu, Bay không người lái
│
├── 02_KET_QUA_DOC/
│   ├── parsed_procedures.jsonl                             <-- Dữ liệu bóc tách thô từ OpenDataLoader PDF
│   └── chunks.jsonl                                        <-- Dữ liệu phân đoạn chuẩn hóa nạp DB/Index
│
└── 03_DU_LIEU_LOI/
    └── failed_files_log.csv                                <-- Nhật ký các file hỏng, lỗi parse
```

### 3.2. Cấu trúc Mã nguồn Dự án (`tthc-ai-chatbot/`)
```text
tthc-ai-chatbot/
├── .env.example
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── data/
│   ├── raw/                                                <-- Mount từ 01_TAI_LIEU_THO của Drive
│   ├── metadata/
│   │   ├── Taxonomy_TTHC_Gia_Lai_168_Linh_Vuc_15_Groups.xlsx
│   │   ├── tthc_master_catalog.json
│   │   ├── procedure_manifest.csv                          <-- Admin UI đọc kiểm soát tiến độ
│   │   └── validation_report.csv                           <-- Admin UI đọc kiểm tra tỷ lệ lỗi
│   ├── processed/
│   │   ├── parsed_procedures.jsonl                         <-- Output từ parser
│   │   └── chunks.jsonl                                    <-- Output từ section chunker
│   └── failed/
│       └── failed_files_log.csv
├── data_pipeline/
│   ├── __init__.py
│   ├── ingest_manifest.py                                  <-- Quét thư mục, tính SHA-256, sinh manifest
│   ├── pdf_parser.py                                       <-- Parse PDF sang parsed_procedures.jsonl
│   ├── section_chunker.py                                  <-- Tách section & sinh chunks.jsonl
│   ├── load_postgres.py                                    <-- Nạp PostgreSQL (procedures, agencies, sections)
│   ├── build_graph.py                                      <-- Dựng thực thể & quan hệ trên Neo4j
│   ├── index_elasticsearch.py                              <-- Tạo BM25 Index với bộ phân tích tiếng Việt
│   └── index_qdrant.py                                     <-- Tạo Dense Vector & Payload Index
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── database/
│   │   ├── postgres.py                                     <-- SQLAlchemy / asyncpg engine
│   │   ├── neo4j_client.py                                 <-- Async Neo4j Driver
│   │   ├── elastic.py                                      <-- Async Elasticsearch Client
│   │   └── qdrant_client.py                                <-- Async Qdrant Client
│   ├── core/
│   │   ├── embeddings.py
│   │   └── reranker.py
│   ├── graph/
│   │   ├── state.py                                        <-- TypedDict AgentState
│   │   ├── router.py                                       <-- LLM Router phân loại 15 Domain Groups & 3 Nhánh
│   │   ├── nodes/
│   │   │   ├── faq_cache_node.py                           <-- Tầng 1: Fast-path FAQ (Cosine >= 0.90)
│   │   │   ├── fact_lookup_node.py                         <-- Tầng 2: Tra cứu PostgreSQL
│   │   │   ├── hybrid_search_node.py                       <-- Tầng 2: Elastic + Qdrant + RRF + Reranker
│   │   │   ├── graph_query_node.py                         <-- Tầng 2: Cypher Execution trên Neo4j
│   │   │   └── synthesizer_node.py                         <-- Tổng hợp phản hồi kèm trích dẫn pháp lý
│   │   └── workflow.py                                     <-- StateGraph Orchestration
│   └── api/
│       ├── main.py                                         <-- FastAPI app
│       ├── routes.py                                       <-- Chat, Lookup, Admin metrics endpoints
│       └── schemas.py                                      <-- Pydantic v2 Models
└── tests/
    ├── test_ingest.py
    ├── test_retrieval.py
    └── test_router.py
```

---

## 4. QUY CHUẨN HỢP ĐỒNG DỮ LIỆU & LƯỢC ĐỒ CSDL (DATA CONTRACTS & SCHEMAS)

### 4.1. Hợp đồng Bảng kiểm soát (`procedure_manifest.csv`)
Tệp CSV quản lý tiến độ bóc tách vật lý, làm việc trực tiếp với Admin UI:
* `procedure_code` (VARCHAR): Mã TTHC (ví dụ: `"1.115336"`).
* `procedure_name` (TEXT): Tên thủ tục (đối chiếu từ catalog JSON).
* `domain_group` (VARCHAR): 1 trong 15 nhóm lớn.
* `source_field` (VARCHAR): Lĩnh vực nguồn nguyên bản.
* `canonical_field` (VARCHAR): Lĩnh vực chuẩn hóa.
* `pdf_path` (TEXT): Đường dẫn tương đối từ `data/raw/`.
* `file_size` (BIGINT): Kích thước byte của tệp PDF.
* `content_hash` (CHAR(64)): Mã băm SHA-256 tính toán từ tệp PDF.
* `ingest_status` (VARCHAR): `PENDING` | `PARSED` | `FAILED_EMPTY` | `FAILED_PARSE`.

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
    issuing_agency TEXT NOT NULL,              -- Cơ quan ban hành (Cấp Bộ/Trung ương)
    target_audience TEXT,                      -- Đối tượng thực hiện (Công dân, Doanh nghiệp...)
    procedure_type VARCHAR(100),              -- Loại thủ tục hành chính
    decision_number VARCHAR(100),             -- Số quyết định công bố
    decision_date VARCHAR(50),                -- Ngày ban hành quyết định
    requirements TEXT,                        -- Yêu cầu, điều kiện thực hiện
    status VARCHAR(50) DEFAULT 'Đã công khai',
    content_hash CHAR(64) NOT NULL,
    pdf_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tạo GIN Index hỗ trợ tìm kiếm mảng cấp thực hiện cực nhanh
CREATE INDEX idx_procedures_levels ON procedures USING GIN (administrative_levels);
CREATE INDEX idx_procedures_domain ON procedures(domain_group);
CREATE INDEX idx_procedures_canonical ON procedures(canonical_field);

-- 2. Bảng nối Cơ quan tham gia đa vai trò (Giải quyết Cơ quan phối hợp, Ủy quyền, Thụ lý)
CREATE TABLE procedure_agencies (
    id SERIAL PRIMARY KEY,
    procedure_code VARCHAR(50) NOT NULL REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    agency_name TEXT NOT NULL,
    role VARCHAR(50) NOT NULL,                -- 'THUC_HIEN', 'THAM_QUYEN', 'PHOI_HOP', 'UY_QUYEN'
    CONSTRAINT chk_agency_role CHECK (role IN ('THUC_HIEN', 'THAM_QUYEN', 'PHOI_HOP', 'UY_QUYEN'))
);

CREATE INDEX idx_proc_agencies_code ON procedure_agencies(procedure_code);
CREATE INDEX idx_proc_agencies_name_role ON procedure_agencies(agency_name, role);

-- 3. Bảng phân đoạn nghiệp vụ chức năng (Trích xuất từ PDF)
CREATE TABLE procedure_sections (
    section_id VARCHAR(100) PRIMARY KEY,       -- Cấu trúc: {procedure_code}:{section_type}
    procedure_code VARCHAR(50) NOT NULL REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    section_type VARCHAR(50) NOT NULL,         -- 'REQUIRED_DOCUMENTS', 'PROCESSING_TIME', 'FEE', 'STEPS', 'LEGAL_BASIS'
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    page_number INT,                           -- Số trang PDF chứa thông tin (Strict Provenance)
    raw_table_json JSONB,                      -- Lưu trữ bảng lệ phí/hồ sơ nếu có cấu trúc bảng
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sections_procedure_code ON procedure_sections(procedure_code);
CREATE INDEX idx_sections_type ON procedure_sections(section_type);
```

### 4.3. Lược đồ Đồ thị Tri thức Neo4j (Knowledge Graph Schema)
Xử lý chính xác tính chất đa cấp và giải quyết điểm nghẽn 66.3% trường Thẩm quyền bị `null`:

* **Các Nhãn Đỉnh Nguyên tử (Atomic Node Labels):**
  * `(:Procedure {code: STRING, name: STRING})`
  * `(:Agency {name: STRING})`
  * `(:DomainGroup {name: STRING})`
  * `(:CanonicalField {name: STRING})`
  * `(:TargetAudience {name: STRING})`
  * `(:AdminLevel {name: STRING})` — *Gồm 5 đỉnh nguyên tử chuẩn:* `Cấp bộ`, `Cấp tỉnh`, `Cấp xã`, `Cơ quan khác`, `Chưa xác định`. Dữ liệu **không có** `Cấp huyện` vì mô hình hành chính hiện hành đã bỏ cấp trung gian này.
* **Các Mối quan hệ Xác định (Deterministic Relationships):**
  * `(:Procedure)-[:BELONGS_TO]->(:DomainGroup)`
  * `(:Procedure)-[:CLASSIFIED_AS]->(:CanonicalField)`
  * `(:Procedure)-[:ISSUED_BY]->(:Agency)`
  * `(:Procedure)-[:EXECUTED_BY]->(:Agency)`
  * `(:Procedure)-[:COORDINATES_WITH]->(:Agency)` *(Biểu diễn 31 thủ tục có cơ quan phối hợp)*
  * `(:Procedure)-[:AUTHORIZED_TO]->(:Agency)` *(Biểu diễn 7 thủ tục có cơ quan được ủy quyền)*
  * `(:Procedure)-[:APPLIES_TO]->(:TargetAudience)`
  * `(:Procedure)-[:RESOLVED_AT_LEVEL]->(:AdminLevel)` *(Một thủ tục nối tới nhiều đỉnh AdminLevel nếu là thủ tục đa cấp, ví dụ nối cả `Cấp tỉnh` và `Cấp xã`)*
  * `(:Procedure)-[:AUTHORITY_OF]->(:Agency)`:
    * *Quy tắc bù khuyết thẩm quyền (Imputation Rule):* Đối với 1.279 thủ tục bị trống trường `Cơ quan có thẩm quyền` (66.3%), hệ thống gán mặc định thẩm quyền theo cấp hành chính cao nhất thụ lý thủ tục đó (ví dụ: TTHC cấp tỉnh gán thẩm quyền là *"Ủy ban nhân dân cấp tỉnh"* hoặc *"Chủ tịch Ủy ban nhân dân cấp tỉnh"*), đồng thời đánh dấu thuộc tính `is_inferred: true` trên cạnh quan hệ để phân biệt với thẩm quyền công bố tường minh (`is_inferred: false`).

---

## 5. KIẾN TRÚC HỆ THỐNG HAI TẦNG & MÔ HÌNH HAI TẦNG CHÂN LÝ

```text
                             [Người dùng nhập Câu hỏi]
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │    TẦNG 1: SEMANTIC FAQ CACHE (FAST-PATH)     │
                 │    - Qdrant Collection: faq_cache             │
                 │    - Tính khoảng cách Cosine Similarity       │
                 └───────────────────────────────────────────────┘
                                         │
                     ┌───────────────────┴───────────────────┐
            >= 0.90 (Cache Hit)                     < 0.90 (Cache Miss)
                     │                                       │
                     ▼                                       ▼
            [Trả ngay kết quả chuẩn]         ┌───────────────────────────────┐
            Độ trễ < 100ms                   │ TẦNG 2: LANGGRAPH WORKFLOW    │
            Tiêu tốn 0 token LLM             │ ROUTER (qwen-flash điều phối) │
                                             └───────────────────────────────┘
                                                             │
                  ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
                  │                                          │                                          │
                  ▼                                          ▼                                          ▼
         [Nhánh 1: FACT_LOOKUP]                    [Nhánh 2: HYBRID_SEARCH]                   [Nhánh 3: GRAPH_QUERY]
         - Động cơ: PostgreSQL                     - Động cơ: Elastic + Qdrant               - Động cơ: Neo4j Cypher
         - Mục tiêu: Tra cứu trực diện             - Mục tiêu: Hướng dẫn nghiệp vụ           - Mục tiêu: Tra cứu liên ngành
         - Chân lý: Metadata Tuyệt đối             - Chân lý: Trích xuất có căn cứ           - Căn cứ: Đa cơ quan thụ lý,
           (Mã, Tên, Cấp, Quyết định, Cơ quan)       (Hồ sơ, Trình tự, Phí, Thời hạn)          phân cấp & cơ quan phối hợp
                  │                                          │                                          │
                  └──────────────────────────────────────────┼──────────────────────────────────────────┘
                                                             │
                                                             ▼
                                             ┌───────────────────────────────┐
                                             │ RESPONSE SYNTHESIZER          │
                                             │ (deepseek-flash / qwen-flash) │
                                             │ - Kiểm soát Căn cứ trích dẫn  │
                                             │ - Guardrails kiểm duyệt mã    │
                                             └───────────────────────────────┘
                                                             │
                                                             ▼
                                               [Phản hồi Cuối cùng cho Dân]
```

---

## 6. LỘ TRÌNH TRIỂN KHAI CHI TIẾT 16 GIAI ĐOẠN (PHASE 1 – PHASE 16)

---

### GIAI ĐOẠN 1: KHỞI TẠO DỰ ÁN & MÔI TRƯỜNG PHÁT TRIỂN (PHASE 1)
* **Mục tiêu:** Thiết lập khung xương dự án chuẩn mực, kiểm soát toàn diện dependencies bằng công cụ hiện đại, cấu hình logging và biến môi trường sẵn sàng cho container hóa.
* **Các công việc thực hiện:**
  1. Khởi tạo repository `tthc-ai-chatbot` với `git`.
  2. Sử dụng trình quản lý gói `uv` để tạo môi trường ảo và file `pyproject.toml`.
  3. Cài đặt các thư viện lõi: `fastapi`, `uvicorn`, `pydantic>=2.0`, `langchain`, `langgraph`, `qdrant-client`, `elasticsearch`, `psycopg[binary]`, `neo4j`, `pandas`, `openpyxl`.
  4. Tạo file cấu hình môi trường `.env.example` chuẩn hóa (chứa chuỗi kết nối các DB và API keys của mô hình).
  5. Xây dựng module `src/config.py` đọc cấu hình bằng Pydantic BaseSettings.
* **Tiêu chuẩn nghiệm thu (Acceptance Criteria):** Chạy lệnh `uv run python -m src.config` in ra cấu hình hợp lệ, không có cảnh báo deprecation hay xung đột phiên bản thư viện.

---

### GIAI ĐOẠN 2: THIẾT LẬP TAXONOMY & CẤU TRÚC LƯU TRỮ VẬT LÝ (PHASE 2)
* **Mục tiêu:** Áp dụng mô hình **15 Domain Groups** và **43 Canonical Fields** vào hệ thống lưu trữ vật lý trên Google Drive và kho dữ liệu máy chủ.
* **Các công việc thực hiện:**
  1. Tổ chức 4 thư mục lớn trên Google Drive: `00_DANH_MUC`, `01_TAI_LIEU_THO`, `02_KET_QUA_DOC`, `03_DU_LIEU_LOI`.
  2. Tạo đủ 15 thư mục con bên trong `01_TAI_LIEU_THO` từ `01. TU_PHAP_BO_TRO` đến `15. QUOC_PHONG_NGOAI_VU`.
  3. Di chuyển 47 file PDF mẫu hiện có vào đúng thư mục nhóm: Đất đai đưa vào `02. TAI_NGUYEN_MOI_TRUONG`, Đường bộ đưa vào `06. XAY_DUNG_GIAO_THONG`.
  4. Đổi tên toàn bộ các file PDF về dạng `{procedure_code}.pdf`.
  5. Xuất tệp `Taxonomy_TTHC_Gia_Lai_168_Linh_Vuc_15_Groups.xlsx` đưa vào thư mục `data/metadata/`.
* **Tiêu chuẩn nghiệm thu:** Toàn bộ 47 file PDF mẫu nằm đúng thư mục nhóm, tên file là chuỗi số chuẩn, không chứa ký tự tiếng Việt hoặc khoảng trắng.

---

### GIAI ĐOẠN 3: SINH BẢNG KIỂM SOÁT TIẾN ĐỘ & HỢP ĐỒNG DỮ LIỆU (PHASE 3)
* **Mục tiêu:** Tự động hóa quá trình quét cây thư mục, trích xuất metadata xác định từ đường dẫn và tính toán mã băm SHA-256 để chống trùng lặp.
* **Các công việc thực hiện:**
  1. Viết script `data_pipeline/ingest_manifest.py`.
  2. Quét đệ quy toàn bộ file `.pdf` trong `data/raw/` (mount từ `01_TAI_LIEU_THO`).
  3. Phân tách đường dẫn để lấy `Domain_Group`, `Mã TTHC`.
  4. Đọc luồng byte để tính chuỗi băm mật mã `SHA-256` cho từng file.
  5. Tra cứu mã thủ tục vào tệp `tthc_master_catalog.json` để bổ sung tên thủ tục và lĩnh vực nguồn.
  6. Xuất ra file `data/metadata/procedure_manifest.csv` với trạng thái `PENDING`.
* **Tiêu chuẩn nghiệm thu:** File CSV sinh ra đủ 47 dòng mẫu, không có trường nào bị `NULL` ở các cột khóa, mã SHA-256 là chuỗi hex 64 ký tự chuẩn.

---

### GIAI ĐOẠN 4: THỬ NGHIỆM & CHẠY HÀNG LOẠT OPENDATALOADER PDF (PHASE 4)
* **Mục tiêu:** Chuyển đổi định dạng văn bản hành chính từ PDF sang dữ liệu có cấu trúc trung gian, bảo toàn nguyên vẹn bảng biểu và thứ tự đọc.
* **Các công việc thực hiện:**
  1. Xây dựng môi trường xử lý văn bản nặng trên Google Colab / máy cục bộ với công cụ đọc chuyên dụng (OpenDataLoader PDF / pdfplumber engine).
  2. Chạy thử nghiệm bóc tách trên 5 file mẫu phức tạp (chọn file Đất đai có bảng biểu phí/lệ phí và file Đường bộ có bảng thành phần hồ sơ).
  3. Kiểm tra bằng mắt chất lượng văn bản bóc tách: độ nguyên vẹn của bảng biểu, thứ tự tiêu đề - nội dung, độ chính xác của dấu tiếng Việt.
  4. Viết script `data_pipeline/pdf_parser.py` chạy xử lý hàng loạt trên tập dữ liệu, xuất kết quả vào tệp trung gian `data/processed/parsed_procedures.jsonl`.
  5. Cập nhật trạng thái `PARSED` vào `data/metadata/procedure_manifest.csv`.
* **Tiêu chuẩn nghiệm thu:** Tệp `parsed_procedures.jsonl` chứa đủ các bản ghi, không bị lỗi font tiếng Việt, các bảng thành phần hồ sơ giữ nguyên cấu trúc dòng/cột.

---

### GIAI ĐOẠN 5: PHÂN RÃ SECTION & TRÍCH XUẤT THỰC THỂ PHÁP LÝ (PHASE 5)
* **Mục tiêu:** Chia nhỏ văn bản thủ tục thành các phân đoạn nghiệp vụ chức năng (Sections) có ý nghĩa tra cứu rõ rệt, thay vì chia đoạn ngẫu nhiên theo số lượng ký tự.
* **Các công việc thực hiện:**
  1. Xây dựng script `data_pipeline/section_chunker.py` sử dụng biểu thức chính quy (Regex) và luật mẫu hành chính Việt Nam để nhận diện các tiêu đề chuẩn:
     * `Trình tự thực hiện` $
ightarrow$ `STEPS`
     * `Thành phần, số lượng hồ sơ` $
ightarrow$ `REQUIRED_DOCUMENTS`
     * `Thời hạn giải quyết` $
ightarrow$ `PROCESSING_TIME`
     * `Phí, lệ phí` $
ightarrow$ `FEE`
     * `Căn cứ pháp lý` $
ightarrow$ `LEGAL_BASIS`
  2. Trích xuất các thực thể định lượng: Số ngày làm việc, Số tiền lệ phí (VNĐ), Tên văn bản luật (Luật Đất đai, Nghị định...).
  3. Gán định danh duy nhất cho từng phân đoạn theo định dạng `{procedure_code}:{section_type}` và xuất ra file `data/processed/chunks.jsonl`.
* **Tiêu chuẩn nghiệm thu:** Mỗi thủ tục bóc tách ra tối thiểu 4 section chính. Không xảy ra hiện tượng mất nội dung bảng lệ phí hoặc nhầm lẫn giữa hồ sơ và trình tự.

---

### GIAI ĐOẠN 6: KHỞI TẠO CƠ SỞ DỮ LIỆU GỐC POSTGRESQL (SSOT) (PHASE 6)
* **Mục tiêu:** Thiết lập cơ sở dữ liệu quan hệ PostgreSQL đóng vai trò Nguồn chân lý duy nhất (SSOT), bảo đảm tính toàn vẹn dữ liệu ở cấp độ cao nhất.
* **Các công việc thực hiện:**
  1. Khởi chạy PostgreSQL thông qua Docker Compose.
  2. Thực thi script DDL tạo bảng `procedures`, `procedure_agencies` và `procedure_sections` kèm các ràng buộc Khóa chính, Khóa ngoại và GIN Index.
  3. Viết script `data_pipeline/load_postgres.py`:
     * Đọc tệp danh mục chủ `tthc_master_catalog.json` để nạp các thông tin thuộc tính hành chính vào bảng `procedures` (chuyển đổi chuỗi cấp hành chính thành mảng `TEXT[]`).
     * Phân tách cơ quan thực hiện, thẩm quyền, phối hợp, ủy quyền vào bảng `procedure_agencies`.
     * Đọc tệp `data/processed/chunks.jsonl` để nạp nội dung chi tiết vào bảng `procedure_sections`.
  4. Thiết lập trigger tự động cập nhật trường `updated_at`.
* **Tiêu chuẩn nghiệm thu:** Lệnh kiểm tra `SELECT COUNT(*) FROM procedures;` phản ánh đúng số lượng bản ghi nạp vào; truy vấn tìm kiếm theo mảng `administrative_levels @> ARRAY['Cấp xã']` đạt thời gian dưới 5ms.

---

### GIAI ĐOẠN 7: DỰNG ĐỒ THỊ TRI THỨC TRÊN NEO4J (PHASE 7)
* **Mục tiêu:** Chuyển hóa các quan hệ quản lý hành chính phức tạp (Cơ quan ban hành, Thẩm quyền quyết định, Đơn vị thụ lý, Cơ quan phối hợp, Cấp hành chính) thành một Knowledge Graph liên kết đa chiều.
* **Các công việc thực hiện:**
  1. Khởi chạy instance Neo4j Community Edition (qua Docker).
  2. Thiết lập ràng buộc duy nhất (Unique Constraints) trên các đỉnh: `(:Procedure {code})`, `(:Agency {name})`, `(:DomainGroup {name})`, `(:AdminLevel {name})`.
  3. Viết script `data_pipeline/build_graph.py` đọc dữ liệu từ PostgreSQL:
     * Tạo các đỉnh `Procedure`, `Agency`, `DomainGroup`, `AdminLevel` (5 đỉnh nguyên tử), `TargetAudience`.
     * Tạo các cạnh quan hệ: `[:BELONGS_TO]`, `[:ISSUED_BY]`, `[:EXECUTED_BY]`, `[:COORDINATES_WITH]`, `[:AUTHORIZED_TO]`, `[:APPLIES_TO]`, `[:RESOLVED_AT_LEVEL]`.
     * Thực hiện quy tắc gán bù thẩm quyền mặc định cho các bản ghi bị khuyết, đánh dấu cờ `is_inferred: true` trên cạnh `[:AUTHORITY_OF]`.
* **Tiêu chuẩn nghiệm thu:** Giao diện Neo4j Browser hiển thị đồ thị mạng lưới kết nối rõ ràng; thực thi câu lệnh Cypher tra cứu thủ tục có sự phối hợp liên ngành hoặc tra cứu thủ tục cấp xã trả về kết quả chính xác tức thì.

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
  4. Viết script `data_pipeline/index_elasticsearch.py` đồng bộ dữ liệu từ PostgreSQL sang Elasticsearch.
* **Tiêu chuẩn nghiệm thu:** Thực hiện các truy vấn gõ tắt không dấu, tìm mã số quyết định hoặc cụm từ viết tắt hành chính đều trả về đúng thủ tục mong muốn với điểm BM25 cao nhất.

---

### GIAI ĐOẠN 9: ĐÁNH CHỈ MỤC TÌM KIẾM NGỮ NGHĨA TRÊN QDRANT (PHASE 9)
* **Mục tiêu:** Xây dựng chỉ mục tìm kiếm vector ngữ nghĩa (Dense Vector Search) để hiểu được các câu hỏi diễn đạt tự nhiên của người dân khi không dùng thuật ngữ chuyên môn.
* **Các công việc thực hiện:**
  1. Khởi chạy cụm cơ sở dữ liệu vector Qdrant.
  2. Tạo Collection `procedure_semantic` với khoảng cách Cosine, kích thước vector 1024 chiều (tương ứng mô hình `bge-m3`).
  3. Viết script `data_pipeline/index_qdrant.py`:
     * Ghép nối ngữ cảnh: `[Tên TTHC] + [Lĩnh vực] + [Tên Section] + [Nội dung chi tiết]`.
     * Tạo vector nhúng thông qua mô hình Embedding.
     * Nạp vector vào Qdrant kèm theo trường `payload` đầy đủ: `{procedure_code, domain_group, canonical_field, administrative_levels, section_type}`.
  4. Tạo Payload Index trên Qdrant cho trường `domain_group` và `administrative_levels` để hỗ trợ lọc trước khi tìm kiếm vector (Pre-filtering).
* **Tiêu chuẩn nghiệm thu:** Tìm kiếm câu hỏi ngôn ngữ đời thường (ví dụ: *"làm giấy tờ cho con mới sinh cần gì"*) tìm ra đúng thủ tục Đăng ký khai sinh trong top 3 kết quả.

---

### GIAI ĐOẠN 10: XÂY DỰNG TẦNG FAST-PATH SEMANTIC FAQ CACHE (PHASE 10)
* **Mục tiêu:** Cắt giảm độ trễ và chi phí tính toán cho các câu hỏi phổ biến thông qua tầng đệm ngữ nghĩa thông minh ở Tầng 1.
* **Các công việc thực hiện:**
  1. Tạo Collection riêng biệt `faq_cache` trên Qdrant.
  2. Soạn thảo tập dữ liệu mẫu gồm 100+ cặp câu hỏi - câu trả lời chuẩn xác đã được thẩm định pháp lý cho các thủ tục phổ biến nhất (Đất đai, Cư trú, GPLX, Hộ tịch).
  3. Nhúng vector các câu hỏi mẫu và nạp vào Collection `faq_cache`.
  4. Viết module `src/graph/nodes/faq_cache_node.py`:
     * Khi nhận câu hỏi từ người dùng, tính toán vector và so khớp độ tương đồng Cosine với kho câu hỏi mẫu.
     * Nếu điểm tương đồng $\ge 0.90 
ightarrow$ Trả về ngay câu trả lời đã lưu trữ (Cache Hit), đánh dấu cờ kết thúc luồng.
     * Nếu điểm tương đồng $< 0.90 
ightarrow$ Đưa câu hỏi tiếp tục xuống Tầng 2 (Cache Miss).
* **Tiêu chuẩn nghiệm thu:** Các câu hỏi trong tập mẫu phản hồi với độ trễ dưới 100ms, không tiêu tốn token gọi mô hình suy luận lớn.

---

### GIAI ĐOẠN 11: PHÁT TRIỂN ĐỘNG CƠ TÌM KIẾM LAI KẾT HỢP RERANKER (PHASE 11)
* **Mục tiêu:** Triển khai cơ chế Hybrid Search kết hợp thế mạnh của BM25 (chính xác từ khóa) và Dense Vector (hiểu ngữ nghĩa) bằng thuật toán Reciprocal Rank Fusion (RRF).
* **Các công việc thực hiện:**
  1. Viết module `src/graph/nodes/hybrid_search_node.py`.
  2. Thực hiện truy vấn song song đồng thời vào Elasticsearch và Qdrant.
  3. Áp dụng công thức dung hợp thứ hạng RRF với hằng số $k = 60$:
     $$RRF\_Score(d) = rac{1}{60 + Rank_{BM25}(d)} + rac{1}{60 + Rank_{Vector}(d)}$$
  4. Lấy ra Top 10 tài liệu có điểm RRF cao nhất.
  5. Đưa danh sách Top 10 qua mô hình Reranker (như `bge-reranker-large` hoặc tương đương) để chấm điểm lại mức độ liên quan theo ngữ cảnh câu hỏi, chọn ra Top 3 – Top 5 đoạn văn bản tinh hoa nhất.
* **Tiêu chuẩn nghiệm thu:** Tỷ lệ truy xuất trúng tài liệu (Hit Rate@3) đạt trên 95% trên bộ câu hỏi đánh giá kiểm thử.

---

### GIAI ĐOẠN 12: ĐỘNG CƠ TRUY VẤN ĐỒ THỊ CHUYÊN BIỆT (GRAPH QUERY ENGINE) (PHASE 12)
* **Mục tiêu:** Giải quyết các câu hỏi phức tạp về thẩm quyền, liên thông cơ quan, cơ quan phối hợp và cây cấu trúc thủ tục mà các phương pháp tìm kiếm văn bản thông thường không làm được.
* **Các công việc thực hiện:**
  1. Viết module `src/graph/nodes/graph_query_node.py`.
  2. Xây dựng tập mẫu các mẫu câu hỏi định tuyến sang đồ thị:
     * Tra cứu theo cấp thực hiện: *"Những thủ tục đất đai nào do cấp xã trực tiếp thụ lý?"*
     * Tra cứu theo cơ quan phối hợp: *"Thủ tục nào do Sở Tài nguyên Môi trường thực hiện nhưng có sự phối hợp của Công an tỉnh?"*
     * Tra cứu theo nhóm đối tượng: *"Liệt kê các thủ tục ngành công thương áp dụng cho người nước ngoài?"*
  3. Sử dụng mô hình Router để trích xuất các thực thể (`Entity Extraction`) và sinh câu truy vấn Cypher chuẩn xác qua các Cypher Template an toàn.
  4. Thực thi câu lệnh trên Neo4j và cấu trúc hóa kết quả trả về dạng danh mục thực thể.
* **Tiêu chuẩn nghiệm thu:** Các câu hỏi liên quan đến cây thẩm quyền và cơ quan phối hợp trả về đầy đủ danh sách mã thủ tục trong thời gian dưới 50ms.

---

### GIAI ĐOẠN 13: XÂY DỰNG WORKFLOW ROUTER BẰNG LANGGRAPH (PHASE 13)
* **Mục tiêu:** Xây dựng bộ điều phối trạng thái luồng làm việc xác định (Deterministic Workflow) bằng LangGraph, thay thế cho mô hình ReAct Agent tự do thiếu kiểm soát.
* **Các công việc thực hiện:**
  1. Định nghĩa cấu trúc `AgentState` trong `src/graph/state.py` chứa: `question`, `domain_group`, `intent_type`, `fact_result`, `search_results`, `graph_result`, `final_answer`, `citations`.
  2. Xây dựng Node điều hướng `Router` sử dụng mô hình ngôn ngữ tốc độ cao (`qwen-flash`) với kỹ thuật Structured Output (ép kiểu JSON):
     * Phân loại câu hỏi vào đúng 1 trong 15 `domain_group`.
     * Định tuyến luồng xử lý vào 1 trong 3 nhánh:
       * `FACT_LOOKUP`: Nếu câu hỏi chứa mã TTHC cụ thể hoặc hỏi về các thuộc tính định danh (Cơ quan ban hành, Cấp thực hiện, Số quyết định).
       * `GRAPH_QUERY`: Nếu câu hỏi hỏi về danh sách thủ tục theo thẩm quyền, cấp hành chính, cơ quan phối hợp, cơ quan được ủy quyền.
       * `HYBRID_SEARCH`: Nếu câu hỏi hỏi về hướng dẫn quy trình, hồ sơ giấy tờ, lệ phí, thời hạn giải quyết.
  3. Biên dịch biểu đồ luồng `StateGraph` với các cạnh rẽ nhánh có điều kiện (Conditional Edges).
* **Tiêu chuẩn nghiệm thu:** Độ chính xác phân loại định tuyến (Routing Accuracy) đạt trên 98% trên tập dữ liệu đánh giá 100 câu hỏi đa dạng.

---

### GIAI ĐOẠN 14: TỔNG HỢP CÂU TRẢ LỜI, TRÍCH DẪN & HÀNG RÀO AN TOÀN (PHASE 14)
* **Mục tiêu:** Tổng hợp câu trả lời tự nhiên, rõ ràng, dễ hiểu cho người dân nhưng bắt buộc phải có trích dẫn căn cứ pháp lý và tuân thủ nguyên tắc không bịa đặt.
* **Các công việc thực hiện:**
  1. Viết module `src/graph/nodes/synthesizer_node.py` sử dụng mô hình LLM chính (`deepseek-flash` hoặc `qwen-flash`).
  2. Thiết kế System Prompt chuẩn mực pháp lý:
     * Ràng buộc câu trả lời chỉ được sử dụng dữ liệu được cung cấp trong Context.
     * Bắt buộc trích dẫn rõ: `Mã thủ tục`, `Tên thủ tục`, `Cơ quan thực hiện`, `Số quyết định công bố` và `Số trang PDF nguồn`.
     * Nếu thông tin trong tài liệu không đề cập (ví dụ lệ phí ghi không quy định), phải trả lời rõ ràng là không thu phí hoặc chưa có quy định, tuyệt đối không suy đoán.
  3. Xây dựng bộ kiểm duyệt sau sinh (Post-generation Guardrails): Quét kiểm tra xem mã thủ tục và cơ quan xuất hiện trong câu trả lời có thực sự tồn tại trong Context hay không; nếu không khớp sẽ tự động chặn và cảnh báo.
* **Tiêu chuẩn nghiệm thu:** 100% câu trả lời đều có trích dẫn mã thủ tục hợp lệ; đạt chỉ số Faithfulness ≥ 0.98 trên tập đánh giá.

---

### GIAI ĐOẠN 15: ĐÓNG GÓI API VÀ ORCHESTRATION DOCKER COMPOSE (PHASE 15)
* **Mục tiêu:** Đóng gói toàn bộ hệ sinh thái dịch vụ thành một khối thống nhất, dễ dàng triển khai, demo và bảo trì trên bất kỳ máy chủ nào chỉ với một câu lệnh.
* **Các công việc thực hiện:**
  1. Xây dựng ứng dụng FastAPI trong `src/api/` với các endpoint chuẩn:
     * `POST /api/v1/chat`: Tiếp nhận câu hỏi và trả về câu trả lời kèm siêu dữ liệu trích dẫn (Metadata Citations).
     * `GET /api/v1/procedures/{code}`: Tra cứu thông tin chi tiết một thủ tục trực tiếp từ PostgreSQL.
     * `GET /api/v1/admin/metrics`: Cung cấp số liệu tiến độ bóc tách từ `procedure_manifest.csv` và `validation_report.csv` cho Admin UI.
     * `GET /api/v1/health`: Kiểm tra tình trạng kết nối tới 4 cơ sở dữ liệu.
  2. Viết file `Dockerfile` đa tầng (Multi-stage build) để tối ưu kích thước image backend.
  3. Hoàn thiện file `docker-compose.yml` điều phối toàn bộ cụm dịch vụ:
     * Service `postgres` (Cổng 5432)
     * Service `neo4j` (Cổng 7474, 7687)
     * Service `elasticsearch` (Cổng 9200)
     * Service `qdrant` (Cổng 6333)
     * Service `backend-api` (Cổng 8000)
  4. Cấu hình giới hạn bộ nhớ (Memory Limits) cho từng container để đảm bảo hệ thống vận hành ổn định trên VPS 16 – 32GB RAM.
* **Tiêu chuẩn nghiệm thu:** Chạy lệnh `docker compose up -d`, toàn bộ 5 dịch vụ khởi động thành công và vượt qua bài kiểm tra Healthcheck trong vòng 60 giây.

---

### GIAI ĐOẠN 16: ĐÁNH GIÁ ĐỘ ĐO RAG CHUYÊN SÂU & CHUẨN BỊ BẢO VỆ (PHASE 16)
* **Mục tiêu:** Thực hiện đánh giá định lượng hệ thống theo tiêu chuẩn học thuật quốc tế (khung đánh giá RAG Triad / Ragas) để đưa số liệu thuyết phục vào báo cáo tốt nghiệp.
* **Các công việc thực hiện:**
  1. Xây dựng tập dữ liệu kiểm thử vàng (Golden Evaluation Dataset) gồm 150 câu hỏi gắn nhãn chuẩn mặt đất (Ground Truth) bao phủ toàn bộ 15 nhóm lĩnh vực.
  2. Đo lường các chỉ số cốt lõi:
     * **Faithfulness (Độ trung thực):** Đảm bảo câu trả lời không chứa thông tin nằm ngoài ngữ cảnh (Mục tiêu ≥ 0.98).
     * **Answer Relevance (Độ liên quan của câu trả lời):** Đánh giá mức độ trả lời đúng trọng tâm câu hỏi của dân (Mục tiêu ≥ 0.95).
     * **Context Precision & Recall:** Đánh giá chất lượng của bộ tìm kiếm lai Hybrid Search (Mục tiêu ≥ 0.90).
     * **End-to-End Latency:** Đo lường thời gian phản hồi trung bình (Cache hit < 100ms; Hybrid search < 1.5s).
  3. Chụp ảnh các đồ thị, sơ đồ kiến trúc, biểu đồ thời gian phản hồi để đưa vào Chương 4 (Thực nghiệm & Đánh giá) của quyển báo cáo.
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

#### Câu hỏi 2: Tại sao lại tách thành 15 Domain Groups mà không giữ 14 nhóm hay gom theo 19 Cơ quan ban hành?
* **Lập luận trả lời:**
  > *"Thứ nhất, không thể gom theo Cơ quan ban hành vì một cơ quan phụ trách rất nhiều mảng nghiệp vụ khác nhau (như Ban QL Khu kinh tế phụ trách cả Đất đai, Môi trường, Xây dựng), và người dân đi làm thủ tục thì tìm theo 'nội dung cần làm' chứ không thể biết trước cơ quan nào thụ lý.
  > Thứ hai, nhóm nghiên cứu quyết định tách riêng nhóm **`14. AN_NINH_TRAT_TU_CU_TRU`** (thuộc thẩm quyền ngành dọc của Công an như thường trú, tạm trú, hộ chiếu) ra khỏi nhóm **`15. QUOC_PHONG_NGOAI_VU`** vì hai mảng này khác biệt hoàn toàn về cơ quan quản lý và tần suất sử dụng của công dân. Mảng cư trú có tần suất hỏi rất cao, việc tách riêng giúp triệt tiêu nhiễu không gian vector (Embedding noise), nâng độ chính xác định tuyến của Router lên mức tối đa."*

#### Câu hỏi 3: Làm thế nào hệ thống đảm bảo Chatbot không bịa đặt thông tin (Hallucination) khi hướng dẫn thủ tục?
* **Lập luận trả lời:**
  > *"Hệ thống kiểm soát ảo giác qua Mô hình Hai Tầng Chân lý (Two-Tier Truth Model):
  > 1. Đối với thông tin thuộc tính định danh (Mã, Cấp, Cơ quan, Quyết định), hệ thống triệt tiêu hoàn toàn ảo giác (Zero Hallucination) bằng cách truy vấn trực diện PostgreSQL, bỏ qua LLM sinh từ.
  > 2. Đối với nội dung chi tiết bóc tách từ PDF (hồ sơ, trình tự, lệ phí), mô hình ngôn ngữ bị ràng buộc chặt chẽ trong Context, bắt buộc trích dẫn số quyết định công bố và số trang tài liệu nguồn.
  > 3. Hệ thống có bộ kiểm duyệt sau sinh (Post-Guardrails) để đối soát mã TTHC trong câu trả lời với CSDL trước khi phản hồi cho người dân, đạt chỉ số Faithfulness ≥ 0.98."*

#### Câu hỏi 4: Trường Cơ quan có thẩm quyền bị khuyết 66.3% trong dữ liệu mở, đồ thị Neo4j xử lý thế nào?
* **Lập luận trả lời:**
  > *"Đây là đặc thù thực tế của dữ liệu Cổng DVC Quốc gia khi nhiều thủ tục không ghi nhận cơ quan thẩm quyền độc lập (do thẩm quyền mặc định thuộc cơ quan thực hiện hoặc UBND tỉnh). Hệ thống xử lý bằng nguyên tắc bù khuyết dữ liệu có kiểm soát (Imputation Heuristic): Gán mặc định thẩm quyền theo cấp hành chính cao nhất thụ lý thủ tục, đồng thời gắn cờ `is_inferred: true` trên cạnh quan hệ trong Neo4j. Điều này vừa giúp đồ thị không bị đứt đoạn khi truy vấn liên thông, vừa đảm bảo tính trung thực học thuật khi báo cáo trước Hội đồng."*

#### Câu hỏi 5: Tầng 1 Semantic FAQ Cache mang lại lợi ích gì cho hệ thống dịch vụ công?
* **Lập luận trả lời:**
  > *"Trong thực tế hành chính công, có hơn 40% câu hỏi của người dân lặp lại cùng một nội dung (ví dụ: lệ phí làm sổ đỏ, địa chỉ làm hộ chiếu, hồ sơ cấp đổi bằng lái xe). Tầng 1 Fast-path sử dụng Qdrant đo độ tương đồng ngữ nghĩa: Với những câu hỏi tương đồng $\ge 0.90$, hệ thống trả về ngay câu trả lời mẫu đã được thẩm định pháp lý trong thời gian dưới 100ms mà không tốn một token LLM nào. Điều này vừa giúp tiết kiệm chi phí vận hành máy chủ, vừa đảm bảo tính chuẩn xác và đồng nhất tuyệt đối cho các câu hỏi phổ biến."*

---

## PHỤ LỤC A — ÁNH XẠ 168 LĨNH VỰC NGUỒN VỀ 15 NHÓM LĨNH VỰC

Bảng dưới đây là kết quả phân nhóm trực tiếp từ cột `Lĩnh vực` của `danh_sach_tthc_bo_tinh_xa.json` (168 giá trị duy nhất, 1.929 TTHC). Cột `canonical_field` là lớp chuẩn hóa trung gian giữa `source_field` và `domain_group`, được nạp vào `config/field_mapping.csv`.

### A.1. Tổng hợp theo 15 Nhóm Lĩnh vực

| STT | Mã Thư mục (`Domain_Group`) | Tên Nhóm Lĩnh Vực Lớn | Số Lĩnh vực Nguồn | Số Canonical Fields | Số TTHC |
|:---:|---|---|:---:|:---:|:---:|
| 1 | `01. TU_PHAP_BO_TRO` | Tư pháp, Hộ tịch & Bổ trợ tư pháp | 20 | 5 | 202 |
| 2 | `02. TAI_NGUYEN_MOI_TRUONG` | Tài nguyên, Đất đai, Khoáng sản & Môi trường | 10 | 3 | 149 |
| 3 | `03. NONG_LAM_THUY_SAN` | Nông nghiệp, Lâm nghiệp, Thủy sản & PTNT | 13 | 3 | 213 |
| 4 | `04. DOANH_NGHIEP_DAU_TU` | Đăng ký Doanh nghiệp, Hợp tác xã & Đầu tư | 11 | 3 | 98 |
| 5 | `05. CONG_THUONG_NANG_LUONG` | Công nghiệp, Năng lượng, Thương mại & Thị trường | 20 | 4 | 218 |
| 6 | `06. XAY_DUNG_GIAO_THONG` | Xây dựng, Nhà ở, Quy hoạch & GTVT | 11 | 3 | 189 |
| 7 | `07. LAO_DONG_AN_SINH_XA_HOI` | Lao động, Việc làm, Người có công & An sinh | 14 | 4 | 127 |
| 8 | `08. Y_TE_SUC_KHOE` | Y tế, Khám chữa bệnh, Dược phẩm & Mỹ phẩm | 7 | 3 | 119 |
| 9 | `09. GIAO_DUC_DAO_TAO` | Giáo dục, Đào tạo & Giáo dục nghề nghiệp | 12 | 2 | 91 |
| 10 | `10. THONG_TIN_KHOA_HOC_CN` | Khoa học, Công nghệ, Bưu chính & Viễn thông | 14 | 3 | 314 |
| 11 | `11. VAN_HOA_THE_THAO_DU_LICH` | Văn hóa, Di sản, Thể thao & Du lịch | 11 | 2 | 106 |
| 12 | `12. TAI_CHINH_NGAN_SACH` | Tài chính, Giá cả, Thuế, Phí & Công sản | 8 | 2 | 11 |
| 13 | `13. NOI_VU_TON_GIAO_DAN_TOC` | Cán bộ công chức, Tôn giáo, Dân tộc & Thi đua | 9 | 2 | 78 |
| 14 | `14. AN_NINH_TRAT_TU_CU_TRU` | An ninh trật tự, Cư trú & Xuất nhập cảnh | 2 | 2 | 2 |
| 15 | `15. QUOC_PHONG_NGOAI_VU` | Quốc phòng, Ngoại vụ & Sự cố đặc thù | 6 | 2 | 12 |
| **Tổng** | **15 nhóm** | **Bao phủ toàn bộ dữ liệu** | **168** | **43** | **1929** |

### A.2. Danh sách 168 lĩnh vực nguồn đã phân nhóm

| # | Lĩnh vực Nguồn (`source_field`) | Canonical Field | Domain Group | Số TTHC |
|:---:|---|---|---|:---:|
| 1 | Bồi thường nhà nước | `THI_HANH_AN_BOI_THUONG` | `01. TU_PHAP_BO_TRO` | 3 |
| 1 | Chứng thực | `CHUNG_THUC_CONG_CHUNG` | `01. TU_PHAP_BO_TRO` | 12 |
| 1 | Công chứng | `CHUNG_THUC_CONG_CHUNG` | `01. TU_PHAP_BO_TRO` | 28 |
| 1 | Giám định | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 2 |
| 1 | Giám định tư pháp | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 9 |
| 1 | Hòa giải thương mại | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 13 |
| 1 | Hòa giải ở cơ sở | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 5 |
| 1 | Hỗ trợ pháp lý cho doanh nghiệp nhỏ và vừa | `TRO_GIUP_PHAP_LY` | `01. TU_PHAP_BO_TRO` | 1 |
| 1 | Hộ tịch | `HO_TICH_QUOC_TICH` | `01. TU_PHAP_BO_TRO` | 39 |
| 1 | Luật sư | `TRO_GIUP_PHAP_LY` | `01. TU_PHAP_BO_TRO` | 20 |
| 1 | Nuôi con nuôi | `HO_TICH_QUOC_TICH` | `01. TU_PHAP_BO_TRO` | 9 |
| 1 | Quản tài viên | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 7 |
| 1 | Quốc tịch | `HO_TICH_QUOC_TICH` | `01. TU_PHAP_BO_TRO` | 5 |
| 1 | Thi hành án dân sự | `THI_HANH_AN_BOI_THUONG` | `01. TU_PHAP_BO_TRO` | 1 |
| 1 | Thừa hành viên | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 8 |
| 1 | Trọng tài thương mại | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 13 |
| 1 | Trợ giúp pháp lý | `TRO_GIUP_PHAP_LY` | `01. TU_PHAP_BO_TRO` | 12 |
| 1 | Tư vấn pháp luật | `TRO_GIUP_PHAP_LY` | `01. TU_PHAP_BO_TRO` | 6 |
| 1 | Đăng ký biện pháp bảo đảm | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 5 |
| 1 | Đấu giá tài sản | `GIAM_DINH_BO_TRO_TU_PHAP` | `01. TU_PHAP_BO_TRO` | 4 |
| 2 | Biến đổi khí hậu | `MOI_TRUONG_KHI_HAU_DA_DANG` | `02. TAI_NGUYEN_MOI_TRUONG` | 7 |
| 2 | Biển và hải đảo | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | `02. TAI_NGUYEN_MOI_TRUONG` | 14 |
| 2 | Bảo tồn thiên nhiên và Đa dạng sinh học | `MOI_TRUONG_KHI_HAU_DA_DANG` | `02. TAI_NGUYEN_MOI_TRUONG` | 9 |
| 2 | Khoáng sản | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | `02. TAI_NGUYEN_MOI_TRUONG` | 4 |
| 2 | Khí tượng, thủy văn | `MOI_TRUONG_KHI_HAU_DA_DANG` | `02. TAI_NGUYEN_MOI_TRUONG` | 4 |
| 2 | Môi trường | `MOI_TRUONG_KHI_HAU_DA_DANG` | `02. TAI_NGUYEN_MOI_TRUONG` | 4 |
| 2 | Tài nguyên nước | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | `02. TAI_NGUYEN_MOI_TRUONG` | 19 |
| 2 | Đo đạc, bản đồ và thông tin địa lý | `MOI_TRUONG_KHI_HAU_DA_DANG` | `02. TAI_NGUYEN_MOI_TRUONG` | 1 |
| 2 | Đất đai | `DAT_DAI` | `02. TAI_NGUYEN_MOI_TRUONG` | 48 |
| 2 | Địa chất và khoáng sản | `KHOANG_SAN_TAI_NGUYEN_NUOC_BIEN` | `02. TAI_NGUYEN_MOI_TRUONG` | 39 |
| 3 | An toàn đập, hồ chứa thuỷ điện | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 9 |
| 3 | Chăn nuôi | `CHAN_NUOI_THU_Y` | `03. NONG_LAM_THUY_SAN` | 21 |
| 3 | Kinh tế hợp tác và Phát triển nông thôn | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 7 |
| 3 | Kiểm lâm | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 14 |
| 3 | Lâm nghiệp và Kiểm lâm | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 27 |
| 3 | Nghề thủ công mỹ nghệ | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 1 |
| 3 | Quản lý chất lượng nông lâm sản và thủy sản | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 12 |
| 3 | Quản lý Đê điều và Phòng, chống thiên tai | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 3 |
| 3 | Thú y | `CHAN_NUOI_THU_Y` | `03. NONG_LAM_THUY_SAN` | 29 |
| 3 | Thủy lợi | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 34 |
| 3 | Thủy sản | `LAM_NGHIEP_THUY_SAN_THUY_LOI` | `03. NONG_LAM_THUY_SAN` | 30 |
| 3 | Trồng trọt | `TRONG_TROT_BVTV` | `03. NONG_LAM_THUY_SAN` | 9 |
| 3 | Trồng trọt và Bảo vệ thực vật | `TRONG_TROT_BVTV` | `03. NONG_LAM_THUY_SAN` | 17 |
| 4 | Hỗ trợ doanh nghiệp nhỏ và vừa | `DOANH_NGHIEP` | `04. DOANH_NGHIEP_DAU_TU` | 7 |
| 4 | Hỗ trợ tổ hợp tác, hợp tác xã, liên hiệp hợp tác xã | `HOP_TAC_XA_TO_HOP_TAC` | `04. DOANH_NGHIEP_DAU_TU` | 1 |
| 4 | Quản lý doanh nghiệp | `DOANH_NGHIEP` | `04. DOANH_NGHIEP_DAU_TU` | 1 |
| 4 | Quản lý nhà nước về khu công nghiệp, khu kinh tế | `DAU_TU_KCN_KKT` | `04. DOANH_NGHIEP_DAU_TU` | 3 |
| 4 | Thành lập và hoạt động của doanh nghiệp | `DOANH_NGHIEP` | `04. DOANH_NGHIEP_DAU_TU` | 30 |
| 4 | Thành lập và hoạt động của tổ hợp tác không đăng ký | `HOP_TAC_XA_TO_HOP_TAC` | `04. DOANH_NGHIEP_DAU_TU` | 2 |
| 4 | Thành lập và hoạt động của tổ hợp tác, hợp tác xã, liên hiệp hợp tác xã | `HOP_TAC_XA_TO_HOP_TAC` | `04. DOANH_NGHIEP_DAU_TU` | 19 |
| 4 | Thành lập và hoạt động doanh nghiệp (hộ kinh doanh) | `DOANH_NGHIEP` | `04. DOANH_NGHIEP_DAU_TU` | 7 |
| 4 | Thành lập và hoạt động doanh nghiệp xã hội | `DOANH_NGHIEP` | `04. DOANH_NGHIEP_DAU_TU` | 2 |
| 4 | Đầu tư bằng vốn hỗ trợ phát triển chính thức (ODA) và viện trợ không hoàn lại không thuộc hỗ trợ phát triển chính thức | `DAU_TU_KCN_KKT` | `04. DOANH_NGHIEP_DAU_TU` | 1 |
| 4 | Đầu tư tại Việt nam | `DAU_TU_KCN_KKT` | `04. DOANH_NGHIEP_DAU_TU` | 25 |
| 5 | Công nghiệp hỗ trợ | `CONG_NGHIEP` | `05. CONG_THUONG_NANG_LUONG` | 3 |
| 5 | Công nghiệp tiêu dùng | `CONG_NGHIEP` | `05. CONG_THUONG_NANG_LUONG` | 8 |
| 5 | Cụm Công nghiệp | `CONG_NGHIEP` | `05. CONG_THUONG_NANG_LUONG` | 1 |
| 5 | Dầu khí | `NANG_LUONG` | `05. CONG_THUONG_NANG_LUONG` | 1 |
| 5 | Giám định thương mại | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 2 |
| 5 | Hóa chất | `HOA_CHAT_VAT_LIEU_NO` | `05. CONG_THUONG_NANG_LUONG` | 31 |
| 5 | Kinh doanh khí | `NANG_LUONG` | `05. CONG_THUONG_NANG_LUONG` | 10 |
| 5 | Lưu thông hàng hóa trong nước | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 9 |
| 5 | Quản lý bán hàng đa cấp | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 6 |
| 5 | Sở giao dịch hàng hóa | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 4 |
| 5 | Thương mại biên giới và miền núi | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 1 |
| 5 | Thương mại quốc tế | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 26 |
| 5 | Thương mại điện tử | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 9 |
| 5 | Vận chuyển hàng hóa nguy hiểm | `HOA_CHAT_VAT_LIEU_NO` | `05. CONG_THUONG_NANG_LUONG` | 6 |
| 5 | Vật liệu nổ công nghiệp, tiền chất thuốc nổ | `HOA_CHAT_VAT_LIEU_NO` | `05. CONG_THUONG_NANG_LUONG` | 14 |
| 5 | Xuất nhập khẩu | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 53 |
| 5 | Xúc tiến thương mại | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 15 |
| 5 | bảo vệ quyền lợi người tiêu dùng | `THUONG_MAI_XTTM` | `05. CONG_THUONG_NANG_LUONG` | 2 |
| 5 | Điện | `NANG_LUONG` | `05. CONG_THUONG_NANG_LUONG` | 9 |
| 5 | Điện lực | `NANG_LUONG` | `05. CONG_THUONG_NANG_LUONG` | 8 |
| 6 | Hoạt động xây dựng | `XAY_DUNG_NHA_O_BDS` | `06. XAY_DUNG_GIAO_THONG` | 19 |
| 6 | Hàng hải và đường thủy nội địa | `GIAO_THONG_VAN_TAI` | `06. XAY_DUNG_GIAO_THONG` | 60 |
| 6 | Hạ tầng kỹ thuật | `QUY_HOACH_HA_TANG` | `06. XAY_DUNG_GIAO_THONG` | 1 |
| 6 | Kinh doanh bất động sản | `XAY_DUNG_NHA_O_BDS` | `06. XAY_DUNG_GIAO_THONG` | 9 |
| 6 | Nhà ở và công sở | `XAY_DUNG_NHA_O_BDS` | `06. XAY_DUNG_GIAO_THONG` | 21 |
| 6 | Quy hoạch đô thị và nông thôn | `QUY_HOACH_HA_TANG` | `06. XAY_DUNG_GIAO_THONG` | 5 |
| 6 | Quản lý chất lượng công trình xây dựng | `XAY_DUNG_NHA_O_BDS` | `06. XAY_DUNG_GIAO_THONG` | 3 |
| 6 | Vật liệu xây dựng | `XAY_DUNG_NHA_O_BDS` | `06. XAY_DUNG_GIAO_THONG` | 2 |
| 6 | Đăng kiểm | `GIAO_THONG_VAN_TAI` | `06. XAY_DUNG_GIAO_THONG` | 6 |
| 6 | Đường bộ | `GIAO_THONG_VAN_TAI` | `06. XAY_DUNG_GIAO_THONG` | 51 |
| 6 | Đường sắt | `GIAO_THONG_VAN_TAI` | `06. XAY_DUNG_GIAO_THONG` | 12 |
| 7 | An toàn vệ sinh lao động | `AN_TOAN_VE_SINH_LAO_DONG` | `07. LAO_DONG_AN_SINH_XA_HOI` | 2 |
| 7 | An toàn, vệ sinh lao động | `AN_TOAN_VE_SINH_LAO_DONG` | `07. LAO_DONG_AN_SINH_XA_HOI` | 4 |
| 7 | Bảo hiểm xã hội | `AN_SINH_XA_HOI` | `07. LAO_DONG_AN_SINH_XA_HOI` | 1 |
| 7 | Bảo trợ xã hội | `AN_SINH_XA_HOI` | `07. LAO_DONG_AN_SINH_XA_HOI` | 13 |
| 7 | Giảm nghèo | `AN_SINH_XA_HOI` | `07. LAO_DONG_AN_SINH_XA_HOI` | 7 |
| 7 | Kiểm định kỹ thuật an toàn lao động | `AN_TOAN_VE_SINH_LAO_DONG` | `07. LAO_DONG_AN_SINH_XA_HOI` | 2 |
| 7 | Lao động | `LAO_DONG_VIEC_LAM` | `07. LAO_DONG_AN_SINH_XA_HOI` | 3 |
| 7 | Lao động, tiền lương | `LAO_DONG_VIEC_LAM` | `07. LAO_DONG_AN_SINH_XA_HOI` | 4 |
| 7 | Lao động, tiền lương và bảo hiểm xã hội | `LAO_DONG_VIEC_LAM` | `07. LAO_DONG_AN_SINH_XA_HOI` | 1 |
| 7 | Người có công | `NGUOI_CO_CONG` | `07. LAO_DONG_AN_SINH_XA_HOI` | 52 |
| 7 | Phòng, chống tệ nạn xã hội | `AN_SINH_XA_HOI` | `07. LAO_DONG_AN_SINH_XA_HOI` | 6 |
| 7 | Quản lý lao động ngoài nước | `LAO_DONG_VIEC_LAM` | `07. LAO_DONG_AN_SINH_XA_HOI` | 9 |
| 7 | Trẻ em | `AN_SINH_XA_HOI` | `07. LAO_DONG_AN_SINH_XA_HOI` | 7 |
| 7 | Việc làm | `LAO_DONG_VIEC_LAM` | `07. LAO_DONG_AN_SINH_XA_HOI` | 16 |
| 8 | An toàn thực phẩm | `PHONG_BENH_AN_TOAN_THUC_PHAM` | `08. Y_TE_SUC_KHOE` | 23 |
| 8 | Dược phẩm | `DUOC_MY_PHAM_TBYT` | `08. Y_TE_SUC_KHOE` | 14 |
| 8 | Khám bệnh, chữa bệnh | `KHAM_CHUA_BENH` | `08. Y_TE_SUC_KHOE` | 23 |
| 8 | Mỹ phẩm | `DUOC_MY_PHAM_TBYT` | `08. Y_TE_SUC_KHOE` | 6 |
| 8 | Phòng bệnh | `PHONG_BENH_AN_TOAN_THUC_PHAM` | `08. Y_TE_SUC_KHOE` | 36 |
| 8 | Thiết bị y tế | `DUOC_MY_PHAM_TBYT` | `08. Y_TE_SUC_KHOE` | 6 |
| 8 | Y Dược cổ truyền | `DUOC_MY_PHAM_TBYT` | `08. Y_TE_SUC_KHOE` | 11 |
| 9 | Các cơ sở giáo dục khác | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 1 |
| 9 | Giáo dục mầm non | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 9 |
| 9 | Giáo dục nghề nghiệp | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | `09. GIAO_DUC_DAO_TAO` | 8 |
| 9 | Giáo dục nghề nghiệp (G07-LĐ06) | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | `09. GIAO_DUC_DAO_TAO` | 5 |
| 9 | Giáo dục thường xuyên | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 12 |
| 9 | Giáo dục tiểu học | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 4 |
| 9 | Giáo dục trung học | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 10 |
| 9 | Giáo dục và Đào tạo thuộc hệ thống giáo dục quốc dân | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | `09. GIAO_DUC_DAO_TAO` | 24 |
| 9 | Giáo dục, đào tạo với nước ngoài | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | `09. GIAO_DUC_DAO_TAO` | 4 |
| 9 | Thi, tuyển sinh | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 8 |
| 9 | Văn bằng, chứng chỉ | `GIAO_DUC_PHO_THONG` | `09. GIAO_DUC_DAO_TAO` | 4 |
| 9 | Đào tạo và Nghiên cứu khoa học | `GIAO_DUC_NGHE_NGHIEP_DAO_TAO` | `09. GIAO_DUC_DAO_TAO` | 2 |
| 10 | An toàn bức xạ và hạt nhân | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 24 |
| 10 | Báo chí | `BAO_CHI_XUAT_BAN` | `10. THONG_TIN_KHOA_HOC_CN` | 11 |
| 10 | Bưu chính | `BUU_CHINH_VIEN_THONG` | `10. THONG_TIN_KHOA_HOC_CN` | 14 |
| 10 | Bản quyền tác giả | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 4 |
| 10 | Chất lượng sản phẩm hàng hóa | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 1 |
| 10 | Công nghiệp công nghệ số, công nghệ thông tin, điện tử | `BUU_CHINH_VIEN_THONG` | `10. THONG_TIN_KHOA_HOC_CN` | 11 |
| 10 | Hoạt động khoa học và công nghệ | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 65 |
| 10 | Khoa học và Công nghệ | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 2 |
| 10 | Phát thanh, truyền hình và thông tin điện tử | `BAO_CHI_XUAT_BAN` | `10. THONG_TIN_KHOA_HOC_CN` | 22 |
| 10 | Sở hữu trí tuệ | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 17 |
| 10 | Tiêu chuẩn đo lường chất lượng | `KHCN_SHTT_TIEU_CHUAN` | `10. THONG_TIN_KHOA_HOC_CN` | 34 |
| 10 | Tần số vô tuyến điện | `BUU_CHINH_VIEN_THONG` | `10. THONG_TIN_KHOA_HOC_CN` | 49 |
| 10 | Viễn thông và Internet | `BUU_CHINH_VIEN_THONG` | `10. THONG_TIN_KHOA_HOC_CN` | 48 |
| 10 | Xuất Bản, In và Phát hành | `BAO_CHI_XUAT_BAN` | `10. THONG_TIN_KHOA_HOC_CN` | 12 |
| 11 | Di sản văn hóa | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 26 |
| 11 | Du lịch | `THE_THAO_DU_LICH_QUANG_CAO` | `11. VAN_HOA_THE_THAO_DU_LICH` | 22 |
| 11 | Gia đình | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 5 |
| 11 | Hoạt động mua bán quốc tế chuyên ngành văn hóa | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 2 |
| 11 | Mỹ thuật, nhiếp ảnh, triển lãm | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 11 |
| 11 | Nghệ thuật biểu diễn | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 4 |
| 11 | Quảng cáo | `THE_THAO_DU_LICH_QUANG_CAO` | `11. VAN_HOA_THE_THAO_DU_LICH` | 2 |
| 11 | Thể dục thể thao | `THE_THAO_DU_LICH_QUANG_CAO` | `11. VAN_HOA_THE_THAO_DU_LICH` | 23 |
| 11 | Văn hóa | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 5 |
| 11 | Văn học | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 2 |
| 11 | Điện ảnh | `DI_SAN_VAN_HOA_GIA_DINH` | `11. VAN_HOA_THE_THAO_DU_LICH` | 4 |
| 12 | Hải quan | `THUE_PHI_HAI_QUAN` | `12. TAI_CHINH_NGAN_SACH` | 1 |
| 12 | Quản lý chương trình mục tiêu quốc gia | `TAI_CHINH_NGAN_SACH_CONG_SAN` | `12. TAI_CHINH_NGAN_SACH` | 1 |
| 12 | Quản lý công sản | `TAI_CHINH_NGAN_SACH_CONG_SAN` | `12. TAI_CHINH_NGAN_SACH` | 1 |
| 12 | Quản lý giá | `TAI_CHINH_NGAN_SACH_CONG_SAN` | `12. TAI_CHINH_NGAN_SACH` | 1 |
| 12 | Quản lý thuế, phí, lệ phí và thu khác của ngân sách nhà nước | `THUE_PHI_HAI_QUAN` | `12. TAI_CHINH_NGAN_SACH` | 1 |
| 12 | Tài chính đất đai | `TAI_CHINH_NGAN_SACH_CONG_SAN` | `12. TAI_CHINH_NGAN_SACH` | 1 |
| 12 | Tài sản kết cấu hạ tầng chợ do Nhà nước đầu tư, quản lý | `TAI_CHINH_NGAN_SACH_CONG_SAN` | `12. TAI_CHINH_NGAN_SACH` | 3 |
| 12 | Đăng ký hoạt động của Ngân hàng Chính sách xã hội | `TAI_CHINH_NGAN_SACH_CONG_SAN` | `12. TAI_CHINH_NGAN_SACH` | 2 |
| 13 | Công chức, viên chức | `NOI_VU_THI_DUA` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 2 |
| 13 | Công tác dân tộc | `TON_GIAO_DAN_TOC_HOI_QUY` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 2 |
| 13 | Công tác thanh niên | `NOI_VU_THI_DUA` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 1 |
| 13 | Quản lý nhà nước về hội, quỹ | `TON_GIAO_DAN_TOC_HOI_QUY` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 28 |
| 13 | Thi đua – Khen thưởng | `NOI_VU_THI_DUA` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 6 |
| 13 | Thi đua, khen thưởng | `NOI_VU_THI_DUA` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 3 |
| 13 | Tín ngưỡng, tôn giáo | `TON_GIAO_DAN_TOC_HOI_QUY` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 33 |
| 13 | Tổng hợp | `NOI_VU_THI_DUA` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 1 |
| 13 | Văn thư và Lưu trữ nhà nước | `NOI_VU_THI_DUA` | `13. NOI_VU_TON_GIAO_DAN_TOC` | 2 |
| 14 | Quản lý xuất nhập cảnh | `XUAT_NHAP_CANH` | `14. AN_NINH_TRAT_TU_CU_TRU` | 1 |
| 14 | Đăng ký, quản lý cư trú | `CU_TRU` | `14. AN_NINH_TRAT_TU_CU_TRU` | 1 |
| 15 | Hội nghị, hội thảo quốc tế | `NGOAI_VU_HOI_NHAP` | `15. QUOC_PHONG_NGOAI_VU` | 2 |
| 15 | Hội nhập kinh tế quốc tế | `NGOAI_VU_HOI_NHAP` | `15. QUOC_PHONG_NGOAI_VU` | 2 |
| 15 | Hợp tác quốc tế | `NGOAI_VU_HOI_NHAP` | `15. QUOC_PHONG_NGOAI_VU` | 3 |
| 15 | Quản lý vùng trời | `QUOC_PHONG_SU_CO_DAC_THU` | `15. QUOC_PHONG_NGOAI_VU` | 1 |
| 15 | Thông tin đối ngoại | `NGOAI_VU_HOI_NHAP` | `15. QUOC_PHONG_NGOAI_VU` | 1 |
| 15 | Ứng phó sự cố tràn dầu BQP | `QUOC_PHONG_SU_CO_DAC_THU` | `15. QUOC_PHONG_NGOAI_VU` | 3 |
