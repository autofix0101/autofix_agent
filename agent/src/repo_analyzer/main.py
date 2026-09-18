"""
Repo Analyzer Agent — Main Orchestrator.

Entry point:  python -m repo_analyzer <repo_id>

The agent:
  1. Fetches repository details (owner, name, branch, last_commit_sha, token)
     from the database (via the backend's shared PostgreSQL instance).
  2. Calls the GitHub API for the current HEAD SHA on the default branch.
  3. Decides between full indexing or incremental indexing:
       • No stored SHA  → full index
       • SHA unchanged  → already up to date, exit
       • SHA differs    → incremental diff
  4. Parses source files with AST-based chunkers.
  5. Generates embeddings via OpenAI text-embedding-3-small.
  6. Writes files + code_chunks to PostgreSQL.
  7. Updates repositories.last_commit_sha ONLY after success.

The backend remains the gatekeeper — the agent does not create or
authenticate repository records; it reads what the backend has already
validated and written.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import sys

import httpx
from dotenv import load_dotenv

from .db.connection import close_pool
from .db import queries
from .github import client as gh
from .chunker.ast_chunker import chunk_file, is_indexable
from .embedder.openai_embedder import embed_chunks
from .models import CodeChunk

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("repo_analyzer")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _index_single_file(
    http: httpx.AsyncClient,
    repo: dict,
    file_path: str,
    ref: str,
) -> None:
    """
    Full pipeline for one file:
      fetch → chunk → embed → delete old chunks → insert new ones.
    """
    owner, name, token = repo["owner"], repo["name"], repo["github_access_token"]
    repo_id: str = repo["id"]

    source = await gh.get_file_content(http, owner, name, file_path, ref, token)
    if source is None:
        # Binary, too large, or not found — skip without failing
        logger.warning("Skipping %s (could not fetch content)", file_path)
        return

    try:
        language, chunks = chunk_file(source, file_path)
    except ValueError:
        # Extension not indexable (shouldn't reach here, but be safe)
        logger.debug("Skipping %s (not indexable)", file_path)
        return

    if not chunks:
        logger.debug("No chunks extracted from %s", file_path)
        return

    # Embed all chunks for this file
    await embed_chunks(chunks)

    # Upsert file record
    file_id = await queries.upsert_file(
        repo_id, file_path, language, _content_hash(source)
    )

    # Clean slate — delete all existing chunks, then insert fresh ones
    await queries.delete_chunks_for_file(file_id)
    await queries.insert_code_chunks(file_id, [c.to_dict() for c in chunks])

    logger.info(
        "Indexed %s — %d chunk(s) [%s]",
        file_path,
        len(chunks),
        language,
    )


# ---------------------------------------------------------------------------
# Full Index
# ---------------------------------------------------------------------------

async def full_index(
    http: httpx.AsyncClient,
    repo: dict,
    head_sha: str,
) -> None:
    """
    Index every indexable file in the repository tree at *head_sha*.
    """
    owner, name, token = repo["owner"], repo["name"], repo["github_access_token"]
    logger.info("Starting FULL INDEX for %s/%s @ %s", owner, name, head_sha[:8])

    all_paths = await gh.get_repo_tree(http, owner, name, head_sha, token)
    indexable = [p for p in all_paths if is_indexable(p)]

    logger.info("Found %d indexable file(s) out of %d total", len(indexable), len(all_paths))

    for path in indexable:
        try:
            await _index_single_file(http, repo, path, head_sha)
        except Exception:
            logger.exception("Error indexing %s — skipping file", path)


# ---------------------------------------------------------------------------
# Incremental Index
# ---------------------------------------------------------------------------

async def incremental_index(
    http: httpx.AsyncClient,
    repo: dict,
    base_sha: str,
    head_sha: str,
) -> None:
    """
    Index only the files that changed between *base_sha* and *head_sha*.

    Strategy per file status:
      added    → index (fetch + chunk + embed + insert)
      modified → delete old chunks → index fresh
      renamed  → delete old path record + index new path
      removed  → delete file record (CASCADE removes code_chunks)
    """
    owner, name, token = repo["owner"], repo["name"], repo["github_access_token"]
    repo_id: str = repo["id"]

    logger.info(
        "Starting INCREMENTAL INDEX for %s/%s  %s → %s",
        owner, name, base_sha[:8], head_sha[:8],
    )

    diff_files = await gh.get_diff_files(http, owner, name, base_sha, head_sha, token)
    logger.info("Diff contains %d changed file(s)", len(diff_files))

    for diff_file in diff_files:
        path = diff_file.path
        status = diff_file.status

        try:
            if status == "removed":
                # Delete the file record; code_chunks cascade automatically
                await queries.delete_file(repo_id, path)
                logger.info("Removed   %s", path)

            elif status == "renamed" and diff_file.previous_path:
                # Remove old path, then index under the new path
                await queries.delete_file(repo_id, diff_file.previous_path)
                logger.info("Removed old path  %s", diff_file.previous_path)
                if is_indexable(path):
                    await _index_single_file(http, repo, path, head_sha)

            elif status in ("added", "modified", "changed", "copied"):
                if is_indexable(path):
                    await _index_single_file(http, repo, path, head_sha)
                else:
                    logger.debug("Skipping non-indexable changed file: %s", path)

            else:
                # unchanged / unknown — nothing to do
                logger.debug("Skipping status=%s for %s", status, path)

        except Exception:
            logger.exception("Error processing diff file %s (status=%s) — skipping", path, status)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run(repo_id: str) -> None:
    """
    Main entry point for the Repo Analyzer Agent.

    Reads repo details from DB, fetches the latest GitHub commit SHA,
    decides full vs incremental indexing, runs it, and updates the SHA
    in the DB only on success.
    """
    async with httpx.AsyncClient(timeout=30.0) as http:
        # ── 1. Load repo details from DB ──────────────────────────────────
        repo = await queries.get_repo_for_indexing(repo_id)
        if repo is None:
            logger.error("Repository %s not found in database", repo_id)
            sys.exit(1)

        owner = repo["owner"]
        name = repo["name"]
        branch = repo["default_branch"]
        stored_sha: str | None = repo["last_commit_sha"]
        token: str = repo["github_access_token"]

        logger.info("Repo: %s/%s  branch=%s", owner, name, branch)

        # ── 2. Fetch latest SHA from GitHub ───────────────────────────────
        try:
            head_sha = await gh.get_latest_commit_sha(http, owner, name, branch, token)
        except Exception:
            logger.exception("Failed to fetch latest commit SHA from GitHub")
            sys.exit(1)

        logger.info("Stored SHA : %s", stored_sha or "(none)")
        logger.info("Remote SHA : %s", head_sha)

        # ── 3. Decide indexing strategy ───────────────────────────────────
        if stored_sha is None:
            # First time — full index
            await full_index(http, repo, head_sha)

        elif stored_sha == head_sha:
            logger.info("Repository is up to date — nothing to do")
            return

        else:
            # Incremental diff
            await incremental_index(http, repo, stored_sha, head_sha)

        # ── 4. Persist new SHA only after success ─────────────────────────
        await queries.update_last_commit_sha(repo_id, head_sha)
        logger.info("Updated last_commit_sha → %s", head_sha)

    logger.info("Repo Analyzer Agent completed successfully for %s/%s", owner, name)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cli() -> None:
    """
    CLI shim:  python -m repo_analyzer <repo_id>
                 or
               repo-analyzer <repo_id>    (if installed via pip)
    """
    if len(sys.argv) != 2:
        print("Usage: repo-analyzer <repo_id>", file=sys.stderr)
        sys.exit(1)

    repo_id = sys.argv[1]

    async def _main() -> None:
        try:
            await run(repo_id)
        finally:
            await close_pool()

    asyncio.run(_main())


if __name__ == "__main__":
    cli()
