"""
Tree-sitter and AST-based Code Chunker.

Implements Part 2 of the Architecture Specification:
Each chunk's embedded text is a composed block containing:
  1. File: <file_path>
  2. Function / Class signature: name + parameters
  3. Leading docstring/comment, if present
  4. Full function/class body
Computes content_hash (sha256) for incremental change detection.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..utils.logging import get_logger

logger = get_logger("indexing.chunker")

# Tree-sitter imports with safe fallbacks
try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser
    _PY_LANG = Language(tspython.language())
    _PY_PARSER = Parser(_PY_LANG)
except Exception as e:
    logger.warning("Tree-sitter Python parser unavailable: %s", e)
    _PY_PARSER = None

try:
    import tree_sitter_typescript as tstypescript
    from tree_sitter import Language, Parser
    _TS_LANG = Language(tstypescript.language_typescript())
    _TS_PARSER = Parser(_TS_LANG)
except Exception:
    _TS_PARSER = None

try:
    import tree_sitter_javascript as tsjavascript
    from tree_sitter import Language, Parser
    _JS_LANG = Language(tsjavascript.language())
    _JS_PARSER = Parser(_JS_LANG)
except Exception:
    _JS_PARSER = None

try:
    import tree_sitter_go as tsgo
    from tree_sitter import Language, Parser
    _GO_LANG = Language(tsgo.language())
    _GO_PARSER = Parser(_GO_LANG)
except Exception:
    _GO_PARSER = None

try:
    import tree_sitter_java as tsjava
    from tree_sitter import Language, Parser
    _JAVA_LANG = Language(tsjava.language())
    _JAVA_PARSER = Parser(_JAVA_LANG)
except Exception:
    _JAVA_PARSER = None


@dataclass
class Chunk:
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str  # 'function' | 'class' | 'block'
    language: str
    content: str
    content_hash: str = field(init=False)
    embedding: list[float] | None = None
    symbol_name: str | None = None

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def chunk_key(self) -> str:
        """Unique key per chunk within a file — matches DB unique constraint (file_id, chunk_key)."""
        if self.symbol_name:
            return f"{self.symbol_name}:{self.start_line}-{self.end_line}"
        return f"block:{self.start_line}-{self.end_line}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_key": self.chunk_key,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_type": self.chunk_type,
            "language": self.language,
            "content": self.content,
            "content_hash": self.content_hash,
            "embedding": self.embedding,
            "symbol_name": self.symbol_name,
        }


def _compose_chunk_content(
    file_path: str,
    symbol_name: str | None,
    signature: str | None,
    docstring: str | None,
    body: str,
) -> str:
    """
    Format composed block matching Part 2 of Architecture Specification:
      File: <file_path>
      Function: <signature>
      <docstring>
      <body>
    """
    lines = [f"File: {file_path}"]
    if signature:
        lines.append(f"Function: {signature}")
    elif symbol_name:
        lines.append(f"Function: {symbol_name}")

    if docstring and docstring.strip():
        lines.append(docstring.strip())

    lines.append(body.strip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Python Chunking
# ---------------------------------------------------------------------------

def _chunk_python_tree_sitter(source: str, file_path: str) -> list[Chunk]:
    if not _PY_PARSER:
        return _chunk_generic_regex(source, file_path, "python")

    source_bytes = source.encode("utf-8")
    tree = _PY_PARSER.parse(source_bytes)
    lines = source.splitlines()
    chunks: list[Chunk] = []

    def visit(node):
        if node.type in ("function_definition", "async_function_definition", "class_definition"):
            start_line = node.start_point.row + 1
            end_line = node.end_point.row + 1
            chunk_type = "class" if node.type == "class_definition" else "function"

            # Extract name and signature
            name = None
            params = "()"
            docstring = None

            for child in node.children:
                if child.type == "identifier":
                    name = child.text.decode("utf-8", errors="replace")
                elif child.type == "parameters":
                    params = child.text.decode("utf-8", errors="replace")

            # Extract leading docstring if present
            body_node = node.child_by_field_name("body")
            if body_node and body_node.children:
                first_stmt = body_node.children[0]
                if first_stmt.type == "expression_statement":
                    for sub in first_stmt.children:
                        if sub.type == "string":
                            docstring = sub.text.decode("utf-8", errors="replace").strip("\"'")

            raw_body = "\n".join(lines[start_line - 1 : end_line])
            sig = f"{name}{params}" if name else None
            composed = _compose_chunk_content(file_path, name, sig, docstring, raw_body)

            chunks.append(
                Chunk(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type=chunk_type,
                    language="python",
                    content=composed,
                    symbol_name=name,
                )
            )

        for child in node.children:
            visit(child)

    visit(tree.root_node)

    # Fallback to entire file if no functions/classes were parsed
    if not chunks and lines:
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=1,
                end_line=len(lines),
                chunk_type="block",
                language="python",
                content=_compose_chunk_content(file_path, None, None, None, source),
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# JavaScript / TypeScript Chunking
# ---------------------------------------------------------------------------

def _chunk_js_ts_tree_sitter(source: str, file_path: str, is_ts: bool = True) -> list[Chunk]:
    parser = _TS_PARSER if (is_ts and _TS_PARSER) else (_JS_PARSER or _TS_PARSER)
    lang = "typescript" if is_ts else "javascript"

    if not parser:
        return _chunk_generic_regex(source, file_path, lang)

    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    lines = source.splitlines()
    chunks: list[Chunk] = []

    target_types = (
        "function_declaration",
        "method_definition",
        "arrow_function",
        "class_declaration",
        "interface_declaration",
    )

    def visit(node):
        if node.type in target_types:
            start_line = node.start_point.row + 1
            end_line = node.end_point.row + 1
            chunk_type = "class" if "class" in node.type or "interface" in node.type else "function"

            name = None
            params = "()"
            for child in node.children:
                if child.type in ("identifier", "type_identifier", "property_identifier"):
                    if not name:
                        name = child.text.decode("utf-8", errors="replace")
                elif child.type in ("formal_parameters", "parameters"):
                    params = child.text.decode("utf-8", errors="replace")

            # Check for leading comment directly preceding node
            docstring = None
            if node.prev_sibling and node.prev_sibling.type == "comment":
                docstring = node.prev_sibling.text.decode("utf-8", errors="replace")

            raw_body = "\n".join(lines[start_line - 1 : end_line])
            sig = f"{name}{params}" if name else None
            composed = _compose_chunk_content(file_path, name, sig, docstring, raw_body)

            chunks.append(
                Chunk(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type=chunk_type,
                    language=lang,
                    content=composed,
                    symbol_name=name,
                )
            )

        for child in node.children:
            visit(child)

    visit(tree.root_node)

    if not chunks and lines:
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=1,
                end_line=len(lines),
                chunk_type="block",
                language=lang,
                content=_compose_chunk_content(file_path, None, None, None, source),
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Go Chunking (Tree-sitter with robust regex fallback)
# ---------------------------------------------------------------------------

_GO_FUNC_RE = re.compile(
    r"^(?P<comments>(?:[ \t]*//[^\n]*\n)*)[ \t]*func\s+(?:\((?P<receiver>[^)]+)\)\s+)?(?P<name>[A-Za-z0-9_]+)\s*(?P<params>\([^)]*\))",
    re.MULTILINE,
)
_GO_TYPE_RE = re.compile(
    r"^(?P<comments>(?:[ \t]*//[^\n]*\n)*)[ \t]*type\s+(?P<name>[A-Za-z0-9_]+)\s+(?P<kind>struct|interface)",
    re.MULTILINE,
)


def _extract_brace_blocks(
    source: str,
    pattern: re.Pattern,
    chunk_type: str,
    language: str,
    file_path: str,
) -> list[Chunk]:
    """Helper to extract balanced-brace blocks for Go and Java."""
    lines = source.splitlines()
    chunks: list[Chunk] = []

    for m in pattern.finditer(source):
        name = m.group("name")
        start_char = m.start()
        start_line = source.count("\n", 0, start_char) + 1

        # Locate opening brace
        match_end = m.end()
        open_pos = source.find("{", match_end - 1 if source[match_end - 1 : match_end] == "{" else match_end)
        if open_pos == -1:
            continue

        brace_count = 1
        pos = open_pos + 1
        in_string = False
        escape = False

        while pos < len(source) and brace_count > 0:
            char = source[pos]
            if char == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
            escape = (char == '\\' and not escape)
            pos += 1

        end_line = source.count("\n", 0, pos) + 1
        body = "\n".join(lines[start_line - 1 : end_line])

        docstring = None
        comments = m.groupdict().get("comments")
        if comments and comments.strip():
            docstring = comments.strip()

        composed = _compose_chunk_content(file_path, name, name, docstring, body)
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                chunk_type=chunk_type,
                language=language,
                content=composed,
                symbol_name=name,
            )
        )
    return chunks


def _chunk_go(source: str, file_path: str) -> list[Chunk]:
    """Chunk Go code using Tree-sitter AST, falling back to brace-aware regex."""
    lines = source.splitlines()
    if not lines:
        return []

    if _GO_PARSER:
        source_bytes = source.encode("utf-8")
        tree = _GO_PARSER.parse(source_bytes)
        chunks: list[Chunk] = []

        def visit(node):
            if node.type in ("function_declaration", "method_declaration", "type_declaration"):
                start_line = node.start_point.row + 1
                end_line = node.end_point.row + 1
                chunk_type = "class" if node.type == "type_declaration" else "function"

                name = None
                receiver = ""
                docstring = None

                for child in node.children:
                    if child.type in ("identifier", "field_identifier"):
                        name = child.text.decode("utf-8", errors="replace")
                    elif child.type == "parameter_list" and node.type == "method_declaration" and not receiver:
                        receiver = child.text.decode("utf-8", errors="replace") + " "
                    elif child.type == "type_spec":
                        for sub in child.children:
                            if sub.type in ("type_identifier", "identifier"):
                                name = sub.text.decode("utf-8", errors="replace")
                                break

                # Extract preceding comments
                comment_lines = []
                idx = start_line - 2
                while idx >= 0:
                    l = lines[idx].strip()
                    if l.startswith("//"):
                        comment_lines.insert(0, l.lstrip("/").strip())
                        idx -= 1
                    else:
                        break
                if comment_lines:
                    docstring = "\n".join(comment_lines)

                raw_body = "\n".join(lines[start_line - 1 : end_line])
                sig = f"{receiver}{name}" if name else None
                composed = _compose_chunk_content(file_path, name, sig, docstring, raw_body)

                chunks.append(
                    Chunk(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type=chunk_type,
                        language="go",
                        content=composed,
                        symbol_name=name,
                    )
                )

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        if chunks:
            return chunks

    # Robust regex AST fallback
    fn_chunks = _extract_brace_blocks(source, _GO_FUNC_RE, "function", "go", file_path)
    type_chunks = _extract_brace_blocks(source, _GO_TYPE_RE, "class", "go", file_path)
    all_chunks = sorted(fn_chunks + type_chunks, key=lambda c: c.start_line)
    if all_chunks:
        return all_chunks

    return _chunk_generic_regex(source, file_path, "go")


# ---------------------------------------------------------------------------
# Java Chunking (Tree-sitter with robust regex fallback)
# ---------------------------------------------------------------------------

_JAVA_CLASS_RE = re.compile(
    r"^(?P<comments>(?:[ \t]*(?://[^\n]*|/\*.*?\*/)\n)*)[ \t]*(?:public|protected|private|static|final|abstract|\s)*\b(?:class|interface|enum)\s+(?P<name>[A-Za-z0-9_]+)",
    re.MULTILINE,
)
_JAVA_METHOD_RE = re.compile(
    r"^(?P<comments>(?:[ \t]*(?://[^\n]*|/\*.*?\*/)\n)*)[ \t]*(?:@[A-Za-z0-9_]+\s*)*(?:public|protected|private|static|final|synchronized|abstract|\s)+(?:[A-Za-z0-9_<>,\[\]]+)\s+(?P<name>[A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:throws\s+[^{]+)?\s*\{",
    re.MULTILINE,
)


def _chunk_java(source: str, file_path: str) -> list[Chunk]:
    """Chunk Java code using Tree-sitter AST, falling back to brace-aware regex."""
    lines = source.splitlines()
    if not lines:
        return []

    if _JAVA_PARSER:
        source_bytes = source.encode("utf-8")
        tree = _JAVA_PARSER.parse(source_bytes)
        chunks: list[Chunk] = []

        target_types = (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "method_declaration",
            "constructor_declaration",
        )

        def visit(node):
            if node.type in target_types:
                start_line = node.start_point.row + 1
                end_line = node.end_point.row + 1
                chunk_type = "class" if "class" in node.type or "interface" in node.type or "enum" in node.type else "function"

                name = None
                for child in node.children:
                    if child.type == "identifier":
                        name = child.text.decode("utf-8", errors="replace")
                        break

                docstring = None
                idx = start_line - 2
                comment_lines = []
                while idx >= 0:
                    l = lines[idx].strip()
                    if l.startswith("*") or l.startswith("/**") or l.startswith("/*") or l.startswith("//"):
                        cleaned = l.lstrip("/*").rstrip("*/").strip()
                        if cleaned:
                            comment_lines.insert(0, cleaned)
                        idx -= 1
                    else:
                        break
                if comment_lines:
                    docstring = "\n".join(comment_lines)

                raw_body = "\n".join(lines[start_line - 1 : end_line])
                composed = _compose_chunk_content(file_path, name, name, docstring, raw_body)

                chunks.append(
                    Chunk(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type=chunk_type,
                        language="java",
                        content=composed,
                        symbol_name=name,
                    )
                )

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        if chunks:
            return chunks

    # Robust regex AST fallback
    class_chunks = _extract_brace_blocks(source, _JAVA_CLASS_RE, "class", "java", file_path)
    method_chunks = _extract_brace_blocks(source, _JAVA_METHOD_RE, "function", "java", file_path)
    all_chunks = sorted(class_chunks + method_chunks, key=lambda c: c.start_line)
    if all_chunks:
        return all_chunks

    return _chunk_generic_regex(source, file_path, "java")


_GENERIC_FUNC_RE = re.compile(
    r"^[ \t]*(?:async\s+)?(?:def|function|class|public|private|protected)?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(\([^)]*\))",
    re.MULTILINE,
)


def _chunk_generic_regex(source: str, file_path: str, language: str) -> list[Chunk]:
    lines = source.splitlines()
    if not lines:
        return []

    chunks: list[Chunk] = []
    # If file is small (< 50 lines), treat as single chunk
    if len(lines) <= 50:
        return [
            Chunk(
                file_path=file_path,
                start_line=1,
                end_line=len(lines),
                chunk_type="block",
                language=language,
                content=_compose_chunk_content(file_path, None, None, None, source),
            )
        ]

    # Split into sliding or logical blocks of 60 lines with 10 lines overlap
    window = 60
    step = 50
    for i in range(0, len(lines), step):
        chunk_lines = lines[i : i + window]
        start_l = i + 1
        end_l = min(len(lines), i + len(chunk_lines))
        body = "\n".join(chunk_lines)
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=start_l,
                end_line=end_l,
                chunk_type="block",
                language=language,
                content=_compose_chunk_content(file_path, None, None, None, body),
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Main Entrypoint
# ---------------------------------------------------------------------------

def chunk_file_content(content: str, file_path: str) -> list[Chunk]:
    """
    Parse source code of a file and return a list of Chunks.
    """
    ext = os.path.splitext(file_path)[1].lower()
    clean_path = file_path.replace("\\", "/").lstrip("/")

    if ext == ".py":
        return _chunk_python_tree_sitter(content, clean_path)
    elif ext in (".ts", ".tsx"):
        return _chunk_js_ts_tree_sitter(content, clean_path, is_ts=True)
    elif ext in (".js", ".jsx", ".mjs"):
        return _chunk_js_ts_tree_sitter(content, clean_path, is_ts=False)
    elif ext == ".go":
        return _chunk_go(content, clean_path)
    elif ext == ".java":
        return _chunk_java(content, clean_path)
    elif ext in (".rs", ".rb", ".cpp", ".c", ".cs", ".php"):
        lang = ext.lstrip(".")
        return _chunk_generic_regex(content, clean_path, lang)
    else:
        # Generic text / config chunk
        return _chunk_generic_regex(content, clean_path, "text")


# Lockfiles and other generated dependency manifests: huge, machine-written,
# and never the place a bug lives.
_IGNORED_FILE_NAMES = {
    # JavaScript / TypeScript
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "deno.lock",
    # Python
    "pipfile.lock",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
    # Go
    "go.sum",
    "go.work.sum",
    # Java / Kotlin
    "gradle.lockfile",
    # Other languages
    "composer.lock",
    "cargo.lock",
    "gemfile.lock",
    "packages.lock.json",
}

# Dependency, virtualenv, build-output and tooling directories. A path is
# skipped if any of its directory segments matches.
_IGNORED_DIR_NAMES = {
    # VCS / editors
    ".git", ".hg", ".svn", ".idea", ".vscode",
    # JavaScript / TypeScript
    "node_modules", "bower_components", "jspm_packages", ".yarn", ".pnpm-store",
    "dist", "build", "out", "coverage", ".next", ".nuxt", ".svelte-kit",
    ".turbo", ".cache", ".parcel-cache", ".angular", "storybook-static",
    # Python
    "venv", ".venv", ".env", "virtualenv", "site-packages", "__pycache__",
    ".tox", ".nox", ".eggs", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "htmlcov",
    # Go / PHP / Ruby
    "vendor",
    # Java / Kotlin / Rust
    "target", ".gradle", ".mvn",
    # C#
    "obj",
}


def _is_ignored_dir(segment: str) -> bool:
    return segment in _IGNORED_DIR_NAMES or segment.endswith(".egg-info")


def is_chunkable_file(file_path: str) -> bool:
    """Return True if the file should be parsed and indexed."""
    clean_path = file_path.replace("\\", "/").strip("/")
    segments = clean_path.lower().split("/")
    base_name = segments[-1]

    if any(_is_ignored_dir(seg) for seg in segments[:-1]):
        return False
    if base_name in _IGNORED_FILE_NAMES:
        return False
    if base_name.endswith((".min.js", ".min.css", ".map", ".bundle.js")):
        return False

    ext = os.path.splitext(clean_path)[1].lower()
    valid_exts = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs",
        ".go", ".java", ".rs", ".rb", ".cpp", ".c",
        ".cs", ".php", ".json", ".yaml", ".yml", ".sql"
    }
    return ext in valid_exts
