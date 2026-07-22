BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(128) NOT NULL DEFAULT 'default';

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_tenant_id
    ON users(tenant_id, id);

ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(128) NOT NULL DEFAULT 'default';

CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_tenant_id
    ON cases(tenant_id, id);

ALTER TABLE analysis_jobs
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'cases_tenant_user_fk'
    ) THEN
        ALTER TABLE cases
            ADD CONSTRAINT cases_tenant_user_fk
            FOREIGN KEY (tenant_id, user_id)
            REFERENCES users(tenant_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'source_documents_tenant_case_fk'
    ) THEN
        ALTER TABLE source_documents
            ADD CONSTRAINT source_documents_tenant_case_fk
            FOREIGN KEY (tenant_id, case_id)
            REFERENCES cases(tenant_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'source_documents_tenant_creator_fk'
    ) THEN
        ALTER TABLE source_documents
            ADD CONSTRAINT source_documents_tenant_creator_fk
            FOREIGN KEY (tenant_id, created_by)
            REFERENCES users(tenant_id, id)
            ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'analysis_jobs_tenant_case_fk'
    ) THEN
        ALTER TABLE analysis_jobs
            ADD CONSTRAINT analysis_jobs_tenant_case_fk
            FOREIGN KEY (tenant_id, case_id)
            REFERENCES cases(tenant_id, id)
            ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'analysis_jobs_tenant_requester_fk'
    ) THEN
        ALTER TABLE analysis_jobs
            ADD CONSTRAINT analysis_jobs_tenant_requester_fk
            FOREIGN KEY (tenant_id, requested_by_user_id)
            REFERENCES users(tenant_id, id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

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

CREATE INDEX IF NOT EXISTS idx_document_audit_case_time
    ON document_audit_events(tenant_id, case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_audit_actor_time
    ON document_audit_events(actor_user_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_document_rate_limit_cleanup
    ON document_rate_limit_windows(window_started_at);

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

CREATE INDEX IF NOT EXISTS idx_document_upload_reservations_case
    ON document_upload_reservations(tenant_id, case_id, created_at DESC);

ALTER TABLE document_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_rate_limit_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_quota_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_upload_reservations ENABLE ROW LEVEL SECURITY;

COMMIT;
