"""
TypeScript / TSX / JavaScript AST chunker using tree-sitter-typescript
and tree-sitter-javascript.
"""
from __future__ import annotations

import logging
from typing import Literal

import tree_sitter_typescript as tsts
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Node, Parser

from ...models import CodeChunk

logger = logging.getLogger(__name__)

# Build language objects once at import time
_TS_LANGUAGE = Language(tsts.language_typescript())
_TSX_LANGUAGE = Language(tsts.language_tsx())
_JS_LANGUAGE = Language(tsjs.language())

_PARSERS: dict[str, Parser] = {
    "typescript": Parser(_TS_LANGUAGE),
    "tsx": Parser(_TSX_LANGUAGE),
    "javascript": Parser(_JS_LANGUAGE),
    "jsx": Parser(_JS_LANGUAGE),
}

# Node types that map to a standalone chunk
_CHUNK_NODE_TYPES: dict[str, str] = {
    "function_declaration": "function",
    "function_expression": "function",
    "generator_function_declaration": "function",
    "method_definition": "function",
    "class_declaration": "class",
    "class_expression": "class",
    # TS-specific
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "abstract_class_declaration": "class",
    "enum_declaration": "type",
}

# Wrapper nodes that may contain a chunkable node (e.g. `export default function`)
_TRANSPARENT_WRAPPERS = frozenset({
    "export_statement",
    "export_default_declaration",
    "decorator",
    "ambient_declaration",
})


def _get_name(node: Node) -> str | None:
    """Try to extract a name identifier from the node."""
    # Most declarations have a direct 'name' child of type 'identifier' or
    # 'type_identifier'
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier"):
            return child.text.decode("utf-8", errors="replace")  # type: ignore[union-attr]
    return None


def _collect_chunks(
    node: Node,
    source_lines: list[str],
    file_path: str,
    language: str,
    seen_keys: set[str],
) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []

    # Transparent wrappers — descend without emitting
    if node.type in _TRANSPARENT_WRAPPERS:
        for child in node.children:
            chunks.extend(
                _collect_chunks(child, source_lines, file_path, language, seen_keys)
            )
        return chunks

    # Arrow functions assigned to a variable:
    #   lexical_declaration > variable_declarator > arrow_function
    if node.type in ("lexical_declaration", "variable_declaration"):
        for declarator in node.children:
            if declarator.type == "variable_declarator":
                var_name = _get_name(declarator)
                for child in declarator.children:
                    if child.type == "arrow_function":
                        _emit_chunk(
                            child,
                            "function",
                            var_name,
                            source_lines,
                            file_path,
                            language,
                            seen_keys,
                            chunks,
                        )
                        # Don't recurse further into this arrow fn
                        return chunks
        # Not an arrow-function assignment — recurse normally
        for child in node.children:
            chunks.extend(
                _collect_chunks(child, source_lines, file_path, language, seen_keys)
            )
        return chunks

    chunk_type = _CHUNK_NODE_TYPES.get(node.type)
    if chunk_type:
        symbol = _get_name(node)
        _emit_chunk(
            node,
            chunk_type,
            symbol,
            source_lines,
            file_path,
            language,
            seen_keys,
            chunks,
        )
        # Recurse into class bodies to capture methods
        for child in node.children:
            chunks.extend(
                _collect_chunks(child, source_lines, file_path, language, seen_keys)
            )
    else:
        for child in node.children:
            chunks.extend(
                _collect_chunks(child, source_lines, file_path, language, seen_keys)
            )

    return chunks


def _emit_chunk(
    node: Node,
    chunk_type: str,
    symbol: str | None,
    source_lines: list[str],
    file_path: str,
    language: str,
    seen_keys: set[str],
    chunks: list[CodeChunk],
) -> None:
    base_key = f"{file_path}::{symbol or 'anonymous'}::{chunk_type}"
    key = base_key
    counter = 1
    while key in seen_keys:
        key = f"{base_key}_{counter}"
        counter += 1
    seen_keys.add(key)

    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    snippet = "\n".join(source_lines[start_line - 1 : end_line])

    content = (
        f"// file: {file_path}\n"
        f"// symbol: {symbol or 'anonymous'}\n"
        f"// type: {chunk_type}\n\n"
        f"{snippet}"
    )

    chunks.append(
        CodeChunk(
            chunk_key=key,
            symbol_name=symbol,
            chunk_type=chunk_type,
            start_line=start_line,
            end_line=end_line,
            language=language,
            content=content,
        )
    )


def chunk(
    source: str,
    file_path: str,
    language: Literal["typescript", "tsx", "javascript", "jsx"] = "typescript",
) -> list[CodeChunk]:
    """
    Parse *source* as TypeScript/TSX/JavaScript and return one CodeChunk
    per function, class, interface, or type alias.

    A single 'module' chunk is emitted if no named symbols are found.
    """
    parser = _PARSERS.get(language, _PARSERS["typescript"])

    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        logger.exception("tree-sitter failed to parse %s — using generic chunker", file_path)
        from .generic import chunk as generic_chunk
        return generic_chunk(source, language, file_path)

    source_lines = source.splitlines()
    seen_keys: set[str] = set()
    chunks = _collect_chunks(tree.root_node, source_lines, file_path, language, seen_keys)

    if not chunks and source.strip():
        comment = "//" if language in ("typescript", "tsx", "javascript", "jsx") else "#"
        content = f"{comment} file: {file_path}\n{comment} type: module\n\n{source}"
        chunks.append(
            CodeChunk(
                chunk_key=f"{file_path}::module",
                symbol_name=None,
                chunk_type="module",
                start_line=1,
                end_line=len(source_lines),
                language=language,
                content=content,
            )
        )

    return chunks
