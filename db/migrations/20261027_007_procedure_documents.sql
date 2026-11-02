BEGIN;

CREATE TABLE IF NOT EXISTS procedure_documents (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    procedure_code          VARCHAR(50) NOT NULL
                            REFERENCES procedures(procedure_code) ON DELETE CASCADE,
    profile_component_id    VARCHAR(64),
    document_name           TEXT NOT NULL,
    file_name               TEXT NOT NULL,
    mime_type               VARCHAR(100),
    size_bytes              BIGINT,
    checksum_sha256         CHAR(64) NOT NULL,
    object_key              TEXT NOT NULL,
    source_bucket           TEXT,
    source_path             TEXT,
    source_url              TEXT,
    sort_order              INT NOT NULL DEFAULT 0,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_procedure_documents_checksum
        UNIQUE (procedure_code, checksum_sha256)
);

CREATE INDEX IF NOT EXISTS idx_procedure_documents_code
    ON procedure_documents(procedure_code, sort_order);

COMMIT;