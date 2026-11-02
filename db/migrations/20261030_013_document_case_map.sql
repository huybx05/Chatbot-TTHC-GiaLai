-- Gắn file mẫu với đúng trường hợp/component và giữ file_id từ cổng DVC.
ALTER TABLE procedure_documents
    ADD COLUMN IF NOT EXISTS case_order INT NOT NULL DEFAULT 0;
ALTER TABLE procedure_documents
    ADD COLUMN IF NOT EXISTS component_index INT NOT NULL DEFAULT 0;
ALTER TABLE procedure_documents
    ADD COLUMN IF NOT EXISTS file_id TEXT;

CREATE INDEX IF NOT EXISTS idx_procedure_documents_case
    ON procedure_documents(procedure_code, case_order, component_index);
CREATE INDEX IF NOT EXISTS idx_procedure_documents_file_id
    ON procedure_documents(file_id);
