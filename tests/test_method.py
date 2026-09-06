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

    def test_scoping_review_manifest_loads_and_validates(self):
        # docs/PLAN.md M3: the parity fix -- a second real, shipped method.
        manifests = method.list_manifests()
        self.assertIn("scoping_review", manifests)
        manifest = manifests["scoping_review"]
        self.assertEqual(manifest["family"], "scoping")
        self.assertEqual(manifest["capture"]["mode"], "charting")
        self.assertEqual(manifest["synthesis"]["families_allowed"], ["descriptive"])
        self.assertEqual(manifest["appraisal"]["requirement"], "optional_with_justification")
        # §2.4: scoping reviews are never downgraded for single screening.
        self.assertEqual(manifest["label_rules"]["requires"], [])
        self.assertEqual(manifest["label_rules"]["label"], "scoping review")

    def test_systematic_mapping_study_manifest_loads_and_validates(self):
        manifests = method.list_manifests()
        self.assertIn("systematic_mapping_study", manifests)
        manifest = manifests["systematic_mapping_study"]
        self.assertEqual(manifest["family"], "mapping")
        self.assertEqual(manifest["capture"]["mode"], "classification")
        self.assertEqual(manifest["search"]["controlled_vocab"], "none")
        self.assertEqual(manifest["synthesis"]["families_allowed"], ["descriptive"])
        self.assertEqual(manifest["label_rules"]["requires"], [])

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
        self.assertEqual(printed["capture_mode"], "extraction")

    def test_cli_reports_error_for_invalid_slug(self):
        rc = method.main(["--topic", "../etc/passwd"])
        self.assertEqual(rc, 1)

    def test_require_capture_mode_passes_when_it_matches(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = method.main(["--topic", self.SLUG, "--require-capture-mode", "extraction"])
        self.assertEqual(rc, 0)
        printed = json.loads(buf.getvalue())
        self.assertNotIn("refused", printed)

    def test_require_capture_mode_refuses_when_it_does_not_match(self):
        # docs/PLAN.md M3: a command whose stage doesn't apply to this
        # review's method must refuse, never silently run its own logic
        # against a manifest that asked for something else.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = method.main(["--topic", self.SLUG, "--require-capture-mode", "charting"])
        self.assertEqual(rc, 1)
        printed = json.loads(buf.getvalue())
        self.assertTrue(printed["refused"])
        self.assertIn("extraction", printed["reason"])


class CaptureModeGenericityTests(unittest.TestCase):
    """Proves the manifest schema and tools/method.py support any
    capture.mode value, not just "extraction" -- the real prerequisite for
    a future scoping_review/systematic_mapping_study manifest (docs/PLAN.md
    M3) to be schema-valid and resolvable at all. Writes a throwaway
    manifest fixture directly under methods/ (real filesystem, per this
    repo's established test convention) and removes it in tearDown."""

    FIXTURE_ID = "test_charting_fixture_zzz"
    SLUG = "capture-mode-genericity-test-topic"

    def setUp(self):
        self.fixture_path = method.METHODS_DIR / f"{self.FIXTURE_ID}.json"
        # addCleanup (not just tearDown) so a crash mid-test still removes
        # this from the real methods/ directory -- left behind, it would
        # fail a later, unrelated check_framework_version.py run (which
        # globs methods/*.json and requires a semver "version" on each)
        # with a confusing error about a file nobody knowingly wrote.
        self.addCleanup(lambda: self.fixture_path.unlink(missing_ok=True))
        manifest = {
            "id": self.FIXTURE_ID, "label": "Test charting fixture", "version": "1.0.0", "family": "mapping",
            "search": {"mode": "protocol_driven", "min_index_families": 0, "known_item_recall": "advisory"},
            "screening": {"recommend_reviewers": 1, "criteria_may_evolve": "versioned"},
            "capture": {"mode": "charting", "schema": "schemas/charting_table.schema.json"},
            "appraisal": {"requirement": "none", "use": []},
            "synthesis": {"families_allowed": ["descriptive"]},
            "label_rules": {"label": "test fixture"},
            "microcopy": {"what": "x", "gives": "y", "costs": "z"},
        }
        self.fixture_path.write_text(json.dumps(manifest))

        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        (self.topic_dir / "protocol.json").write_text(json.dumps({"method": {"id": self.FIXTURE_ID}}))

    def tearDown(self):
        if self.fixture_path.exists():
            self.fixture_path.unlink()
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_non_extraction_capture_mode_manifest_validates_and_resolves(self):
        resolved = method.resolve(self.SLUG)
        self.assertEqual(resolved["manifest"]["capture"]["mode"], "charting")

    def test_require_capture_mode_refuses_for_mismatched_manifest(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = method.main(["--topic", self.SLUG, "--require-capture-mode", "extraction"])
        self.assertEqual(rc, 1)
        printed = json.loads(buf.getvalue())
        self.assertTrue(printed["refused"])
        self.assertIn("charting", printed["reason"])


if __name__ == "__main__":
    unittest.main()
