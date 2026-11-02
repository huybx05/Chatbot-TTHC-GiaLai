-- Phiên khách: user_id nullable, token cookie và TTL không tương tác.
ALTER TABLE chat_sessions
    ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS guest_token_hash CHAR(64);
ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sessions_guest_token
    ON chat_sessions(guest_token_hash)
    WHERE guest_token_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_guest_expiry
    ON chat_sessions(expires_at)
    WHERE user_id IS NULL;
