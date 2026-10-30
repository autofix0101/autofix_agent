# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

AutoFix turns GitHub bug signals (issues, failed CI runs) into validated patches. Three independent apps share one Postgres database (with the `pgvector` extension); they never call each other directly, so all coordination happens through DB rows.

- `server/` — Express 5 + TypeScript (ESM) API on port 3000. GitHub OAuth login (JWT in cookie), repository management, GitHub webhook ingestion, SSE notifications.
- `client/vite-project/` — React 19 + Vite + Tailwind v4 dashboard on port 5173. The Vite dev server proxies `/auth`, `/repositories`, `/githubrepos`, `/signals`, `/webhooks` to `localhost:3000`, so client code uses relative paths (`apiFetch` in `src/api/client.ts`, `credentials: "include"`).
- `agent/` — Python async worker (`autofix_agent` package) that claims fix jobs and runs the fix pipeline.

## Commands

Server (`cd server`):
- `npm run dev` — run with `tsx watch src/app.ts`
- `npm run build` — `tsc`
- No test suite (`npm test` is a placeholder).

Client (`cd client/vite-project`):
- `npm run dev` / `npm run build` (`tsc -b && vite build`) / `npm run lint` (eslint)

Agent (`cd agent`, using a venv; `pip install -e .` or `pip install -r requirements.txt`):
- `autofix-worker` or `python -m autofix_agent.worker` — start the polling worker
- `pytest` — run tests (pytest is not listed as a dependency; install it separately)
- `pytest tests/test_chunker.py::<test_name>` — run a single test
- `python test_job.py` — seed a fake signal + queued `fix_jobs` row against the first repo in the DB and run the full pipeline end-to-end
- `python check_db.py` — dump repositories/files/chunks/jobs for inspection

Database: the schema lives in `server/src/db/migrations/`. `consolidated_schema.sql` is the full current schema (meant to be run once, e.g. in the Supabase SQL editor); the numbered files are the incremental history. There is no migration runner — keep `consolidated_schema.sql` in sync when adding a numbered migration.

## Configuration

- `agent/.env` (see `.env.example`), loaded by `autofix_agent/config.py` into a frozen `settings` dataclass: `DATABASE_URL`, `GROQ_API_KEY` (LLM via Groq), `GEMINI_API_KEY` (embeddings), `LLM_MODEL`, `EMBED_MODEL`, `EMBED_DIM` (must match the `vector(...)` column size in the schema), `REPOS_DIR`, `MAX_VALIDATION_ATTEMPTS`, `WORKER_POLL_INTERVAL`.
- `server/.env`: `DATABASE_URL`, `JWT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_CALLBACK_URL`, `GITHUB_WEBHOOK_SECRET`, `AUTOFIX_API_BASE_URL` (public URL GitHub webhooks are registered against), `NODE_ENV`.

## Architecture

### Signal ingestion (server)
`POST /webhooks/github` (`controllers/webhookController.ts`) is mounted in `app.ts` **before** `express.json()` because it needs the raw body for HMAC verification. It maps `issues` (opened/reopened) → `signals.type='github_issue'` and failed `workflow_run` → `'ci_failure'`, stores the signal (deduped by a unique constraint), and broadcasts to the repo owner's browser tabs via the in-memory `sseService` (`GET /signals/stream`). It deliberately returns 200 for everything except bad signatures, to avoid GitHub retry storms. The webhook handler does **not** start fixing — it only stores the signal.

### Job queue
The agent polls `fix_jobs` via `db.claim_next_job()` (`SELECT ... FOR UPDATE SKIP LOCKED`), so multiple workers can run concurrently. Note: currently nothing in server/client inserts `fix_jobs` rows; only `agent/test_job.py` does.

### Pipeline (`agent/autofix_agent/pipeline.py`)
Each stage updates `fix_jobs.status` and appends to `job_events` (that's how progress is surfaced):
1. **reindexing** (`indexing/`) — compares `repositories.last_commit_sha` with the remote HEAD via the GitHub API. Full index if no SHA or no stored files, otherwise incremental (only changed files via `diff_detector`). Files are chunked with tree-sitter (Python/JS/TS/Go/Java) in `chunker.py`, embedded with Gemini (`embedder.py`, with rate-limit retries), and stored in `files` / `code_chunks`. `last_commit_sha` is updated only after success. Indexing failure is non-fatal — the pipeline continues on the existing index.
2. **localizing** (`signals/` + `localization/`) — `issue_preprocessor` + `stack_trace_parser` extract frames; `ranker.localize_and_rank` tries direct file+line matches from app-code frames first, then pgvector similarity, then symbol/keyword search as fallbacks. Results are persisted to `localization_candidates`.
3. **generating** (`generation/`) — `agent_loop.run_generation_loop` runs an LLM tool-calling loop (Groq client in `llm_client.py`, prompts in `prompts.py`) with `read_file` / `search_code` / `list_files` tools (`tools.py`, `RepoToolExecutor`) over a fresh shallow clone, producing a unified diff saved to `patches`.
4. **validating** (`validation/`) — copies the clone into a `Sandbox`, applies the diff (`patch_apply.py`), runs Python syntax checks then an auto-detected test command (`test_runners.py`: pytest / npm test / go test / Java). On failure, the log is fed back into the next generation attempt, up to `MAX_VALIDATION_ATTEMPTS`.
5. Success → `awaiting_approval` (human review in the UI); otherwise `failed` with `error_message`.

GitHub access uses the repo owner's OAuth token (`users.github_access_token`), injected into clone URLs as `x-access-token`.
