import express from "express";
import { verifyGithubSignature } from "../utils/webhookSignature.js";
import {
    findRepoByGithubRepoId,
    insertSignalIgnoreDuplicate,
    upsertIssueSignal,
} from "../db/queries/signalQueries.js";
import { sseService } from "../services/sseService.js";

const WEBHOOK_SECRET = process.env.GITHUB_WEBHOOK_SECRET!;

/**
 * POST /webhooks/github
 *
 * Receives GitHub webhook events, verifies the HMAC signature, maps the event
 * to an internal repository, and persists a signal for supported event types.
 *
 * Supported events:
 *   issues       → action: opened | reopened  → signals.type = 'github_issue'
 *   workflow_run → action: completed + conclusion: failure → signals.type = 'ci_failure'
 *
 * This handler ONLY ingests and stores the signal. It does NOT start the
 * agentic workflow (embedding, indexing, root-cause, patch, PR). That is
 * handled downstream by the fix-job pipeline.
 *
 * Response conventions (to avoid GitHub retry storms):
 *   401 — invalid HMAC signature (only case we reject hard)
 *   200 — everything else, including untracked repos, unsupported events,
 *          malformed payloads, and duplicate deliveries
 *   500 — unexpected server errors during DB writes
 */
export const handleGithubWebhook = async (
    req: express.Request,
    res: express.Response,
) => {
    const rawBody = req.body as Buffer; // express.raw() delivers a Buffer
    const signature = req.headers["x-hub-signature-256"];
    const event = req.headers["x-github-event"];
    const delivery = req.headers["x-github-delivery"];

    // ── 1. Verify HMAC signature ──────────────────────────────────────────────
    if (
        typeof signature !== "string" ||
        !verifyGithubSignature(WEBHOOK_SECRET, rawBody, signature)
    ) {
        console.warn(
            `[webhook] Rejected delivery ${delivery ?? "(unknown)"} — invalid signature`,
        );
        return res.status(401).json({ error: "Invalid webhook signature" });
    }

    // ── 2. Parse JSON payload ─────────────────────────────────────────────────
    let payload: any;
    try {
        payload = JSON.parse(rawBody.toString("utf8"));
    } catch {
        // Return 200 so GitHub does not retry a permanently malformed payload
        console.warn(
            `[webhook] Delivery ${delivery ?? "(unknown)"} — failed to parse JSON body`,
        );
        return res.status(200).json({ message: "ignored: malformed payload" });
    }

    // ── 3. Extract and validate the GitHub repository ID ─────────────────────
    const githubRepoId: unknown = payload?.repository?.id;
    if (typeof githubRepoId !== "number") {
        console.warn(
            `[webhook] Delivery ${delivery ?? "(unknown)"}, event="${event}" — missing or non-numeric repository.id`,
        );
        return res
            .status(200)
            .json({ message: "ignored: missing repository id" });
    }

    // ── 4. Map to internal repository ────────────────────────────────────────
    let repo: { id: string; user_id: string | null } | null;
    try {
        repo = await findRepoByGithubRepoId(githubRepoId);
    } catch (err) {
        console.error(
            `[webhook] DB error looking up github_repo_id=${githubRepoId}`,
            err,
        );
        return res.status(500).json({ error: "Internal server error" });
    }

    if (!repo) {
        // Repository exists on GitHub but is not tracked in Autofix — ignore
        console.warn(
            `[webhook] Delivery ${delivery ?? "(unknown)"} — github_repo_id=${githubRepoId} is not tracked in Autofix`,
        );
        return res.status(200).json({ message: "repository not tracked" });
    }

    // ── 5. Dispatch to event-specific handler ─────────────────────────────────
    try {
        if (event === "issues") {
            const signal = await handleIssueEvent(payload, repo.id);
            // Broadcast to any open SSE connections for this user
            if (signal && repo.user_id) {
                const parsed = typeof signal.parsed_data === "string" ? (() => {
                    try { return JSON.parse(signal.parsed_data); } catch { return {}; }
                })() : (signal.parsed_data || {});

                sseService.broadcast(repo.user_id, {
                    repoId: repo.id,
                    signalId: signal.id,
                    type: "github_issue",
                    title: parsed?.title ?? `Issue #${signal.source_ref}`,
                });
            }
        } else if (event === "workflow_run") {
            const signal = await handleWorkflowRunEvent(payload, repo.id);
            if (signal && repo.user_id) {
                const parsed = typeof signal.parsed_data === "string" ? (() => {
                    try { return JSON.parse(signal.parsed_data); } catch { return {}; }
                })() : (signal.parsed_data || {});

                sseService.broadcast(repo.user_id, {
                    repoId: repo.id,
                    signalId: signal.id,
                    type: "ci_failure",
                    title: parsed?.workflow_name ?? `CI failure (run ${signal.source_ref})`,
                });
            }
        } else {
            // Unknown / future event type — acknowledge and ignore
            return res.status(200).json({ message: "event not handled" });
        }
    } catch (err) {
        console.error(
            `[webhook] Error processing event="${event}" delivery=${delivery ?? "(unknown)"}`,
            err,
        );
        return res.status(500).json({ error: "Internal server error" });
    }

    return res.status(200).json({ message: "ok" });
};

// ── Issue event ───────────────────────────────────────────────────────────────

async function handleIssueEvent(payload: any, repoId: string) {
    const { action, issue, repository } = payload;

    // Only create/update signals for issues being opened or reopened.
    // edited, labeled, commented, closed, etc. are deliberately ignored —
    // signals are snapshots of the "needs investigation" state.
    if (action !== "opened" && action !== "reopened") {
        return null;
    }

    const sourceRef = String(issue.number);

    const rawContent = [issue.title, issue.body]
        .filter((s): s is string => typeof s === "string" && s.trim().length > 0)
        .join("\n\n");

    const parsedData = {
        action,
        number: issue.number,
        title: issue.title,
        body: issue.body ?? null,
        url: issue.html_url,
        github_issue_id: issue.id,
        author: issue.user?.login ?? null,
        labels: (issue.labels ?? []).map((l: { name: string }) => l.name),
        repository_full_name: repository?.full_name ?? null,
    };

    const signal = await upsertIssueSignal({
        repo_id: repoId,
        type: "github_issue",
        source_ref: sourceRef,
        raw_content: rawContent,
        parsed_data: parsedData,
    });

    if (signal) {
        console.log(
            `[webhook] github_issue signal id=${signal.id} upserted for issue #${issue.number} (action="${action}") in internal repo ${repoId}`,
        );
    }
    return signal;
}

// ── Workflow run event ────────────────────────────────────────────────────────

async function handleWorkflowRunEvent(
    payload: any,
    repoId: string,
) {
    const { action, workflow_run, repository } = payload;

    // Only act on completed runs that actually failed.
    // success, cancelled, skipped, etc. are not actionable by Autofix.
    if (action !== "completed") return null;
    if (workflow_run?.conclusion !== "failure") return null;

    const sourceRef = String(workflow_run.id);

    const rawContent = [
        `Workflow: ${workflow_run.name}`,
        `Branch: ${workflow_run.head_branch}`,
        `Conclusion: ${workflow_run.conclusion}`,
        `Triggered by: ${workflow_run.event}`,
        `Run URL: ${workflow_run.html_url}`,
    ].join("\n");

    const parsedData = {
        workflow_name: workflow_run.name,
        run_id: workflow_run.id,
        run_number: workflow_run.run_number,
        branch: workflow_run.head_branch,
        head_sha: workflow_run.head_sha,
        conclusion: workflow_run.conclusion,
        html_url: workflow_run.html_url,
        event: workflow_run.event,
        actor: workflow_run.actor?.login ?? null,
        repository_full_name: repository?.full_name ?? null,
        head_commit: workflow_run.head_commit ?? null,
    };

    const signal = await insertSignalIgnoreDuplicate({
        repo_id: repoId,
        type: "ci_failure",
        source_ref: sourceRef,
        raw_content: rawContent,
        parsed_data: parsedData,
    });

    if (signal) {
        console.log(
            `[webhook] ci_failure signal id=${signal.id} inserted for workflow run ${workflow_run.id} in internal repo ${repoId}`,
        );
    } else {
        // null returned by DO NOTHING — this was a retried delivery
        console.log(
            `[webhook] ci_failure signal for run ${workflow_run.id} already exists — duplicate delivery ignored`,
        );
    }
    return signal;
}
