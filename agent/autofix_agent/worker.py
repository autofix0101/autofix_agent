"""
Worker Entrypoint for AutoFix Agent.

Runs the continuous worker loop:
1. Polls for queued fix jobs via `claim_next_job()`.
2. Executes `run_pipeline(job)`.
3. Handles graceful shutdown on SIGINT/SIGTERM.
"""
from __future__ import annotations

import asyncio
import signal
import sys

from . import db
from .config import settings
from .pipeline import run_pipeline
from .utils.logging import get_logger, setup_logger

logger = get_logger("worker")

_stop_requested = False


def _signal_handler(sig, frame):
    global _stop_requested
    logger.info("Termination signal received. Shutting down worker gracefully...")
    _stop_requested = True


async def start_worker() -> None:
    """Run the worker loop."""
    logger.info("AutoFix Agent Worker started. Polling interval: %.1fs", settings.WORKER_POLL_INTERVAL)

    try:
        while not _stop_requested:
            try:
                job = await db.claim_next_job()
                if job:
                    logger.info("Claimed job #%s for repo #%s. Executing pipeline...", job["id"], job["repo_id"])
                    await run_pipeline(job)
                else:
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in worker polling loop: %s", e)
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL)

    finally:
        logger.info("Closing database connection pool...")
        await db.close_pool()
        logger.info("AutoFix Agent Worker stopped.")


def main():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    try:
        asyncio.run(start_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
