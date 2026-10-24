"""
Vector Search for Code Localization.

Implements the pgvector query from Part 4 & 5 of the Architecture Specification:
SELECT id, file_path, start_line, end_line, content,
       1 - (embedding <=> $1::vector) AS similarity
FROM code_chunks
WHERE repo_id = $2
ORDER BY embedding <=> $1::vector
LIMIT 10;
"""
from __future__ import annotations

from typing import Any
from .. import db
from ..indexing.embedder import embed_query
from ..utils.logging import get_logger

logger = get_logger("localization.vector_search")


async def search_vector_candidates(
    repo_id: int | str,
    query_text: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Generate query embedding and perform pgvector cosine similarity search.
    """
    if not query_text or not query_text.strip():
        return []

    embedding = await embed_query(query_text)
    if not embedding:
        logger.warning("Could not generate embedding for query: %s", query_text[:60])
        return []

    try:
        rows = await db.search_chunks_by_vector(repo_id, embedding, limit=limit)
        results = []
        for r in rows:
            results.append({
                "chunk_id": r["id"],
                "file_path": r["file_path"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "content": r["content"],
                "score": float(r.get("similarity") or 0.0),
                "method": "embedding",
            })
        return results
    except Exception as e:
        logger.error("Failed pgvector search query: %s", e)
        return []
