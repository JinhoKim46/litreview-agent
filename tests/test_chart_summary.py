"""Unit tests for tools/chart_summary.py (docs/PLAN.md M3 S7)."""
import json
import os
import shutil
import sys
import unittest

import jsonschema

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import chart_summary, charting_gate, classification_gate, path_policy

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas", "descriptive_summary.schema.json")


class FrequencyAndCrossTabTests(unittest.TestCase):
    def test_compute_frequencies_counts_scalar_values(self):
        studies = [
            {"data": {"year": 2024, "venue": "MICCAI"}},
            {"data": {"year": 2024, "venue": "NeurIPS"}},
            {"data": {"year": 2023, "venue": "MICCAI"}},
        ]
        freq = chart_summary.compute_frequencies(studies, "data", ["year", "venue"])
        self.assertEqual(freq["year"], {"2024": 2, "2023": 1})
        self.assertEqual(freq["venue"], {"MICCAI": 2, "NeurIPS": 1})

    def test_compute_frequencies_counts_each_element_of_a_multi_valued_facet(self):
        studies = [
            {"codes": {"dataset": ["fastMRI", "BraTS"]}},
            {"codes": {"dataset": ["fastMRI"]}},
        ]
        freq = chart_summary.compute_frequencies(studies, "codes", ["dataset"])
        self.assertEqual(freq["dataset"], {"fastMRI": 2, "BraTS": 1})

    def test_compute_frequencies_missing_value_becomes_not_reported(self):
        studies = [{"data": {"year": 2024}}, {"data": {}}]
        freq = chart_summary.compute_frequencies(studies, "data", ["year"])
        self.assertEqual(freq["year"], {"2024": 1, "not reported": 1})

    def test_compute_cross_tabs_one_entry_per_unordered_pair(self):
        studies = [
            {"codes": {"research_type": "validation", "dataset": "public"}},
            {"codes": {"research_type": "validation", "dataset": "public"}},
            {"codes": {"research_type": "evaluation", "dataset": "private"}},
        ]
        cross_tabs = chart_summary.compute_cross_tabs(studies, "codes", ["research_type", "dataset"])
        self.assertEqual(len(cross_tabs), 1)
        self.assertEqual(cross_tabs[0]["facet_a"], "research_type")
        self.assertEqual(cross_tabs[0]["facet_b"], "dataset")
        self.assertEqual(cross_tabs[0]["counts"], {"validation|public": 2, "evaluation|private": 1})

    def test_compute_cross_tabs_expands_multi_valued_facets_as_a_cartesian_product(self):
        studies = [{"codes": {"a": ["x", "y"], "b": ["p"]}}]
        cross_tabs = chart_summary.compute_cross_tabs(studies, "codes", ["a", "b"])
        self.assertEqual(cross_tabs[0]["counts"], {"x|p": 1, "y|p": 1})


class RunTests(unittest.TestCase):
    CHARTING_SLUG = "chart-summary-charting-test-topic"
    CLASSIFICATION_SLUG = "chart-summary-classification-test-topic"

    def setUp(self):
        self.charting_dir = path_policy.RESULTS_ROOT / self.CHARTING_SLUG
        self.classification_dir = path_policy.RESULTS_ROOT / self.CLASSIFICATION_SLUG
        for d in (self.charting_dir, self.classification_dir):
            if d.exists():
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)
        (self.charting_dir / "protocol.json").write_text(json.dumps({"method": {"id": "scoping_review"}}))
        (self.classification_dir / "protocol.json").write_text(json.dumps({"method": {"id": "systematic_mapping_study"}}))

    def tearDown(self):
        for d in (self.charting_dir, self.classification_dir):
            if d.exists():
                shutil.rmtree(d)

    def test_refuses_before_charting_form_is_frozen(self):
        with self.assertRaises(chart_summary.ChartSummaryError):
            chart_summary.run(self.CHARTING_SLUG, topic_dir=self.charting_dir)

    def test_refuses_before_classification_scheme_is_frozen(self):
        with self.assertRaises(chart_summary.ChartSummaryError):
            chart_summary.run(self.CLASSIFICATION_SLUG, topic_dir=self.classification_dir)

    def test_refuses_on_drifted_charting_row(self):
        table = charting_gate.freeze(self.charting_dir, self.CHARTING_SLUG, ["year"])
        table["studies"].append({"record_id": "bad1", "data": {}})
        (self.charting_dir / "charting_table.json").write_text(json.dumps(table))
        with self.assertRaises(chart_summary.ChartSummaryError):
            chart_summary.run(self.CHARTING_SLUG, topic_dir=self.charting_dir)

    def test_charting_run_writes_frequencies_and_no_cross_tabs(self):
        table = charting_gate.freeze(self.charting_dir, self.CHARTING_SLUG, ["year", "venue"])
        table["studies"] = [
            {"record_id": "r1", "data": {"year": 2024, "venue": "MICCAI"}},
            {"record_id": "r2", "data": {"year": 2024, "venue": "NeurIPS"}},
        ]
        (self.charting_dir / "charting_table.json").write_text(json.dumps(table))

        result = chart_summary.run(self.CHARTING_SLUG, topic_dir=self.charting_dir)
        self.assertEqual(result["capture_mode"], "charting")
        self.assertEqual(result["n_studies"], 2)
        self.assertEqual(result["category_frequencies"]["year"], {"2024": 2})
        self.assertEqual(result["cross_tabs"], [])
        written = json.loads((self.charting_dir / "synthesis" / "descriptive_summary.json").read_text())
        self.assertEqual(written, result)

    def test_classification_run_writes_frequencies_and_cross_tabs(self):
        table = classification_gate.freeze(self.classification_dir, self.CLASSIFICATION_SLUG, [
            {"name": "research_type", "categories": ["validation", "evaluation"]},
            {"name": "dataset", "categories": ["public", "private"]},
        ])
        table["studies"] = [
            {"record_id": "r1", "codes": {"research_type": "validation", "dataset": "public"}},
            {"record_id": "r2", "codes": {"research_type": "evaluation", "dataset": "private"}},
        ]
        (self.classification_dir / "classification_table.json").write_text(json.dumps(table))

        result = chart_summary.run(self.CLASSIFICATION_SLUG, topic_dir=self.classification_dir)
        self.assertEqual(result["capture_mode"], "classification")
        self.assertEqual(result["category_frequencies"]["research_type"], {"validation": 1, "evaluation": 1})
        self.assertEqual(len(result["cross_tabs"]), 1)
        self.assertEqual(result["cross_tabs"][0]["counts"], {"validation|public": 1, "evaluation|private": 1})

    def test_cli_smoke(self):
        charting_gate.freeze(self.charting_dir, self.CHARTING_SLUG, ["year"])
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = chart_summary.main(["--topic", self.CHARTING_SLUG])
        self.assertEqual(rc, 0)
        self.assertIn("capture_mode=charting", buf.getvalue())

    def test_cli_refuses_for_invalid_slug(self):
        rc = chart_summary.main(["--topic", "../etc/passwd"])
        self.assertEqual(rc, 1)

    def test_charting_output_validates_against_its_schema(self):
        table = charting_gate.freeze(self.charting_dir, self.CHARTING_SLUG, ["year", "venue"])
        table["studies"] = [{"record_id": "r1", "data": {"year": 2024, "venue": "MICCAI"}}]
        (self.charting_dir / "charting_table.json").write_text(json.dumps(table))
        result = chart_summary.run(self.CHARTING_SLUG, topic_dir=self.charting_dir)
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        jsonschema.validate(result, schema)

    def test_classification_output_validates_against_its_schema(self):
        table = classification_gate.freeze(self.classification_dir, self.CLASSIFICATION_SLUG, [
            {"name": "research_type", "categories": ["validation"]},
        ])
        table["studies"] = [{"record_id": "r1", "codes": {"research_type": "validation"}}]
        (self.classification_dir / "classification_table.json").write_text(json.dumps(table))
        result = chart_summary.run(self.CLASSIFICATION_SLUG, topic_dir=self.classification_dir)
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        jsonschema.validate(result, schema)


if __name__ == "__main__":
    unittest.main()
