import express from "express";
import type { AuthRequest } from "../middleware/auth.js";
import {
    addRepository,
    deleteRepoById,
    getAllUserRepos,
    getRepoDetailsById,
    updateRepoWebhookId,
} from "../db/queries/repoQueries.js";
import { getUserGithubAccessToken } from "../db/queries/userQueries.js";
import {
    createGithubWebhook,
    deleteGithubWebhook,
} from "../services/githubService.js";
import {
    createFixJobForSignal,
    getSignalsByRepoId,
} from "../db/queries/signalQueries.js";
import {
    getFixRunsForSignal,
    getFixRunStates,
    getSignalEventsAfter,
    getSignalForUser,
} from "../db/queries/fixRunQueries.js";

const getAllRepos = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }

        const repos = await getAllUserRepos(userId);
        return res.status(200).json(repos);
    } catch (err) {
        console.error("Error while getting all user repos", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

const getRepoDetails = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }

        const repoId = req.params.id;
        if (!repoId || typeof repoId !== "string") {
            return res
                .status(400)
                .json({ message: "Invalid or missing repository ID" });
        }

        const repo = await getRepoDetailsById(repoId, userId);
        if (!repo) {
            return res.status(404).json({
                message: "Repository not found",
            });
        }
        return res.status(200).json(repo);
    } catch (err) {
        console.error("Error while getting repo details", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

const createRepository = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }

        const {
            githubRepoId,
            name,
            owner,
            cloneUrl,
            htmlUrl,
            defaultBranch,
            isPrivate,
        } = req.body;

        if (
            !githubRepoId ||
            !name ||
            !owner ||
            !cloneUrl ||
            !htmlUrl ||
            !defaultBranch ||
            typeof isPrivate !== "boolean"
        ) {
            return res.status(400).json({
                message: "Missing or invalid repository details",
            });
        }

        // Fetch the user's GitHub access token — reused for both the commit-SHA
        // lookup below and the webhook registration afterward.
        const accessToken = await getUserGithubAccessToken(userId);

        // ── Fetch latest commit SHA ────────────────────────────────────────────
        const response = await fetch(
            `https://api.github.com/repos/${owner}/${name}/commits?sha=${defaultBranch}&per_page=1`,
            {
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                    Accept: "application/vnd.github+json",
                },
            },
        );

        if (!response.ok) {
            console.error("GitHub API error:", await response.text());

            return res.status(response.status).json({
                message: "Failed to fetch repository commits from GitHub",
            });
        }

        const commits = await response.json();
        const lastCommitSha = commits[0]?.sha;

        if (!lastCommitSha) {
            return res.status(400).json({
                message: "Could not determine latest commit",
            });
        }

        // ── Save the repository record ─────────────────────────────────────────
        const result = await addRepository({
            user_id: userId,
            github_repo_id: githubRepoId,
            name: name,
            owner: owner,
            clone_url: cloneUrl,
            html_url: htmlUrl,
            default_branch: defaultBranch,
            is_private: isPrivate,
            last_commit_sha: lastCommitSha,
        });

        // ── Register GitHub webhook (best-effort) ──────────────────────────────
        // If this fails (e.g. user lacks admin access on the repo), the repository
        // is still saved and the caller receives a 201 with a webhookSetupError
        // field. The user can re-trigger webhook registration or set it up manually.
        let webhookSetupError: string | undefined;

        // Skip creation if a webhook ID is already recorded (re-add guard).
        if (!result.github_webhook_id) {
            const webhookUrl = `${process.env.AUTOFIX_API_BASE_URL}/webhooks/github`;
            const webhookSecret = process.env.GITHUB_WEBHOOK_SECRET!;

            try {
                const webhook = await createGithubWebhook(
                    accessToken,
                    owner,
                    name,
                    webhookUrl,
                    webhookSecret,
                );

                // Persist the GitHub-assigned webhook ID for lifecycle management.
                await updateRepoWebhookId(result.id, webhook.id);
                result.github_webhook_id = webhook.id;

                console.log(
                    `[webhook-setup] Registered webhook id=${webhook.id} on ${owner}/${name} for repo ${result.id}`,
                );
            } catch (err) {
                console.error(
                    `[webhook-setup] Failed to register GitHub webhook for ${owner}/${name}:`,
                    err,
                );
                webhookSetupError =
                    "Repository connected, but automatic webhook registration failed. " +
                    "Ensure Autofix has admin access to the repository on GitHub " +
                    "(requires the admin:repo_hook permission). " +
                    "Without a webhook, GitHub Issues and CI failures will not be ingested automatically.";
            }
        }

        return res.status(201).json({
            message: "Successfully added repository",
            result,
            ...(webhookSetupError ? { webhookSetupError } : {}),
        });
    } catch (err) {
        console.error("Error while creating repo", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

const deleteRepo = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }

        const repoId = req.params.id;
        if (!repoId || typeof repoId !== "string") {
            return res
                .status(400)
                .json({ message: "Invalid or missing repository ID" });
        }

        // Fetch repo details first so we have the webhook ID and repo name/owner
        // available for cleanup before the row is deleted.
        const repoDetails = await getRepoDetailsById(repoId, userId);
        if (!repoDetails) {
            return res.status(404).json({
                message: "Repository not found",
            });
        }

        // ── Best-effort webhook cleanup ────────────────────────────────────────
        // Delete the GitHub webhook before removing the DB row. If this fails
        // (e.g. webhook was already deleted on GitHub, or token lacks permission),
        // we log the error and continue — repo deletion always proceeds.
        if (repoDetails.github_webhook_id) {
            try {
                const accessToken = await getUserGithubAccessToken(userId);
                await deleteGithubWebhook(
                    accessToken,
                    repoDetails.owner,
                    repoDetails.name,
                    repoDetails.github_webhook_id,
                );
                console.log(
                    `[webhook-cleanup] Deleted webhook id=${repoDetails.github_webhook_id} from ${repoDetails.owner}/${repoDetails.name}`,
                );
            } catch (err) {
                console.error(
                    `[webhook-cleanup] Failed to delete webhook id=${repoDetails.github_webhook_id} from ${repoDetails.owner}/${repoDetails.name}:`,
                    err,
                );
                // Non-fatal — continue with repo deletion regardless.
            }
        }

        // ── Remove DB record ───────────────────────────────────────────────────
        const result = await deleteRepoById(repoId, userId);
        if (!result) {
            return res.status(404).json({
                message: "Repository not found",
            });
        }
        return res.status(200).json({
            message: "Successfully removed repository",
            result,
        });
    } catch (err) {
        console.error("Error while removing repo", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

const getRepoSignals = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }

        const repoId = req.params.id;
        if (!repoId || typeof repoId !== "string") {
            return res.status(400).json({ message: "Invalid or missing repository ID" });
        }

        // Verify the repo exists and belongs to this user before fetching signals
        const repo = await getRepoDetailsById(repoId, userId);
        if (!repo) {
            return res.status(404).json({ message: "Repository not found" });
        }

        const signals = await getSignalsByRepoId(repoId, userId);
        return res.status(200).json(signals);
    } catch (err) {
        console.error("Error while fetching repo signals", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

/**
 * POST /repositories/:id/signals/:signalId/fix
 *
 * Queues a fix job for the signal. The Python agent polls fix_jobs for
 * status = 'queued' and runs the pipeline (reindex → localize → generate →
 * validate → open PR) on its own; this endpoint only creates the row.
 *
 *   201 — job queued
 *   404 — signal not found in this user's repository
 *   409 — signal already has a non-failed job (queued, running, or PR opened)
 */
const fixSignal = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }

        const repoId = req.params.id;
        const signalId = req.params.signalId;
        if (!repoId || typeof repoId !== "string" || !signalId || typeof signalId !== "string") {
            return res.status(400).json({ message: "Invalid or missing repository or signal ID" });
        }

        const result = await createFixJobForSignal(repoId, signalId, userId);

        if (result.kind === "signal_not_found") {
            return res.status(404).json({ message: "Signal not found" });
        }
        if (result.kind === "already_active") {
            return res.status(409).json({
                message: `A fix job for this signal already exists (status: ${result.jobStatus})`,
                jobId: result.jobId,
                jobStatus: result.jobStatus,
            });
        }

        return res.status(201).json({ message: "Fix job queued", job: result.job });
    } catch (err: any) {
        // Lost a race against a concurrent request (fix_jobs_one_active_per_signal)
        if (err?.code === "23505") {
            return res.status(409).json({ message: "A fix job for this signal already exists" });
        }
        // Malformed UUID in the path
        if (err?.code === "22P02") {
            return res.status(404).json({ message: "Signal not found" });
        }
        console.error("Error while queuing fix job", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

/** Validated `:id` and `:signalId` path params, or null after sending a 400. */
function signalParams(req: AuthRequest, res: express.Response) {
    const repoId = req.params.id;
    const signalId = req.params.signalId;
    if (!repoId || typeof repoId !== "string" || !signalId || typeof signalId !== "string") {
        res.status(400).json({ message: "Invalid or missing repository or signal ID" });
        return null;
    }
    return { repoId, signalId };
}

/**
 * GET /repositories/:id/signals/:signalId
 *
 * The signal plus every fix run for it (newest first): progress timeline,
 * suspected code locations, each patch attempt with its outcome, and PR.
 */
const getSignalDetail = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }
        const params = signalParams(req, res);
        if (!params) return;

        const signal = await getSignalForUser(params.repoId, params.signalId, userId);
        if (!signal) {
            return res.status(404).json({ message: "Signal not found" });
        }

        const runs = await getFixRunsForSignal(params.signalId);
        return res.status(200).json({ signal, runs });
    } catch (err: any) {
        // Malformed UUID in the path
        if (err?.code === "22P02") {
            return res.status(404).json({ message: "Signal not found" });
        }
        console.error("Error while fetching signal detail", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

const STREAM_POLL_MS = 1_000;
const STREAM_KEEPALIVE_MS = 25_000;

/**
 * GET /repositories/:id/signals/:signalId/stream (Server-Sent Events)
 *
 * The agent only writes to the database, so this endpoint watches job_events
 * and fix_jobs for the signal and pushes changes to the page:
 *   event: progress — one new timeline event (`id:` is its cursor, so a
 *                     reconnecting EventSource resumes via Last-Event-ID)
 *   event: run      — a fix run was created or changed status; the client
 *                     refetches the detail for patches, outcome and PR.
 * Resumes after `?after=<cursor>` (the last event the page already has).
 */
const streamSignalProgress = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not Authorized" });
        }
        const params = signalParams(req, res);
        if (!params) return;

        const signal = await getSignalForUser(params.repoId, params.signalId, userId);
        if (!signal) {
            return res.status(404).json({ message: "Signal not found" });
        }

        res.setHeader("Content-Type", "text/event-stream");
        res.setHeader("Cache-Control", "no-cache");
        res.setHeader("Connection", "keep-alive");
        res.flushHeaders();

        const lastEventId = req.headers["last-event-id"];
        const after = req.query.after;
        let cursor: string | null =
            (typeof lastEventId === "string" && lastEventId) ||
            (typeof after === "string" && after) ||
            null;
        let runsSnapshot: string | null = null;
        let closed = false;
        let busy = false;

        const tick = async () => {
            if (closed || busy) return;
            busy = true;
            try {
                const events = await getSignalEventsAfter(params.signalId, cursor);
                for (const event of events) {
                    cursor = event.cursor;
                    res.write(`id: ${event.cursor}\nevent: progress\ndata: ${JSON.stringify(event)}\n\n`);
                }

                const runs = JSON.stringify(await getFixRunStates(params.signalId));
                if (runsSnapshot !== null && runs !== runsSnapshot) {
                    res.write(`event: run\ndata: ${runs}\n\n`);
                }
                runsSnapshot = runs;
            } catch (err: any) {
                // A malformed client-supplied cursor: start over (the client dedupes by event id)
                if (err?.code === "22007" || err?.code === "22008") {
                    cursor = null;
                } else {
                    console.error("[signal-stream] Failed to poll progress", err);
                }
            } finally {
                busy = false;
            }
        };

        await tick();
        const poll = setInterval(tick, STREAM_POLL_MS);
        const keepAlive = setInterval(() => {
            if (!closed) res.write(": ping\n\n");
        }, STREAM_KEEPALIVE_MS);

        req.on("close", () => {
            closed = true;
            clearInterval(poll);
            clearInterval(keepAlive);
        });
    } catch (err: any) {
        if (res.headersSent) {
            res.end();
            return;
        }
        if (err?.code === "22P02") {
            return res.status(404).json({ message: "Signal not found" });
        }
        console.error("Error while opening signal progress stream", err);
        return res.status(500).json({ error: "Internal server error" });
    }
};

export {
    getAllRepos,
    getRepoDetails,
    createRepository,
    deleteRepo,
    getRepoSignals,
    fixSignal,
    getSignalDetail,
    streamSignalProgress,
};
