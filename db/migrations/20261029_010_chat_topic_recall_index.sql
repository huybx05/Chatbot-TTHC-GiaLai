BEGIN;

-- Recall topic cũ dùng predicate:
--   session_id = :session_id
--   role = 'assistant'
--   metadata -> 'procedure' ->> 'procedure_code' = :procedure_code
--   ORDER BY created_at DESC, id DESC
--
-- Index tổ hợp theo đúng predicate + thứ tự đó để session lớn không phải
-- quét toàn bộ chat_messages.
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_procedure_created
    ON chat_messages(
        session_id,
        (metadata -> 'procedure' ->> 'procedure_code'),
        created_at DESC,
        id DESC
    )
    WHERE role = 'assistant';

COMMIT;
