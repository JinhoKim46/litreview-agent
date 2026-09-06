"""Unit tests for tools/method.py (docs/PLAN.md M1)."""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import method, path_policy
from tools.path_policy import UnsafePathError


class ListManifestsTests(unittest.TestCase):
    def test_systematic_review_manifest_loads_and_validates(self):
        manifests = method.list_manifests()
        self.assertIn("systematic_review", manifests)
        self.assertEqual(manifests["systematic_review"]["family"], "systematic")
        self.assertEqual(manifests["systematic_review"]["synthesis"]["families_allowed"],
                          ["structured_narrative", "swim", "pairwise_iv"])

    def test_schema_and_routing_files_never_treated_as_manifests(self):
        manifests = method.list_manifests()
        self.assertNotIn("_schema", manifests)
        self.assertNotIn("_routing", manifests)


class LoadPackTests(unittest.TestCase):
    def test_invalid_pack_id_rejected(self):
        with self.assertRaises(method.MethodError):
            method.load_pack("has-a-hyphen")

    def test_nonexistent_pack_returns_none_not_error(self):
        # No pack manifest ships until M3 -- a missing packs/<id>.json is
        # the expected M1 state.
        self.assertIsNone(method.load_pack("generic"))


class ProtocolMethodBlockTests(unittest.TestCase):
    def test_missing_protocol_defaults_to_systematic_review_not_recorded(self):
        method_id, recorded = method._load_protocol_method_block(None)
        self.assertEqual(method_id, method.DEFAULT_METHOD_ID)
        self.assertFalse(recorded)

    def test_protocol_without_method_key_defaults_the_same_way(self):
        method_id, recorded = method._load_protocol_method_block({"topic": "x"})
        self.assertEqual(method_id, method.DEFAULT_METHOD_ID)
        self.assertFalse(recorded)

    def test_explicit_method_block_is_recorded(self):
        method_id, recorded = method._load_protocol_method_block({"method": {"id": "systematic_review"}})
        self.assertEqual(method_id, "systematic_review")
        self.assertTrue(recorded)

    def test_malformed_method_block_raises(self):
        with self.assertRaises(method.MethodError):
            method._load_protocol_method_block({"method": {"not_id": "oops"}})


class ResolveTests(unittest.TestCase):
    SLUG = "method-resolve-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def _write_protocol(self, content):
        with open(self.topic_dir / "protocol.json", "w") as f:
            json.dump(content, f)

    def test_legacy_topic_with_no_protocol_json_resolves_to_sr_not_recorded(self):
        resolved = method.resolve(self.SLUG)
        self.assertEqual(resolved["method_id"], "systematic_review")
        self.assertFalse(resolved["recorded"])
        self.assertEqual(resolved["manifest"]["label"], "Systematic review")
        self.assertEqual(resolved["pack_id"], "generic")
        self.assertIsNone(resolved["pack"])  # no pack ships until M3

    def test_legacy_topic_with_protocol_but_no_method_key_same_result(self):
        self._write_protocol({"topic": self.SLUG})
        resolved = method.resolve(self.SLUG)
        self.assertEqual(resolved["method_id"], "systematic_review")
        self.assertFalse(resolved["recorded"])

    def test_explicit_method_recorded(self):
        self._write_protocol({"method": {"id": "systematic_review"}})
        resolved = method.resolve(self.SLUG)
        self.assertEqual(resolved["method_id"], "systematic_review")
        self.assertTrue(resolved["recorded"])

    def test_unknown_method_id_raises(self):
        self._write_protocol({"method": {"id": "not_a_real_method"}})
        with self.assertRaises(method.MethodError):
            method.resolve(self.SLUG)

    def test_invalid_topic_slug_rejected_by_path_policy(self):
        with self.assertRaises(UnsafePathError):
            method.resolve("../etc/passwd")

    def test_pack_override_returned_verbatim(self):
        resolved = method.resolve(self.SLUG, pack_id="clinical_interventions")
        self.assertEqual(resolved["pack_id"], "clinical_interventions")
        self.assertIsNone(resolved["pack"])  # no pack manifest ships until M3


class MainCliTests(unittest.TestCase):
    SLUG = "method-cli-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_cli_prints_resolved_method_as_json(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = method.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)
        printed = json.loads(buf.getvalue())
        self.assertEqual(printed["method_id"], "systematic_review")
        self.assertFalse(printed["recorded"])

    def test_cli_reports_error_for_invalid_slug(self):
        rc = method.main(["--topic", "../etc/passwd"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
