"""
JavaScript / TypeScript validation for patched repositories.

For every npm package (directory with a package.json) that a patch touches:
  1. Install dependencies once per job into the pristine source clone with
     `npm ci` / `npm install --ignore-scripts`. node_modules is added to the
     clone's .git/info/exclude so it can never end up in the PR commit.
  2. Type-check with the project's own TypeScript (`tsc --noEmit`). Repos often
     have type errors before any patch, so only errors the unpatched code does
     not already have count as failures.
  3. Syntax-check changed plain JS files with `node --check`.
  4. Run `npm test` if the package defines a real test script (npm's
     "no test specified" placeholder is ignored). Test failures only count if
     the tests passed before the patch.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass

from ..utils.logging import get_logger
from .sandbox import Sandbox

logger = get_logger("validation.js_checks")

INSTALL_TIMEOUT = 300
TSC_TIMEOUT = 180
TEST_TIMEOUT = 120

_TSC_ERROR_RE = re.compile(r"^(?P<file>.+?)\(\d+,\d+\): error (?P<code>TS\d+): (?P<msg>.*)$")
_TSC_GLOBAL_ERROR_RE = re.compile(r"^error (?P<code>TS\d+): (?P<msg>.*)$")
_JS_EXTENSIONS = (".js", ".mjs", ".cjs")


@dataclass
class _PackageState:
    rel_dir: str                      # "" for the repo root
    deps_ready: bool = False
    tsc_bin: str | None = None
    baseline_ts_errors: Counter | None = None
    test_script: str | None = None
    baseline_tests_pass: bool | None = None
    notes: str = ""


def _run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    """Run a command, returning (returncode, combined output). -1 on timeout/launch failure."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            env={**os.environ, "CI": "true"},
        )
        return proc.returncode, (proc.stdout + "\n" + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, f"Timed out after {timeout}s: {' '.join(cmd)}"
    except OSError as e:
        return -1, f"Could not run {' '.join(cmd)}: {e}"


def _parse_tsc_errors(output: str, pkg_path: str) -> Counter:
    """
    Key tsc errors by (file relative to the package, code, message) — line numbers
    shift when a patch is applied, and the baseline (source clone) and patched
    (sandbox) runs live in different directories.
    """
    errors: Counter = Counter()
    root = os.path.realpath(pkg_path)
    for line in output.splitlines():
        m = _TSC_ERROR_RE.match(line.strip())
        if m:
            abs_file = os.path.realpath(os.path.join(root, m["file"]))
            rel_file = os.path.relpath(abs_file, root).replace("\\", "/")
            errors[(rel_file, m["code"], m["msg"])] += 1
            continue
        m = _TSC_GLOBAL_ERROR_RE.match(line.strip())
        if m:
            errors[("", m["code"], m["msg"])] += 1
    return errors


def _is_real_test_script(script: str | None) -> bool:
    return bool(script) and "no test specified" not in script


class JsValidator:
    """Per-job validator; caches dependency installs and baselines per package."""

    def __init__(self, source_repo_path: str):
        self.source = os.path.abspath(source_repo_path)
        self._packages: dict[str, _PackageState] = {}
        self._node_available = shutil.which("node") is not None and shutil.which("npm") is not None

    # ------------------------------------------------------------------
    # Package discovery and preparation
    # ------------------------------------------------------------------

    def find_package_dir(self, rel_file: str) -> str | None:
        """Nearest ancestor directory (relative to repo root) that has a package.json."""
        parts = rel_file.replace("\\", "/").split("/")[:-1]
        while True:
            rel_dir = "/".join(parts)
            if os.path.isfile(os.path.join(self.source, rel_dir, "package.json")):
                return rel_dir
            if not parts:
                return None
            parts.pop()

    def _exclude_from_git(self) -> None:
        """Keep install/build artefacts out of `git add -A` in the PR step."""
        exclude = os.path.join(self.source, ".git", "info", "exclude")
        if not os.path.isdir(os.path.dirname(exclude)):
            return
        existing = ""
        if os.path.exists(exclude):
            with open(exclude, encoding="utf-8") as f:
                existing = f.read()
        additions = [p for p in ("node_modules/", "*.tsbuildinfo") if p not in existing.splitlines()]
        if additions:
            with open(exclude, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(additions) + "\n")

    def _tsc(self, pkg_path: str, tsc_bin: str) -> tuple[int, str]:
        pkg_path = os.path.realpath(pkg_path)
        return _run(
            [tsc_bin, "--noEmit", "--pretty", "false", "--incremental", "false", "-p", pkg_path],
            cwd=pkg_path, timeout=TSC_TIMEOUT,
        )

    def _prepare(self, rel_dir: str) -> _PackageState:
        if rel_dir in self._packages:
            return self._packages[rel_dir]

        state = _PackageState(rel_dir=rel_dir)
        self._packages[rel_dir] = state
        pkg_path = os.path.join(self.source, rel_dir)
        label = rel_dir or "."

        try:
            with open(os.path.join(pkg_path, "package.json"), encoding="utf-8") as f:
                state.test_script = (json.load(f).get("scripts") or {}).get("test")
        except (OSError, ValueError) as e:
            state.notes = f"[{label}] Could not read package.json: {e}"
            return state

        self._exclude_from_git()

        # 1. Dependencies (once per job)
        if os.path.isdir(os.path.join(pkg_path, "node_modules")):
            state.deps_ready = True
        else:
            logger.info("Installing npm dependencies in %s (scripts disabled)...", label)
            flags = ["--ignore-scripts", "--no-audit", "--no-fund"]
            code, out = -1, ""
            if os.path.exists(os.path.join(pkg_path, "package-lock.json")):
                code, out = _run(["npm", "ci", *flags], cwd=pkg_path, timeout=INSTALL_TIMEOUT)
            if code != 0:
                # --no-package-lock: never create/modify package-lock.json in the clone
                code, out = _run(["npm", "install", "--no-package-lock", *flags], cwd=pkg_path, timeout=INSTALL_TIMEOUT)
            state.deps_ready = code == 0
            if not state.deps_ready:
                state.notes = f"[{label}] npm install failed; skipping type-check and tests.\n{out[-1500:]}"
                logger.warning("npm install failed in %s", label)
                return state

        # 2. TypeScript baseline on the unpatched code
        tsc_bin = os.path.join(pkg_path, "node_modules", ".bin", "tsc")
        if os.path.exists(os.path.join(pkg_path, "tsconfig.json")) and os.path.exists(tsc_bin):
            state.tsc_bin = tsc_bin
            _, out = self._tsc(pkg_path, tsc_bin)
            state.baseline_ts_errors = _parse_tsc_errors(out, pkg_path)
            logger.info("[%s] TypeScript baseline: %d pre-existing error(s)", label, sum(state.baseline_ts_errors.values()))

        return state

    def _link_node_modules(self, sandbox_path: str, rel_dir: str) -> None:
        src = os.path.join(self.source, rel_dir, "node_modules")
        dst = os.path.join(sandbox_path, rel_dir, "node_modules")
        if os.path.isdir(src) and not os.path.exists(dst):
            os.symlink(src, dst)

    def _baseline_tests_pass(self, state: _PackageState) -> bool:
        """Run the test script once on the unpatched code (in a throwaway copy)."""
        if state.baseline_tests_pass is None:
            with Sandbox(self.source) as baseline:
                self._link_node_modules(baseline, state.rel_dir)
                code, _ = _run(["npm", "test"], cwd=os.path.join(baseline, state.rel_dir), timeout=TEST_TIMEOUT)
            state.baseline_tests_pass = code == 0
        return state.baseline_tests_pass

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, sandbox_path: str, changed_files: list[str]) -> tuple[bool, str]:
        """Validate the patched sandbox. Returns (passed, log)."""
        pkg_dirs = sorted({d for d in (self.find_package_dir(f) for f in changed_files) if d is not None})
        if not pkg_dirs:
            return True, ""
        if not self._node_available:
            return True, "node/npm not installed on the agent host; skipped JS/TS checks."

        ok = True
        logs: list[str] = []
        for rel_dir in pkg_dirs:
            label = rel_dir or "."
            state = self._prepare(rel_dir)
            if state.notes:
                logs.append(state.notes)
            if not state.deps_ready:
                continue

            self._link_node_modules(sandbox_path, rel_dir)
            pkg_path = os.path.join(sandbox_path, rel_dir)

            # Type-check: only errors introduced by the patch fail validation
            if state.tsc_bin:
                _, out = self._tsc(pkg_path, state.tsc_bin)
                new_errors = _parse_tsc_errors(out, pkg_path) - (state.baseline_ts_errors or Counter())
                if new_errors:
                    ok = False
                    lines = [f"{f}: error {code}: {msg}" for (f, code, msg) in new_errors]
                    logs.append(f"[{label}] TypeScript type-check FAILED — errors introduced by the patch:\n" + "\n".join(lines[:30]))
                else:
                    logs.append(f"[{label}] TypeScript type-check passed (no new errors).")

            # Syntax-check changed plain JS files
            prefix = f"{rel_dir}/" if rel_dir else ""
            for rel_file in changed_files:
                if rel_file.endswith(_JS_EXTENSIONS) and rel_file.startswith(prefix):
                    full = os.path.join(sandbox_path, rel_file)
                    if os.path.exists(full):
                        code, out = _run(["node", "--check", full], cwd=pkg_path, timeout=30)
                        if code != 0:
                            ok = False
                            logs.append(f"[{label}] Syntax error in {rel_file}:\n{out[-1500:]}")

            # Tests
            if _is_real_test_script(state.test_script):
                if not self._baseline_tests_pass(state):
                    logs.append(f"[{label}] `npm test` already fails before the patch; not used for validation.")
                else:
                    code, out = _run(["npm", "test"], cwd=pkg_path, timeout=TEST_TIMEOUT)
                    if code != 0:
                        ok = False
                        logs.append(f"[{label}] `npm test` FAILED after the patch:\n{out[-3000:]}")
                    else:
                        logs.append(f"[{label}] `npm test` passed.")
            else:
                logs.append(f"[{label}] No test script defined; validated by type-check/syntax only.")

        return ok, "\n\n".join(logs)
