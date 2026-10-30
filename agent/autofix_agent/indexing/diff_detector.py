"""
Diff detector for incremental indexing.

Uses `git diff --name-status <last_indexed_sha> <current_head_sha>` to detect
which files were added, modified, or deleted without walking the entire codebase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from ..utils.git_utils import get_diff_name_status
from ..utils.logging import get_logger

logger = get_logger("indexing.diff_detector")


@dataclass
class ChangedFiles:
    """Represents file changes between two commit SHAs."""
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.modified and not self.deleted

    @property
    def total_changed(self) -> int:
        return len(self.added) + len(self.modified) + len(self.deleted)


def detect_changed_files(
    repo_path: str,
    old_sha: str | None,
    new_sha: str,
) -> ChangedFiles:
    """
    Detect files changed between old_sha and new_sha.

    Args:
        repo_path: Local path to git repository.
        old_sha: Last indexed commit SHA (or None for initial index).
        new_sha: Current HEAD commit SHA.

    Returns:
        ChangedFiles containing lists of added, modified, deleted paths.
    """
    if old_sha == new_sha:
        logger.info("old_sha is identical to new_sha (%s). No files changed.", new_sha)
        return ChangedFiles()

    raw_statuses = get_diff_name_status(repo_path, old_sha, new_sha)
    changes = ChangedFiles()

    for status, path in raw_statuses:
        # Normalize separators
        clean_path = path.replace("\\", "/").lstrip("/")
        if status in ("A", "C"):  # Added or Copied
            changes.added.append(clean_path)
        elif status in ("M", "T"):  # Modified or type changed
            changes.modified.append(clean_path)
        elif status == "D":  # Deleted
            changes.deleted.append(clean_path)
        elif status.startswith("R"):  # Renamed
            changes.modified.append(clean_path)
        else:
            changes.modified.append(clean_path)

    logger.info(
        "Detected changes (%s -> %s): %d added, %d modified, %d deleted",
        old_sha[:8] if old_sha else "NONE",
        new_sha[:8],
        len(changes.added),
        len(changes.modified),
        len(changes.deleted),
    )
    return changes
