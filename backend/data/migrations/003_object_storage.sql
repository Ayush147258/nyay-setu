BEGIN;

ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE document_versions
    ADD COLUMN IF NOT EXISTS original_object_key TEXT,
    ADD COLUMN IF NOT EXISTS ir_object_key TEXT;

UPDATE document_versions
SET original_object_key = object_uri
WHERE original_object_key IS NULL;

ALTER TABLE document_versions
    ALTER COLUMN original_object_key SET NOT NULL;

ALTER TABLE document_versions
    DROP CONSTRAINT IF EXISTS document_versions_parse_status_check;

ALTER TABLE document_versions
    ADD CONSTRAINT document_versions_parse_status_check CHECK (
        parse_status IN (
            'pending',
            'ready',
            'partial',
            'ocr_required',
            'unsupported',
            'failed'
        )
    );

CREATE INDEX IF NOT EXISTS idx_source_documents_tenant_case
    ON source_documents(tenant_id, case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_document_versions_object_key
    ON document_versions(original_object_key);

COMMIT;
