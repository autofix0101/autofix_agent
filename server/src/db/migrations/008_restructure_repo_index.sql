CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,

    path TEXT NOT NULL,
    language TEXT,

    -- Used to quickly determine whether the file changed.
    content_hash TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (repo_id, path)
);

CREATE INDEX files_repo_id_idx ON files(repo_id);


CREATE TABLE code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,

    -- Stable identity of the logical code unit.
    chunk_key TEXT NOT NULL,

    symbol_name TEXT,

    chunk_type TEXT NOT NULL,

    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,

    language TEXT NOT NULL,

    -- Contextual representation used for embedding/search, may contain file path, symbol, signature,
    content TEXT NOT NULL,

    -- Hash of this chunk's current content.
    -- Used for incremental embedding generation.
    content_hash TEXT NOT NULL,
    embedding VECTOR(1536),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (file_id, chunk_key)
);


CREATE INDEX code_chunks_file_id_idx
    ON code_chunks(file_id);

CREATE INDEX code_chunks_symbol_name_idx
    ON code_chunks(file_id, symbol_name);

CREATE INDEX code_chunks_chunk_type_idx
    ON code_chunks(file_id, chunk_type);