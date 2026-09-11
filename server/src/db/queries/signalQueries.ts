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
