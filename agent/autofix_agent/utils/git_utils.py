"""
Shared low-level git subprocess helpers.
"""
from __future__ import annotations

import os
import subprocess
from typing import Sequence

from .logging import get_logger

logger = get_logger("git_utils")


def run_git(
    args: Sequence[str],
    cwd: str | None = None,
    check: bool = False,
) -> tuple[int, str, str]:
    """
    Execute a git command using subprocess.

    Returns:
        tuple (returncode, stdout, stderr)
    """
    cmd = ["git"] + list(args)
    logger.debug("Executing git command: %s (cwd=%s)", " ".join(cmd), cwd)

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if check and proc.returncode != 0:
        err_msg = f"Git command failed: {' '.join(cmd)}\nSTDERR: {proc.stderr}\nSTDOUT: {proc.stdout}"
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def get_head_sha(repo_path: str) -> str:
    """Return the current HEAD commit SHA of the repository."""
    code, stdout, stderr = run_git(["rev-parse", "HEAD"], cwd=repo_path, check=True)
    return stdout.strip()


def get_diff_name_status(
    repo_path: str,
    old_sha: str | None,
    new_sha: str,
) -> list[tuple[str, str]]:
    """
    Run `git diff --name-status <old_sha> <new_sha>`.

    Returns a list of tuples: [(status_code, file_path), ...]
    where status_code is 'A', 'M', 'D', 'R', etc.
    """
    if not old_sha:
        # If no previous sha, list all tracked files as Added ('A')
        code, stdout, stderr = run_git(["ls-files"], cwd=repo_path, check=True)
        files = [line.strip() for line in stdout.splitlines() if line.strip()]
        return [("A", f) for f in files]

    args = ["diff", "--name-status", old_sha, new_sha]
    code, stdout, stderr = run_git(args, cwd=repo_path, check=True)

    results: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            status = parts[0][0].upper()  # 'A', 'M', 'D', 'R'
            # If renamed, parts can be [R100, old_path, new_path]
            path = parts[-1]
            results.append((status, path))

    return results


def clone_repo(
    clone_url: str,
    target_dir: str,
    branch: str = "main",
) -> str:
    """Clone a git repository to target_dir."""
    os.makedirs(os.path.dirname(os.path.abspath(target_dir)), exist_ok=True)
    if os.path.exists(target_dir):
        logger.info("Target directory %s already exists, skipping clone.", target_dir)
        return target_dir

    logger.info("Cloning %s (branch: %s) -> %s", clone_url, branch, target_dir)
    args = ["clone", "--branch", branch, clone_url, target_dir]
    run_git(args, check=True)
    return target_dir


def pull_repo(repo_path: str, branch: str = "main") -> str:
    """Pull latest changes from origin branch."""
    logger.info("Pulling latest git changes in %s (branch: %s)", repo_path, branch)
    run_git(["checkout", branch], cwd=repo_path, check=False)
    run_git(["pull", "origin", branch], cwd=repo_path, check=True)
    return get_head_sha(repo_path)


def apply_patch_git(
    repo_path: str,
    patch_content: str,
    check_only: bool = False,
) -> tuple[bool, str]:
    """
    Apply a unified diff patch using `git apply`.
    """
    cmd = ["apply"]
    if check_only:
        cmd.append("--check")
    cmd.append("-")

    proc = subprocess.run(
        ["git"] + cmd,
        cwd=repo_path,
        input=patch_content,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode == 0:
        return True, "Patch applied successfully."

    # Try with --ignore-whitespace if failed
    retry_cmd = ["git", "apply", "--ignore-whitespace"]
    if check_only:
        retry_cmd.append("--check")
    retry_cmd.append("-")

    retry_proc = subprocess.run(
        retry_cmd,
        cwd=repo_path,
        input=patch_content,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if retry_proc.returncode == 0:
        return True, "Patch applied with --ignore-whitespace."

    err = f"git apply failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}\nFallback STDERR: {retry_proc.stderr}"
    return False, err
