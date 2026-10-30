"""
Issue and CI Signal Preprocessor.

Performs light cleanup of issue and failure texts before embedding:
- Extracts code blocks / stack traces
- Finds mentioned files and function symbols
- Composes a clean semantic search query
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .stack_trace_parser import ParsedStackTrace, parse_stack_trace

_CODE_BLOCK_RE = re.compile(r"```(?:[a-zA-Z0-9_\-]+)?\n(.*?)```", re.DOTALL)
_FILE_PATH_RE = re.compile(
    r"(?:[\s`\"'\(]|^)([a-zA-Z0-9_\-./\\]+\.(?:py|ts|js|tsx|jsx|go|rs|java|rb|json|sql|ya?ml))(?:[\s`\"'\):]|$)",
    re.IGNORECASE,
)
_SYMBOL_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*(?:\(\))?)`")


@dataclass
class PreprocessedSignal:
    title: str
    cleaned_text: str
    search_query: str
    stack_trace: ParsedStackTrace | None = None
    mentioned_files: list[str] = field(default_factory=list)
    mentioned_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "cleaned_text": self.cleaned_text,
            "search_query": self.search_query,
            "stack_trace": self.stack_trace.to_dict() if self.stack_trace else None,
            "mentioned_files": self.mentioned_files,
            "mentioned_symbols": self.mentioned_symbols,
        }


def preprocess_signal_content(raw_content: str, title: str = "") -> PreprocessedSignal:
    """
    Clean up issue / CI signal and formulate semantic query.
    """
    stack_trace = None

    # Check for stack trace in code blocks
    for block in _CODE_BLOCK_RE.findall(raw_content):
        parsed = parse_stack_trace(block)
        if parsed and parsed.frames:
            stack_trace = parsed
            break

    # If not found in code blocks, search raw content
    if not stack_trace:
        stack_trace = parse_stack_trace(raw_content)

    # Extract file mentions
    mentioned_files = list(
        dict.fromkeys(
            m.group(1).replace("\\", "/").strip()
            for m in _FILE_PATH_RE.finditer(raw_content)
        )
    )

    # Extract symbols
    mentioned_symbols = list(
        dict.fromkeys(
            m.group(1).rstrip("()").strip()
            for m in _SYMBOL_RE.finditer(raw_content)
        )
    )

    # Strip code blocks to clean descriptive text
    cleaned_text = _CODE_BLOCK_RE.sub("", raw_content).strip()
    cleaned_text = re.sub(r"\s+", " ", cleaned_text)

    # Construct search query
    query_parts = []
    if title:
        query_parts.append(title)
    if stack_trace:
        query_parts.append(f"{stack_trace.error_type}: {stack_trace.error_message}")
        if stack_trace.primary_frame:
            pf = stack_trace.primary_frame
            if pf.function_name:
                query_parts.append(f"Function: {pf.function_name}")
            query_parts.append(f"File: {pf.file_path}")
    elif mentioned_symbols:
        query_parts.append(" ".join(mentioned_symbols[:3]))

    if cleaned_text and len(query_parts) < 3:
        query_parts.append(cleaned_text[:200])

    search_query = " | ".join(filter(None, query_parts))

    return PreprocessedSignal(
        title=title,
        cleaned_text=cleaned_text,
        search_query=search_query,
        stack_trace=stack_trace,
        mentioned_files=mentioned_files,
        mentioned_symbols=mentioned_symbols,
    )
