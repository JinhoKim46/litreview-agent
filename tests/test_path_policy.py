import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import path_policy


class ValidateTopicSlugTests(unittest.TestCase):
    def test_accepts_a_normal_slug(self):
        self.assertEqual(path_policy.validate_topic_slug("streptococcus-suis-infection"),
                          "streptococcus-suis-infection")

    def test_rejects_empty_uppercase_underscore_and_separators(self):
        for bad in ("", "Has-Upper", "has_underscore", "a/b", "a\\b", "a b"):
            with self.assertRaises(path_policy.UnsafePathError, msg=bad):
                path_policy.validate_topic_slug(bad)

    def test_rejects_leading_trailing_and_double_hyphens(self):
        for bad in ("-leading", "trailing-", "double--hyphen"):
            with self.assertRaises(path_policy.UnsafePathError, msg=bad):
                path_policy.validate_topic_slug(bad)

    def test_rejects_over_length_slug(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.validate_topic_slug("a" * (path_policy.MAX_SLUG_LEN + 1))

    def test_rejects_non_string(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.validate_topic_slug(None)


class ResolveUnderResultsTests(unittest.TestCase):
    def test_normal_path_under_results_resolves(self):
        resolved = path_policy.resolve_under_results("results/some-topic/raw/pubmed-20260905.json")
        self.assertEqual(resolved, path_policy.RESULTS_ROOT / "some-topic" / "raw" / "pubmed-20260905.json")

    def test_rejects_absolute_path_outside_results(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.resolve_under_results("/etc/passwd")

    def test_rejects_relative_traversal_outside_results(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.resolve_under_results("results/some-topic/../../../etc/passwd")

    def test_rejects_repo_path_outside_results(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.resolve_under_results("connectors/_shared.py")

    def test_rejects_tmp_style_absolute_path(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.resolve_under_results("/tmp/evil.json")

    def test_rejects_symlink_planted_inside_results_pointing_outside(self):
        # A symlink physically inside results/ whose target resolves outside
        # it must still be caught -- resolve() follows the symlink, so the
        # escape is visible after resolution even though the literal string
        # argument looked like it was under results/.
        path_policy.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as outside_dir:
            link_path = path_policy.RESULTS_ROOT / "test-escape-symlink"
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            os.symlink(outside_dir, link_path)
            try:
                with self.assertRaises(path_policy.UnsafePathError):
                    path_policy.resolve_under_results("results/test-escape-symlink/evil.json")
            finally:
                link_path.unlink()

    def test_does_not_require_the_path_to_already_exist(self):
        # Writers call this before the file/directory exists yet.
        resolved = path_policy.resolve_under_results("results/brand-new-topic/raw/new.json")
        self.assertEqual(resolved, path_policy.RESULTS_ROOT / "brand-new-topic" / "raw" / "new.json")


class SafeTopicPathTests(unittest.TestCase):
    def test_builds_and_validates_results_slug_path(self):
        # Regression test: an earlier version of safe_topic_path omitted the
        # "results/" prefix entirely, so it resolved to <repo-root>/<slug>/...
        # instead of <repo-root>/results/<slug>/... and every real caller
        # (synthesis/run_synthesis.py's --topic, tools/export_report.py)
        # would have failed its own containment check on every legitimate
        # invocation.
        resolved = path_policy.safe_topic_path("some-topic", "extraction_table.json")
        self.assertEqual(resolved, path_policy.RESULTS_ROOT / "some-topic" / "extraction_table.json")

    def test_rejects_unsafe_slug_before_touching_the_path(self):
        with self.assertRaises(path_policy.UnsafePathError):
            path_policy.safe_topic_path("../../etc", "passwd")


if __name__ == "__main__":
    unittest.main()
