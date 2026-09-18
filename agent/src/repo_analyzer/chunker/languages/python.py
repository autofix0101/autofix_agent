"""
Python AST chunker using tree-sitter-python.

Extracts top-level and class-nested functions and classes as individual chunks.
Falls back to the generic chunker for files that fail to parse.
"""
from __future__ import annotations

import logging

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from ...models import CodeChunk

logger = logging.getLogger(__name__)

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)

# Node types we treat as independent chunk boundaries
_CHUNK_NODE_TYPES = frozenset({
    "function_definition",
    "async_function_def",
    "decorated_definition",  # covers @decorator\ndef / @decorator\nclass
    "class_definition",
})


def _node_name(node: Node) -> str | None:
    """Extract the identifier name from a named node."""
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8", errors="replace")  # type: ignore[union-attr]
        # decorated_definition wraps the actual def/class
        if child.type in ("function_definition", "async_function_def", "class_definition"):
            return _node_name(child)
    return None


def _chunk_type_for(node: Node) -> str:
    if node.type == "class_definition":
        return "class"
    if node.type in ("function_definition", "async_function_def"):
        return "function"
    # decorated_definition — look at the inner node
    for child in node.children:
        if child.type == "class_definition":
            return "class"
        if child.type in ("function_definition", "async_function_def"):
            return "function"
    return "function"


def _collect_chunks(
    node: Node,
    source_lines: list[str],
    file_path: str,
    seen_keys: set[str],
) -> list[CodeChunk]:
    """Recursively walk the tree, emitting a chunk for each target node."""
    chunks: list[CodeChunk] = []

    if node.type in _CHUNK_NODE_TYPES:
        symbol = _node_name(node)
        ctype = _chunk_type_for(node)

        # Build a stable, unique key (handle overloads/duplicates with a counter)
        base_key = f"{file_path}::{symbol or 'anonymous'}::{ctype}"
        key = base_key
        counter = 1
        while key in seen_keys:
            key = f"{base_key}_{counter}"
            counter += 1
        seen_keys.add(key)

        start_line = node.start_point[0] + 1  # tree-sitter is 0-indexed
        end_line = node.end_point[0] + 1
        snippet = "\n".join(source_lines[start_line - 1 : end_line])

        content = (
            f"# file: {file_path}\n"
            f"# symbol: {symbol or 'anonymous'}\n"
            f"# type: {ctype}\n\n"
            f"{snippet}"
        )

        chunks.append(
            CodeChunk(
                chunk_key=key,
                symbol_name=symbol,
                chunk_type=ctype,
                start_line=start_line,
                end_line=end_line,
                language="python",
                content=content,
            )
        )
        # Still recurse into class bodies to capture methods as separate chunks
        for child in node.children:
            chunks.extend(_collect_chunks(child, source_lines, file_path, seen_keys))

    else:
        for child in node.children:
            chunks.extend(_collect_chunks(child, source_lines, file_path, seen_keys))

    return chunks


def chunk(source: str, file_path: str) -> list[CodeChunk]:
    """
    Parse *source* as Python and return one CodeChunk per top-level/nested
    function or class definition.

    If the file produces no named chunks (e.g. pure script), a single
    'module' chunk wrapping the entire file is returned instead.
    """
    try:
        tree = _PARSER.parse(source.encode("utf-8"))
    except Exception:
        logger.exception("tree-sitter failed to parse %s — using generic chunker", file_path)
        from .generic import chunk as generic_chunk
        return generic_chunk(source, "python", file_path)

    source_lines = source.splitlines()
    seen_keys: set[str] = set()
    chunks = _collect_chunks(tree.root_node, source_lines, file_path, seen_keys)

    # If nothing was extracted (empty file / pure expressions), emit a module chunk
    if not chunks and source.strip():
        content = f"# file: {file_path}\n# type: module\n\n{source}"
        chunks.append(
            CodeChunk(
                chunk_key=f"{file_path}::module",
                symbol_name=None,
                chunk_type="module",
                start_line=1,
                end_line=len(source_lines),
                language="python",
                content=content,
            )
        )

    return chunks
