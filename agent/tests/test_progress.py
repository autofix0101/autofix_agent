"""
Unit tests for user-facing progress messages.
"""
import unittest

from autofix_agent.progress import describe_tool_call, describe_validation_failure, scrub


class TestProgress(unittest.TestCase):

    def test_scrub_removes_url_credentials(self):
        text = "fatal: could not read https://x-access-token:gho_secret@github.com/a/b.git"
        self.assertEqual(scrub(text), "fatal: could not read https://github.com/a/b.git")
        self.assertEqual(scrub("see https://github.com/a/b/pull/3"), "see https://github.com/a/b/pull/3")

    def test_describe_tool_call(self):
        self.assertEqual(
            describe_tool_call("read_file", {"file_path": "src/app.py", "start_line": 10, "end_line": 40}),
            "Reading `src/app.py` (lines 10–40)",
        )
        self.assertEqual(describe_tool_call("search_code", {"query": "createNote"}), "Searching the code for “createNote”")
        self.assertEqual(describe_tool_call("list_files", {}), "Looking at how the project is organised")
        self.assertIsNone(describe_tool_call("propose_patch", {}))

    def test_describe_validation_failure(self):
        self.assertIn("couldn't be applied", describe_validation_failure("Patch apply failed:\nhunk 1 rejected"))
        self.assertIn("TypeScript", describe_validation_failure("[.] TypeScript type-check FAILED — errors"))
        self.assertIn("tests failed", describe_validation_failure("=== 2 failed, 3 passed ==="))


if __name__ == "__main__":
    unittest.main()
