"""
Gemini embedding generator for code chunks.

Uses Google's text-embedding-004 model (768 dimensions) — matches the
VECTOR(768) column in code_chunks.embedding (migration 009).

Processes chunks in batches of 100 (Gemini's per-request limit for
embedContent with multiple inputs).

Requires GEMINI_API_KEY in the environment.
"""
from __future__ import annotations

import logging
import os

from google import genai
from google.genai import types

from ..models import CodeChunk

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-004"
_BATCH_SIZE = 100          # Gemini embedContent supports up to 100 inputs per call
_EMBEDDING_DIM = 768       # must match VECTOR(768) in schema (migration 009)


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


async def embed_chunks(chunks: list[CodeChunk]) -> list[CodeChunk]:
    """
    Generate embeddings for all chunks in *chunks* (in-place mutation).

    Each chunk's .embedding field is set to a list[float] of length 768.
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

        # Gemini SDK: embed_content accepts a list of strings directly.
        # task_type="RETRIEVAL_DOCUMENT" is optimal for code/text being indexed.
        response = client.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )

        # response.embeddings is a list of ContentEmbedding objects
        for chunk, embedding_obj in zip(batch, response.embeddings):
            chunk.embedding = embedding_obj.values

    return chunks
