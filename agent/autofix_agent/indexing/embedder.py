"""
Embedding generator for code chunks and search queries.

Batches embedding API calls (up to 100 chunks per request) to optimize
round-trip performance on large repositories. Produces 1536-dim vectors.
"""
from __future__ import annotations

import asyncio
import os
from typing import Sequence

from ..config import settings
from ..utils.logging import get_logger
from .chunker import Chunk

logger = get_logger("indexing.embedder")

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore


def _get_gemini_client() -> genai.Client | None:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        fallback = settings.LLM_API_KEY
        if fallback and not fallback.startswith("gsk_"):
            api_key = fallback
    if not api_key or not genai:
        return None
    return genai.Client(api_key=api_key)


async def embed_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """
    Generate 1536-dim vector embeddings for chunks in-place, in small batches
    with automatic retry on rate limits (429).
    """
    if not chunks:
        return chunks

    client = _get_gemini_client()
    if not client:
        logger.warning("Gemini client unavailable or GEMINI_API_KEY missing; skipping embeddings.")
        return chunks

    # Use smaller batch size (max 10) to respect free-tier token limits (30k tokens/min)
    batch_size = min(settings.EMBED_BATCH_SIZE, 10)

    for start_idx in range(0, len(chunks), batch_size):
        batch = chunks[start_idx : start_idx + batch_size]
        texts = [c.content for c in batch]

        logger.debug(
            "Embedding batch %d-%d / %d",
            start_idx + 1,
            start_idx + len(batch),
            len(chunks),
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.embed_content(
                    model=settings.EMBED_MODEL,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=settings.EMBED_DIM,
                    ),
                )
                for chunk, emb_obj in zip(batch, response.embeddings):
                    chunk.embedding = emb_obj.values
                break
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                    sleep_time = (attempt + 1) * 15
                    logger.warning(
                        "Embeddings rate limited (429). Retrying in %ds... (attempt %d/%d)",
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error(
                        "Error generating embeddings for batch (%d-%d): %s",
                        start_idx,
                        start_idx + len(batch),
                        e,
                    )
                    break

        # Brief pause between batches to avoid exceeding per-minute quotas
        await asyncio.sleep(1.0)

    return chunks


async def embed_query(query: str) -> list[float] | None:
    """
    Generate 1536-dim query embedding vector for semantic search.
    """
    if not query or not query.strip():
        return None

    client = _get_gemini_client()
    if not client:
        logger.warning("Gemini client unavailable for query embedding.")
        return None

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.embed_content(
                model=settings.EMBED_MODEL,
                contents=query.strip(),
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=settings.EMBED_DIM,
                ),
            )
            if response.embeddings:
                return response.embeddings[0].values
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                sleep_time = (attempt + 1) * 10
                logger.warning(
                    "Query embedding rate limited (429). Retrying in %ds... (attempt %d/%d)",
                    sleep_time,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(sleep_time)
            else:
                logger.error("Failed to embed query: %s", e)
                break
    return None
