import express from "express";
import type { AuthRequest } from "../middleware/auth.js";
import {
    addRepository,
    deleteRepoById,
    getAllUserRepos,
    getRepoDetailsById,
} from "../db/queries/repoQueries.js";
import { getUserGithubAccessToken } from "../db/queries/userQueries.js";

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

        //getting the last commit sha
        const accessToken = await getUserGithubAccessToken(userId);
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

        return res.status(201).json({
            message: "Successfully added repository",
            result,
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
