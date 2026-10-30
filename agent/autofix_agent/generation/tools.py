"""
Tool definitions and execution engine for AutoFix Code Generation.

Available tools for LLM agent:
- read_file(file_path, start_line, end_line)
- search_code(query, path_filter)
- get_related_tests(file_path)
- propose_patch(file_path, diff_content, explanation)
"""
from __future__ import annotations

import difflib
import fnmatch
import os
import re
from typing import Any

from ..utils.logging import get_logger

logger = get_logger("generation.tools")

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file in the repository, optionally restricted to line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path to file in repo"},
                    "start_line": {"type": "integer", "description": "1-based starting line number (optional)"},
                    "end_line": {"type": "integer", "description": "1-based ending line number (optional)"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search repository files for a regex pattern or keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text or regex search pattern"},
                    "path_filter": {"type": "string", "description": "Glob filter (e.g. '*.py' or 'tests/*') (optional)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the repository or within a specific subdirectory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Relative subdirectory path (optional, defaults to repo root)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_tests",
            "description": "Find test files corresponding to a source file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path to target source file"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_patch",
            "description": "Propose the final code fix as a unified diff and plain-English explanation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path to broken file"},
                    "diff_content": {"type": "string", "description": "Unified git diff (starting with --- a/... and +++ b/...)"},
                    "explanation": {"type": "string", "description": "Explanation of the root cause and why this fix resolves it"},
                },
                "required": ["file_path", "diff_content", "explanation"],
            },
        },
    },
]


class RepoToolExecutor:
    """Executes tool requests against a checked-out repository working directory."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def _resolve(self, rel_path: str) -> str:
        clean = rel_path.replace("\\", "/").lstrip("/")
        full = os.path.abspath(os.path.join(self.repo_path, clean))
        # Sandbox path check
        if not full.startswith(self.repo_path):
            raise PermissionError(f"Access denied: {rel_path} escapes repository root.")
        return full

    def read_file(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        target = self._resolve(file_path)
        if not os.path.isfile(target):
            return f"Error: File '{file_path}' does not exist."

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        s = max(1, start_line) if start_line is not None else 1
        e = min(total, end_line) if end_line is not None else total

        sliced = lines[s - 1 : e]
        annotated = [f"{s + idx}: {l}" for idx, l in enumerate(sliced)]
        return f"File: {file_path} (Lines {s}-{e} of {total})\n" + "".join(annotated)

    def search_code(
        self,
        query: str,
        path_filter: str | None = None,
        max_results: int = 15,
    ) -> str:
        pattern = re.compile(query, re.IGNORECASE)
        results = []

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build")]
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), self.repo_path).replace("\\", "/")
                if path_filter and not fnmatch.fnmatch(rel, path_filter):
                    continue

                full_p = os.path.join(root, file)
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as f:
                        for l_idx, line in enumerate(f, start=1):
                            if pattern.search(line):
                                results.append(f"{rel}:{l_idx}: {line.strip()[:120]}")
                                if len(results) >= max_results:
                                    return "\n".join(results)
                except Exception:
                    pass

        return "\n".join(results) if results else "No matching lines found."

    def get_related_tests(self, file_path: str) -> str:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        test_patterns = [
            f"test_{base_name}.py",
            f"{base_name}_test.py",
            f"{base_name}.test.ts",
            f"{base_name}.spec.ts",
            f"{base_name}.test.js",
            f"{base_name}_test.go",
            f"{base_name}Test.java",
            f"{base_name}Tests.java",
            f"Test{base_name}.java",
        ]

        found = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "venv", ".venv")]
            for f in files:
                for pat in test_patterns:
                    if fnmatch.fnmatch(f, pat):
                        rel = os.path.relpath(os.path.join(root, f), self.repo_path).replace("\\", "/")
                        found.append(rel)

        return "Related test files:\n" + "\n".join(found) if found else "No directly named test files found."

    def list_files(self, directory: str = "") -> str:
        target = self._resolve(directory) if directory else self.repo_path
        if not os.path.isdir(target):
            return f"Error: '{directory}' is not a directory."
        file_list = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build")]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), self.repo_path).replace("\\", "/")
                file_list.append(rel)
                if len(file_list) >= 100:
                    break
            if len(file_list) >= 100:
                break
        return "\n".join(file_list) if file_list else "No files found."

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> str:
        """Dispatch tool name and return text response."""
        try:
            if name == "read_file":
                return self.read_file(args.get("file_path", ""), args.get("start_line"), args.get("end_line"))
            elif name == "search_code":
                return self.search_code(args.get("query", ""), args.get("path_filter"))
            elif name == "list_files":
                return self.list_files(args.get("directory", ""))
            elif name == "get_related_tests":
                return self.get_related_tests(args.get("file_path", ""))
            elif name == "propose_patch":
                return "Patch proposed successfully."
            else:
                return f"Error: Unknown tool function '{name}'"
        except Exception as e:
            return f"Tool execution error: {e}"


def create_unified_diff(
    original_code: str,
    modified_code: str,
    file_path: str,
) -> str:
    """Generate git-apply compatible unified diff."""
    orig_lines = original_code.splitlines(keepends=True)
    mod_lines = modified_code.splitlines(keepends=True)
    clean_path = file_path.replace("\\", "/").lstrip("/")

    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{clean_path}",
            tofile=f"b/{clean_path}",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)
