"""
Test runners for validating generated patches.

Executes pytest / npm test or language-specific syntax parsers and parses test results.
"""
from __future__ import annotations

import ast
import os
import subprocess
from ..utils.logging import get_logger

logger = get_logger("validation.test_runners")


def validate_python_files(directory: str) -> tuple[bool, str]:
    """Parse all modified .py files in directory using ast.parse."""
    errors = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as py_file:
                        ast.parse(py_file.read(), filename=path)
                except SyntaxError as e:
                    rel = os.path.relpath(path, directory)
                    errors.append(f"SyntaxError in {rel}:{e.lineno}:{e.offset} - {e.msg}")
                except Exception as e:
                    rel = os.path.relpath(path, directory)
                    errors.append(f"Error checking {rel}: {e}")

    if errors:
        return False, "\n".join(errors)
    return True, "Python AST syntax parse succeeded."


def run_tests_in_directory(
    directory: str,
    test_cmd: str | None = None,
    timeout: int = 120,
) -> tuple[bool, str]:
    """
    Run the test suite or syntax validation in directory.

    Returns:
        tuple (passed: bool, output_log: str)
    """
    # 1. Run Python syntax validation first if python files exist
    py_ok, py_msg = validate_python_files(directory)
    if not py_ok:
        return False, f"Syntax Validation Failed:\n{py_msg}"

    # 2. Determine test command if not provided
    if not test_cmd:
        # JS/TS packages (anywhere in the repo) are handled by js_checks.JsValidator
        if os.path.exists(os.path.join(directory, "pytest.ini")) or os.path.exists(os.path.join(directory, "tests")):
            test_cmd = "pytest"
        elif os.path.exists(os.path.join(directory, "go.mod")):
            test_cmd = "go test ./..."
        elif os.path.exists(os.path.join(directory, "pom.xml")):
            mvn_cmd = "./mvnw" if os.path.exists(os.path.join(directory, "mvnw")) else "mvn"
            test_cmd = f"{mvn_cmd} test"
        elif os.path.exists(os.path.join(directory, "build.gradle")) or os.path.exists(os.path.join(directory, "build.gradle.kts")):
            gradle_cmd = "./gradlew" if os.path.exists(os.path.join(directory, "gradlew")) else "gradle"
            test_cmd = f"{gradle_cmd} test"

    # If no test runner found, pass on syntax validation
    if not test_cmd:
        logger.info("No explicit test suite detected in %s; passed syntax validation.", directory)
        return True, "No automated test suite detected. Syntax validation passed."

    logger.info("Running test command '%s' in %s", test_cmd, directory)
    try:
        proc = subprocess.run(
            test_cmd,
            cwd=directory,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = (proc.stdout + "\n" + proc.stderr).strip()
        passed = (proc.returncode == 0)

        if passed:
            logger.info("Test suite PASSED.")
        else:
            logger.warning("Test suite FAILED with returncode %d.", proc.returncode)

        return passed, output

    except subprocess.TimeoutExpired:
        logger.error("Test execution timed out after %d seconds.", timeout)
        return False, f"Test execution timed out after {timeout} seconds."
    except Exception as e:
        logger.error("Failed to execute test command: %s", e)
        return False, f"Test runner invocation error: {e}"
