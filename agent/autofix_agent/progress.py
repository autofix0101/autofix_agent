"""
User-facing progress reporting.

Every message written here is shown on the issue page in the dashboard, so it
is phrased for the repo owner rather than for whoever reads the worker logs:
no internal IDs, scores or raw tool output. The `stage` matches the fix_jobs
status the message belongs to, which the UI uses to group the timeline.
"""
from __future__ import annotations

import re
from typing import Any

from . import db
from .utils.logging import get_logger

logger = get_logger("progress")

# Credentials embedded in URLs, e.g. https://x-access-token:<token>@github.com/...
_URL_CREDENTIALS_RE = re.compile(r"(https?://)[^/@\s]+@")


def scrub(text: str) -> str:
    """Remove credentials from any URL in text before it can reach the browser."""
    return _URL_CREDENTIALS_RE.sub(r"\1", text)


async def report_progress(job_id: str, stage: str, message: str) -> None:
    """Append a user-facing job event. Never raises: progress must not break a fix."""
    try:
        await db.add_job_event(str(job_id), stage, scrub(message))
    except Exception as e:
        logger.warning("Could not record progress for job %s: %s", job_id, e)


def _code(path: str) -> str:
    return f"`{path}`"


def describe_tool_call(name: str, args: dict[str, Any]) -> str | None:
    """Plain-language description of what the AI is doing with a tool call."""
    if name == "read_file":
        path = args.get("file_path") or "a file"
        start, end = args.get("start_line"), args.get("end_line")
        if start and end:
            return f"Reading {_code(path)} (lines {start}–{end})"
        return f"Reading {_code(path)}"
    if name == "search_code":
        query = str(args.get("query") or "").strip()
        where = f" in {_code(args['path_filter'])}" if args.get("path_filter") else ""
        return f"Searching the code for “{query[:80]}”{where}"
    if name == "list_files":
        directory = args.get("directory")
        return f"Looking at the files in {_code(directory)}" if directory else "Looking at how the project is organised"
    if name == "get_related_tests":
        return f"Looking for tests that cover {_code(args.get('file_path') or 'the code')}"
    return None


def describe_files(paths: list[str], limit: int = 3) -> str:
    shown = ", ".join(_code(p) for p in paths[:limit])
    more = len(paths) - limit
    return f"{shown} and {more} more" if more > 0 else shown


def describe_validation_failure(log: str | None) -> str:
    """Why a patch failed validation, in one sentence. Mirrors the server's summary."""
    log = log or ""
    if log.startswith("Patch apply failed"):
        return "The proposed change didn't line up with the current code, so it couldn't be applied."
    if log.startswith("Syntax Validation Failed"):
        return "The change introduced a syntax error."
    if "TypeScript type-check FAILED" in log:
        return "The change introduced TypeScript type errors."
    if "] Syntax error in " in log:
        return "The change introduced a JavaScript syntax error."
    if "timed out" in log.lower():
        return "The project's tests took too long and were stopped."
    if log.startswith("Test runner invocation error"):
        return "The project's tests couldn't be run."
    return "The project's tests failed with the change applied."
