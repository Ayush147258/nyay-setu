-- ============================================================
-- NyaySetu — Neon PostgreSQL Schema
-- Run once in the Neon SQL Editor for your project.
-- Neon uses standard PostgreSQL — no Supabase extensions needed.
-- ============================================================

-- Enable pgvector for shared case memory (Prompt 07 upgrade)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
  id                  UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
  email               TEXT         UNIQUE,
  name                TEXT,
  tier                TEXT         NOT NULL DEFAULT 'free'
                                   CHECK (tier IN ('free', 'premium')),
  cases_analyzed      INTEGER      NOT NULL DEFAULT 0,
  premium_expires_at  TIMESTAMPTZ,
  created_at          TIMESTAMPTZ  DEFAULT NOW(),
  updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- Cases
-- ============================================================
CREATE TABLE IF NOT EXISTS cases (
  id                          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id                     UUID        REFERENCES users(id) ON DELETE SET NULL,  -- nullable: anonymous users
  case_type                   TEXT        NOT NULL,
  detected_language           TEXT        NOT NULL DEFAULT 'en',
  original_text               TEXT,
  document_title              TEXT,
  document_body               TEXT,
  document_status             TEXT        DEFAULT 'draft',
  confidence_score            FLOAT,
  has_unresolved_gaps         BOOLEAN     DEFAULT FALSE,
  total_debate_rounds         INTEGER     DEFAULT 0,
  mediator_override_triggered BOOLEAN     DEFAULT FALSE,
  tier_used                   TEXT        DEFAULT 'free',
  provider_used               TEXT        DEFAULT 'gemini',
  document_json               JSONB       NOT NULL,   -- full LegalDocument as JSON
  processing_time_ms          INTEGER,
  created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Shared case memory — pgvector (README upgrade #3)
-- Stores successful adversarial corrections as embeddings.
-- ResearchAgent queries this before IndianKanoon for local context.
-- ============================================================
CREATE TABLE IF NOT EXISTS case_memory (
  id                  UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
  case_type           TEXT         NOT NULL,
  district            TEXT,
  state               TEXT,
  correction_summary  TEXT         NOT NULL,   -- what the bureaucrat caught + mediator fixed
  embedding           vector(1536),            -- text-embedding-3-small (OpenAI / Gemini)
  created_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cases_user_id    ON cases(user_id);
CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_case_type  ON cases(case_type);

-- pgvector cosine similarity index for case_memory lookups
CREATE INDEX IF NOT EXISTS idx_case_memory_embedding
  ON case_memory USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);   -- tune lists = sqrt(row_count) when > 1M rows

-- ============================================================
-- Row Level Security (good practice — not required for service-role backend)
-- ============================================================
ALTER TABLE users       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases       ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_memory ENABLE ROW LEVEL SECURITY;

-- Service role (backend) bypasses RLS automatically.
-- Frontend (Next.js / Prisma) uses user JWT — add policies as needed.
