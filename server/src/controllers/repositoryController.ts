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

export { getAllRepos, getRepoDetails, createRepository, deleteRepo };
