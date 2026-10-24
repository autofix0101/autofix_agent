"""
Agent Loop for Patch Generation.

Drives the multi-turn tool-calling loop:
1. Feeds bug signal and localized code candidates into prompt.
2. Lets LLM use tools (read_file, search_code, get_related_tests).
3. Intercepts propose_patch or parses structured JSON diff.
4. Writes patch record to PostgreSQL `patches` table.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .. import db
from ..signals.issue_preprocessor import PreprocessedSignal
from ..utils.logging import get_logger
from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT, RETRY_PROMPT_TEMPLATE
from .tools import TOOL_DEFINITIONS, RepoToolExecutor, create_unified_diff

logger = get_logger("generation.agent_loop")


async def run_generation_loop(
    job_id: int | str,
    repo_path: str,
    signal: PreprocessedSignal,
    candidates: list[dict[str, Any]],
    attempt_number: int = 1,
    previous_validation_log: str | None = None,
    max_turns: int = 6,
) -> dict[str, Any]:
    """
    Run generation stage and persist candidate fix to patches table.

    Returns dict:
      {"patch_id": int, "diff_content": str, "explanation": str, "file_path": str}
    """
    executor = RepoToolExecutor(repo_path)
    client = LLMClient()

    # Build context from localization candidates
    candidate_context_blocks = []
    for c in candidates[:3]:
        candidate_context_blocks.append(
            f"Candidate #{c.get('rank', 1)} ({c.get('method', 'search')}, score {c.get('score', 0):.2f}):\n"
            f"File: {c['file_path']} (lines {c.get('start_line', 1)}-{c.get('end_line', 1)})\n"
            f"Snippet:\n{c.get('content', '')[:600]}\n"
        )
    candidate_summary = "\n".join(candidate_context_blocks)

    user_instructions = f"""A bug was reported in the repository.

Bug Signal Summary:
- Title: {signal.title}
- Search Query: {signal.search_query}
"""
    if signal.stack_trace:
        user_instructions += f"\nStack Trace:\n{signal.stack_trace.raw_trace[:800]}\n"
    else:
        user_instructions += f"\nDescription:\n{signal.cleaned_text[:600]}\n"

    user_instructions += f"""
Top Localized Code Candidates:
{candidate_summary}

Please inspect the code using your tools, identify the bug, and propose a surgical fix using `propose_patch`.
"""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_instructions},
    ]

    if previous_validation_log:
        messages.append({
            "role": "user",
            "content": RETRY_PROMPT_TEMPLATE.format(validation_log=previous_validation_log),
        })

    proposed_patch = None

    for turn in range(max_turns):
        logger.debug("Running generation turn %d/%d for job %s", turn + 1, max_turns, job_id)
        try:
            resp = await client.call_with_tools(messages, TOOL_DEFINITIONS)
        except Exception as e:
            logger.error("LLM call failed on turn %d: %s", turn + 1, e)
            break

        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if resp.get("content"):
            assistant_msg["content"] = resp["content"]

        tool_calls = resp.get("tool_calls", [])
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }
                for tc in tool_calls
            ]
            messages.append(assistant_msg)

            for tc in tool_calls:
                name = tc["name"]
                args = tc["arguments"]

                if name == "propose_patch":
                    proposed_patch = {
                        "file_path": args.get("file_path", ""),
                        "diff_content": args.get("diff_content", ""),
                        "explanation": args.get("explanation", "Automated fix proposed by LLM."),
                    }
                    tool_output = "Patch proposed and captured."
                else:
                    tool_output = executor.execute_tool_call(name, args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_output,
                })

            if proposed_patch:
                break
        else:
            messages.append(assistant_msg)
            # Check if LLM outputted raw diff in text content
            content = resp.get("content", "")
            if "--- a/" in content and "+++ b/" in content:
                match = re.search(r"(--- a/.*?\n\+\+\+ b/.*?\n@@.*)", content, re.DOTALL)
                if match:
                    diff_text = match.group(1).split("```")[0].strip()
                    top_file = candidates[0]["file_path"] if candidates else "target_file"
                    proposed_patch = {
                        "file_path": top_file,
                        "diff_content": diff_text,
                        "explanation": content.split("--- a/")[0].strip() or "Fix generated directly.",
                    }
                    break

    # If no patch produced by tool calls, generate minimal default from first candidate
    if not proposed_patch:
        top_file = candidates[0]["file_path"] if candidates else "unknown"
        logger.warning("No patch proposed during agent turns; constructing empty patch.")
        proposed_patch = {
            "file_path": top_file,
            "diff_content": "",
            "explanation": "Agent was unable to synthesize a clean patch.",
        }

    # Write patch to patches table
    patch_id = await db.insert_patch(
        job_id=job_id,
        attempt_number=attempt_number,
        diff_content=proposed_patch["diff_content"],
        explanation=proposed_patch["explanation"],
        validation_passed=False,
    )

    logger.info("Inserted patch #%s for job %s (attempt %d)", patch_id, job_id, attempt_number)
    return {
        "patch_id": patch_id,
        "diff_content": proposed_patch["diff_content"],
        "explanation": proposed_patch["explanation"],
        "file_path": proposed_patch["file_path"],
    }
