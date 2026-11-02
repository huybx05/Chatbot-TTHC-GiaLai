-- Một file nội dung có thể có nhiều file_id (mỗi case một id từ cổng).
ALTER TABLE procedure_documents
    ADD COLUMN IF NOT EXISTS file_ids TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_procedure_documents_file_ids
    ON procedure_documents USING GIN (file_ids);
