-- Metadata block/case cho chunk sinh từ execution_cases.
ALTER TABLE procedure_sections
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Truy vấn lọc block theo trường hợp (case) trong procedure_sections.
CREATE INDEX IF NOT EXISTS idx_sections_metadata_case
    ON procedure_sections ((metadata->>'case_order'));
