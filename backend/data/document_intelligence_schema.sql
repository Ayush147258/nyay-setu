-- NyaySetu Track C document-intelligence schema.
-- Apply after backend/app/db/models/schema.sql. Tenant and case scopes are
-- retained for every source, job, evidence item, and report.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL DEFAULT 'default',
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, case_id)
        REFERENCES cases(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, created_by)
        REFERENCES users(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    media_type TEXT NOT NULL,
    document_format TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    object_uri TEXT NOT NULL,
    original_object_key TEXT NOT NULL,
    ir_object_key TEXT,
    parse_status TEXT NOT NULL CHECK (
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
    ),
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    language_hint TEXT,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, sha256)
);

CREATE TABLE IF NOT EXISTS document_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    width DOUBLE PRECISION,
    height DOUBLE PRECISION,
    rotation INTEGER NOT NULL DEFAULT 0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (
        confidence BETWEEN 0 AND 1
    ),
    extraction_method TEXT NOT NULL DEFAULT 'none' CHECK (
        extraction_method IN ('digital', 'ocr', 'mixed', 'none')
    ),
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (version_id, page_number)
);

CREATE TABLE IF NOT EXISTS document_blocks (
    id TEXT PRIMARY KEY,
    page_id UUID NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    block_kind TEXT NOT NULL,
    text_content TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    bbox JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(text_content, ''))
    ) STORED,
    UNIQUE (page_id, sequence)
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

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
    requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (
        status IN (
            'queued',
            'extracting',
            'researching',
            'synthesizing',
            'verifying',
            'completed',
            'needs_review',
            'failed',
            'cancelled'
        )
    ),
    workflow_version TEXT NOT NULL,
    idempotency_key CHAR(64) NOT NULL UNIQUE CHECK (
        idempotency_key ~ '^[a-f0-9]{64}$'
    ),
    document_version_ids JSONB NOT NULL CHECK (
        jsonb_typeof(document_version_ids) = 'array'
    ),
    document_hashes JSONB NOT NULL CHECK (
        jsonb_typeof(document_hashes) = 'array'
    ),
    enable_external_research BOOLEAN NOT NULL DEFAULT FALSE,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    leased_until TIMESTAMPTZ,
    worker_id TEXT,
    cancel_requested_at TIMESTAMPTZ,
    run_id TEXT,
    report_id TEXT,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, case_id)
        REFERENCES cases(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, requested_by_user_id)
        REFERENCES users(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS analysis_job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'queued',
            'extracting',
            'researching',
            'synthesizing',
            'verifying',
            'completed',
            'needs_review',
            'failed',
            'cancelled'
        )
    ),
    agent TEXT,
    message TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, sequence)
);

CREATE TABLE IF NOT EXISTS analysis_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL CHECK (
        artifact_type IN ('run', 'report', 'evidence', 'integrity', 'research')
    ),
    artifact_id TEXT NOT NULL,
    reference_uri TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, artifact_type, artifact_id)
);
CREATE TABLE IF NOT EXISTS evidence_atoms (
    id TEXT PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_kind TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    review_state TEXT NOT NULL CHECK (
        review_state IN ('verified', 'needs_review', 'rejected')
    ),
    source_spans JSONB NOT NULL CHECK (jsonb_array_length(source_spans) > 0),
    extractor_name TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    first_block_id TEXT NOT NULL REFERENCES document_blocks(id) ON DELETE CASCADE,
    last_block_id TEXT NOT NULL REFERENCES document_blocks(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    embedding_model TEXT,
    embedding vector(768),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(chunk_text, ''))
    ) STORED,
    UNIQUE (version_id, first_block_id, last_block_id)
);

CREATE TABLE IF NOT EXISTS evidence_relationships (
    id TEXT PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    source_evidence_id TEXT NOT NULL REFERENCES evidence_atoms(id) ON DELETE CASCADE,
    target_evidence_id TEXT NOT NULL REFERENCES evidence_atoms(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    supporting_evidence_ids JSONB NOT NULL,
    review_state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    date_text TEXT NOT NULL,
    normalized_date DATE,
    description TEXT NOT NULL,
    evidence_ids JSONB NOT NULL CHECK (jsonb_array_length(evidence_ids) > 0),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    document_version_ids JSONB NOT NULL,
    error JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS document_agent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES document_analysis_runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL,
    round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 2),
    summary TEXT NOT NULL,
    input_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    output_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS legal_analysis_reports (
    id TEXT PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES document_analysis_runs(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    source_document_versions JSONB NOT NULL,
    caveats JSONB NOT NULL DEFAULT '[]'::jsonb,
    report_json JSONB NOT NULL,
    html_object_uri TEXT,
    pdf_object_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (case_id, version)
);

CREATE TABLE IF NOT EXISTS report_claims (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES legal_analysis_reports(id) ON DELETE CASCADE,
    section_id TEXT NOT NULL,
    claim_kind TEXT NOT NULL CHECK (
        claim_kind IN ('fact', 'law', 'inference', 'recommendation')
    ),
    statement TEXT NOT NULL,
    evidence_ids JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    caveat TEXT
);

CREATE TABLE IF NOT EXISTS report_citations (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES legal_analysis_reports(id) ON DELETE CASCADE,
    claim_id TEXT REFERENCES report_claims(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_atoms(id) ON DELETE RESTRICT,
    source_span JSONB NOT NULL,
    display_label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'blocking')),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'resolved', 'dismissed')
    ),
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
    resolution_note TEXT,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_audit_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    actor_user_id UUID NOT NULL,
    case_id UUID REFERENCES cases(id) ON DELETE SET NULL,
    event_type VARCHAR(80) NOT NULL,
    outcome VARCHAR(16) NOT NULL CHECK (
        outcome IN ('allowed', 'denied', 'failed')
    ),
    resource_type VARCHAR(80),
    resource_id TEXT,
    request_id VARCHAR(128),
    client_ip TEXT,
    user_agent VARCHAR(500),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES users(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS document_rate_limit_windows (
    tenant_id VARCHAR(128) NOT NULL,
    user_id UUID NOT NULL,
    bucket VARCHAR(80) NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id, bucket, window_started_at),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES users(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_quota_usage (
    tenant_id VARCHAR(128) NOT NULL,
    user_id UUID NOT NULL,
    period_started_at TIMESTAMPTZ NOT NULL,
    bytes_used BIGINT NOT NULL DEFAULT 0 CHECK (bytes_used >= 0),
    file_count INTEGER NOT NULL DEFAULT 0 CHECK (file_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id, period_started_at),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES users(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_upload_reservations (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    user_id UUID NOT NULL,
    case_id UUID NOT NULL,
    period_started_at TIMESTAMPTZ NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    status VARCHAR(16) NOT NULL CHECK (
        status IN ('reserved', 'committed', 'released')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, user_id, period_started_at)
        REFERENCES document_quota_usage(tenant_id, user_id, period_started_at)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, case_id)
        REFERENCES cases(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_documents_tenant_case
    ON source_documents(tenant_id, case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_document_versions_sha
    ON document_versions(sha256);
CREATE INDEX IF NOT EXISTS idx_document_blocks_search
    ON document_blocks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_document_tables_page
    ON document_tables(page_id);
CREATE INDEX IF NOT EXISTS idx_document_table_rows_table
    ON document_table_rows(table_id, row_index);
CREATE INDEX IF NOT EXISTS idx_document_chunks_case
    ON document_chunks(case_id, version_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_search
    ON document_chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_claim
    ON analysis_jobs(status, available_at, leased_until);
CREATE INDEX IF NOT EXISTS idx_analysis_job_events_stream
    ON analysis_job_events(job_id, sequence);
CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_case
    ON analysis_artifacts(case_id, artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_case_kind
    ON evidence_atoms(case_id, evidence_kind, review_state);
CREATE INDEX IF NOT EXISTS idx_relationships_case
    ON evidence_relationships(case_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_timeline_case_date
    ON timeline_events(case_id, normalized_date);
CREATE INDEX IF NOT EXISTS idx_review_queue
    ON review_items(case_id, status, severity, created_at);
CREATE INDEX IF NOT EXISTS idx_document_audit_case_time
    ON document_audit_events(tenant_id, case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_audit_actor_time
    ON document_audit_events(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_rate_limit_cleanup
    ON document_rate_limit_windows(window_started_at);
CREATE INDEX IF NOT EXISTS idx_document_upload_reservations_case
    ON document_upload_reservations(tenant_id, case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox_events(available_at) WHERE published_at IS NULL;

-- Service connections are expected to bypass RLS. User-scoped connections must
-- set app.current_user_id and can only see cases owned by that user.
ALTER TABLE source_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_atoms ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE timeline_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_analysis_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_rate_limit_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_quota_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_upload_reservations ENABLE ROW LEVEL SECURITY;

CREATE POLICY source_documents_case_owner ON source_documents
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = source_documents.case_id
              AND cases.tenant_id = source_documents.tenant_id
              AND cases.tenant_id = nullif(current_setting('app.current_tenant_id', true), '')
              AND cases.user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
        )
    );

