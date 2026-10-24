"""
Indexing Orchestrator — adapted from the original src/repo_analyzer/main.py.

Uses GitHub API to fetch files (same as the working original), then
chunks + embeds + stores into the existing files/code_chunks schema.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from .. import db
from ..utils.logging import get_logger
from .chunker import chunk_file_content, is_chunkable_file
from .embedder import embed_chunks
from .github_client import (
    DiffFile,
    get_diff_files,
    get_file_content,
    get_latest_commit_sha,
    get_repo_tree,
)

logger = get_logger("indexing.indexer")


def _content_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _index_single_file(
    http: httpx.AsyncClient,
    repo: dict[str, Any],
    file_path: str,
    ref: str,
) -> None:
    """
    Full pipeline for one file:
      fetch from GitHub → chunk → embed → upsert file row → delete old chunks → insert new chunks
    """
    owner = repo["owner"]
    name = repo["name"]
    token = repo["github_access_token"]
    repo_id = str(repo["id"])

    source = await get_file_content(http, owner, name, file_path, ref, token)
    if source is None:
        logger.warning("Skipping %s (could not fetch content)", file_path)
        return

    chunks = chunk_file_content(source, file_path)
    if not chunks:
        logger.debug("No chunks extracted from %s", file_path)
        return

    # Determine language from first chunk
    language = chunks[0].language if chunks else None

    # Embed all chunks for this file
    await embed_chunks(chunks)

    # Upsert file record, get file_id
    file_id = await db.upsert_file(repo_id, file_path, language, _content_hash(source))

    # Clean slate — delete existing chunks then insert fresh ones
    await db.delete_chunks_for_file(file_id)
    await db.insert_code_chunks(file_id, [c.to_dict() for c in chunks])

    logger.info("Indexed %s — %d chunk(s) [%s]", file_path, len(chunks), language)


async def full_index(
    http: httpx.AsyncClient,
    repo: dict[str, Any],
    head_sha: str,
) -> None:
    """Index every indexable file in the repository tree at head_sha."""
    owner = repo["owner"]
    name = repo["name"]
    token = repo["github_access_token"]

    logger.info("Starting FULL INDEX for %s/%s @ %s", owner, name, head_sha[:8])

    all_paths = await get_repo_tree(http, owner, name, head_sha, token)
    indexable = [p for p in all_paths if is_chunkable_file(p)]

    logger.info("Found %d indexable file(s) out of %d total", len(indexable), len(all_paths))

    for path in indexable:
        await _index_single_file(http, repo, path, head_sha)


async def incremental_index(
    http: httpx.AsyncClient,
    repo: dict[str, Any],
    base_sha: str,
    head_sha: str,
) -> None:
    """Index only files that changed between base_sha and head_sha."""
    owner = repo["owner"]
    name = repo["name"]
    token = repo["github_access_token"]
    repo_id = str(repo["id"])

    logger.info(
        "Starting INCREMENTAL INDEX for %s/%s  %s → %s",
        owner, name, base_sha[:8], head_sha[:8],
    )

    diff_files = await get_diff_files(http, owner, name, base_sha, head_sha, token)
    logger.info("Diff contains %d changed file(s)", len(diff_files))

    for diff_file in diff_files:
        path = diff_file.path
        status = diff_file.status

        if status == "removed":
            await db.delete_file(repo_id, path)
            logger.info("Removed   %s", path)

        elif status == "renamed" and diff_file.previous_path:
            await db.delete_file(repo_id, diff_file.previous_path)
            logger.info("Removed old path  %s", diff_file.previous_path)
            if is_chunkable_file(path):
                await _index_single_file(http, repo, path, head_sha)

        elif status in ("added", "modified", "changed", "copied"):
            if is_chunkable_file(path):
                await _index_single_file(http, repo, path, head_sha)
            else:
                logger.debug("Skipping non-indexable changed file: %s", path)

        else:
            logger.debug("Skipping status=%s for %s", status, path)


async def run_indexing(repo_id: str) -> str:
    """
    Main indexing entry point. Fetches repo from DB, decides full vs incremental,
    runs it, and updates last_commit_sha only on success.
    Returns the new head_sha.
    """
    repo = await db.get_repo_for_indexing(repo_id)
    if repo is None:
        raise ValueError(f"Repository {repo_id} not found in database.")

    owner = repo["owner"]
    name = repo["name"]
    branch = repo["default_branch"]
    stored_sha: str | None = repo["last_commit_sha"]
    token: str = repo["github_access_token"]

    logger.info("Repo: %s/%s  branch=%s", owner, name, branch)

    async with httpx.AsyncClient(timeout=30.0) as http:
        head_sha = await get_latest_commit_sha(http, owner, name, branch, token)

        logger.info("Stored SHA : %s", stored_sha or "(none — full index)")
        logger.info("Remote SHA : %s", head_sha)

        if stored_sha is None:
            await full_index(http, repo, head_sha)
        elif stored_sha == head_sha:
            logger.info("Repository is up to date — nothing to do")
            return head_sha
        else:
            await incremental_index(http, repo, stored_sha, head_sha)

        # Update SHA only after successful completion
        await db.update_last_commit_sha(repo_id, head_sha)
        logger.info("Updated last_commit_sha → %s", head_sha)

    logger.info("Indexing completed for %s/%s", owner, name)
    return head_sha
