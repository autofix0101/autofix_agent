-- At most one non-failed fix job per signal.
-- Guards POST /repositories/:id/signals/:signalId/fix against double clicks
-- and concurrent requests; a failed job can be retried by creating a new one.

CREATE UNIQUE INDEX IF NOT EXISTS fix_jobs_one_active_per_signal
ON fix_jobs(signal_id)
WHERE status <> 'failed';
