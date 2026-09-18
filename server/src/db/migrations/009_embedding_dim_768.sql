-- Migration 009: change embedding dimension from 1536 (OpenAI) to 768 (Gemini text-embedding-004)
-- Safe to run on an empty code_chunks table (no data yet).
-- If embeddings already exist they must be re-generated after this migration.

ALTER TABLE code_chunks
    ALTER COLUMN embedding TYPE VECTOR(768);
