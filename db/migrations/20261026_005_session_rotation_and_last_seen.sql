BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

UPDATE users
   SET last_seen_at = COALESCE(last_login_at, created_at)
 WHERE last_seen_at IS NULL;

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS previous_token_hash CHAR(64);

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_sessions_previous_token
    ON sessions(previous_token_hash)
    WHERE previous_token_hash IS NOT NULL AND revoked_at IS NULL;

COMMIT;
