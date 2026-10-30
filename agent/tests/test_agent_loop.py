"""
Unit tests for the generation loop's turn budget and forced final propose_patch.
"""
import os
import unittest
from unittest import mock

from autofix_agent.generation import agent_loop
from autofix_agent.signals.issue_preprocessor import preprocess_signal_content

FIXTURE_REPO = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")
DIFF = "--- a/math_utils.py\n+++ b/math_utils.py\n@@ -1 +1 @@\n-x\n+y\n"


class ExploringForeverLLM:
    """Mimics a model that keeps reading files unless forced to propose a patch."""

    def __init__(self, *args, **kwargs):
        self.calls = []

    async def call_with_tools(self, messages, tools, tool_choice="auto"):
        self.calls.append({"tool_choice": tool_choice, "last_message": messages[-1]["content"]})
        n = len(self.calls)
        if tool_choice != "auto":
            return {"content": None, "reasoning": None, "tool_calls": [{
                "id": f"c{n}", "name": "propose_patch",
                "arguments": {"file_path": "math_utils.py", "diff_content": DIFF, "explanation": "fix"},
            }]}
        return {"content": None, "reasoning": "need more context", "tool_calls": [{
            "id": f"c{n}", "name": "read_file", "arguments": {"file_path": "math_utils.py"},
        }]}


class TestGenerationLoop(unittest.IsolatedAsyncioTestCase):

    async def _run(self, **kwargs):
        llm = ExploringForeverLLM()
        with mock.patch.object(agent_loop, "LLMClient", return_value=llm), \
             mock.patch.object(agent_loop.db, "insert_patch", mock.AsyncMock(return_value="patch-1")):
            result = await agent_loop.run_generation_loop(
                job_id="job-1",
                repo_path=FIXTURE_REPO,
                signal=preprocess_signal_content("divide crashes", title="Crash"),
                candidates=[],
                max_turns=4,
                **kwargs,
            )
        return llm, result

    async def test_final_turn_forces_propose_patch(self):
        llm, result = await self._run()
        self.assertEqual(len(llm.calls), 4)
        self.assertEqual([c["tool_choice"] for c in llm.calls[:3]], ["auto"] * 3)
        self.assertEqual(llm.calls[3]["tool_choice"]["function"]["name"], "propose_patch")
        self.assertEqual(result["diff_content"], DIFF)
        self.assertFalse(result["no_fix"])

    async def test_every_turn_carries_budget_note(self):
        llm, _ = await self._run()
        self.assertIn("[Turn 1/4]", llm.calls[0]["last_message"])
        self.assertIn("[Turn 3/4]", llm.calls[2]["last_message"])
        self.assertIn("[Final turn]", llm.calls[3]["last_message"])

    async def test_retry_after_failed_validation_includes_previous_diff(self):
        with mock.patch.object(agent_loop, "LLMClient") as cls:
            llm = ExploringForeverLLM()
            cls.return_value = llm
            seen = []

            async def capture(messages, tools, tool_choice="auto"):
                seen.extend(m.get("content") or "" for m in messages)
                return await ExploringForeverLLM.call_with_tools(llm, messages, tools, "forced")

            llm.call_with_tools = capture
            with mock.patch.object(agent_loop.db, "insert_patch", mock.AsyncMock(return_value="p")):
                await agent_loop.run_generation_loop(
                    job_id="job-1", repo_path=FIXTURE_REPO,
                    signal=preprocess_signal_content("bug", title="Bug"), candidates=[],
                    previous_diff=DIFF, previous_validation_log="TS2304: Cannot find name 'x'",
                    max_turns=2,
                )
        joined = "\n".join(seen)
        self.assertIn("TS2304", joined)
        self.assertIn("+++ b/math_utils.py", joined)


if __name__ == "__main__":
    unittest.main()
