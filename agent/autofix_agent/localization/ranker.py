"""
Localization Ranker.

Merges direct stack trace frame matches with pgvector vector search candidates,
assigns ranks and confidence scores, and persists to localization_candidates.
"""
from __future__ import annotations

from typing import Any

from .. import db
from ..signals.issue_preprocessor import PreprocessedSignal
from ..utils.logging import get_logger
from .vector_search import search_vector_candidates

logger = get_logger("localization.ranker")


async def localize_and_rank(
    repo_id: str,
    job_id: str,
    signal: PreprocessedSignal,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Localize bug culprits and persist to localization_candidates.
    Returns ranked list of candidate dicts.
    """
    candidates: list[dict[str, Any]] = []
    seen_chunk_ids: set = set()

    # -----------------------------------------------------------------------
    # 1. Direct stack trace matching (highest confidence)
    # -----------------------------------------------------------------------
    if signal.stack_trace and signal.stack_trace.frames:
        app_frames = [f for f in signal.stack_trace.frames if f.is_app_code]
        frames_to_check = app_frames if app_frames else list(signal.stack_trace.frames)

        for idx, frame in enumerate(reversed(frames_to_check)):
            # Try direct file+line match first
            chunk_row = await db.find_chunk_by_file_and_line(
                repo_id, frame.file_path, frame.line_number
            )
            # Fallback: symbol name match
            if not chunk_row and frame.function_name:
                symbol_rows = await db.find_chunk_by_symbol(
                    repo_id, frame.function_name, frame.file_path
                )
                if symbol_rows:
                    chunk_row = symbol_rows[0]

            if chunk_row:
                cid = chunk_row["id"]
                if cid not in seen_chunk_ids:
                    seen_chunk_ids.add(cid)
                    score = max(0.75, 1.0 - (idx * 0.05))
                    candidates.append({
                        "chunk_id": str(cid),
                        "file_path": chunk_row["file_path"],
                        "start_line": chunk_row["start_line"],
                        "end_line": chunk_row["end_line"],
                        "content": chunk_row.get("content", ""),
                        "score": score,
                        "method": "stack_trace_direct",
                    })

    # -----------------------------------------------------------------------
    # 2. pgvector similarity search
    # -----------------------------------------------------------------------
    if signal.search_query:
        vector_candidates = await search_vector_candidates(repo_id, signal.search_query, limit=limit)
        for vc in vector_candidates:
            cid = vc["chunk_id"]
            if cid in seen_chunk_ids:
                # Boost already-found chunk for semantic corroboration
                for existing in candidates:
                    if str(existing["chunk_id"]) == str(cid):
                        existing["score"] = min(1.0, existing["score"] + 0.05)
                        break
            else:
                seen_chunk_ids.add(cid)
                candidates.append(vc)

    # -----------------------------------------------------------------------
    # 3. Mentioned symbols & files fallback
    # -----------------------------------------------------------------------
    if not candidates and signal.mentioned_symbols:
        for sym in signal.mentioned_symbols[:3]:
            symbol_rows = await db.find_chunk_by_symbol(repo_id, sym)
            for s_row in symbol_rows:
                cid = s_row["id"]
                if cid not in seen_chunk_ids:
                    seen_chunk_ids.add(cid)
                    candidates.append({
                        "chunk_id": str(cid),
                        "file_path": s_row["file_path"],
                        "start_line": s_row["start_line"],
                        "end_line": s_row["end_line"],
                        "content": s_row.get("content", ""),
                        "score": 0.70,
                        "method": "mentioned_symbol",
                    })

    # -----------------------------------------------------------------------
    # 4. Keyword search fallback (when vector search returns empty)
    # -----------------------------------------------------------------------
    if not candidates:
        import re
        raw_text = f"{signal.title} {signal.cleaned_text}"
        words = re.findall(r"\b[A-Za-z0-9_]{3,}\b", raw_text)
        stopwords = {
            "the", "and", "not", "with", "this", "that", "from", "for", "are",
            "been", "was", "were", "when", "user", "attempts", "does", "after",
            "being", "actual", "expected", "behavior", "should", "appear", "into"
        }
        meaningful_words = [w for w in words if w.lower() not in stopwords]
        # Deduplicate while preserving order
        unique_kws = list(dict.fromkeys(meaningful_words))
        for kw in unique_kws[:4]:
            kw_rows = await db.search_chunks_by_keyword(repo_id, kw, limit=3)
            for kr in kw_rows:
                cid = kr["id"]
                if cid not in seen_chunk_ids:
                    seen_chunk_ids.add(cid)
                    candidates.append({
                        "chunk_id": str(cid),
                        "file_path": kr["file_path"],
                        "start_line": kr["start_line"],
                        "end_line": kr["end_line"],
                        "content": kr.get("content", ""),
                        "score": 0.55,
                        "method": "keyword_search",
                    })

    # -----------------------------------------------------------------------
    # 5. Sort, rank, and persist
    # -----------------------------------------------------------------------
    candidates.sort(key=lambda x: x["score"], reverse=True)
    ranked = candidates[:limit]
    for r_idx, c in enumerate(ranked, start=1):
        c["rank"] = r_idx

    if ranked:
        await db.insert_localization_candidates(job_id, ranked)
        logger.info("Persisted %d localization candidates for job %s", len(ranked), job_id)

    return ranked
