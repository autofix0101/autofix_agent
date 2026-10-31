import pool from "../index.js";

// Credentials embedded in URLs (e.g. https://x-access-token:<token>@github.com/...)
// can end up in git or validation output; never send them to the browser.
const URL_CREDENTIALS_RE = /(https?:\/\/)[^/@\s]+@/g;

function scrub(text: string | null): string | null {
    return text === null ? null : text.replace(URL_CREDENTIALS_RE, "$1");
}

const MAX_DIFF_CHARS = 20_000;
const LOG_EXCERPT_CHARS = 4_000;

/**
 * One-sentence outcome of a patch attempt, from the validation log the agent
 * stored. Mirrors `describe_validation_failure` in agent/autofix_agent/progress.py.
 */
function describeAttemptOutcome(passed: boolean | null, log: string | null): string | null {
    if (passed) return "Passed all checks.";
    if (passed === null || log === null) return null; // still being validated
    if (log.startsWith("LLM concluded no code change is needed")) {
        return "The AI concluded no code change is needed.";
    }
    if (log.startsWith("LLM did not produce a patch")) {
        return "The AI couldn't come up with a fix on this attempt.";
    }
    if (log.startsWith("Patch apply failed")) {
        return "The proposed change didn't line up with the current code, so it couldn't be applied.";
    }
    if (log.startsWith("Syntax Validation Failed")) return "The change introduced a syntax error.";
    if (log.includes("TypeScript type-check FAILED")) return "The change introduced TypeScript type errors.";
    if (log.includes("] Syntax error in ")) return "The change introduced a JavaScript syntax error.";
    if (log.toLowerCase().includes("timed out")) return "The project's tests took too long and were stopped.";
    if (log.startsWith("Test runner invocation error")) return "The project's tests couldn't be run.";
    return "The project's tests failed with the change applied.";
}

/**
 * The signal, if it belongs to `repoId` and that repository is owned by `userId`.
 * Every other query in this module is keyed by a signal ID that passed this check.
 */
export async function getSignalForUser(repoId: string, signalId: string, userId: string) {
    const result = await pool.query(
        `
        SELECT s.id, s.type, s.source_ref, s.status, s.parsed_data, s.raw_content, s.created_at
        FROM signals s
        JOIN repositories r ON r.id = s.repo_id
        WHERE s.id = $1
          AND s.repo_id = $2
          AND r.user_id = $3;
        `,
        [signalId, repoId, userId],
    );
    return result.rows[0] ?? null;
}

/**
 * Every fix run (fix_job) for a signal, newest first, with its progress
 * timeline, the code locations it suspected, each patch attempt and its PR.
 */
export async function getFixRunsForSignal(signalId: string) {
    const jobs = await pool.query(
        `
        SELECT fj.id, fj.status, fj.attempt_count, fj.error_message, fj.created_at, fj.updated_at,
               pr.pr_number, pr.pr_url, pr.status AS pr_status
        FROM fix_jobs fj
        LEFT JOIN pull_requests pr ON pr.job_id = fj.id
        WHERE fj.signal_id = $1
        ORDER BY fj.created_at DESC;
        `,
        [signalId],
    );
    if (jobs.rowCount === 0) return [];

    const jobIds = jobs.rows.map((j) => j.id);
    const [events, candidates, patches] = await Promise.all([
        pool.query(
            `
            SELECT id, job_id, stage, message, created_at, created_at::text AS cursor
            FROM job_events
            WHERE job_id = ANY($1::uuid[])
            ORDER BY created_at, id;
            `,
            [jobIds],
        ),
        pool.query(
            `
            SELECT lc.job_id, lc.rank, lc.method, f.path AS file_path, cc.start_line, cc.end_line
            FROM localization_candidates lc
            JOIN code_chunks cc ON cc.id = lc.chunk_id
            JOIN files f ON f.id = cc.file_id
            WHERE lc.job_id = ANY($1::uuid[])
            ORDER BY lc.rank;
            `,
            [jobIds],
        ),
        pool.query(
            `
            SELECT job_id, attempt_number, diff_content, explanation, validation_passed,
                   validation_log, created_at
            FROM patches
            WHERE job_id = ANY($1::uuid[])
            ORDER BY attempt_number;
            `,
            [jobIds],
        ),
    ]);

    return jobs.rows.map((job) => ({
        id: job.id,
        status: job.status,
        attempt_count: job.attempt_count,
        error_message: scrub(job.error_message),
        created_at: job.created_at,
        updated_at: job.updated_at,
        pull_request: job.pr_url
            ? { pr_number: job.pr_number, pr_url: job.pr_url, status: job.pr_status }
            : null,
        events: events.rows
            .filter((e) => e.job_id === job.id)
            .map(({ id, job_id, stage, message, created_at, cursor }) => ({
                id, job_id, stage, message, created_at, cursor,
            })),
        candidates: candidates.rows
            .filter((c) => c.job_id === job.id)
            .map(({ rank, method, file_path, start_line, end_line }) => ({
                rank, method, file_path, start_line, end_line,
            })),
        attempts: patches.rows
            .filter((p) => p.job_id === job.id)
            .map((p) => {
                const log: string | null = p.validation_log;
                // An empty diff on a finished attempt means no change was proposed
                const finished = p.validation_passed === true || log !== null;
                return {
                    attempt_number: p.attempt_number,
                    explanation: p.explanation,
                    diff_content: p.diff_content.slice(0, MAX_DIFF_CHARS),
                    diff_truncated: p.diff_content.length > MAX_DIFF_CHARS,
                    validation_passed: finished ? p.validation_passed : null,
                    outcome: describeAttemptOutcome(finished ? p.validation_passed : null, log),
                    log_excerpt: log ? scrub(log.slice(-LOG_EXCERPT_CHARS)) : null,
                    created_at: p.created_at,
                };
            }),
    }));
}

/**
 * Progress events for any of the signal's runs recorded after `cursor`
 * (a microsecond-precision timestamp from a previous event's `cursor`).
 */
export async function getSignalEventsAfter(signalId: string, cursor: string | null) {
    const result = await pool.query(
        `
        SELECT e.id, e.job_id, e.stage, e.message, e.created_at, e.created_at::text AS cursor
        FROM job_events e
        JOIN fix_jobs fj ON fj.id = e.job_id
        WHERE fj.signal_id = $1
          AND ($2::timestamptz IS NULL OR e.created_at > $2::timestamptz)
        ORDER BY e.created_at, e.id
        LIMIT 200;
        `,
        [signalId, cursor],
    );
    return result.rows;
}

/** Cheap snapshot of the signal's runs, used to detect status changes. */
export async function getFixRunStates(signalId: string) {
    const result = await pool.query(
        `
        SELECT id, status, attempt_count, updated_at::text AS updated_at
        FROM fix_jobs
        WHERE signal_id = $1
        ORDER BY created_at DESC;
        `,
        [signalId],
    );
    return result.rows;
}
