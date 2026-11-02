BEGIN;

-- Tin nhắn của từng cuộc trò chuyện.
-- Xoá chat_sessions là xoá toàn bộ tin nhắn đi theo.
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

COMMIT;
