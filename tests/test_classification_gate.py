"""Unit tests for tools/classification_gate.py (docs/PLAN.md M3)."""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import classification_gate, path_policy


class CheckGateTests(unittest.TestCase):
    def test_unfrozen_scheme_state_check_is_ok(self):
        table = {"scheme_frozen": False, "facets": [], "studies": []}
        result = classification_gate.check_gate(table)
        self.assertTrue(result["ok"])
        self.assertFalse(result["scheme_frozen"])

    def test_unfrozen_scheme_row_write_attempt_blocks(self):
        # M3 exit criterion: bulk coding is blocked until the scheme is frozen.
        table = {"scheme_frozen": False, "facets": [], "studies": []}
        result = classification_gate.check_gate(table, row_codes={"research_type": "validation"})
        self.assertFalse(result["ok"])
        self.assertIn("frozen", result["reason"])

    def test_frozen_scheme_with_matching_row_is_ok(self):
        table = {"scheme_frozen": True, "facets": [{"name": "research_type", "categories": ["validation", "evaluation"]}], "studies": []}
        result = classification_gate.check_gate(table, row_codes={"research_type": "validation"})
        self.assertTrue(result["ok"])
        self.assertIsNone(result["row_facet_mismatch"])

    def test_frozen_scheme_with_missing_facet_blocks(self):
        table = {"scheme_frozen": True, "facets": [{"name": "research_type", "categories": ["validation"]}, {"name": "dataset", "categories": ["public"]}], "studies": []}
        result = classification_gate.check_gate(table, row_codes={"research_type": "validation"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["row_facet_mismatch"]["missing"], ["dataset"])

    def test_frozen_scheme_with_extra_facet_blocks(self):
        table = {"scheme_frozen": True, "facets": [{"name": "research_type", "categories": ["validation"]}], "studies": []}
        result = classification_gate.check_gate(table, row_codes={"research_type": "validation", "surprise": "x"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["row_facet_mismatch"]["extra"], ["surprise"])

    def test_frozen_scheme_without_row_codes_is_just_ok(self):
        table = {"scheme_frozen": True, "facets": [{"name": "research_type", "categories": ["validation"]}], "studies": []}
        result = classification_gate.check_gate(table)
        self.assertTrue(result["ok"])


class VerifyTableTests(unittest.TestCase):
    def test_unfrozen_table_is_never_flagged(self):
        table = {"scheme_frozen": False, "facets": [], "studies": [{"record_id": "r1", "codes": {}}]}
        self.assertEqual(classification_gate.verify_table(table), [])

    def test_frozen_table_with_matching_rows_is_clean(self):
        table = {
            "scheme_frozen": True,
            "facets": [{"name": "research_type", "categories": ["validation"]}],
            "studies": [{"record_id": "r1", "codes": {"research_type": "validation"}}],
        }
        self.assertEqual(classification_gate.verify_table(table), [])

    def test_frozen_table_with_drifted_row_is_flagged(self):
        table = {
            "scheme_frozen": True,
            "facets": [{"name": "research_type", "categories": ["validation"]}],
            "studies": [
                {"record_id": "r1", "codes": {"research_type": "validation"}},
                {"record_id": "r2", "codes": {}},
            ],
        }
        self.assertEqual(classification_gate.verify_table(table), ["r2"])


class FreezeCalibrationAndCliTests(unittest.TestCase):
    SLUG = "classification-gate-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        (self.topic_dir / "protocol.json").write_text(json.dumps({"method": {"id": "systematic_mapping_study"}}))

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_freeze_writes_file_and_is_idempotent(self):
        facets = [{"name": "research_type", "categories": ["validation", "evaluation"]}]
        table = classification_gate.freeze(self.topic_dir, self.SLUG, facets)
        self.assertTrue(table["scheme_frozen"])
        self.assertEqual(table["facets"], facets)
        self.assertTrue((self.topic_dir / "classification_table.json").exists())
        again = classification_gate.freeze(self.topic_dir, self.SLUG, facets)
        self.assertEqual(again["facets"], facets)

    def test_freeze_with_different_facets_after_already_frozen_raises(self):
        classification_gate.freeze(self.topic_dir, self.SLUG, [{"name": "a", "categories": ["x"]}])
        with self.assertRaises(classification_gate.ClassificationGateError):
            classification_gate.freeze(self.topic_dir, self.SLUG, [{"name": "b", "categories": ["y"]}])

    def test_freeze_with_empty_facets_raises(self):
        with self.assertRaises(classification_gate.ClassificationGateError):
            classification_gate.freeze(self.topic_dir, self.SLUG, [])

    def test_record_calibration_before_freeze_raises(self):
        with self.assertRaises(classification_gate.ClassificationGateError):
            classification_gate.record_calibration(self.topic_dir, self.SLUG, {"mode": "intra_rater_delayed", "sample_size": 10, "agreement": 0.9})

    def test_record_calibration_after_freeze_writes_block(self):
        classification_gate.freeze(self.topic_dir, self.SLUG, [{"name": "a", "categories": ["x"]}])
        calibration = {"mode": "intra_rater_delayed", "sample_size": 10, "agreement": 0.87, "disagreements": ["r3"]}
        table = classification_gate.record_calibration(self.topic_dir, self.SLUG, calibration)
        self.assertEqual(table["calibration"], calibration)

    def test_record_calibration_rejects_unknown_mode(self):
        classification_gate.freeze(self.topic_dir, self.SLUG, [{"name": "a", "categories": ["x"]}])
        with self.assertRaises(classification_gate.ClassificationGateError):
            classification_gate.record_calibration(self.topic_dir, self.SLUG, {"mode": "bogus", "sample_size": 10, "agreement": 0.9})

    def test_cli_gate_before_freeze_ok_with_no_row(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = classification_gate.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)
        self.assertFalse(json.loads(buf.getvalue())["scheme_frozen"])

    def test_cli_refuses_for_invalid_slug(self):
        rc = classification_gate.main(["--topic", "../etc/passwd"])
        self.assertEqual(rc, 1)

    def test_cli_verify_clean_table_ok(self):
        classification_gate.freeze(self.topic_dir, self.SLUG, [{"name": "a", "categories": ["x"]}])
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = classification_gate.main(["--topic", self.SLUG, "verify"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["offending_record_ids"], [])

    def test_cli_verify_drifted_table_fails(self):
        table = classification_gate.freeze(self.topic_dir, self.SLUG, [{"name": "a", "categories": ["x"]}])
        table["studies"].append({"record_id": "bad1", "codes": {}})
        (self.topic_dir / "classification_table.json").write_text(json.dumps(table))
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = classification_gate.main(["--topic", self.SLUG, "verify"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(buf.getvalue())["offending_record_ids"], ["bad1"])


if __name__ == "__main__":
    unittest.main()
