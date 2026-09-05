"""Unit tests for connectors._shared.write_output's path-safety hardening.

PRODUCT_READINESS_AUDIT.md P0-1: `--out` is reachable through a pre-approved
Bash permission with no interactive review, so write_output must never trust
it as a bare filesystem path. These tests exercise write_output directly
(no HTTP mocking needed -- it takes an already-built payload) against the
adversarial cases the audit's acceptance criteria name explicitly.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connectors import _shared
from tools import path_policy

VALID_OUTPUT = {
    "meta": {
        "source": "openalex", "query": "test", "retrieved": 0,
        "total_available": 0, "truncated": False, "fetched_at": "2026-01-01T00:00:00Z",
    },
    "results": [],
}


class WriteOutputPathSafetyTests(unittest.TestCase):
    def _write_and_capture_exit(self, out_path):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                _shared.write_output(VALID_OUTPUT, "json", out_path)
        self.assertEqual(ctx.exception.code, 1)
        return stderr.getvalue()

    def test_rejects_absolute_path_outside_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "evil.json")
            err = self._write_and_capture_exit(target)
            self.assertIn("UNSAFE_PATH", err)
            self.assertFalse(os.path.exists(target))

    def test_rejects_relative_traversal_outside_results(self):
        err = self._write_and_capture_exit("results/../../../tmp/evil.json")
        self.assertIn("UNSAFE_PATH", err)

    def test_rejects_lua_filter_style_path_injection(self):
        # Not an actual Lua-filter flag (write_output only ever receives a
        # path, never arbitrary flags) -- this documents that even a
        # deliberately adversarial *path* string containing shell-looking
        # content is still just resolved and checked for containment, never
        # interpreted.
        err = self._write_and_capture_exit("/tmp/x; rm -rf /")
        self.assertIn("UNSAFE_PATH", err)

    def test_writes_atomically_under_a_safe_results_path(self):
        with tempfile.TemporaryDirectory() as tmp_results:
            # Point RESULTS_ROOT-under-test at a scratch dir so this test
            # never touches the repo's own results/ directory.
            original_root = path_policy.RESULTS_ROOT
            try:
                path_policy.RESULTS_ROOT = Path(tmp_results).resolve()
                safe_path = os.path.join(tmp_results, "some-topic", "raw", "out.json")
                _shared.write_output(VALID_OUTPUT, "json", safe_path)
                self.assertTrue(os.path.exists(safe_path))
                with open(safe_path) as f:
                    self.assertEqual(json.load(f), VALID_OUTPUT)
                # No leftover temp file from the atomic-write step.
                leftover = [p for p in os.listdir(os.path.dirname(safe_path)) if ".tmp" in p]
                self.assertEqual(leftover, [])
            finally:
                path_policy.RESULTS_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
