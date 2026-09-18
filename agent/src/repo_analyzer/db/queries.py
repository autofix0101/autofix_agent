from __future__ import annotations

from typing import Any
import asyncpg

from .connection import get_pool


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

async def get_repo_for_indexing(repo_id: str) -> dict[str, Any] | None:
    """
    Fetch everything the agent needs to index a repository.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
            r.id,
            r.owner,
            r.name,
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
# Files
# ---------------------------------------------------------------------------

async def upsert_file(
    repo_id: str,
    path: str,
    language: str | None,
    content_hash: str,
) -> str:
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
    """
    Delete a file record (and all its code_chunks via CASCADE).
    Used when a file is removed in a git diff.
    """
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
# Code chunks
# ---------------------------------------------------------------------------

async def delete_chunks_for_file(file_id: str) -> None:
    """
    Remove all code chunks for a file before re-inserting fresh ones.
    """
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM code_chunks WHERE file_id = $1",
        file_id,
    )


def _to_pgvector(embedding: list[float] | None) -> str | None:
    """
    Convert a Python list of floats to the pgvector string literal format.
    """
    if embedding is None:
        return None
    return "[" + ",".join(str(v) for v in embedding) + "]"


async def insert_code_chunks(
    file_id: str,
    chunks: list[dict[str, Any]],
) -> None:
    """
    Bulk-insert code chunks for a file.
    """
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
            # asyncpg cannot serialise list[float] directly into pgvector.
            # Cast to the "[x,y,z]" string representation that the
            # `$10::vector` cast in the SQL can then parse correctly.
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
