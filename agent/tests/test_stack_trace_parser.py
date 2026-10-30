"""
Unit tests for Stack Trace Parser and Preprocessor.
"""
import unittest

from autofix_agent.signals.stack_trace_parser import (
    parse_python_traceback,
    parse_js_traceback,
    parse_go_traceback,
    parse_java_traceback,
    parse_stack_trace,
)
from autofix_agent.signals.issue_preprocessor import preprocess_signal_content
from tests.fixtures import (
    PYTHON_TRACEBACK_SAMPLE,
    JS_STACK_TRACE_SAMPLE,
    GITHUB_ISSUE_SAMPLE,
    GO_PANIC_SAMPLE,
    JAVA_EXCEPTION_SAMPLE,
)


class TestStackTraceParser(unittest.TestCase):

    def test_parse_python_traceback(self):
        parsed = parse_python_traceback(PYTHON_TRACEBACK_SAMPLE)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.error_type, "TypeError")
        self.assertIn("unsupported operand", parsed.error_message)

        self.assertIsNotNone(parsed.primary_frame)
        self.assertEqual(parsed.primary_frame.file_path, "/workspace/src/payment/processor.py")
        self.assertEqual(parsed.primary_frame.line_number, 45)
        self.assertEqual(parsed.primary_frame.function_name, "calculate_fee")

    def test_parse_js_stack_trace(self):
        parsed = parse_js_traceback(JS_STACK_TRACE_SAMPLE)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.error_type, "TypeError")
        self.assertIsNotNone(parsed.primary_frame)
        self.assertEqual(parsed.primary_frame.file_path, "services/taxCalculator.ts")
        self.assertEqual(parsed.primary_frame.line_number, 24)

    def test_parse_go_panic(self):
        parsed = parse_stack_trace(GO_PANIC_SAMPLE)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.error_type, "Panic")
        self.assertIn("nil pointer dereference", parsed.error_message)
        self.assertIsNotNone(parsed.primary_frame)
        self.assertEqual(parsed.primary_frame.file_path, "/workspace/payment/processor.go")
        self.assertEqual(parsed.primary_frame.line_number, 45)

    def test_parse_java_exception(self):
        parsed = parse_stack_trace(JAVA_EXCEPTION_SAMPLE)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.error_type, "java.lang.NullPointerException")
        self.assertIsNotNone(parsed.primary_frame)
        self.assertEqual(parsed.primary_frame.file_path, "PaymentProcessor.java")
        self.assertEqual(parsed.primary_frame.line_number, 45)

    def test_preprocess_signal(self):
        preprocessed = preprocess_signal_content(GITHUB_ISSUE_SAMPLE, title="Payment failed")
        self.assertIsNotNone(preprocessed.stack_trace)
        self.assertEqual(preprocessed.stack_trace.primary_frame.file_path, "services/taxCalculator.ts")
        self.assertIn("services/taxCalculator.ts", preprocessed.mentioned_files)


if __name__ == "__main__":
    unittest.main()
