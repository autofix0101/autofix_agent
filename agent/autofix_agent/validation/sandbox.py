"""
Sandbox environment manager for patch testing.

Creates an isolated throwaway clone or worktree so the test suite can run
safely without mutating or dirtying the agent's primary repository working directory.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from ..utils.git_utils import run_git
from ..utils.logging import get_logger

logger = get_logger("validation.sandbox")


class Sandbox:
    """Manages an isolated throwaway clone for validating patches."""

    def __init__(self, source_repo_path: str):
        self.source_repo_path = os.path.abspath(source_repo_path)
        self.sandbox_dir: str | None = None

    def __enter__(self) -> str:
        self.sandbox_dir = tempfile.mkdtemp(prefix="autofix_sandbox_")
        logger.info("Created throwaway sandbox at %s", self.sandbox_dir)

        # Clone locally from source repo to sandbox for complete isolation
        code, stdout, stderr = run_git(
            ["clone", "--local", self.source_repo_path, self.sandbox_dir],
            check=False,
        )
        if code != 0:
            logger.warning("Local git clone failed (%s); falling back to direct copy", stderr)
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)
            shutil.copytree(
                self.source_repo_path,
                self.sandbox_dir,
                ignore=shutil.ignore_patterns(".git", "venv", ".venv", "node_modules", "__pycache__"),
            )

        return self.sandbox_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sandbox_dir and os.path.exists(self.sandbox_dir):
            try:
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
                logger.info("Cleaned up sandbox directory %s", self.sandbox_dir)
            except Exception as e:
                logger.warning("Failed to clean up sandbox %s: %s", self.sandbox_dir, e)
