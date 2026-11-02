-- Giữ lại log chat khi người dùng xoá phiên hoặc phiên khách hết hạn.
ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_active
    ON chat_sessions (updated_at DESC)
    WHERE deleted_at IS NULL;
