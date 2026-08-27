CREATE TABLE users(
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id BIGINT NOT NULL UNIQUE,
    github_username VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    avatar_url VARCHAR(255),
    github_access_token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);