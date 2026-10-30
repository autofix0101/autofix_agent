"""
Unit tests for PR delivery (branch naming, PR text, commit + push to a branch).
"""
import os
import shutil
import tempfile
import unittest

from autofix_agent.delivery.pull_request import (
    PullRequestError,
    build_branch_name,
    build_pr_text,
    commit_and_push_branch,
)
from autofix_agent.utils.git_utils import run_git

JOB_ID = "1a2b3c4d-0000-0000-0000-000000000000"

DIFF = """--- a/math_utils.py
+++ b/math_utils.py
@@ -1,2 +1,4 @@
 def divide(a, b):
+    if b == 0:
+        return None
     return a / b
"""


class TestPrText(unittest.TestCase):

    def test_branch_name_issue(self):
        signal = {"type": "github_issue", "source_ref": "42"}
        self.assertEqual(build_branch_name(JOB_ID, signal), "autofix/issue-42-1a2b3c4d")

    def test_branch_name_ci(self):
        signal = {"type": "ci_failure", "source_ref": "987654"}
        self.assertEqual(build_branch_name(JOB_ID, signal), "autofix/ci-987654-1a2b3c4d")

    def test_branch_name_sanitizes_and_falls_back(self):
        self.assertEqual(build_branch_name(JOB_ID, None), "autofix/job-1a2b3c4d")
        signal = {"type": "github_issue", "source_ref": "a b:c"}
        self.assertEqual(build_branch_name(JOB_ID, signal), "autofix/issue-a-b-c-1a2b3c4d")

    def test_issue_pr_text_links_issue(self):
        signal = {
            "type": "github_issue",
            "source_ref": "42",
            "parsed_data": '{"title": "Crash on divide", "number": 42}',
        }
        patch = {"attempt_number": 2, "explanation": "Guard zero divisor.", "validation_log": "1 passed"}
        title, body = build_pr_text(JOB_ID, signal, patch)
        self.assertEqual(title, "fix: Crash on divide")
        self.assertTrue(body.startswith("Fixes #42"))
        self.assertIn("Guard zero divisor.", body)
        self.assertIn("attempt 2", body)


class TestCommitAndPush(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="test_pr_")
        self.remote = os.path.join(self.root, "remote.git")
        self.clone = os.path.join(self.root, "clone")
        run_git(["init", "--bare", "-b", "main", self.remote], check=True)

        seed = os.path.join(self.root, "seed")
        run_git(["clone", self.remote, seed], check=True)
        with open(os.path.join(seed, "math_utils.py"), "w") as f:
            f.write("def divide(a, b):\n    return a / b\n")
        run_git(["add", "."], cwd=seed, check=True)
        run_git(["-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "init"], cwd=seed, check=True)
        run_git(["push", "origin", "HEAD:main"], cwd=seed, check=True)

        run_git(["clone", "--depth", "1", "--branch", "main", f"file://{self.remote}", self.clone], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_pushes_branch_with_patch(self):
        commit_and_push_branch(
            self.clone, "autofix/issue-1-abc", DIFF, "fix: divide", "octocat", "1+octocat@users.noreply.github.com",
        )
        code, out, _ = run_git(["show", "autofix/issue-1-abc:math_utils.py"], cwd=self.remote)
        self.assertEqual(code, 0)
        self.assertIn("if b == 0:", out)

        _, author, _ = run_git(["log", "-1", "--format=%an <%ae>", "autofix/issue-1-abc"], cwd=self.remote)
        self.assertEqual(author, "octocat <1+octocat@users.noreply.github.com>")

        # Default branch is untouched
        _, main_content, _ = run_git(["show", "main:math_utils.py"], cwd=self.remote)
        self.assertNotIn("if b == 0:", main_content)

    def test_rejects_patch_that_does_not_apply(self):
        bad = DIFF.replace("return a / b", "return a // b")
        with self.assertRaises(PullRequestError):
            commit_and_push_branch(self.clone, "autofix/bad", bad, "fix", "octocat", "o@x")
        code, _, _ = run_git(["rev-parse", "--verify", "autofix/bad"], cwd=self.remote)
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
