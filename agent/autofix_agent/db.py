"""
PostgreSQL database queries — matched to the existing server DB schema.

Existing tables (unchanged):
  repositories  — id, user_id, owner, name, clone_url, default_branch, last_commit_sha, github_access_token (via users join)
  files         — id, repo_id, path, language, content_hash
  code_chunks   — id, file_id, chunk_key, symbol_name, chunk_type, start_line, end_line, language, content, content_hash, embedding
  signals       — id, repo_id, type, source_ref, raw_content, status, parsed_stack_trace, parsed_data
  fix_jobs      — id, repo_id, signal_id, status, attempt_count, error_message
  job_events    — id, job_id, stage, message, created_at
  localization_candidates — id, job_id, chunk_id, rank, score, method
  patches       — id, job_id, attempt_number, diff_content, explanation, validation_passed, validation_log
  pull_requests — id, job_id, ...
"""
from __future__ import annotations

from typing import Any
import asyncpg

from .config import settings
from .utils.logging import get_logger

logger = get_logger("db")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the global asyncpg connection pool, initializing if necessary."""
    global _pool
    if _pool is None:
        logger.info("Initializing asyncpg connection pool...")
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    """Close the global asyncpg connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed.")


def _to_pgvector(embedding: list[float] | None) -> str | None:
    """Convert list of floats to pgvector string: '[x,y,z]'."""
    if embedding is None:
        return None
    return "[" + ",".join(str(v) for v in embedding) + "]"


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

async def get_repo_for_indexing(repo_id: str) -> dict[str, Any] | None:
    """
    Fetch everything the agent needs to index a repository.
    Returns: id, owner, name, default_branch, last_commit_sha, github_access_token
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
            r.id,
            r.owner,
            r.name,
            r.clone_url,
            r.default_branch,
            r.last_commit_sha,
            u.github_access_token
        FROM repositories r
        JOIN users u ON u.id = r.user_id
        WHERE r.id = $1
        """,
        repo_id,
    )
    return dict(row) if row else None


async def update_last_commit_sha(repo_id: str, sha: str) -> None:
    """Update last_commit_sha after successful indexing."""
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE repositories
        SET last_commit_sha = $2,
            updated_at      = NOW()
        WHERE id = $1
        """,
        repo_id,
        sha,
    )


# ---------------------------------------------------------------------------
# Files  (files table — join between repositories and code_chunks)
# ---------------------------------------------------------------------------

async def upsert_file(
    repo_id: str,
    path: str,
    language: str | None,
    content_hash: str,
) -> str:
    """Upsert a file record and return its UUID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO files (repo_id, path, language, content_hash)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (repo_id, path) DO UPDATE
            SET language     = EXCLUDED.language,
                content_hash = EXCLUDED.content_hash,
                updated_at   = NOW()
        RETURNING id
        """,
        repo_id,
        path,
        language,
        content_hash,
    )
    return str(row["id"])  # type: ignore[index]


async def delete_file(repo_id: str, path: str) -> None:
    """Delete a file record — code_chunks cascade-delete automatically."""
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM files WHERE repo_id = $1 AND path = $2",
        repo_id,
        path,
    )


async def get_file_paths_for_repo(repo_id: str) -> list[str]:
    """Return every indexed file path for a repository."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT path FROM files WHERE repo_id = $1",
        repo_id,
    )
    return [row["path"] for row in rows]


# ---------------------------------------------------------------------------
# Code Chunks
# ---------------------------------------------------------------------------

async def delete_chunks_for_file(file_id: str) -> None:
    """Remove all code chunks for a file before re-inserting fresh ones."""
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM code_chunks WHERE file_id = $1",
        file_id,
    )


async def insert_code_chunks(
    file_id: str,
    chunks: list[dict[str, Any]],
) -> None:
    """Bulk-insert code chunks for a file."""
    pool = await get_pool()
    records = [
        (
            file_id,
            c["chunk_key"],
            c.get("symbol_name"),
            c["chunk_type"],
            c["start_line"],
            c["end_line"],
            c["language"],
            c["content"],
            c["content_hash"],
            _to_pgvector(c.get("embedding")),
        )
        for c in chunks
    ]
    await pool.executemany(
        """
        INSERT INTO code_chunks
            (file_id, chunk_key, symbol_name, chunk_type,
             start_line, end_line, language, content, content_hash, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector)
        ON CONFLICT (file_id, chunk_key) DO UPDATE
            SET symbol_name  = EXCLUDED.symbol_name,
                chunk_type   = EXCLUDED.chunk_type,
                start_line   = EXCLUDED.start_line,
                end_line     = EXCLUDED.end_line,
                language     = EXCLUDED.language,
                content      = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                embedding    = EXCLUDED.embedding,
                updated_at   = NOW()
        """,
        records,
    )


# ---------------------------------------------------------------------------
# Localization — chunk search queries
# ---------------------------------------------------------------------------

async def find_chunk_by_file_and_line(
    repo_id: str,
    file_path: str,
    line_number: int,
) -> dict[str, Any] | None:
    """
    Direct match: find the most specific chunk enclosing line_number in file_path.
    Uses the files join table to resolve repo_id -> file_id -> code_chunks.
    """
    pool = await get_pool()
    clean_path = file_path.replace("\\", "/").lstrip("/")
    row = await pool.fetchrow(
        """
        SELECT c.id, c.file_id, f.path as file_path, c.symbol_name, c.chunk_type,
               c.start_line, c.end_line, c.language, c.content
        FROM code_chunks c
        JOIN files f ON f.id = c.file_id
        WHERE f.repo_id = $1
          AND (f.path = $2 OR f.path LIKE '%' || $2 OR $2 LIKE '%' || f.path)
          AND c.start_line <= $3 AND c.end_line >= $3
        ORDER BY (c.end_line - c.start_line) ASC
        LIMIT 1
        """,
        repo_id,
        clean_path,
        line_number,
    )
    return dict(row) if row else None


async def find_chunk_by_symbol(
    repo_id: str,
    symbol_name: str,
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    """Find code chunks by symbol name (optionally within a specific file)."""
    pool = await get_pool()
    if file_path:
        clean_path = file_path.replace("\\", "/").lstrip("/")
        rows = await pool.fetch(
            """
            SELECT c.id, c.file_id, f.path as file_path, c.symbol_name, c.chunk_type,
                   c.start_line, c.end_line, c.language, c.content
            FROM code_chunks c
            JOIN files f ON f.id = c.file_id
            WHERE f.repo_id = $1
              AND c.symbol_name = $2
              AND (f.path = $3 OR f.path LIKE '%' || $3 OR $3 LIKE '%' || f.path)
            LIMIT 5
            """,
            repo_id, symbol_name, clean_path,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT c.id, c.file_id, f.path as file_path, c.symbol_name, c.chunk_type,
                   c.start_line, c.end_line, c.language, c.content
            FROM code_chunks c
            JOIN files f ON f.id = c.file_id
            WHERE f.repo_id = $1
              AND c.symbol_name = $2
            LIMIT 5
            """,
            repo_id, symbol_name,
        )
    return [dict(r) for r in rows]


async def search_chunks_by_vector(
    repo_id: str,
    embedding: list[float],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """pgvector cosine similarity search over code_chunks."""
    pool = await get_pool()
    pgvec = _to_pgvector(embedding)
    if not pgvec:
        return []
    rows = await pool.fetch(
        """
        SELECT c.id, c.file_id, f.path as file_path, c.symbol_name, c.chunk_type,
               c.start_line, c.end_line, c.language, c.content,
               1 - (c.embedding <=> $2::vector) AS similarity
        FROM code_chunks c
        JOIN files f ON f.id = c.file_id
        WHERE f.repo_id = $1
          AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> $2::vector ASC
        LIMIT $3
        """,
        repo_id,
        pgvec,
        limit,
    )
    return [dict(r) for r in rows]


async def search_chunks_by_keyword(
    repo_id: str,
    keyword: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Keyword fallback search across chunk content and symbol names."""
    pool = await get_pool()
    pattern = f"%{keyword}%"
    rows = await pool.fetch(
        """
        SELECT c.id, c.file_id, f.path as file_path, c.symbol_name, c.chunk_type,
               c.start_line, c.end_line, c.language, c.content
        FROM code_chunks c
        JOIN files f ON f.id = c.file_id
        WHERE f.repo_id = $1
          AND (c.content ILIKE $2 OR c.symbol_name ILIKE $2)
        LIMIT $3
        """,
        repo_id,
        pattern,
        limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

async def get_signal(signal_id: str) -> dict[str, Any] | None:
    """Fetch a signal by ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, repo_id, type, source_ref, raw_content,
               parsed_stack_trace, parsed_data, status, created_at
        FROM signals
        WHERE id = $1
        """,
        signal_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Fix Jobs
# ---------------------------------------------------------------------------

async def claim_next_job() -> dict[str, Any] | None:
    """
    Atomically claim the next queued fix job using SELECT ... FOR UPDATE SKIP LOCKED.
    Updates status to 'reindexing' immediately on claim.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, repo_id, signal_id, status, attempt_count
                FROM fix_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            if not row:
                return None

            job_id = row["id"]
            await conn.execute(
                """
                UPDATE fix_jobs
                SET status = 'reindexing',
                    updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
            )
            await conn.execute(
                """
                INSERT INTO job_events (job_id, stage, message)
                VALUES ($1, 'reindexing', 'Agent claimed job.')
                """,
                job_id,
            )
            job = dict(row)
            job["status"] = "reindexing"
            return job


async def update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
    attempt_count: int | None = None,
) -> None:
    """Update fix_job status and optional error message."""
    pool = await get_pool()
    if attempt_count is not None:
        await pool.execute(
            """
            UPDATE fix_jobs
            SET status = $2, error_message = $3, attempt_count = $4, updated_at = NOW()
            WHERE id = $1
            """,
            job_id, status, error_message, attempt_count,
        )
    else:
        await pool.execute(
            """
            UPDATE fix_jobs
            SET status = $2, error_message = $3, updated_at = NOW()
            WHERE id = $1
            """,
            job_id, status, error_message,
        )


async def add_job_event(job_id: str, stage: str, message: str) -> None:
    """Insert a job_events row for progress tracking."""
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO job_events (job_id, stage, message) VALUES ($1, $2, $3)",
        job_id, stage, message,
    )


# ---------------------------------------------------------------------------
# Localization Candidates
# ---------------------------------------------------------------------------

async def insert_localization_candidates(
    job_id: str,
    candidates: list[dict[str, Any]],
) -> None:
    """Save ranked candidate chunks to localization_candidates table."""
    if not candidates:
        return
    pool = await get_pool()
    records = [
        (
            job_id,
            c["chunk_id"],
            c["rank"],
            float(c["score"]),
            c["method"],
        )
        for c in candidates
        if c.get("chunk_id")
    ]
    if not records:
        return
    await pool.executemany(
        """
        INSERT INTO localization_candidates (job_id, chunk_id, rank, score, method)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (job_id, chunk_id) DO UPDATE
            SET rank   = EXCLUDED.rank,
                score  = EXCLUDED.score,
                method = EXCLUDED.method
        """,
        records,
    )


# ---------------------------------------------------------------------------
# Patches
# ---------------------------------------------------------------------------

async def insert_patch(
    job_id: str,
    attempt_number: int,
    diff_content: str,
    explanation: str,
    validation_passed: bool = False,
    validation_log: str | None = None,
) -> str:
    """Insert a patch and return its UUID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO patches (job_id, attempt_number, diff_content, explanation,
                             validation_passed, validation_log)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        job_id, attempt_number, diff_content, explanation,
        validation_passed, validation_log,
    )
    return str(row["id"])


async def update_patch_validation(
    patch_id: str,
    validation_passed: bool,
    validation_log: str | None = None,
) -> None:
    """Update validation outcome for a patch."""
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE patches
        SET validation_passed = $2, validation_log = $3
        WHERE id = $1
        """,
        patch_id, validation_passed, validation_log,
    )
