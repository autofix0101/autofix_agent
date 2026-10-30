"""
Stack trace parser for error signals.

Parses traceback outputs from:
- Python (Traceback most recent call last...)
- JavaScript / TypeScript (at function file:line:col)
- CI logs & compiler outputs (file:line: error)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..utils.logging import get_logger

logger = get_logger("signals.stack_trace_parser")

_SYSTEM_PATTERNS = (
    "node_modules",
    "site-packages",
    "dist-packages",
    "lib/python",
    "internal/process",
    "internal/modules",
    "node:",
    "<anonymous>",
    "<unknown>",
    "jest-circus",
    "jest-runner",
    "mocha/lib",
    "_pytest",
    "pluggy",
)


def _is_app_frame(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    return not any(pat in normalized for pat in _SYSTEM_PATTERNS)


@dataclass
class StackFrame:
    file_path: str
    line_number: int
    column: int | None = None
    function_name: str | None = None
    code_context: str | None = None
    is_app_code: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "function_name": self.function_name,
            "code_context": self.code_context,
            "is_app_code": self.is_app_code,
        }


@dataclass
class ParsedStackTrace:
    error_type: str
    error_message: str
    raw_trace: str
    frames: list[StackFrame] = field(default_factory=list)
    primary_frame: StackFrame | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "raw_trace": self.raw_trace,
            "frames": [f.to_dict() for f in self.frames],
            "primary_frame": self.primary_frame.to_dict() if self.primary_frame else None,
        }


# ---------------------------------------------------------------------------
# Python Traceback Parser
# ---------------------------------------------------------------------------

_PY_FRAME_RE = re.compile(
    r'File\s+["\'](?P<file>[^"\']+)["\'],\s+line\s+(?P<line>\d+)(?:,\s+in(?:\s+(?P<func>[^\n]+))?)?',
    re.IGNORECASE,
)
_PY_ERROR_RE = re.compile(
    r"^([A-Z][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt|Fault|Exit)):(?:\s*(.*))?$",
    re.MULTILINE,
)


def parse_python_traceback(text: str) -> ParsedStackTrace | None:
    if "Traceback (most recent call last):" not in text and "File \"" not in text:
        return None

    frames: list[StackFrame] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        m = _PY_FRAME_RE.search(line)
        if m:
            fp = m.group("file").strip()
            ln = int(m.group("line"))
            fn = m.group("func").strip() if m.group("func") else None
            snippet = None
            if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith("File "):
                snippet = lines[i + 1].strip()

            frames.append(
                StackFrame(
                    file_path=fp,
                    line_number=ln,
                    function_name=fn,
                    code_context=snippet,
                    is_app_code=_is_app_frame(fp),
                )
            )

    error_type = "Error"
    error_message = ""
    err_matches = list(_PY_ERROR_RE.finditer(text))
    if err_matches:
        last = err_matches[-1]
        error_type = last.group(1).strip()
        error_message = (last.group(2) or "").strip()
    elif frames:
        error_type = "PythonRuntimeError"

    app_frames = [f for f in frames if f.is_app_code]
    primary = app_frames[-1] if app_frames else (frames[-1] if frames else None)

    return ParsedStackTrace(
        error_type=error_type,
        error_message=error_message,
        raw_trace=text.strip(),
        frames=frames,
        primary_frame=primary,
    )


# ---------------------------------------------------------------------------
# JS / TS Stack Trace Parser
# ---------------------------------------------------------------------------

_JS_FRAME_RE = re.compile(
    r"^\s*at\s+(?:(?P<func>[^\s(]+)\s+\()?(?P<file>[^\s():]+):(?P<line>\d+)(?::(?P<col>\d+))?\)?",
    re.MULTILINE,
)
_JS_ERROR_RE = re.compile(
    r"^([A-Z][A-Za-z0-9_.]*(?:Error|Exception)):\s*(.*)$",
    re.MULTILINE,
)


def parse_js_traceback(text: str) -> ParsedStackTrace | None:
    matches = list(_JS_FRAME_RE.finditer(text))
    if not matches:
        return None

    frames: list[StackFrame] = []
    for m in matches:
        fp = m.group("file").strip()
        ln = int(m.group("line"))
        col = int(m.group("col")) if m.group("col") else None
        fn = m.group("func").strip() if m.group("func") else None

        frames.append(
            StackFrame(
                file_path=fp,
                line_number=ln,
                column=col,
                function_name=fn,
                is_app_code=_is_app_frame(fp),
            )
        )

    error_type = "Error"
    error_message = ""
    err_match = _JS_ERROR_RE.search(text)
    if err_match:
        error_type = err_match.group(1).strip()
        error_message = err_match.group(2).strip()

    app_frames = [f for f in frames if f.is_app_code]
    primary = app_frames[0] if app_frames else (frames[0] if frames else None)

    return ParsedStackTrace(
        error_type=error_type,
        error_message=error_message,
        raw_trace=text.strip(),
        frames=frames,
        primary_frame=primary,
    )


# ---------------------------------------------------------------------------
# Go Panic / Traceback Parser
# ---------------------------------------------------------------------------

_GO_FRAME_FILE_RE = re.compile(r"^\t(?P<file>[^\s:]+\.go):(?P<line>\d+)(?:\s+\+0x[0-9a-fA-F]+)?", re.MULTILINE)
_GO_PANIC_RE = re.compile(r"panic:\s*(.*)")


def parse_go_traceback(text: str) -> ParsedStackTrace | None:
    if "panic:" not in text and ".go:" not in text and "goroutine " not in text:
        return None

    frames: list[StackFrame] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        m = _GO_FRAME_FILE_RE.search(line)
        if m:
            fp = m.group("file").strip()
            ln = int(m.group("line"))
            fn = None
            if i > 0:
                prev = lines[i - 1].strip()
                if "(" in prev and not prev.startswith("goroutine "):
                    fn = prev.split("(")[0].strip()

            frames.append(
                StackFrame(
                    file_path=fp,
                    line_number=ln,
                    function_name=fn,
                    is_app_code=_is_app_frame(fp),
                )
            )

    if not frames:
        return None

    error_type = "Panic"
    error_message = ""
    panic_m = _GO_PANIC_RE.search(text)
    if panic_m:
        error_message = panic_m.group(1).strip()

    app_frames = [f for f in frames if f.is_app_code]
    primary = app_frames[0] if app_frames else frames[0]

    return ParsedStackTrace(
        error_type=error_type,
        error_message=error_message,
        raw_trace=text.strip(),
        frames=frames,
        primary_frame=primary,
    )


# ---------------------------------------------------------------------------
# Java Exception Stack Trace Parser
# ---------------------------------------------------------------------------

_JAVA_FRAME_RE = re.compile(
    r"^\s*at\s+(?P<class>[a-zA-Z0-9_$]+(?:\.[a-zA-Z0-9_$]+)*)\.(?P<method>[a-zA-Z0-9_$<>]+)\((?P<file>[a-zA-Z0-9_]+\.java):(?P<line>\d+)\)",
    re.MULTILINE,
)
_JAVA_ERROR_RE = re.compile(
    r"^(?:Exception in thread \"[^\"]+\"\s+)?(?P<type>[a-zA-Z0-9_.]*(?:Exception|Error)):(?:\s*(?P<msg>.*))?$",
    re.MULTILINE,
)


def parse_java_traceback(text: str) -> ParsedStackTrace | None:
    matches = list(_JAVA_FRAME_RE.finditer(text))
    if not matches:
        return None

    frames: list[StackFrame] = []
    for m in matches:
        fp = m.group("file").strip()
        ln = int(m.group("line"))
        fn = f"{m.group('class')}.{m.group('method')}"

        frames.append(
            StackFrame(
                file_path=fp,
                line_number=ln,
                function_name=fn,
                is_app_code=_is_app_frame(fp) and not fp.startswith("java/"),
            )
        )

    error_type = "JavaException"
    error_message = ""
    err_match = _JAVA_ERROR_RE.search(text)
    if err_match:
        error_type = err_match.group("type").strip()
        error_message = (err_match.group("msg") or "").strip()

    app_frames = [f for f in frames if f.is_app_code]
    primary = app_frames[0] if app_frames else (frames[0] if frames else None)

    return ParsedStackTrace(
        error_type=error_type,
        error_message=error_message,
        raw_trace=text.strip(),
        frames=frames,
        primary_frame=primary,
    )


# ---------------------------------------------------------------------------
# Unified Parser
# ---------------------------------------------------------------------------

def parse_stack_trace(raw_text: str) -> ParsedStackTrace | None:
    """Detect format and parse stack trace."""
    if not raw_text or not raw_text.strip():
        return None

    parsed = parse_python_traceback(raw_text)
    if parsed and parsed.frames:
        return parsed

    parsed = parse_js_traceback(raw_text)
    if parsed and parsed.frames:
        return parsed

    parsed = parse_go_traceback(raw_text)
    if parsed and parsed.frames:
        return parsed

    parsed = parse_java_traceback(raw_text)
    if parsed and parsed.frames:
        return parsed

    # Generic file:line: error regex
    generic_re = re.compile(r"([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+):(\d+):(?:\s*(.*))?")
    gen_frames: list[StackFrame] = []
    for line in raw_text.splitlines():
        m = generic_re.search(line)
        if m:
            fp = m.group(1).strip()
            ln = int(m.group(2))
            msg = (m.group(3) or "").strip()
            gen_frames.append(
                StackFrame(
                    file_path=fp,
                    line_number=ln,
                    code_context=msg,
                    is_app_code=_is_app_frame(fp),
                )
            )

    if gen_frames:
        app_frames = [f for f in gen_frames if f.is_app_code]
        return ParsedStackTrace(
            error_type="BuildOrTestError",
            error_message="Detected error location from logs",
            raw_trace=raw_text.strip(),
            frames=gen_frames,
            primary_frame=app_frames[-1] if app_frames else gen_frames[-1],
        )

    return None
