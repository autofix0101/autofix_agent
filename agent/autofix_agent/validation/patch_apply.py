"""
Git patch apply wrapper with error handling.
"""
from __future__ import annotations

import os
from ..utils.git_utils import apply_patch_git
from ..utils.logging import get_logger

logger = get_logger("validation.patch_apply")


def apply_patch(
    repo_path: str,
    diff_content: str,
    check_only: bool = False,
) -> tuple[bool, str]:
    """
    Apply a unified diff patch to the target directory.

    Returns:
        tuple (success: bool, message: str)
    """
    if not diff_content or not diff_content.strip():
        return False, "Error: Diff content is empty."

    success, message = apply_patch_git(repo_path, diff_content, check_only=check_only)
    if not success:
        logger.warning("Failed to apply patch in %s: %s", repo_path, message[:200])
    else:
        logger.info("Successfully applied patch to %s", repo_path)

    return success, message
