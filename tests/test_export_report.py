"""Tests for tools/export_report.py, the Pandoc wrapper that replaced the
unrestricted `Bash(pandoc:*)` permission (PRODUCT_READINESS_AUDIT.md P0-1).

Mocks shutil.which/subprocess.run throughout: this environment may not have
Pandoc installed, and even where it is, these tests care about the argument
list the wrapper builds and the paths it will and won't touch -- not about
exercising real Pandoc. Uses a real, uniquely-named topic directory under the
repo's own (gitignored) results/ root rather than monkeypatching
path_policy's constants, so path resolution is exercised exactly as it runs
in production.
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import export_report, path_policy

TEST_SLUG = "export-report-test-scratch-topic"


class ExportReportTests(unittest.TestCase):
    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / TEST_SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        self.addCleanup(lambda: shutil.rmtree(self.topic_dir, ignore_errors=True))

    def _write_manuscript(self):
        manuscript_dir = self.topic_dir / "manuscript"
        manuscript_dir.mkdir(parents=True)
        (manuscript_dir / "manuscript.md").write_text("# Test\n")
        return manuscript_dir

    def test_rejects_unsafe_topic_slug(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = export_report.main(["--topic", "../../etc", "--format", "docx"])
        self.assertEqual(rc, 1)
        self.assertIn("invalid topic slug", stderr.getvalue())

    def test_missing_manuscript_is_an_error(self):
        self.topic_dir.mkdir(parents=True)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = export_report.main(["--topic", TEST_SLUG, "--format", "docx"])
        self.assertEqual(rc, 1)
        self.assertIn("does not exist", stderr.getvalue())

    def test_pandoc_not_installed_prints_hint_and_fails(self):
        self._write_manuscript()
        with mock.patch.object(export_report.shutil, "which", return_value=None):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = export_report.main(["--topic", TEST_SLUG, "--format", "docx"])
        self.assertEqual(rc, 1)
        self.assertIn("Pandoc not found", stderr.getvalue())

    def test_reference_doc_rejected_for_pdf_format(self):
        self._write_manuscript()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = export_report.main([
                "--topic", TEST_SLUG, "--format", "pdf",
                "--reference-doc", f"results/{TEST_SLUG}/template.docx",
            ])
        self.assertEqual(rc, 1)
        self.assertIn("only supported with --format docx", stderr.getvalue())

    def test_reference_doc_outside_results_rejected(self):
        self._write_manuscript()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = export_report.main([
                "--topic", TEST_SLUG, "--format", "docx", "--reference-doc", "/etc/passwd",
            ])
        self.assertEqual(rc, 1)
        self.assertIn("outside", stderr.getvalue())

    def test_successful_conversion_builds_fixed_arg_list_and_verifies_output(self):
        manuscript_dir = self._write_manuscript()
        output_path = manuscript_dir / "manuscript.docx"

        def fake_run(cmd, capture_output, text):
            # The wrapper must never pass anything beyond input/-o/output --
            # no filters, no extra flags, nothing caller-controlled.
            self.assertEqual(cmd[0], "pandoc")
            self.assertEqual(cmd[1], str(manuscript_dir / "manuscript.md"))
            self.assertEqual(cmd[2], "-o")
            self.assertEqual(cmd[3], str(output_path))
            self.assertEqual(len(cmd), 4)
            output_path.write_bytes(b"fake docx bytes")
            return mock.Mock(returncode=0, stderr="")

        with mock.patch.object(export_report.shutil, "which", return_value="/usr/bin/pandoc"), \
             mock.patch.object(export_report.subprocess, "run", side_effect=fake_run):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = export_report.main(["--topic", TEST_SLUG, "--format", "docx"])
        self.assertEqual(rc, 0)
        self.assertIn(str(output_path), stdout.getvalue())

    def test_empty_output_after_success_is_still_an_error(self):
        self._write_manuscript()

        def fake_run(cmd, capture_output, text):
            return mock.Mock(returncode=0, stderr="")  # never writes the output file

        with mock.patch.object(export_report.shutil, "which", return_value="/usr/bin/pandoc"), \
             mock.patch.object(export_report.subprocess, "run", side_effect=fake_run):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = export_report.main(["--topic", TEST_SLUG, "--format", "docx"])
        self.assertEqual(rc, 1)
        self.assertIn("missing or empty", stderr.getvalue())

    def test_pandoc_nonzero_exit_is_an_error(self):
        self._write_manuscript()

        def fake_run(cmd, capture_output, text):
            return mock.Mock(returncode=1, stderr="pandoc: something went wrong")

        with mock.patch.object(export_report.shutil, "which", return_value="/usr/bin/pandoc"), \
             mock.patch.object(export_report.subprocess, "run", side_effect=fake_run):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = export_report.main(["--topic", TEST_SLUG, "--format", "docx"])
        self.assertEqual(rc, 1)
        self.assertIn("something went wrong", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
