-- Store the GitHub-assigned webhook ID for each connected repository.
-- This enables:
--   1. Cleanup: when a user disconnects a repo, Autofix calls
--      DELETE /repos/{owner}/{repo}/hooks/{id} before removing the DB row.
--   2. Idempotency: createRepository checks this column before attempting
--      to register a new webhook, preventing duplicate hooks on re-add.
--
-- Nullable — repos connected before this migration, and repos where webhook
-- creation failed (e.g. user lacks admin access), will have NULL.

ALTER TABLE repositories
ADD COLUMN github_webhook_id BIGINT;
