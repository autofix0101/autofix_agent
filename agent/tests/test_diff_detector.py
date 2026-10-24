"""
Unit tests for Diff Detector (Incremental Indexing scalability piece).
"""
import os
import shutil
import tempfile
import unittest

from autofix_agent.indexing.diff_detector import detect_changed_files
from autofix_agent.utils.git_utils import run_git, get_head_sha


class TestDiffDetector(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_repo_")
        # Initialize test git repo
        run_git(["init", "-b", "main"], cwd=self.temp_dir, check=True)
        run_git(["config", "user.name", "Tester"], cwd=self.temp_dir, check=True)
        run_git(["config", "user.email", "tester@test.com"], cwd=self.temp_dir, check=True)

        # Commit 1
        with open(os.path.join(self.temp_dir, "file1.py"), "w") as f:
            f.write("def foo(): pass\n")
        with open(os.path.join(self.temp_dir, "file2.py"), "w") as f:
            f.write("def bar(): pass\n")

        run_git(["add", "."], cwd=self.temp_dir, check=True)
        run_git(["commit", "-m", "Initial commit"], cwd=self.temp_dir, check=True)
        self.sha1 = get_head_sha(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_incremental_changes_detected(self):
        # Modify file1, delete file2, add file3
        with open(os.path.join(self.temp_dir, "file1.py"), "w") as f:
            f.write("def foo(): return 42\n")
        os.remove(os.path.join(self.temp_dir, "file2.py"))
        with open(os.path.join(self.temp_dir, "file3.py"), "w") as f:
            f.write("def baz(): pass\n")

        run_git(["add", "-A"], cwd=self.temp_dir, check=True)
        run_git(["commit", "-m", "Second commit"], cwd=self.temp_dir, check=True)
        sha2 = get_head_sha(self.temp_dir)

        changes = detect_changed_files(self.temp_dir, self.sha1, sha2)
        self.assertIn("file3.py", changes.added)
        self.assertIn("file1.py", changes.modified)
        self.assertIn("file2.py", changes.deleted)

    def test_no_changes(self):
        changes = detect_changed_files(self.temp_dir, self.sha1, self.sha1)
        self.assertTrue(changes.is_empty)


if __name__ == "__main__":
    unittest.main()
