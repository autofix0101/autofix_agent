import pool from "../index.js";

type SignalInput = {
    repo_id: string;
    type: string;
    source_ref: string;
    raw_content: string;
    parsed_data: object;
};

/**
 * Look up an internal repository record by its GitHub numeric repo ID.
 * This is the canonical lookup for webhook events — GitHub is the source of
 * truth, so we join on github_repo_id rather than trusting any client-supplied ID.
 */
export async function findRepoByGithubRepoId(githubRepoId: number) {
    const query = `
        SELECT id, user_id
        FROM repositories
        WHERE github_repo_id = $1;
    `;
    const result = await pool.query(query, [githubRepoId]);
    return result.rows[0] ?? null;
}

/**
 * Insert a new signal, silently ignoring duplicate deliveries.
 *
 * Used for ci_failure signals: the source_ref is the workflow run ID, which
 * is globally unique per run. If GitHub retries the same delivery, the
 * conflict is harmless and the original record is preserved.
 */
export async function insertSignalIgnoreDuplicate(signal: SignalInput) {
    const query = `
        INSERT INTO signals (repo_id, type, source_ref, raw_content, parsed_data)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (repo_id, type, source_ref) DO NOTHING
        RETURNING *;
    `;
    const values = [
        signal.repo_id,
        signal.type,
        signal.source_ref,
        signal.raw_content,
        JSON.stringify(signal.parsed_data),
    ];
    const result = await pool.query(query, values);
    return result.rows[0] ?? null;
}

/**
 * Upsert a GitHub issue signal.
 *
 * On conflict (same issue number in the same repo), update the signal back to
 * status = 'open' and refresh raw_content/parsed_data with the latest payload.
 * This correctly handles the "reopened" action: an issue that was previously
 * resolved and is reopened on GitHub will reset the Autofix signal to 'open'.
 */
export async function upsertIssueSignal(signal: SignalInput) {
    const query = `
        INSERT INTO signals (repo_id, type, source_ref, raw_content, parsed_data)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (repo_id, type, source_ref) DO UPDATE
            SET status       = 'open',
                raw_content  = EXCLUDED.raw_content,
                parsed_data  = EXCLUDED.parsed_data
        RETURNING *;
    `;
    const values = [
        signal.repo_id,
        signal.type,
        signal.source_ref,
        signal.raw_content,
        JSON.stringify(signal.parsed_data),
    ];
    const result = await pool.query(query, values);
    return result.rows[0] ?? null;
}

/**
 * Return all signals for a repository, ordered newest-first.
 * Joins through `repositories` so the user_id ownership check is implicit —
 * only signals belonging to repos owned by `userId` can be returned.
 *
 * Each signal carries its latest fix job (if any) and that job's PR, so the
 * UI can show the Fix button, live job status, or a link to the PR.
 */
export async function getSignalsByRepoId(repoId: string, userId: string) {
    const query = `
        SELECT
            s.id,
            s.type,
            s.source_ref,
            s.status,
            s.parsed_data,
            s.raw_content,
            s.created_at,
            fj.id            AS job_id,
            fj.status        AS job_status,
            fj.error_message AS job_error,
            pr.pr_number,
            pr.pr_url
        FROM signals s
        JOIN repositories r ON r.id = s.repo_id
        LEFT JOIN LATERAL (
            SELECT id, status, error_message
            FROM fix_jobs
            WHERE signal_id = s.id
            ORDER BY created_at DESC
            LIMIT 1
        ) fj ON TRUE
        LEFT JOIN pull_requests pr ON pr.job_id = fj.id
        WHERE s.repo_id = $1
          AND r.user_id = $2
        ORDER BY s.created_at DESC
        LIMIT 100;
    `;
    const result = await pool.query(query, [repoId, userId]);
    return result.rows;
}

export type CreateFixJobResult =
    | { kind: "created"; job: { id: string; status: string; signal_id: string } }
    | { kind: "signal_not_found" }
    | { kind: "already_active"; jobId: string; jobStatus: string };

/**
 * Queue a fix job for a signal. The Python agent picks up `queued` rows
 * automatically (claim_next_job → FOR UPDATE SKIP LOCKED).
 *
 * The signal must belong to `repoId`, which must be owned by `userId`.
 * Rejects if the signal already has a non-failed job (also enforced by the
 * fix_jobs_one_active_per_signal partial unique index, which makes
 * concurrent requests safe). Marks the signal 'in_progress'.
 */
export async function createFixJobForSignal(
    repoId: string,
    signalId: string,
    userId: string,
): Promise<CreateFixJobResult> {
    const client = await pool.connect();
    try {
        await client.query("BEGIN");

        const signal = await client.query(
            `
            SELECT s.id
            FROM signals s
            JOIN repositories r ON r.id = s.repo_id
            WHERE s.id = $1
              AND s.repo_id = $2
              AND r.user_id = $3
            FOR UPDATE OF s;
            `,
            [signalId, repoId, userId],
        );
        if (signal.rowCount === 0) {
            await client.query("ROLLBACK");
            return { kind: "signal_not_found" };
        }

        const active = await client.query(
            `
            SELECT id, status
            FROM fix_jobs
            WHERE signal_id = $1 AND status <> 'failed'
            LIMIT 1;
            `,
            [signalId],
        );
        if (active.rows[0]) {
            await client.query("ROLLBACK");
            return {
                kind: "already_active",
                jobId: active.rows[0].id,
                jobStatus: active.rows[0].status,
            };
        }

        const job = await client.query(
            `
            INSERT INTO fix_jobs (repo_id, signal_id, status)
            VALUES ($1, $2, 'queued')
            RETURNING id, status, signal_id;
            `,
            [repoId, signalId],
        );
        await client.query(
            `UPDATE signals SET status = 'in_progress' WHERE id = $1;`,
            [signalId],
        );

        await client.query("COMMIT");
        return { kind: "created", job: job.rows[0] };
    } catch (err) {
        await client.query("ROLLBACK");
        throw err;
    } finally {
        client.release();
    }
}
