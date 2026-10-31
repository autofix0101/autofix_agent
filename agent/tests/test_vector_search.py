"""
Unit tests for Vector Search and Localization Ranker.
"""
import unittest
from unittest.mock import AsyncMock, patch

from autofix_agent.localization.ranker import is_test_path, localize_and_rank
from autofix_agent.signals.issue_preprocessor import preprocess_signal_content


class TestVectorSearchAndRanker(unittest.TestCase):

    @patch("autofix_agent.db.insert_localization_candidates", new_callable=AsyncMock)
    @patch("autofix_agent.localization.ranker.search_vector_candidates", new_callable=AsyncMock)
    @patch("autofix_agent.db.find_chunk_by_file_and_line", new_callable=AsyncMock)
    def test_direct_match_and_vector_merge(
        self,
        mock_find_chunk,
        mock_search_vector,
        mock_insert_candidates,
    ):
        mock_find_chunk.return_value = {
            "id": 101,
            "file_path": "services/noteService.js",
            "start_line": 15,
            "end_line": 30,
            "content": "function createNote() { ... }",
        }
        mock_search_vector.return_value = [
            {
                "chunk_id": 102,
                "file_path": "services/authService.js",
                "start_line": 1,
                "end_line": 20,
                "content": "function authenticate() { ... }",
                "score": 0.85,
                "method": "embedding",
            }
        ]

        signal_text = """
TypeError: Cannot read properties of undefined at createNote (services/noteService.js:18:10)
        """
        signal = preprocess_signal_content(signal_text)

        import asyncio
        candidates = asyncio.run(localize_and_rank(repo_id=1, job_id=1, signal=signal))

        self.assertTrue(len(candidates) >= 2)
        # Direct match should be ranked #1
        self.assertEqual(str(candidates[0]["chunk_id"]), "101")
        self.assertEqual(candidates[0]["rank"], 1)
        self.assertEqual(candidates[0]["method"], "stack_trace_direct")

        # Vector match ranked #2
        self.assertEqual(str(candidates[1]["chunk_id"]), "102")
        self.assertEqual(candidates[1]["rank"], 2)

    def test_is_test_path(self):
        for path in [
            "tests/test_payment.py",
            "app/payment_test.py",
            "conftest.py",
            "pkg/payment/processor_test.go",
            "src/__tests__/Button.tsx",
            "src/utils/format.test.ts",
            "client/src/App.spec.jsx",
            "src/test/java/com/acme/PaymentProcessorTest.java",
            "core/PaymentProcessorIT.java",
        ]:
            self.assertTrue(is_test_path(path), path)

        for path in [
            "src/payment/processor.py",
            "src/testimonials/list.tsx",
            "src/contest.py",
            "pkg/payment/processor.go",
            "src/main/java/com/acme/TestDataLoader.java",
            "services/noteService.js",
        ]:
            self.assertFalse(is_test_path(path), path)

    @patch("autofix_agent.db.insert_localization_candidates", new_callable=AsyncMock)
    @patch("autofix_agent.localization.ranker.search_vector_candidates", new_callable=AsyncMock)
    def test_test_files_ranked_below_source(self, mock_search_vector, mock_insert_candidates):
        mock_search_vector.return_value = [
            {
                "chunk_id": 201,
                "file_path": "tests/test_payment.py",
                "start_line": 1,
                "end_line": 20,
                "content": "def test_fee(): ...",
                "score": 0.82,
                "method": "embedding",
            },
            {
                "chunk_id": 202,
                "file_path": "payment/processor.py",
                "start_line": 10,
                "end_line": 40,
                "content": "def calculate_fee(): ...",
                "score": 0.75,
                "method": "embedding",
            },
        ]
        signal = preprocess_signal_content("Fee calculation rounds incorrectly for large amounts")

        import asyncio
        candidates = asyncio.run(localize_and_rank(repo_id=1, job_id=1, signal=signal))

        self.assertEqual([str(c["chunk_id"]) for c in candidates], ["202", "201"])
        self.assertAlmostEqual(candidates[1]["score"], 0.82 * 0.8)


if __name__ == "__main__":
    unittest.main()
