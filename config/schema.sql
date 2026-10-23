\encoding UTF8

BEGIN;

-- ════════════════════════════════════════════════════════════════════════════
-- PHẦN A — BA BẢNG NGHIỆP VỤ (SSOT)
-- ════════════════════════════════════════════════════════════════════════════

-- ── A1. Bảng Thủ tục Hành chính Gốc (Metadata Master SSOT) ──────────────────
-- 29 trường JSON không nằm hết ở đây: các trường danh sách và trường dài được
-- tách sang bảng con (procedure_agencies, procedure_sections) để truy vấn được
-- bằng index thay vì phải quét chuỗi.
CREATE TABLE IF NOT EXISTS procedures (
    procedure_code        VARCHAR(50) PRIMARY KEY,
    procedure_name        TEXT NOT NULL,
    domain_group          VARCHAR(100) NOT NULL,
    source_field          VARCHAR(255) NOT NULL,
    canonical_field       VARCHAR(255) NOT NULL,
    -- Mảng đa cấp: ARRAY['Cấp tỉnh', 'Cấp xã']
    administrative_levels TEXT[] NOT NULL DEFAULT '{}',
    issuing_agency        TEXT NOT NULL DEFAULT '',
    target_audience       TEXT,
    procedure_type        VARCHAR(100),
    decision_number       VARCHAR(100),
    decision_date         VARCHAR(50),
    requirements          TEXT,
    status                VARCHAR(50) DEFAULT 'Đã công khai',
    -- Ba cột dưới đây là bảng/biến thể có cấu trúc, lưu dạng TEXT NGUYÊN VĂN.
    --
    -- Vì sao lưu TEXT chứ không tách bảng:
    --   * `can_cu_phap_ly` là BẢNG dùng tab phân cách cột. Tách bảng thì phải
    --     parse, và parse sai một dòng là mất một viện dẫn pháp lý — trong khi
    --     đây chính là nguồn của cạnh trục `[:CAN_CU_PHAP_LY]` (8.286 cạnh).
    --     Lưu nguyên văn thì tầng dựng đồ thị tự parse bằng `split_legal_documents()`.
    --   * `thu_tuc_lien_quan` và `ket_qua_xu_ly` là chuỗi ngăn bằng `", "` / `"; "`.
    --     Tách bảng cho hai trường có 9 và 1.903 giá trị là quá mức cần thiết.
    --
    -- `ket_qua_xu_ly` tách riêng khỏi `target_audience` dù cùng là TEXT: chúng
    -- trả lời hai câu hỏi khác nhau ("ai làm" vs "nhận được gì").
    can_cu_phap_ly        TEXT,          -- bảng tab-phân-cách: Tên văn bản \t Mã văn bản
    thu_tuc_lien_quan     TEXT,          -- tên các thủ tục liên quan, ngăn bằng ", "
    ket_qua_xu_ly         TEXT,          -- kết quả người dân nhận được, ngăn bằng "; "
    -- UUID bản ghi trên cổng DVC. TEXT chứ không UUID vì:
    --   (1) 4 TTHC liên thông không có UUID — cổng dùng ID số, để NULL
    --   (2) cổng đã đổi định dạng định danh một lần rồi, TEXT chịu được cả hai
    -- Không bắt buộc; khóa đồng bộ là procedure_code.
    formality_id          TEXT,
    detail_url            TEXT,
    domain_field_code     VARCHAR(50),
    content_hash          CHAR(64) NOT NULL,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_procedures_levels
    ON procedures USING GIN (administrative_levels);
CREATE INDEX IF NOT EXISTS idx_procedures_domain      ON procedures(domain_group);
CREATE INDEX IF NOT EXISTS idx_procedures_canonical   ON procedures(canonical_field);
-- UNIQUE trên cột cho phép nhiều NULL — 4 bản ghi liên thông vẫn nạp được.
CREATE UNIQUE INDEX IF NOT EXISTS idx_procedures_formality ON procedures(formality_id);

-- ── A2. Bảng nối Cơ quan tham gia đa vai trò ────────────────────────────────
-- Giải quyết "cơ quan phối hợp / ủy quyền / thụ lý": cùng một cơ quan có thể giữ
-- nhiều vai trò ở nhiều thủ tục, và ngược lại. Cột phẳng không biểu diễn được.
CREATE TABLE IF NOT EXISTS procedure_agencies (
    id             SERIAL PRIMARY KEY,
    procedure_code VARCHAR(50) NOT NULL
                   REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    agency_name    TEXT NOT NULL,
    role           VARCHAR(50) NOT NULL,
    -- TRUE nếu cơ quan được SUY LUẬN bù khuyết (xem §4.3d của guide), FALSE nếu
    -- cổng công bố tường minh. Bắt buộc có để không trộn dữ liệu thật với suy luận.
    is_inferred    BOOLEAN DEFAULT FALSE,
    CONSTRAINT chk_agency_role
        CHECK (role IN ('THUC_HIEN', 'THAM_QUYEN', 'PHOI_HOP', 'UY_QUYEN'))
);

CREATE INDEX IF NOT EXISTS idx_proc_agencies_code
    ON procedure_agencies(procedure_code);
CREATE INDEX IF NOT EXISTS idx_proc_agencies_name_role
    ON procedure_agencies(agency_name, role);
-- Không nạp trùng cùng một cặp (thủ tục, cơ quan, vai trò) khi chạy lại.
CREATE UNIQUE INDEX IF NOT EXISTS uq_proc_agencies
    ON procedure_agencies(procedure_code, agency_name, role);

-- ── A3. Bảng phân đoạn nghiệp vụ chức năng ──────────────────────────────────
-- `section_id` CHÍNH LÀ `chunk_id` của Giai đoạn 5. Đồng bộ với Elasticsearch và
-- Qdrant bằng chính giá trị này, nên không cần bảng ánh xạ trung gian.
CREATE TABLE IF NOT EXISTS procedure_sections (
    section_id     VARCHAR(120) PRIMARY KEY,
    procedure_code VARCHAR(50) NOT NULL
                   REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    section_type   VARCHAR(50) NOT NULL,
    title          VARCHAR(255) NOT NULL,
    -- Nội dung chunk; bảng biểu giữ dạng text có tab.
    content        TEXT NOT NULL,
    chunk_order    INT NOT NULL DEFAULT 0,
    detail_url     TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sections_procedure_code
    ON procedure_sections(procedure_code);
CREATE INDEX IF NOT EXISTS idx_sections_type
    ON procedure_sections(section_type);
-- Truy vấn "lấy chunk theo đúng thứ tự của một thủ tục" là truy vấn nóng nhất
-- của tầng truy xuất, nên đánh index tổ hợp.
CREATE INDEX IF NOT EXISTS idx_sections_proc_order
    ON procedure_sections(procedure_code, chunk_order);

CREATE TABLE IF NOT EXISTS faq (
    faq_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    procedure_code  VARCHAR(50) NOT NULL
                    REFERENCES procedures(procedure_code) ON DELETE CASCADE,

    procedure_name  TEXT,
    domain_group    VARCHAR(100),
    source_field    VARCHAR(255),
    detail_url      TEXT,
    source_file     TEXT,

    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    intent          VARCHAR(50) NOT NULL DEFAULT 'general',
    source_section  VARCHAR(100),
    source_text     TEXT,
    tags            TEXT[] NOT NULL DEFAULT '{}',

    confidence      NUMERIC(4,3),
    status          VARCHAR(20) NOT NULL DEFAULT 'draft',
    priority        INT NOT NULL DEFAULT 0,

    hit_count       INT NOT NULL DEFAULT 0,
    last_used_at    TIMESTAMPTZ,

    created_by      VARCHAR(50) NOT NULL DEFAULT 'llm',
    reviewed_by     VARCHAR(100),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_faq_status
        CHECK (status IN ('draft', 'ready')),

    CONSTRAINT chk_faq_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_faq_procedure
    ON faq(procedure_code);

CREATE INDEX IF NOT EXISTS idx_faq_status
    ON faq(status);

CREATE INDEX IF NOT EXISTS idx_faq_intent
    ON faq(intent);

CREATE INDEX IF NOT EXISTS idx_faq_domain_source
    ON faq(domain_group, source_field);

CREATE UNIQUE INDEX IF NOT EXISTS uq_faq_proc_question
    ON faq(procedure_code, lower(question));

DROP TRIGGER IF EXISTS trg_faq_updated ON faq;
CREATE TRIGGER trg_faq_updated
    BEFORE UPDATE ON faq
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ════════════════════════════════════════════════════════════════════════════
-- PHẦN B — XÁC THỰC NGƯỜI DÙNG (bảo vệ endpoint /admin)
-- ════════════════════════════════════════════════════════════════════════════
--  Yêu cầu: chỉ người có tài khoản mới vào được trang giám sát /admin.
--
--  Hai bảng, tách vai trò rõ ràng:
--    * users    — TÀI KHOẢN. Chứa thông tin đăng nhập và quyền.
--    * sessions — PHIÊN ĐĂNG NHẬP. Chứa refresh token đã băm, để thu hồi được.
--
--  Vì sao tách `sessions` khỏi `users`: access token là JWT **không trạng thái**
--  (không truy vấn CSDL mỗi request) nên nó không thu hồi được giữa chừng. Refresh
--  token thì CẦN thu hồi được — đăng xuất, đổi mật khẩu, phát hiện lộ token.
--  Đặt nó ở bảng riêng cho phép "đăng xuất mọi thiết bị" bằng một câu UPDATE, và
--  giữ được vết kiểm toán (IP, trình duyệt, thời điểm).
-- ════════════════════════════════════════════════════════════════════════════

-- ── B1. Tài khoản ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(64)  NOT NULL,
    email           VARCHAR(255),
    -- CHỈ chứa chuỗi băm, KHÔNG BAO GIỜ chứa mật khẩu gốc.
    -- Định dạng của pwdlib: `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`
    -- Tham số băm nằm NGAY TRONG chuỗi nên nâng cấu hình sau này vẫn xác thực
    -- được mật khẩu cũ (pwdlib tự đọc tham số cũ), và `needs_rehash()` phát hiện
    -- được tài khoản cần băm lại.
    password_hash   TEXT         NOT NULL,
    full_name       VARCHAR(255) NOT NULL DEFAULT '',
    -- 'admin'   — toàn quyền, vào được /admin
    -- 'analyst' — chỉ đọc số liệu giám sát
    -- 'viewer'  — chỉ đọc
    role            VARCHAR(32)  NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Bộ đếm phục vụ khoá tài khoản tạm thời khi dò mật khẩu. Không dùng cột
    -- `last_login_at` để suy ra vì cần biết số lần SAI, không phải lần cuối đúng.
    failed_attempts INT          NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_users_role CHECK (role IN ('admin', 'analyst', 'viewer')),
    -- Tên đăng nhập không phân biệt hoa/thường: `Admin` và `admin` là một người.
    -- Không dùng CITEXT để tránh phụ thuộc extension; UNIQUE trên LOWER() là đủ.
    CONSTRAINT chk_users_username_format
        CHECK (username ~ '^[A-Za-z0-9._-]{3,64}$')
);

-- UNIQUE trên biểu thức: chặn `Admin` và `admin` cùng tồn tại.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_lower ON users(LOWER(username));
-- Email là tuỳ chọn nhưng nếu có thì không được trùng (bỏ qua NULL).
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower
    ON users(LOWER(email)) WHERE email IS NOT NULL;

-- ── B2. Phiên đăng nhập (refresh token) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Băm SHA-256 của refresh token, KHÔNG lưu token gốc. Nếu CSDL bị lộ thì kẻ
    -- tấn công cũng không dùng được giá trị trong bảng này để đăng nhập.
    -- Refresh token là chuỗi ngẫu nhiên 256-bit nên SHA-256 là đủ — không cần
    -- Argon2 (Argon2 dành cho mật khẩu do người chọn, entropy thấp).
    token_hash    CHAR(64)     NOT NULL UNIQUE,
    -- Gia đình token: khi refresh, token cũ bị thu hồi và sinh token mới CÙNG
    -- family_id. Nếu một token đã thu hồi bị dùng lại (dấu hiệu bị đánh cắp) thì
    -- thu hồi TOÀN BỘ family — đăng xuất kẻ tấn công lẫn người dùng.
    family_id     UUID         NOT NULL DEFAULT gen_random_uuid(),
    user_agent    TEXT,
    ip_address    INET,
    expires_at    TIMESTAMPTZ  NOT NULL,
    revoked_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user     ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_family   ON sessions(family_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires  ON sessions(expires_at);
-- Truy vấn nóng nhất của khâu làm mới token: tra theo token_hash, chỉ lấy phiên
-- còn sống. Index bộ phận (partial) nhỏ hơn nhiều so với index toàn bảng.
CREATE INDEX IF NOT EXISTS idx_sessions_active
    ON sessions(token_hash) WHERE revoked_at IS NULL;

-- ── B3. Nhật ký thao tác quản trị (bắt buộc cho trang giám sát) ─────────────
-- Trang /admin cho phép xem dữ liệu và cấu hình. Không có vết kiểm toán thì
-- không trả lời được "ai đã đổi cái này" khi có sự cố.
CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(64)  NOT NULL,
    entity      VARCHAR(64),
    entity_id   VARCHAR(128),
    detail      JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user_time  ON audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action     ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity     ON audit_logs(entity, entity_id);

-- ── B4. Trigger tự cập nhật `updated_at` ────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_procedures_updated ON procedures;
CREATE TRIGGER trg_procedures_updated
    BEFORE UPDATE ON procedures
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ── A4. Nhóm thủ tục (Giai đoạn 3) ─────────────────────────────────────────
-- Nhóm sinh từ 4 từ đầu của tên thủ tục; chỉ để trả lời câu chung khi các
-- biến thể cùng nội dung hoặc có thủ tục đại diện. KHÔNG phải bảng hồ sơ/định danh.
CREATE TABLE IF NOT EXISTS procedure_themes (
    theme_id        VARCHAR(128) PRIMARY KEY,
    label           TEXT NOT NULL,
    canonical_code  VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE procedures
    ADD COLUMN IF NOT EXISTS theme_id VARCHAR(128)
    REFERENCES procedure_themes(theme_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_procedures_theme ON procedures(theme_id);

COMMIT;
