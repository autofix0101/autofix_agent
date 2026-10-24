"""
Git clone and git pull helpers for the Indexing Agent.
"""
from __future__ import annotations

import os
from ..utils.git_utils import clone_repo, pull_repo, get_head_sha
from ..utils.logging import get_logger

logger = get_logger("indexing.clone")


def ensure_repo_cloned(
    clone_url: str,
    local_path: str,
    default_branch: str = "main",
) -> str:
    """
    Ensure the repository is cloned locally at `local_path`.
    Returns the repository HEAD commit sha.
    """
    if not os.path.exists(local_path) or not os.path.exists(os.path.join(local_path, ".git")):
        logger.info("Cloning repository %s -> %s", clone_url, local_path)
        clone_repo(clone_url, local_path, default_branch)
    return get_head_sha(local_path)


def pull_and_get_head(
    local_path: str,
    default_branch: str = "main",
) -> str:
    """
    Pull latest changes from the default branch and return HEAD sha.
    """
    return pull_repo(local_path, default_branch)
