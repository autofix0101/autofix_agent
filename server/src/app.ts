import "dotenv/config";

import express from "express";
import cookieParser from "cookie-parser";
import authRoutes from "./routes/authRoutes.js";
import githubRepoRoutes from "./routes/githubRepoRoutes.js";
import repoRoutes from "./routes/repoRoutes.js";
import webhookRoutes from "./routes/webhookRoutes.js";
import { isLoggedIn } from "./middleware/auth.js";
import type { AuthRequest } from "./middleware/auth.js";
import { sseService } from "./services/sseService.js";

const app = express();

// ── Webhook routes ────────────────────────────────────────────────────────────
// Mounted BEFORE express.json() so that the raw body Buffer is preserved for
// HMAC-SHA256 signature verification. The webhook route applies express.raw()
// locally; express.json() below does not affect it.
app.use("/webhooks", webhookRoutes);

// ── Global middleware ─────────────────────────────────────────────────────────
app.use(express.json());
app.use(cookieParser());

app.get("/home", (req, res) => {
    res.send("Hi");
});

// ── SSE stream endpoint ───────────────────────────────────────────────────────
// Clients subscribe here to receive real-time signal notifications.
// Requires authentication; each connection is keyed by user ID.
app.get("/signals/stream", isLoggedIn, (req: AuthRequest, res) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("Access-Control-Allow-Origin", req.headers.origin ?? "*");
    res.setHeader("Access-Control-Allow-Credentials", "true");
    res.flushHeaders();

    const userId = req.userId!;
    sseService.register(userId, res);

    // Send a keep-alive comment every 25 s to prevent idle timeouts
    const keepAlive = setInterval(() => {
        try {
            res.write(": ping\n\n");
        } catch {
            clearInterval(keepAlive);
        }
    }, 25_000);

    res.on("close", () => {
        clearInterval(keepAlive);
    });
});

app.use("/auth", authRoutes);
app.use("/githubrepos", githubRepoRoutes);
app.use("/repositories", repoRoutes);

app.listen(3000, () => {
    console.log("Server running on 3000");
});
