"""
Generic fallback chunker for unsupported languages.
"""
from __future__ import annotations

from ...models import CodeChunk

WINDOW_LINES = 60
OVERLAP_LINES = 10


def chunk(source: str, language: str, file_path: str) -> list[CodeChunk]:
    """
    Split *source* into overlapping line-window chunks.

    Each chunk is labelled chunk_type='block' with a positional chunk_key.
    """
    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    block_index = 0

    start = 0
    while start < len(lines):
        end = min(start + WINDOW_LINES, len(lines))
        snippet = "\n".join(lines[start:end])
        chunk_key = f"{file_path}::block_{block_index}"

        content = (
            f"# file: {file_path}\n"
            f"# lines: {start + 1}-{end}\n\n"
            f"{snippet}"
        )

        chunks.append(
            CodeChunk(
                chunk_key=chunk_key,
                symbol_name=None,
                chunk_type="block",
                start_line=start + 1,
                end_line=end,
                language=language,
                content=content,
            )
        )

        block_index += 1
        if end == len(lines):
            break
        start = end - OVERLAP_LINES  # overlap with next window

    return chunks
