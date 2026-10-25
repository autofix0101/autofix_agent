"""
Unit tests for Code Chunker.
"""
import unittest

from autofix_agent.indexing.chunker import chunk_file_content, is_chunkable_file
from tests.fixtures import (
    PYTHON_SOURCE_SAMPLE,
    TYPESCRIPT_SOURCE_SAMPLE,
    GO_SOURCE_SAMPLE,
    JAVA_SOURCE_SAMPLE,
)


class TestChunker(unittest.TestCase):

    def test_is_chunkable_file(self):
        self.assertTrue(is_chunkable_file("services/noteService.js"))
        self.assertTrue(is_chunkable_file("src/app.py"))
        self.assertTrue(is_chunkable_file("components/Button.tsx"))
        self.assertTrue(is_chunkable_file("main.go"))
        self.assertTrue(is_chunkable_file("PaymentProcessor.java"))

        self.assertFalse(is_chunkable_file("image.png"))
        self.assertFalse(is_chunkable_file("archive.zip"))

    def test_chunk_python(self):
        chunks = chunk_file_content(PYTHON_SOURCE_SAMPLE, "payment/processor.py")
        self.assertTrue(len(chunks) >= 2)

        symbols = [c.symbol_name for c in chunks if c.symbol_name]
        self.assertIn("PaymentProcessor", symbols)
        self.assertIn("calculate_fee", symbols)

        # Check Part 2 composed block format
        fee_chunk = next(c for c in chunks if c.symbol_name == "calculate_fee")
        self.assertIn("File: payment/processor.py", fee_chunk.content)
        self.assertIn("Function: calculate_fee", fee_chunk.content)
        self.assertTrue(len(fee_chunk.content_hash) == 64)  # sha256

    def test_chunk_typescript(self):
        chunks = chunk_file_content(TYPESCRIPT_SOURCE_SAMPLE, "services/taxCalculator.ts")
        self.assertTrue(len(chunks) >= 2)

        symbols = [c.symbol_name for c in chunks if c.symbol_name]
        self.assertIn("calculateTax", symbols)

        calc_chunk = next(c for c in chunks if c.symbol_name == "calculateTax")
        self.assertIn("File: services/taxCalculator.ts", calc_chunk.content)
        self.assertIn("Function: calculateTax", calc_chunk.content)
        self.assertTrue(len(calc_chunk.content_hash) == 64)

    def test_chunk_go(self):
        chunks = chunk_file_content(GO_SOURCE_SAMPLE, "payment/processor.go")
        self.assertTrue(len(chunks) >= 2)

        symbols = [c.symbol_name for c in chunks if c.symbol_name]
        self.assertIn("CalculateFee", symbols)

        fee_chunk = next(c for c in chunks if c.symbol_name == "CalculateFee")
        self.assertIn("File: payment/processor.go", fee_chunk.content)
        self.assertIn("CalculateFee", fee_chunk.content)
        self.assertEqual(fee_chunk.language, "go")
        self.assertTrue(len(fee_chunk.content_hash) == 64)

    def test_chunk_java(self):
        chunks = chunk_file_content(JAVA_SOURCE_SAMPLE, "com/example/payment/PaymentProcessor.java")
        self.assertTrue(len(chunks) >= 2)

        symbols = [c.symbol_name for c in chunks if c.symbol_name]
        self.assertIn("PaymentProcessor", symbols)

        proc_chunk = next(c for c in chunks if c.symbol_name == "PaymentProcessor")
        self.assertIn("File: com/example/payment/PaymentProcessor.java", proc_chunk.content)
        self.assertEqual(proc_chunk.language, "java")
        self.assertTrue(len(proc_chunk.content_hash) == 64)


if __name__ == "__main__":
    unittest.main()
