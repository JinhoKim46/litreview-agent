"""Unit tests for tools/charting_gate.py (docs/PLAN.md M3)."""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import charting_gate, path_policy


class CheckGateTests(unittest.TestCase):
    def test_empty_table_before_pilot_quota_is_ok(self):
        table = {"charting_form_frozen": False, "fields": [], "studies": [{"record_id": "r1", "data": {}, "by": "x"}]}
        result = charting_gate.check_gate(table, pilot_records_required=8)
        self.assertTrue(result["ok"])
        self.assertFalse(result["must_freeze_now"])

    def test_pilot_quota_met_without_freezing_blocks(self):
        studies = [{"record_id": f"r{i}", "data": {}, "by": "x"} for i in range(8)]
        table = {"charting_form_frozen": False, "fields": [], "studies": studies}
        result = charting_gate.check_gate(table, pilot_records_required=8)
        self.assertFalse(result["ok"])
        self.assertTrue(result["must_freeze_now"])
        self.assertIn("G-Freeze", result["reason"])

    def test_frozen_table_with_matching_row_is_ok(self):
        table = {"charting_form_frozen": True, "fields": ["year", "venue"], "studies": []}
        result = charting_gate.check_gate(table, pilot_records_required=8, row_data={"year": 2024, "venue": "X"})
        self.assertTrue(result["ok"])
        self.assertIsNone(result["row_field_mismatch"])

    def test_frozen_table_with_missing_field_blocks(self):
        table = {"charting_form_frozen": True, "fields": ["year", "venue"], "studies": []}
        result = charting_gate.check_gate(table, pilot_records_required=8, row_data={"year": 2024})
        self.assertFalse(result["ok"])
        self.assertEqual(result["row_field_mismatch"]["missing"], ["venue"])

    def test_frozen_table_with_extra_field_blocks(self):
        table = {"charting_form_frozen": True, "fields": ["year"], "studies": []}
        result = charting_gate.check_gate(table, pilot_records_required=8, row_data={"year": 2024, "surprise": "x"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["row_field_mismatch"]["extra"], ["surprise"])

    def test_frozen_table_without_row_data_is_just_ok(self):
        # Checking overall state (no candidate row yet) never fails once frozen.
        table = {"charting_form_frozen": True, "fields": ["year"], "studies": []}
        result = charting_gate.check_gate(table, pilot_records_required=8)
        self.assertTrue(result["ok"])


class VerifyTableTests(unittest.TestCase):
    def test_unfrozen_table_is_never_flagged(self):
        table = {"charting_form_frozen": False, "fields": [], "studies": [{"record_id": "r1", "data": {}}]}
        self.assertEqual(charting_gate.verify_table(table), [])

    def test_frozen_table_with_matching_rows_is_clean(self):
        table = {
            "charting_form_frozen": True,
            "fields": ["year", "venue"],
            "studies": [{"record_id": "r1", "data": {"year": 2024, "venue": "X"}}],
        }
        self.assertEqual(charting_gate.verify_table(table), [])

    def test_frozen_table_with_drifted_row_is_flagged(self):
        # Simulates a row written without ever calling check_gate first --
        # the exact bypass this function exists to catch after the fact.
        table = {
            "charting_form_frozen": True,
            "fields": ["year", "venue"],
            "studies": [
                {"record_id": "r1", "data": {"year": 2024, "venue": "X"}},
                {"record_id": "r2", "data": {"year": 2024}},
            ],
        }
        self.assertEqual(charting_gate.verify_table(table), ["r2"])


class FreezeAndCliTests(unittest.TestCase):
    SLUG = "charting-gate-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        (self.topic_dir / "protocol.json").write_text(json.dumps({"method": {"id": "scoping_review"}}))

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_freeze_writes_file_and_is_idempotent(self):
        table = charting_gate.freeze(self.topic_dir, self.SLUG, ["year", "venue"])
        self.assertTrue(table["charting_form_frozen"])
        self.assertEqual(table["fields"], ["year", "venue"])
        self.assertTrue((self.topic_dir / "charting_table.json").exists())
        # Idempotent re-freeze with the same fields is a no-op, not an error.
        again = charting_gate.freeze(self.topic_dir, self.SLUG, ["year", "venue"])
        self.assertEqual(again["fields"], ["year", "venue"])

    def test_freeze_with_different_fields_after_already_frozen_raises(self):
        charting_gate.freeze(self.topic_dir, self.SLUG, ["year"])
        with self.assertRaises(charting_gate.ChartingGateError):
            charting_gate.freeze(self.topic_dir, self.SLUG, ["year", "venue"])

    def test_freeze_with_empty_fields_raises(self):
        with self.assertRaises(charting_gate.ChartingGateError):
            charting_gate.freeze(self.topic_dir, self.SLUG, [])

    def test_cli_gate_reads_manifest_pilot_records(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = charting_gate.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)
        printed = json.loads(buf.getvalue())
        self.assertEqual(printed["pilot_records_required"], 8)  # methods/scoping_review.json's capture.pilot_records

    def test_cli_refuses_for_invalid_slug(self):
        rc = charting_gate.main(["--topic", "../etc/passwd"])
        self.assertEqual(rc, 1)

    def test_cli_verify_clean_table_ok(self):
        charting_gate.freeze(self.topic_dir, self.SLUG, ["year"])
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = charting_gate.main(["--topic", self.SLUG, "verify"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["offending_record_ids"], [])

    def test_cli_verify_drifted_table_fails(self):
        table = charting_gate.freeze(self.topic_dir, self.SLUG, ["year"])
        table["studies"].append({"record_id": "bad1", "data": {"year": 2024, "venue": "extra"}})
        (self.topic_dir / "charting_table.json").write_text(json.dumps(table))
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = charting_gate.main(["--topic", self.SLUG, "verify"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(buf.getvalue())["offending_record_ids"], ["bad1"])


if __name__ == "__main__":
    unittest.main()
