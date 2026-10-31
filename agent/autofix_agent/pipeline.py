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

import asyncio
import json
from typing import Any, Callable

from . import db
from .config import settings
from .delivery import PullRequestError, create_pull_request_for_job
from .generation.agent_loop import run_generation_loop
from .indexing.indexer import run_indexing
from .localization.ranker import localize_and_rank
from .progress import describe_files, describe_validation_failure, report_progress
from .signals.issue_preprocessor import preprocess_signal_content
from .utils.git_utils import diff_changed_files
from .utils.logging import get_logger
from .validation.js_checks import JsValidator
from .validation.patch_apply import apply_patch
from .validation.sandbox import Sandbox
from .validation.test_runners import run_tests_in_directory

logger = get_logger("pipeline")


def _signal_title(signal_row: dict[str, Any] | None) -> str:
    """Human title of the signal: issue title / workflow name, not the issue number."""
    if not signal_row:
        return ""
    data = signal_row.get("parsed_data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    if signal_row.get("type") == "ci_failure":
        title = data.get("workflow_name") and f"CI failure in workflow '{data['workflow_name']}'"
    else:
        title = data.get("title")
    return title or str(signal_row.get("source_ref") or "")


_JS_TS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")


def _validate_patch(
    sandbox_source: str,
    diff_content: str,
    js_validator: JsValidator,
    on_step: Callable[[str], None] = lambda _: None,
) -> tuple[bool, str]:
    """Apply the patch in a throwaway sandbox and run every applicable check (blocking).

    on_step receives a user-facing description of each check as it starts.
    """
    with Sandbox(sandbox_source) as sandbox_path:
        on_step("Applying the change to a separate copy of your project.")
        apply_ok, apply_msg = apply_patch(sandbox_path, diff_content)
        if not apply_ok:
            return False, f"Patch apply failed:\n{apply_msg}"

        on_step("Checking the code still parses and running the project's tests.")
        test_ok, test_log = run_tests_in_directory(sandbox_path)
        if not test_ok:
            return False, test_log

        changed = diff_changed_files(diff_content)
        if any(f.endswith(_JS_TS_EXTENSIONS) for f in changed):
            on_step(
                "Type-checking and testing the JavaScript/TypeScript code "
                "(the first run installs dependencies, which can take a minute)."
            )
        js_ok, js_log = js_validator.validate(sandbox_path, changed)
        return js_ok, "\n\n".join(filter(None, [test_log, js_log]))


def _describe_locations(candidates: list[dict[str, Any]], limit: int = 3) -> str:
    """Distinct candidate files, best first, with the line range of their best chunk."""
    seen: dict[str, str] = {}
    for c in candidates:
        path = c["file_path"]
        if path not in seen:
            seen[path] = f"`{path}` (lines {c.get('start_line', 1)}–{c.get('end_line', 1)})"
        if len(seen) >= limit:
            break
    return ", ".join(seen.values())


async def run_pipeline(job: dict[str, Any]) -> None:
    """Execute all pipeline stages for a claimed fix_job."""
    job_id = str(job["id"])
    repo_id = str(job["repo_id"])
    signal_id = str(job["signal_id"]) if job.get("signal_id") else None

    logger.info(">>> Starting pipeline for Job #%s (Repo #%s)", job_id, repo_id)

    # Load signal (raw_content + parsed data)
    signal_row = await db.get_signal(signal_id) if signal_id else None
    raw_content = signal_row.get("raw_content", "") if signal_row else ""
    signal_title = _signal_title(signal_row)

    try:
        # ==================================================================
        # STAGE 1: REINDEXING
        # ==================================================================
        await db.update_job_status(job_id, status="reindexing")
        await report_progress(job_id, "reindexing", "Fetching the latest version of your code and updating the search index.")

        logger.info("[Job %s] ---> STAGE 1: Reindexing repository...", job_id)
        try:
            head_sha = await run_indexing(repo_id)
            logger.info("[Job %s] Indexing complete (HEAD=%s)", job_id, head_sha[:8])
            await report_progress(job_id, "reindexing", f"Code is up to date (latest commit {head_sha[:7]}).")
        except Exception as e:
            logger.warning("[Job %s] Indexing failed (continuing with existing index): %s", job_id, e)
            await report_progress(
                job_id, "reindexing",
                "Couldn't refresh the search index, so the last saved copy of your code will be used.",
            )

        # ==================================================================
        # STAGE 2: LOCALIZING
        # ==================================================================
        await db.update_job_status(job_id, status="localizing")
        await report_progress(job_id, "localizing", "Reading the report and searching your code for the parts most likely involved.")

        logger.info("[Job %s] ---> STAGE 2: Localizing bug signal...", job_id)
        preprocessed = preprocess_signal_content(raw_content, title=signal_title)
        if preprocessed.stack_trace and preprocessed.stack_trace.frames:
            await report_progress(
                job_id, "localizing",
                "The report includes an error trace, so we're following it to the code that failed.",
            )
        candidates = await localize_and_rank(repo_id, job_id, preprocessed, limit=10)

        if candidates:
            logger.info("[Job %s] Localization found %d candidate(s):", job_id, len(candidates))
            for c in candidates[:3]:
                logger.info(
                    "[Job %s]   Rank #%d: %s (lines %d-%d, score=%.2f, method=%s)",
                    job_id, c.get("rank", 1), c["file_path"], c.get("start_line", 1),
                    c.get("end_line", 1), c.get("score", 0), c.get("method", "unknown")
                )
            await report_progress(
                job_id, "localizing",
                f"Most likely places to look: {_describe_locations(candidates)}.",
            )
        else:
            logger.warning("[Job %s] No candidates found — using empty fallback", job_id)
            await report_progress(
                job_id, "localizing",
                "Couldn't pinpoint a likely location from the report; the AI will explore the code itself.",
            )

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
                    await report_progress(
                        job_id, "generating",
                        "Couldn't download a working copy of the repository, so fixes can't be tested properly.",
                    )
                else:
                    logger.info("[Job %s] Repo cloned successfully into sandbox %s", job_id, sandbox_source)
        except Exception as e:
            logger.warning("[Job %s] Could not clone repo for sandbox (%s); validation will skip test run.", job_id, e)

        js_validator = JsValidator(sandbox_source)
        # Retry context: either the last failed diff + its log, or the last no-patch explanation
        last_diff: str | None = None
        last_explanation: str | None = None

        while attempt <= max_attempts and not validation_passed:
            logger.info("[Job %s] ---> STAGE 3: Generating patch (attempt %d/%d)...", job_id, attempt, max_attempts)
            await db.update_job_status(job_id, status="generating", attempt_count=attempt)
            if attempt == 1:
                await report_progress(job_id, "generating", f"Attempt 1 of {max_attempts}: the AI is studying the problem and writing a fix.")
            else:
                await report_progress(
                    job_id, "generating",
                    f"Attempt {attempt} of {max_attempts}: trying again, taking into account what went wrong last time.",
                )

            patch_result = await run_generation_loop(
                job_id=job_id,
                repo_path=sandbox_source,
                signal=preprocessed,
                candidates=candidates,
                attempt_number=attempt,
                previous_validation_log=last_log if last_diff else None,
                previous_diff=last_diff,
                previous_explanation=last_explanation,
            )
            patch_id = patch_result["patch_id"]
            diff_content = patch_result["diff_content"]

            if not diff_content or not diff_content.strip():
                explanation = patch_result.get("explanation", "")
                if patch_result.get("no_fix"):
                    last_log = f"LLM concluded no code change is needed: {explanation}"
                    friendly = f"The AI concluded no code change is needed: {explanation[:300]}"
                else:
                    last_log = "LLM did not produce a patch."
                    friendly = "The AI couldn't come up with a fix on this attempt."
                logger.warning("[Job %s] No patch on attempt %d: %s", job_id, attempt, last_log[:200])
                await db.update_patch_validation(patch_id, False, last_log)
                await report_progress(job_id, "generating", friendly)
                last_diff, last_explanation = None, explanation
                attempt += 1
                continue

            logger.info(
                "[Job %s] Patch #%s proposed for %s: %s",
                job_id, patch_id, patch_result.get("file_path"), patch_result.get("explanation", "")[:80]
            )

            await report_progress(
                job_id, "generating",
                f"Proposed a change to {describe_files(diff_changed_files(diff_content))}.",
            )

            # Validate patch in sandbox
            logger.info("[Job %s] ---> STAGE 4: Validating patch #%s in sandbox...", job_id, patch_id)
            await db.update_job_status(job_id, status="validating")
            await report_progress(job_id, "validating", "Testing the proposed change before suggesting it.")

            # Blocking work (git, npm install, tsc, tests) — keep it off the event loop.
            # Step updates are recorded from the worker thread, in order.
            loop = asyncio.get_running_loop()

            def on_step(message: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    report_progress(job_id, "validating", message), loop
                ).result()

            validation_passed, last_log = await asyncio.to_thread(
                _validate_patch, sandbox_source, diff_content, js_validator, on_step,
            )
            last_diff, last_explanation = diff_content, None
            logger.info("[Job %s] Validation log:\n%s", job_id, (last_log or "")[:1500])

            await db.update_patch_validation(patch_id, validation_passed, last_log)

            if validation_passed:
                successful_patch_id = patch_id
                await report_progress(job_id, "validating", "The change passed all checks.")
                logger.info("[Job %s] [PASSED] Patch #%s PASSED validation on attempt %d!", job_id, patch_id, attempt)
                break
            else:
                logger.warning("[Job %s] [FAILED] Patch #%s FAILED validation on attempt %d: %s", job_id, patch_id, attempt, (last_log or '')[:120])
                await report_progress(
                    job_id, "validating",
                    f"Attempt {attempt} didn't pass: {describe_validation_failure(last_log)}",
                )
                attempt += 1

        try:
            # ==================================================================
            # STAGE 5: FINALIZATION
            # ==================================================================
            if validation_passed and successful_patch_id:
                await db.update_job_status(job_id, status="awaiting_approval")
                await report_progress(job_id, "awaiting_approval", "Opening a pull request on GitHub with the fix.")
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
                    await report_progress(
                        job_id, "pr_failed",
                        "The fix passed all checks, but the pull request couldn't be opened on GitHub. "
                        "Logging in again to refresh GitHub permissions usually fixes this.",
                    )
                else:
                    if pr_url:
                        await report_progress(job_id, "pr_created", f"Pull request opened: {pr_url}")
                        logger.info(">>> Job %s complete → pr_created (%s)", job_id, pr_url)
                    else:
                        await report_progress(job_id, "awaiting_approval", "The fix is ready, but a pull request wasn't opened.")
            else:
                err = f"All {max_attempts} attempts failed. Last log:\n{(last_log or '')[:300]}"
                await db.update_job_status(job_id, status="failed", error_message=err[:500])
                await report_progress(
                    job_id, "failed",
                    f"Couldn't find a fix that passes all checks after {max_attempts} attempt(s).",
                )
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
        await report_progress(job_id, "failed", "Something went wrong on our side and the fix attempt stopped.")
        if signal_id:
            await db.update_signal_status(signal_id, "failed")
