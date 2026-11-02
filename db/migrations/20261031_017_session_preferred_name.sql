-- Tên gọi ưa thích của người dùng, chỉ trong phạm vi một phiên chat.
ALTER TABLE chat_session_memory
    ADD COLUMN IF NOT EXISTS preferred_name VARCHAR(80);
