import { Router } from "express";
import express from "express";
import { handleGithubWebhook } from "../controllers/webhookController.js";

const router = Router();

/**
 * POST /webhooks/github
 *
 * GitHub webhook receiver for issues and workflow_run events.
 *
 * express.raw() is applied per-route (not globally) so the raw Buffer body
 * is available for HMAC signature verification before JSON parsing.
 * This route is intentionally mounted in app.ts BEFORE app.use(express.json())
 * to prevent the global JSON middleware from consuming the body stream first.
 *
 * No authentication middleware — the endpoint is public but secured by
 * HMAC-SHA256 verification using GITHUB_WEBHOOK_SECRET.
 */
router.post(
    "/github",
    express.raw({ type: "application/json" }),
    handleGithubWebhook,
);

export default router;
