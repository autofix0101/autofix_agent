import express from "express";
import { getGithubRepos } from "../services/githubService.js";
import type { AuthRequest } from "../middleware/auth.js";
import { getUserGithubAccessToken } from "../db/queries/userQueries.js";

const fetchGithubRepo = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ message: "Not authenticated" });
        }

        const accessToken = await getUserGithubAccessToken(userId);
        const repos = await getGithubRepos(accessToken);
        return res.status(200).json({ repos });
    } catch (err) {
        console.error("Error while fetching repos from github", err);
        return res
            .status(500)
            .json({ message: "Failed to fetch github repositories" });
    }
};

export { fetchGithubRepo };
