import express from "express";
import {
    getGithubAccessToken,
    getGithubAuthUrl,
    getGithubUser,
} from "../services/githubService.js";
import {
    createUser,
    findUserByGithubId,
    findUserById,
    updateGithubAccessToken,
} from "../db/queries/userQueries.js";
import { generateToken } from "../utils/jwt.js";
import type { AuthRequest } from "../middleware/auth.js";

const githubLogin = (req: express.Request, res: express.Response) => {
    const authUrl = getGithubAuthUrl();
    res.redirect(authUrl);
};

const setAuthCookie = (res: express.Response, userId: string) => {
    const auth_token = generateToken(userId);
    res.cookie("token", auth_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        maxAge: 1000 * 60 * 60 * 24, // 1 day
    });
};

//for both register and login
const githubCallback = async (req: express.Request, res: express.Response) => {
    try {
        const { code } = req.query;

        if (!code || typeof code !== "string") {
            return res.status(400).json({
                message: "Authorization code missing",
            });
        }

        const accessToken = await getGithubAccessToken(code);

        const githubUser = await getGithubUser(accessToken);

        const githubId = githubUser.id;
        const githubUsername = githubUser.login;
        const avatar_url = githubUser.avatar_url;
        const email = githubUser.email;

        const existingUser = await findUserByGithubId(githubId);

        let user;
        if (existingUser) {
            user = await updateGithubAccessToken(githubId, accessToken);
        } else {
            user = await createUser(
                githubId,
                githubUsername,
                email,
                avatar_url,
                accessToken,
            );
        }

        setAuthCookie(res, user.id);

        return res.redirect("http://localhost:3000/auth/me"); //redirect to be changed later
    } catch (err) {
        console.error("Github oauth error", err);
        return res.status(500).json({
            message: "Github authentication failed",
        });
    }
};

const getUserDetails = async (req: AuthRequest, res: express.Response) => {
    try {
        const userId = req.userId;
        if (!userId) {
            return res.status(401).json({ error: "Not Authenticated" });
        }

        const user = await findUserById(userId);
        if (!user) {
            return res.status(404).json({
                error: "User not found",
            });
        }

        return res.status(200).json({ user });
    } catch (err) {
        console.error("Error while getting user details", err);
        return res.status(500).json({ message: "Internal server error" });
    }
};

const logoutUser = (req: AuthRequest, res: express.Response) => {
    res.clearCookie("token", {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
    });
    return res.status(200).json({ message: "Logged out successfully" });
};

export { githubLogin, githubCallback, getUserDetails, logoutUser };
