BEGIN;

-- Bộ nhớ ngắn hạn theo phiên.
-- chat_messages vẫn là nguồn lưu toàn bộ lượt hội thoại; bảng này chỉ lưu
-- summary, checkpoint và topic ledger để dựng context cho các lượt sau.
CREATE TABLE IF NOT EXISTS chat_session_memory (
    session_id UUID PRIMARY KEY
        REFERENCES chat_sessions(id) ON DELETE CASCADE,

    summary TEXT NOT NULL DEFAULT '',

    -- Message cuối cùng đã được đưa vào summary. NULL = chưa tóm tắt.
    summary_through_message_id UUID
        REFERENCES chat_messages(id) ON DELETE SET NULL,

    -- Danh sách topic có thứ tự:
    -- [{"order":1,"procedure_code":"...","procedure_name":"...",
    --   "first_message_id":"...","last_message_id":"..."}]
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_chat_session_memory_topics
        CHECK (jsonb_typeof(topics) = 'array')
);

COMMIT;
