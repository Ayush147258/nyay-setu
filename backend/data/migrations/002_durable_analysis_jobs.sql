BEGIN;

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    workflow_version TEXT,
    idempotency_key TEXT NOT NULL,
    document_version_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    document_hashes JSONB NOT NULL DEFAULT '[]'::jsonb,
    enable_external_research BOOLEAN NOT NULL DEFAULT FALSE,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE analysis_jobs
    ADD COLUMN IF NOT EXISTS workflow_version TEXT,
    ADD COLUMN IF NOT EXISTS document_version_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS document_hashes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS enable_external_research BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS run_id TEXT,
    ADD COLUMN IF NOT EXISTS report_id TEXT,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

UPDATE analysis_jobs
SET workflow_version = COALESCE(workflow_version, 'track-c-1.1.0')
WHERE workflow_version IS NULL;

ALTER TABLE analysis_jobs
    ALTER COLUMN workflow_version SET NOT NULL;

UPDATE analysis_jobs
SET status = CASE status
    WHEN 'running' THEN 'extracting'
    WHEN 'retrying' THEN 'queued'
    WHEN 'dead_letter' THEN 'failed'
    ELSE status
END;

ALTER TABLE analysis_jobs
    DROP CONSTRAINT IF EXISTS analysis_jobs_status_check;

ALTER TABLE analysis_jobs
    ADD CONSTRAINT analysis_jobs_status_check CHECK (
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
    );

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'analysis_jobs'
          AND column_name = 'job_type'
    ) THEN
        ALTER TABLE analysis_jobs ALTER COLUMN job_type DROP NOT NULL;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_jobs_idempotency
    ON analysis_jobs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_claim
    ON analysis_jobs(status, available_at, leased_until);

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

CREATE INDEX IF NOT EXISTS idx_analysis_job_events_stream
    ON analysis_job_events(job_id, sequence);

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

CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_case
    ON analysis_artifacts(case_id, artifact_type, created_at DESC);

ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_artifacts ENABLE ROW LEVEL SECURITY;

COMMIT;