BEGIN;

ALTER TABLE document_versions
    DROP CONSTRAINT IF EXISTS document_versions_parse_status_check;

ALTER TABLE document_versions
    ADD CONSTRAINT document_versions_parse_status_check CHECK (
        parse_status IN (
            'pending',
            'ready',
            'partial',
            'ocr_required',
            'password_protected',
            'corrupted',
            'limit_exceeded',
            'unsupported',
            'failed'
        )
    );

ALTER TABLE document_pages
    ADD COLUMN IF NOT EXISTS rotation INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extraction_method TEXT NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE document_pages
    DROP CONSTRAINT IF EXISTS document_pages_confidence_check;

ALTER TABLE document_pages
    ADD CONSTRAINT document_pages_confidence_check CHECK (
        confidence BETWEEN 0 AND 1
    );

ALTER TABLE document_pages
    DROP CONSTRAINT IF EXISTS document_pages_extraction_method_check;

ALTER TABLE document_pages
    ADD CONSTRAINT document_pages_extraction_method_check CHECK (
        extraction_method IN ('digital', 'ocr', 'mixed', 'none')
    );

CREATE TABLE IF NOT EXISTS document_tables (
    id TEXT PRIMARY KEY,
    page_id UUID NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
    block_id TEXT NOT NULL UNIQUE REFERENCES document_blocks(id) ON DELETE CASCADE,
    bbox JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_table_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id TEXT NOT NULL REFERENCES document_tables(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL CHECK (row_index >= 0),
    UNIQUE (table_id, row_index)
);

CREATE TABLE IF NOT EXISTS document_table_cells (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    row_id UUID NOT NULL REFERENCES document_table_rows(id) ON DELETE CASCADE,
    column_index INTEGER NOT NULL CHECK (column_index >= 0),
    text_content TEXT NOT NULL DEFAULT '',
    row_span INTEGER NOT NULL DEFAULT 1 CHECK (row_span > 0),
    column_span INTEGER NOT NULL DEFAULT 1 CHECK (column_span > 0),
    bbox JSONB,
    UNIQUE (row_id, column_index)
);

CREATE INDEX IF NOT EXISTS idx_document_tables_page
    ON document_tables(page_id);

CREATE INDEX IF NOT EXISTS idx_document_table_rows_table
    ON document_table_rows(table_id, row_index);

COMMIT;
