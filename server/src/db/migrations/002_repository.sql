CREATE TABLE repositories (
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

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, github_repo_id)
);