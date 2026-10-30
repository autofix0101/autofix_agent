"""
AutoFix Pipeline Orchestrator.

Stages per fix_job:
  1. reindexing  — GitHub pull + incremental re-index (only changed files)
  2. localizing  — stack trace direct match + pgvector similarity search
  3. generating  — LLM tool-calling loop produces unified git diff
  4. validating  — apply patch in sandbox clone, run test suite
  5. retry       — up to MAX_VALIDATION_ATTEMPTS on failure
  6. awaiting_approval — patch validated
  7. pr_created — patch pushed to a new branch and PR opened as the repo owner
"""
from __future__ import annotations

from typing import Any

from . import db
from .config import settings
from .delivery import PullRequestError, create_pull_request_for_job
from .generation.agent_loop import run_generation_loop
from .indexing.indexer import run_indexing
from .localization.ranker import localize_and_rank
from .signals.issue_preprocessor import preprocess_signal_content
from .utils.logging import get_logger
from .validation.patch_apply import apply_patch
from .validation.sandbox import Sandbox
from .validation.test_runners import run_tests_in_directory

logger = get_logger("pipeline")


async def run_pipeline(job: dict[str, Any]) -> None:
    """Execute all pipeline stages for a claimed fix_job."""
    job_id = str(job["id"])
    repo_id = str(job["repo_id"])
    signal_id = str(job["signal_id"]) if job.get("signal_id") else None

    logger.info(">>> Starting pipeline for Job #%s (Repo #%s)", job_id, repo_id)

    # Load signal (raw_content + parsed data)
    signal_row = await db.get_signal(signal_id) if signal_id else None
    raw_content = signal_row.get("raw_content", "") if signal_row else ""
    signal_title = signal_row.get("source_ref", "") if signal_row else ""

    try:
        # ==================================================================
        # STAGE 1: REINDEXING
        # ==================================================================
        await db.update_job_status(job_id, status="reindexing")
        await db.add_job_event(job_id, "reindexing", "Pulling latest code and running incremental re-index.")

        logger.info("[Job %s] ---> STAGE 1: Reindexing repository...", job_id)
        try:
            head_sha = await run_indexing(repo_id)
            logger.info("[Job %s] Indexing complete (HEAD=%s)", job_id, head_sha[:8])
            await db.add_job_event(job_id, "reindexing", f"Indexing complete. HEAD={head_sha[:8]}")
        except Exception as e:
            logger.warning("[Job %s] Indexing failed (continuing with existing index): %s", job_id, e)
            await db.add_job_event(job_id, "reindexing", f"Indexing skipped: {e}")

        # ==================================================================
        # STAGE 2: LOCALIZING
        # ==================================================================
        await db.update_job_status(job_id, status="localizing")
        await db.add_job_event(job_id, "localizing", "Analyzing bug signal and finding candidate code chunks.")

        logger.info("[Job %s] ---> STAGE 2: Localizing bug signal...", job_id)
        preprocessed = preprocess_signal_content(raw_content, title=signal_title)
        candidates = await localize_and_rank(repo_id, job_id, preprocessed, limit=10)

        if candidates:
            logger.info("[Job %s] Localization found %d candidate(s):", job_id, len(candidates))
            for c in candidates[:3]:
                logger.info(
                    "[Job %s]   Rank #%d: %s (lines %d-%d, score=%.2f, method=%s)",
                    job_id, c.get("rank", 1), c["file_path"], c.get("start_line", 1),
                    c.get("end_line", 1), c.get("score", 0), c.get("method", "unknown")
                )
            top = candidates[0]
            await db.add_job_event(
                job_id, "localizing",
                f"Top candidate: {top['file_path']} (score={top.get('score', 0):.2f}, method={top.get('method')})"
            )
        else:
            logger.warning("[Job %s] No candidates found — using empty fallback", job_id)
            await db.add_job_event(job_id, "localizing", "No localization candidates found.")

        # ==================================================================
        # STAGES 3 & 4: GENERATING + VALIDATING (with retry)
        # ==================================================================
        max_attempts = settings.MAX_VALIDATION_ATTEMPTS
        attempt = 1
        validation_passed = False
        last_log = None
        successful_patch_id = None

        # We need the repo local path for sandbox — try to clone url from DB
        repo_row = await db.get_repo_for_indexing(repo_id)
        clone_url = repo_row.get("clone_url", "") if repo_row else ""
        branch = repo_row.get("default_branch", "main") if repo_row else "main"
        token = repo_row.get("github_access_token", "") if repo_row else ""

        target_clone_url = clone_url
        if token and clone_url.startswith("https://"):
            target_clone_url = clone_url.replace("https://", f"https://x-access-token:{token}@")

        import os, tempfile
        sandbox_source = tempfile.mkdtemp(prefix="autofix_repo_")
        try:
            # Shallow clone for sandbox base
            import subprocess
            logger.info("[Job %s] Cloning repo for sandbox: %s (branch: %s)", job_id, clone_url, branch)
            if target_clone_url:
                proc = subprocess.run(
                    ["git", "clone", "--depth", "1", "--branch", branch, target_clone_url, sandbox_source],
                    capture_output=True, text=True
                )
                if proc.returncode != 0:
                    logger.warning("[Job %s] git clone failed (code %d): %s", job_id, proc.returncode, proc.stderr)
                else:
                    logger.info("[Job %s] Repo cloned successfully into sandbox %s", job_id, sandbox_source)
        except Exception as e:
            logger.warning("[Job %s] Could not clone repo for sandbox (%s); validation will skip test run.", job_id, e)

        while attempt <= max_attempts and not validation_passed:
            logger.info("[Job %s] ---> STAGE 3: Generating patch (attempt %d/%d)...", job_id, attempt, max_attempts)
            await db.update_job_status(job_id, status="generating", attempt_count=attempt)
            await db.add_job_event(job_id, "generating", f"LLM generating patch (attempt {attempt}/{max_attempts}).")

            patch_result = await run_generation_loop(
                job_id=job_id,
                repo_path=sandbox_source,
                signal=preprocessed,
                candidates=candidates,
                attempt_number=attempt,
                previous_validation_log=last_log,
            )
            patch_id = patch_result["patch_id"]
            diff_content = patch_result["diff_content"]

            if not diff_content or not diff_content.strip():
                last_log = "Error: Generated patch was empty."
                logger.warning("[Job %s] LLM produced an empty patch on attempt %d.", job_id, attempt)
                await db.update_patch_validation(patch_id, False, last_log)
                await db.add_job_event(
                    job_id, "generating",
                    f"Attempt {attempt} failed: LLM produced empty patch. {patch_result.get('explanation', '')[:100]}"
                )
                attempt += 1
                continue

            logger.info(
                "[Job %s] Patch #%s proposed for %s: %s",
                job_id, patch_id, patch_result.get("file_path"), patch_result.get("explanation", "")[:80]
            )

            # Validate patch in sandbox
            logger.info("[Job %s] ---> STAGE 4: Validating patch #%s in sandbox...", job_id, patch_id)
            await db.update_job_status(job_id, status="validating")
            await db.add_job_event(job_id, "validating", f"Testing patch #{patch_id} in isolated sandbox.")

            with Sandbox(sandbox_source) as sandbox_path:
                apply_ok, apply_msg = apply_patch(sandbox_path, diff_content)
                if not apply_ok:
                    validation_passed = False
                    last_log = f"Patch apply failed:\n{apply_msg}"
                    logger.warning("[Job %s] Patch apply failed in sandbox: %s", job_id, apply_msg)
                else:
                    test_ok, test_log = run_tests_in_directory(sandbox_path)
                    validation_passed = test_ok
                    last_log = test_log

            await db.update_patch_validation(patch_id, validation_passed, last_log)

            if validation_passed:
                successful_patch_id = patch_id
                logger.info("[Job %s] [PASSED] Patch #%s PASSED validation on attempt %d!", job_id, patch_id, attempt)
                break
            else:
                logger.warning("[Job %s] [FAILED] Patch #%s FAILED validation on attempt %d: %s", job_id, patch_id, attempt, (last_log or '')[:120])
                await db.add_job_event(
                    job_id, "validating",
                    f"Attempt {attempt} failed: {(last_log or '')[:150]}"
                )
                attempt += 1

        try:
            # ==================================================================
            # STAGE 5: FINALIZATION
            # ==================================================================
            if validation_passed and successful_patch_id:
                await db.update_job_status(job_id, status="awaiting_approval")
                await db.add_job_event(
                    job_id, "awaiting_approval",
                    f"Patch #{successful_patch_id} verified. Opening pull request."
                )
                logger.info(">>> Job %s validated → awaiting_approval", job_id)

                # ==============================================================
                # STAGE 6: PULL REQUEST
                # ==============================================================
                # sandbox_source is still a pristine clone of the default branch
                # (generation only reads it; validation ran on a copy).
                logger.info("[Job %s] ---> STAGE 6: Creating pull request...", job_id)
                try:
                    pr_url = await create_pull_request_for_job(
                        job_id=job_id,
                        patch_id=successful_patch_id,
                        repo_path=sandbox_source,
                        repo_row=repo_row or {},
                        signal_row=signal_row,
                    )
                except PullRequestError as e:
                    # Keep the job in awaiting_approval: the validated patch is still usable.
                    logger.error("[Job %s] Pull request creation failed: %s", job_id, e)
                    await db.update_job_status(
                        job_id, status="awaiting_approval",
                        error_message=f"PR creation failed: {e}"[:500],
                    )
                    await db.add_job_event(job_id, "pr_failed", f"PR creation failed: {str(e)[:250]}")
                else:
                    if pr_url:
                        await db.add_job_event(job_id, "pr_created", f"Pull request opened: {pr_url}")
                        logger.info(">>> Job %s complete → pr_created (%s)", job_id, pr_url)
                    else:
                        await db.add_job_event(job_id, "awaiting_approval", "PR preconditions not met; no PR opened.")
            else:
                err = f"All {max_attempts} attempts failed. Last log:\n{(last_log or '')[:300]}"
                await db.update_job_status(job_id, status="failed", error_message=err[:500])
                await db.add_job_event(job_id, "failed", err[:250])
                if signal_id:
                    await db.update_signal_status(signal_id, "failed")
                logger.error(">>> Job %s FAILED after %d attempts.", job_id, max_attempts)
        finally:
            # Cleanup temp clone
            import shutil
            shutil.rmtree(sandbox_source, ignore_errors=True)

    except Exception as e:
        logger.exception("[Job %s] Unhandled pipeline exception: %s", job_id, e)
        await db.update_job_status(job_id, status="failed", error_message=str(e)[:500])
        await db.add_job_event(job_id, "failed", f"Unhandled exception: {e}")
        if signal_id:
            await db.update_signal_status(signal_id, "failed")
