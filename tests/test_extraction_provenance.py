"""Unit tests for extraction provenance pass-through (docs/PLAN.md PR
p0-11-extraction-provenance): a study's `reports`/`by`/`verified_by`
fields and each `effect_data` entry's `source` (quote/locator/notes) block
must survive synthesis/run_synthesis.py's flatten_rows -> process_outcome_group
-> effect_sizes.json pipeline unchanged, never dropped or recomputed.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis.run_synthesis import flatten_rows, run


def _study_with_provenance(record_id, events_t, total_t, events_c, total_c, **overrides):
    study = {
        "record_id": record_id, "author_year": record_id, "study_design": "RCT",
        "outcomes_measured": ["PONV"],
        "risk_of_bias": {"tool": "RoB1", "overall_judgement": "low risk"},
        "reports": [{"citation": f"{record_id} main report", "doi": "10.1234/abcd", "url": "https://doi.org/10.1234/abcd"}],
        "by": "claude (single extractor pass)",
        "verified_by": None,
        "effect_data": [{
            "outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
            "intervention_arm": {"label": "drug", "events": events_t, "total": total_t},
            "comparator_arm": {"label": "placebo", "events": events_c, "total": total_c},
            "source": {"quote": "12 of 60 patients in the treatment group experienced PONV.",
                       "locator": "Table 2", "notes": None},
        }],
    }
    study.update(overrides)
    return study


class FlattenRowsProvenanceTests(unittest.TestCase):
    def test_quantitative_row_carries_study_level_provenance(self):
        study = _study_with_provenance("s1", 12, 60, 25, 60)
        rows = flatten_rows([study])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["reports"], study["reports"])
        self.assertEqual(row["by"], "claude (single extractor pass)")
        self.assertIsNone(row["verified_by"])

    def test_qualitative_row_also_carries_study_level_provenance(self):
        study = _study_with_provenance("s1", 12, 60, 25, 60)
        study["outcomes_measured"] = ["PONV", "narrative-only outcome"]  # no matching effect_data
        rows = flatten_rows([study])
        narrative_row = next(r for r in rows if r["outcome"] == "narrative-only outcome")
        self.assertEqual(narrative_row["reports"], study["reports"])
        self.assertEqual(narrative_row["by"], "claude (single extractor pass)")

    def test_verified_by_set_when_present(self):
        study = _study_with_provenance("s1", 12, 60, 25, 60, verified_by="Dr. Reviewer")
        rows = flatten_rows([study])
        self.assertEqual(rows[0]["verified_by"], "Dr. Reviewer")

    def test_missing_provenance_fields_are_none_not_a_crash(self):
        study = {
            "record_id": "s1", "author_year": "s1", "study_design": "RCT",
            "outcomes_measured": ["PONV"], "effect_data": [],
        }
        rows = flatten_rows([study])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["reports"])
        self.assertIsNone(rows[0]["by"])
        self.assertIsNone(rows[0]["verified_by"])

    def test_effect_data_source_untouched_by_flatten(self):
        # source lives inside effect_data itself, verbatim -- flatten_rows
        # must not need to (and must not) touch it separately.
        study = _study_with_provenance("s1", 12, 60, 25, 60)
        rows = flatten_rows([study])
        self.assertEqual(rows[0]["effect_data"]["source"], study["effect_data"][0]["source"])


class RunEffectSizesProvenanceTests(unittest.TestCase):
    def _fixture_path(self, tmp, studies):
        fixture = {"framework_version": "1.0.0", "topic": "t", "studies": studies}
        path = os.path.join(tmp, "extraction_table.json")
        with open(path, "w") as f:
            json.dump(fixture, f)
        return path

    def test_source_and_provenance_survive_into_effect_sizes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            studies = [
                _study_with_provenance("s1", 12, 60, 25, 60),
                _study_with_provenance("s2", 8, 50, 20, 50),
            ]
            path = self._fixture_path(tmp, studies)
            result = run(path, os.path.join(tmp, "out"), model="fixed", model_source="protocol")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            for i, study_effect in enumerate(es["studies"]):
                expected_study = studies[i]
                self.assertEqual(study_effect["source"], expected_study["effect_data"][0]["source"])
                self.assertEqual(study_effect["reports"], expected_study["reports"])
                self.assertEqual(study_effect["by"], expected_study["by"])
                self.assertIsNone(study_effect["verified_by"])

    def test_provenance_persisted_to_disk_effect_sizes_json(self):
        # Confirm the on-disk file, not just the in-memory return value,
        # carries the provenance fields -- effect_sizes.json is what
        # /litreview-report actually reads.
        with tempfile.TemporaryDirectory() as tmp:
            studies = [_study_with_provenance("s1", 12, 60, 25, 60), _study_with_provenance("s2", 8, 50, 20, 50)]
            path = self._fixture_path(tmp, studies)
            out_dir = os.path.join(tmp, "out")
            run(path, out_dir, model="fixed", model_source="protocol")
            with open(os.path.join(out_dir, "effect_sizes.json")) as f:
                on_disk = json.load(f)
            es = next(e for e in on_disk if e["outcome"] == "PONV")
            self.assertEqual(es["studies"][0]["source"]["locator"], "Table 2")
            self.assertEqual(es["studies"][0]["reports"][0]["doi"], "10.1234/abcd")

    def test_missing_source_is_none_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare_studies = [
                {
                    "record_id": "s1", "author_year": "s1", "study_design": "RCT",
                    "outcomes_measured": ["PONV"],
                    "effect_data": [{"outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
                                      "intervention_arm": {"label": "drug", "events": 12, "total": 60},
                                      "comparator_arm": {"label": "placebo", "events": 25, "total": 60}}],
                },
                {
                    "record_id": "s2", "author_year": "s2", "study_design": "RCT",
                    "outcomes_measured": ["PONV"],
                    "effect_data": [{"outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
                                      "intervention_arm": {"label": "drug", "events": 8, "total": 50},
                                      "comparator_arm": {"label": "placebo", "events": 20, "total": 50}}],
                },
            ]
            path = self._fixture_path(tmp, bare_studies)
            result = run(path, os.path.join(tmp, "out"), model="fixed", model_source="protocol")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            for study_effect in es["studies"]:
                self.assertIsNone(study_effect["source"])
                self.assertIsNone(study_effect["reports"])
                self.assertIsNone(study_effect["by"])
                self.assertIsNone(study_effect["verified_by"])

    def test_narrative_fallback_outcome_unaffected_by_provenance_fields(self):
        # A study with only one usable effect-data study (k < POOL_MIN_K=2)
        # falls back to narrative -- provenance pass-through must not
        # interfere with that gate.
        with tempfile.TemporaryDirectory() as tmp:
            studies = [_study_with_provenance("s1", 12, 60, 25, 60)]
            path = self._fixture_path(tmp, studies)
            result = run(path, os.path.join(tmp, "out"), model="fixed", model_source="protocol")
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "PONV")
            self.assertFalse(het["pooled"])


if __name__ == "__main__":
    unittest.main()
