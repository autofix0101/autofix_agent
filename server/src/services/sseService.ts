import type { Response } from "express";

/**
 * Data broadcast to the client when a new webhook signal is ingested.
 * The client uses `repoId` to identify which repo card to highlight.
 */
export interface SignalBroadcast {
    repoId: string;
    signalId: string;
    type: "github_issue" | "ci_failure";
    title: string;
}

/**
 * SseService manages Server-Sent Event (SSE) client connections keyed by
 * the internal user ID. When a webhook signal arrives, `broadcast` pushes
 * a lightweight JSON event to every browser tab the user has open.
 *
 * This is intentionally in-process and in-memory; for a multi-process or
 * multi-node deployment you would replace this with a pub/sub layer (e.g.
 * Redis pub/sub), but it is sufficient for a single-server setup.
 */
class SseService {
    /** userId → set of currently-open SSE response streams */
    private readonly clients = new Map<string, Set<Response>>();

    /**
     * Register a new SSE client response for the given user.
     * Automatically cleans up when the connection closes.
     */
    register(userId: string, res: Response): void {
        if (!this.clients.has(userId)) {
            this.clients.set(userId, new Set());
        }
        this.clients.get(userId)!.add(res);

        res.on("close", () => {
            this.unregister(userId, res);
        });
    }

    private unregister(userId: string, res: Response): void {
        const set = this.clients.get(userId);
        if (!set) return;
        set.delete(res);
        if (set.size === 0) this.clients.delete(userId);
    }

    /**
     * Push a signal event to all open SSE connections for the given user.
     * Silently swallows write errors and removes broken connections.
     */
    broadcast(userId: string, data: SignalBroadcast): void {
        const clients = this.clients.get(userId);
        if (!clients || clients.size === 0) return;

        const payload = `data: ${JSON.stringify(data)}\n\n`;
        for (const res of clients) {
            try {
                res.write(payload);
            } catch {
                // Connection broken — clean it up
                this.unregister(userId, res);
            }
        }
    }
}

/** Singleton instance shared across the application */
export const sseService = new SseService();
