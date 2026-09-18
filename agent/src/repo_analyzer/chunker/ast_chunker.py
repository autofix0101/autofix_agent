"""
AST-based code chunker — language dispatcher.

Detects language from file extension and delegates to the appropriate
language-specific chunker.  Falls back to the generic sliding-window
chunker for unsupported extensions.
"""
from __future__ import annotations

import os
import logging
from typing import Literal

from .languages import python, typescript, generic
from ..models import CodeChunk

logger = logging.getLogger(__name__)

# Extension → (language tag, chunker key)
_EXT_MAP: dict[str, tuple[str, str]] = {
    ".py":   ("python",     "python"),
    ".ts":   ("typescript", "typescript"),
    ".tsx":  ("tsx",        "tsx"),
    ".js":   ("javascript", "javascript"),
    ".jsx":  ("jsx",        "jsx"),
}

# Extensions that use the generic chunker (language tag only)
_GENERIC_EXT_MAP: dict[str, str] = {
    ".go":   "go",
    ".java": "java",
    ".rb":   "ruby",
    ".rs":   "rust",
    ".cpp":  "cpp",
    ".cc":   "cpp",
    ".cxx":  "cpp",
    ".c":    "c",
    ".h":    "c",
    ".cs":   "csharp",
    ".php":  "php",
    ".kt":   "kotlin",
    ".swift": "swift",
}


def detect_language(file_path: str) -> str | None:
    """Return the language tag for *file_path*, or None if not indexable."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext][0]
    if ext in _GENERIC_EXT_MAP:
        return _GENERIC_EXT_MAP[ext]
    return None


def chunk_file(source: str, file_path: str) -> tuple[str, list[CodeChunk]]:
    """
    Chunk *source* using the appropriate AST or generic chunker.

    Returns:
        (language, chunks)   — language is the detected/inferred tag.

    Raises ValueError if the file extension is not indexable.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in _EXT_MAP:
        language, chunker_key = _EXT_MAP[ext]
        if chunker_key == "python":
            chunks = python.chunk(source, file_path)
        else:
            # All TS/JS variants share the typescript module
            chunks = typescript.chunk(source, file_path, language=chunker_key)  # type: ignore[arg-type]
        return language, chunks

    if ext in _GENERIC_EXT_MAP:
        language = _GENERIC_EXT_MAP[ext]
        chunks = generic.chunk(source, language, file_path)
        return language, chunks

    raise ValueError(f"Unsupported file extension: {ext!r} ({file_path})")


def is_indexable(file_path: str) -> bool:
    """Return True if this file should be indexed."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _EXT_MAP or ext in _GENERIC_EXT_MAP
