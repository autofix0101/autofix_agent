"""
GitHub REST API client for the Repo Analyzer Agent.

"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _auth_headers(token: str) -> dict[str, str]:
    return {**_HEADERS, "Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DiffFile:
    path: str
    status: Literal["added", "modified", "removed", "renamed", "copied", "changed", "unchanged"]
    # For renames: previous path (same as path for non-renames)
    previous_path: str | None = None


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

async def get_latest_commit_sha(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    branch: str,
    token: str,
) -> str:
    """Return the SHA of the latest commit on *branch*."""
    resp = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        headers=_auth_headers(token),
        params={"sha": branch, "per_page": 1},
    )
    resp.raise_for_status()
    commits = resp.json()
    if not commits:
        raise ValueError(f"No commits found on branch '{branch}' for {owner}/{repo}")
    return commits[0]["sha"]


async def get_diff_files(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    base_sha: str,
    head_sha: str,
    token: str,
) -> list[DiffFile]:
    """
    Return files changed between *base_sha* and *head_sha*.

    Uses GET /repos/{owner}/{repo}/compare/{base}...{head}.
    GitHub paginates at 300 files; we follow the 'next' link if present.
    """
    diff_files: list[DiffFile] = []
    url = f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}"

    while url:
        resp = await client.get(url, headers=_auth_headers(token))
        resp.raise_for_status()
        data = resp.json()

        for f in data.get("files", []):
            status = f["status"]
            filename = f["filename"]
            previous = f.get("previous_filename")

            diff_files.append(
                DiffFile(
                    path=filename,
                    status=status,
                    previous_path=previous if previous != filename else None,
                )
            )

        # Follow pagination (rare but possible for large diffs)
        url = resp.links.get("next", {}).get("url")  # type: ignore[assignment]

    return diff_files


async def get_file_content(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    ref: str,
    token: str,
) -> str | None:
    """
    Fetch the decoded text content of a file at *ref*.

    Returns None if the file is binary, too large (>1 MB), or not found.
    GitHub's /contents/ API encodes content as base64 and caps at 1 MB.
    """
    resp = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers=_auth_headers(token),
        params={"ref": ref},
    )

    if resp.status_code == 404:
        logger.warning("File not found on GitHub: %s@%s", path, ref[:8])
        return None

    resp.raise_for_status()
    data = resp.json()

    # Directories or submodules are returned as lists or have type != 'file'
    if isinstance(data, list) or data.get("type") != "file":
        return None

    # GitHub marks files > 1 MB as having encoding == 'none'
    if data.get("encoding") != "base64":
        logger.warning("Skipping %s — content not base64 (size > 1 MB?)", path)
        return None

    raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return raw


async def get_repo_tree(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    sha: str,
    token: str,
) -> list[str]:
    """
    Return every blob path in the repository tree at *sha*.

    Uses the Git Trees API with recursive=1 (flat list).
    GitHub truncates trees with > 100 000 entries; we log a warning if so.
    """
    resp = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{sha}",
        headers=_auth_headers(token),
        params={"recursive": "1"},
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("truncated"):
        logger.warning(
            "Git tree for %s/%s@%s is truncated (>100k entries). "
            "Some files will not be indexed.",
            owner, repo, sha[:8],
        )

    return [
        item["path"]
        for item in data.get("tree", [])
        if item["type"] == "blob"
    ]
