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
    -- Metadata block/case cho chunk sinh từ execution_cases.
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
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

    procedure_code  VARCHAR(50)
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

-- Hàm dùng chung phải được định nghĩa **trước trigger đầu tiên** dùng nó.
-- Trước đây hàm nằm ở cuối file nên `schema.sql` chạy trên database mới sẽ
-- dừng ở đúng trigger này với lỗi `function set_updated_at() does not exist`.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
    -- 'admin'  — toàn quyền, vào được /admin
    -- 'client' — người dùng chatbot
    role            VARCHAR(32)  NOT NULL DEFAULT 'client',
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Bộ đếm phục vụ khoá tài khoản tạm thời khi dò mật khẩu. Không dùng cột
    -- `last_login_at` để suy ra vì cần biết số lần SAI, không phải lần cuối đúng.
    failed_attempts INT          NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    last_seen_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_users_role CHECK (role IN ('admin', 'client')),
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
    previous_token_hash CHAR(64),
    -- Gia đình token: refresh cập nhật token mới trên cùng dòng session. Nếu token
    -- ngay trước đó bị dùng lại (dấu hiệu bị đánh cắp) thì thu hồi TOÀN BỘ family.
    family_id     UUID         NOT NULL DEFAULT gen_random_uuid(),
    user_agent    TEXT,
    ip_address    INET,
    expires_at    TIMESTAMPTZ  NOT NULL,
    last_used_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
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
CREATE INDEX IF NOT EXISTS idx_sessions_previous_token
    ON sessions(previous_token_hash)
    WHERE previous_token_hash IS NOT NULL AND revoked_at IS NULL;

-- ── B2.5. Phiên trò chuyện của người dùng ───────────────────────────────────
-- Mỗi dòng là một cuộc trò chuyện (metadata). Tin nhắn chi tiết nằm ở bảng
-- chat_messages bên dưới; bảng này giữ tiêu đề, trạng thái ghim và thời điểm
-- cập nhật gần nhất.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     BIGINT       REFERENCES users(id) ON DELETE CASCADE,
    guest_token_hash CHAR(64),
    expires_at  TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    title       VARCHAR(120) NOT NULL DEFAULT 'Cuộc trò chuyện mới',
    is_pinned   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_chat_sessions_title
        CHECK (char_length(btrim(title)) BETWEEN 1 AND 120)
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
    ON chat_sessions(user_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sessions_guest_token
    ON chat_sessions(guest_token_hash)
    WHERE guest_token_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_guest_expiry
    ON chat_sessions(expires_at)
    WHERE user_id IS NULL;

-- ── B2.6. Tin nhắn trong một cuộc trò chuyện ────────────────────────────────
-- Xoá session là xoá toàn bộ tin nhắn đi theo (ON DELETE CASCADE), nên không
-- bao giờ còn tin nhắn mồ côi. `metadata` giữ citation, mã thủ tục, trạng thái
-- và các lựa chọn hỏi lại để lần sau mở lại vẫn dựng được đúng giao diện.
CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID         NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(16)  NOT NULL,
    content     TEXT         NOT NULL,
    metadata    JSONB        NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_chat_messages_role
        CHECK (role IN ('user', 'assistant')),
    CONSTRAINT chk_chat_messages_content
        CHECK (char_length(btrim(content)) BETWEEN 1 AND 20000)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages(session_id, created_at, id);

-- Recall một topic cũ không được quét toàn bộ session. Index biểu thức này khớp
-- đúng predicate của Memory Reader:
--   session_id = ? AND role = 'assistant'
--   AND metadata->'procedure'->>'procedure_code' = ?
--   ORDER BY created_at DESC, id DESC
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_procedure_created
    ON chat_messages(
        session_id,
        (metadata -> 'procedure' ->> 'procedure_code'),
        created_at DESC,
        id DESC
    )
    WHERE role = 'assistant';

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
-- `set_updated_at()` đã được định nghĩa ở PHẦN A (trước trigger đầu tiên).

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


CREATE TABLE IF NOT EXISTS procedure_documents (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    procedure_code          VARCHAR(50) NOT NULL
                            REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    profile_component_id    VARCHAR(64),
    file_id                 TEXT,
    case_order              INT NOT NULL DEFAULT 0,
    component_index         INT NOT NULL DEFAULT 0,
    document_name           TEXT NOT NULL,
    file_name               TEXT NOT NULL,
    mime_type               VARCHAR(100),
    size_bytes              BIGINT,
    checksum_sha256         CHAR(64) NOT NULL,
    object_key              TEXT NOT NULL,
    source_bucket           TEXT,
    source_path             TEXT,
    source_url              TEXT,
    sort_order              INT NOT NULL DEFAULT 0,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_procedure_documents_checksum
        UNIQUE (procedure_code, checksum_sha256)
);

CREATE INDEX IF NOT EXISTS idx_procedure_documents_code
    ON procedure_documents(procedure_code, sort_order);


COMMIT;
