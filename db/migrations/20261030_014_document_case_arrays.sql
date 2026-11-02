-- Một file có thể dùng cho nhiều case/component; lưu tập thay vì một giá trị.
ALTER TABLE procedure_documents
    ADD COLUMN IF NOT EXISTS case_orders INT[] NOT NULL DEFAULT '{}';
ALTER TABLE procedure_documents
    ADD COLUMN IF NOT EXISTS component_indexes INT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_procedure_documents_case_orders
    ON procedure_documents USING GIN (case_orders);
