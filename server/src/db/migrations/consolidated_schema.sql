-- =============================================================================
-- AUTOFIX COMPLETE DATABASE SCHEMA
-- Run this single script in Supabase SQL Editor to set up the entire database.
-- =============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- -----------------------------------------------------------------------------
-- 2. Users Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id BIGINT NOT NULL UNIQUE,
    github_username VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    avatar_url VARCHAR(255),
    github_access_token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 3. Repositories Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repositories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    github_repo_id BIGINT NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    owner VARCHAR(255) NOT NULL,
    clone_url TEXT NOT NULL,
    html_url TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    last_commit_sha TEXT,
    github_webhook_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, github_repo_id)
);

CREATE INDEX IF NOT EXISTS repositories_user_id_idx ON repositories(user_id);

-- -----------------------------------------------------------------------------
-- 4. Files Table (Repository Codebase Indexing)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    language TEXT,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repo_id, path)
);

CREATE INDEX IF NOT EXISTS files_repo_id_idx ON files(repo_id);

-- -----------------------------------------------------------------------------
-- 5. Code Chunks Table (AST Chunks + 1536-dim pgvector Embeddings)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    chunk_key TEXT NOT NULL,
    symbol_name TEXT,
    chunk_type TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    language TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (file_id, chunk_key)
);

CREATE INDEX IF NOT EXISTS code_chunks_file_id_idx ON code_chunks(file_id);
CREATE INDEX IF NOT EXISTS code_chunks_symbol_name_idx ON code_chunks(file_id, symbol_name);
CREATE INDEX IF NOT EXISTS code_chunks_chunk_type_idx ON code_chunks(file_id, chunk_type);

-- -----------------------------------------------------------------------------
-- 6. Signals Table (Incoming Errors from Webhooks / CI / Issues)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'ci_failure' | 'github_issue' | 'log'
    source_ref TEXT,    -- Issue number or workflow run ID
    raw_content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'failed')),
    parsed_stack_trace JSONB,
    parsed_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT signals_repo_source_type_unique UNIQUE (repo_id, type, source_ref)
);

CREATE INDEX IF NOT EXISTS signals_repo_id_idx ON signals(repo_id);
CREATE INDEX IF NOT EXISTS signals_type_idx ON signals(type);
CREATE INDEX IF NOT EXISTS signals_status_idx ON signals(status);

-- -----------------------------------------------------------------------------
-- 7. Fix Jobs Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fix_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued',
            'reindexing',
            'analyzing_signal',
            'localizing',
            'root_cause',
            'generating',
            'validating',
            'awaiting_approval',
            'pr_created',
            'failed'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0 AND attempt_count <= 3),
    approved_at TIMESTAMPTZ,
    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fix_jobs_repo_id_idx ON fix_jobs(repo_id);
CREATE INDEX IF NOT EXISTS fix_jobs_signal_id_idx ON fix_jobs(signal_id);
CREATE INDEX IF NOT EXISTS fix_jobs_status_idx ON fix_jobs(status);
CREATE UNIQUE INDEX IF NOT EXISTS fix_jobs_one_active_per_signal ON fix_jobs(signal_id) WHERE status <> 'failed';

-- -----------------------------------------------------------------------------
-- 8. Job Events Table (Progress Timeline / Logs)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES fix_jobs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS job_events_job_id_idx ON job_events(job_id);
CREATE INDEX IF NOT EXISTS job_events_job_created_idx ON job_events(job_id, created_at);

-- -----------------------------------------------------------------------------
-- 9. Localization Candidates Table (Ranked Culprit Code Locations)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS localization_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES fix_jobs(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES code_chunks(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    score DOUBLE PRECISION,
    method TEXT NOT NULL, -- 'stack_trace_direct' | 'embedding'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS localization_candidates_job_idx ON localization_candidates(job_id);
CREATE INDEX IF NOT EXISTS localization_candidates_rank_idx ON localization_candidates(job_id, rank);

-- -----------------------------------------------------------------------------
-- 10. Patches Table (Unified Git Diffs & Validation)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES fix_jobs(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1 AND attempt_number <= 3),
    diff_content TEXT NOT NULL,
    explanation TEXT,
    validation_passed BOOLEAN,
    validation_log TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS patches_job_id_idx ON patches(job_id);

-- -----------------------------------------------------------------------------
-- 11. Pull Requests Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pull_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES fix_jobs(id) ON DELETE CASCADE,
    patch_id UUID NOT NULL REFERENCES patches(id) ON DELETE RESTRICT,
    pr_number INTEGER,
    pr_url TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'merged')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id)
);

CREATE INDEX IF NOT EXISTS pull_requests_job_id_idx ON pull_requests(job_id);
