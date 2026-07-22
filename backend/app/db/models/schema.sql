-- backend/app/db/models/schema.sql
-- Raw SQL schema matching the style of neon_client.py

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    avatar_url VARCHAR(512),
    google_id VARCHAR(255) UNIQUE,
    role VARCHAR(50) DEFAULT 'citizen',
    preferred_lang VARCHAR(10) DEFAULT 'hi',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_tenant_id
    ON users(tenant_id, id);

CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    case_type VARCHAR(100) NOT NULL DEFAULT 'other',
    raw_input TEXT,
    detected_language VARCHAR(10) DEFAULT 'hi',
    status VARCHAR(50) DEFAULT 'intake',
    title VARCHAR(255),
    description TEXT,
    ai_summary TEXT,
    priority VARCHAR(50) DEFAULT 'medium',
    district VARCHAR(100),
    state VARCHAR(100),
    debate_round INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES users(tenant_id, id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cases_tenant_id
    ON cases(tenant_id, id);

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    round_number INT DEFAULT 0,
    input_summary TEXT,
    output_summary TEXT,
    score INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS petitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    final_document_text TEXT NOT NULL,
    pdf_url VARCHAR(512),
    filed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    next_check_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_status VARCHAR(255),
    escalated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
