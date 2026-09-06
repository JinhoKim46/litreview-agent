"""Unit tests for synthesis/run_synthesis.py's risk-of-bias label handling:
the RoB1 legacy-alias normalization (a topic's extraction_table.json may
still say "RoB2" from before the mislabeling was corrected -- see
.claude/skills/quality-appraisal/01-risk-of-bias.md), the added `instrument`
id, and is_low_risk's plain low/high/unclear rollup (no RoB 2 "some
concerns" tier).
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis.run_synthesis import (
    INSTRUMENT_BY_TOOL,
    ROB1_LEGACY_TOOL_ALIASES,
    build_rob_entry,
    is_low_risk,
    load_studies,
    normalize_risk_of_bias,
)


class NormalizeRiskOfBiasTests(unittest.TestCase):
    def test_current_label_untouched_but_gains_instrument(self):
        rob = {"tool": "RoB1", "overall_judgement": "low risk"}
        out = normalize_risk_of_bias(rob, "study1")
        self.assertEqual(out["tool"], "RoB1")
        self.assertEqual(out["instrument"], "cochrane_rob1_2011")
        # never mutates the caller's dict
        self.assertNotIn("instrument", rob)

    def test_legacy_rob2_label_normalized_with_warning(self):
        self.assertIn("RoB2", ROB1_LEGACY_TOOL_ALIASES)
        rob = {"tool": "RoB2", "overall_judgement": "low risk"}
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            out = normalize_risk_of_bias(rob, "legacy_study")
        self.assertEqual(out["tool"], "RoB1")
        self.assertEqual(out["instrument"], "cochrane_rob1_2011")
        warning = stderr.getvalue()
        self.assertIn("legacy_study", warning)
        self.assertIn("RoB2", warning)
        self.assertIn("RoB1", warning)

    def test_nos_gets_nos_instrument(self):
        out = normalize_risk_of_bias({"tool": "NOS", "overall_judgement": "good quality"}, "study2")
        self.assertEqual(out["instrument"], "nos")
        self.assertEqual(INSTRUMENT_BY_TOOL["NOS"], "nos")

    def test_explicit_instrument_is_not_overwritten(self):
        out = normalize_risk_of_bias({"tool": "RoB1", "instrument": "custom_id"}, "study3")
        self.assertEqual(out["instrument"], "custom_id")

    def test_none_or_empty_passes_through(self):
        self.assertIsNone(normalize_risk_of_bias(None, "study4"))
        self.assertEqual(normalize_risk_of_bias({}, "study5"), {})


class LoadStudiesLegacyAliasTests(unittest.TestCase):
    def _write_table(self, tmpdir, studies):
        path = os.path.join(tmpdir, "extraction_table.json")
        with open(path, "w") as f:
            json.dump({"framework_version": "1.0.0", "topic": "t", "studies": studies}, f)
        return path

    def test_load_studies_normalizes_legacy_tool_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_table(tmp, [
                {"record_id": "a1", "risk_of_bias": {"tool": "RoB2", "overall_judgement": "high risk"}},
                {"record_id": "a2", "risk_of_bias": {"tool": "NOS", "overall_judgement": "good quality"}},
                {"record_id": "a3", "risk_of_bias": None},
            ])
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                studies = load_studies(path)
        self.assertEqual(studies[0]["risk_of_bias"]["tool"], "RoB1")
        self.assertEqual(studies[0]["risk_of_bias"]["instrument"], "cochrane_rob1_2011")
        self.assertEqual(studies[1]["risk_of_bias"]["instrument"], "nos")
        self.assertIsNone(studies[2]["risk_of_bias"])
        self.assertIn("a1", stderr.getvalue())

    def test_load_studies_rejects_malformed_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "extraction_table.json")
            with open(path, "w") as f:
                json.dump({"studies": "not-a-list"}, f)
            with self.assertRaises(ValueError):
                load_studies(path)


class IsLowRiskRollupTests(unittest.TestCase):
    def test_rob1_low_risk_true(self):
        self.assertTrue(is_low_risk({"tool": "RoB1", "overall_judgement": "low risk"}))

    def test_rob1_high_risk_false(self):
        self.assertFalse(is_low_risk({"tool": "RoB1", "overall_judgement": "high risk"}))

    def test_rob1_unclear_risk_false(self):
        """RoB1 has no "some concerns" middle tier (that's RoB 2) -- an
        "unclear risk" overall judgement is not low risk."""
        self.assertFalse(is_low_risk({"tool": "RoB1", "overall_judgement": "unclear risk"}))

    def test_nos_good_quality_true(self):
        self.assertTrue(is_low_risk({"tool": "NOS", "overall_judgement": "good quality"}))

    def test_nos_poor_quality_false(self):
        self.assertFalse(is_low_risk({"tool": "NOS", "overall_judgement": "poor quality"}))

    def test_missing_rob_returns_none(self):
        self.assertIsNone(is_low_risk(None))

    def test_unsupported_tool_returns_none(self):
        self.assertIsNone(is_low_risk({"tool": "unsupported", "overall_judgement": "n/a"}))


class BuildRobEntryTests(unittest.TestCase):
    def test_proportion_low_risk_with_legacy_and_current_labels(self):
        rows = [
            {"study_id": "s1", "risk_of_bias": {"tool": "RoB1", "overall_judgement": "low risk"}},
            {"study_id": "s2", "risk_of_bias": {"tool": "RoB1", "overall_judgement": "high risk"}},
            {"study_id": "s3", "risk_of_bias": None},
        ]
        entry = build_rob_entry("outcome1", rows)
        self.assertEqual(entry["proportion_low_risk"], 0.5)
        self.assertEqual(entry["missing_assessment"], ["s3"])


if __name__ == "__main__":
    unittest.main()
