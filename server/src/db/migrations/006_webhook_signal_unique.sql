-- Enforce idempotency for webhook-delivered signals.
-- The combination of (repo_id, type, source_ref) uniquely identifies a signal
-- originating from a specific GitHub event on a specific repository:
--   github_issue  → source_ref = issue number (e.g. "42")
--   ci_failure    → source_ref = workflow run ID (e.g. "12345678")
--
-- ON CONFLICT handling in the application layer:
--   github_issue  → DO UPDATE SET status = 'open' (reopened issues reset the signal)
--   ci_failure    → DO NOTHING (same run ID = retried delivery, already stored)

ALTER TABLE signals
ADD CONSTRAINT signals_repo_source_type_unique
UNIQUE (repo_id, type, source_ref);
