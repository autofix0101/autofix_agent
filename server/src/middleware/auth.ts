import express from "express";
import { verifyToken } from "../utils/jwt.js";

export interface AuthRequest extends express.Request {
    userId?: string;
}

export function isLoggedIn(
    req: AuthRequest,
    res: express.Response,
    next: express.NextFunction,
) {
    try {
        const token = req.cookies.token;
        if (!token) {
            return res.status(401).json({ error: "Not Authenticated" });
        }
        const decoded = verifyToken(token);

        if (typeof decoded === "string" || !decoded.userId) {
            return res.status(401).json({ error: "Invalid token" });
        }

        req.userId = decoded.userId;
        next();
    } catch (err) {
        return res.status(401).json({
            error: "Invalid or expired token",
        });
    }
}
