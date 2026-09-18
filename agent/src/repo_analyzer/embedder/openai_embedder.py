"""
OpenAI embedding generator for code chunks.

Uses text-embedding-3-small (1536 dimensions) — matches the VECTOR(1536)
column in code_chunks.embedding.

Processes chunks in batches of 96 to stay within the API's per-request
token limits while keeping the number of HTTP round-trips low.
"""
from __future__ import annotations

import logging
import os

from openai import AsyncOpenAI

from ..models import CodeChunk

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 96          # max chunks per API call
_EMBEDDING_DIM = 1536     # must match VECTOR(1536) in schema


def _get_client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=api_key)


async def embed_chunks(chunks: list[CodeChunk]) -> list[CodeChunk]:
    """
    Generate embeddings for all chunks in *chunks* (in-place mutation).

    Each chunk's .embedding field is set to a list[float] of length 1536.
    Chunks are processed in batches; the order is preserved.

    Returns the same list for convenience.
    """
    if not chunks:
        return chunks

    client = _get_client()

    for batch_start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _BATCH_SIZE]
        texts = [c.content for c in batch]

        logger.debug(
            "Embedding batch %d-%d / %d",
            batch_start + 1,
            batch_start + len(batch),
            len(chunks),
        )

        response = await client.embeddings.create(
            model=_EMBEDDING_MODEL,
            input=texts,
            dimensions=_EMBEDDING_DIM,
        )

        # Response objects are ordered to match the input
        for chunk, embedding_obj in zip(batch, response.data):
            chunk.embedding = embedding_obj.embedding

    return chunks
