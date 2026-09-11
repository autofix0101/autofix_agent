import "dotenv/config";

import express from "express";
import cookieParser from "cookie-parser";
import authRoutes from "./routes/authRoutes.js";
import githubRepoRoutes from "./routes/githubRepoRoutes.js";
import repoRoutes from "./routes/repoRoutes.js";
import webhookRoutes from "./routes/webhookRoutes.js";

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

app.use("/auth", authRoutes);
app.use("/githubrepos", githubRepoRoutes);
app.use("/repositories", repoRoutes);

app.listen(3000, () => {
    console.log("Server running on 3000");
});
