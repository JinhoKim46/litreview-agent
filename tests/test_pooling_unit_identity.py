"""Unit tests for the core pooling-unit-identity refusal predicate
(docs/ROADMAP.md M5): synthesis/run_synthesis.py's
check_pooling_unit_identity(), plus its wiring into run()/
process_outcome_group() via synthesis_plan.json's pooling_unit.identity_fields.

Deliberately pack-agnostic -- no packs/*.json involved anywhere here. The
predicate must work purely from a synthetic identity_fields list, since it
has to behave identically whether those field names were hand-typed at
G-Protocol or pre-filled from a pack's own pooling_unit_identity_proposal
(docs/ROADMAP.md M5's exit criterion: "refused by the core rules, not by
pack-specific code").
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis.run_synthesis import check_pooling_unit_identity, run


def _rr_study(record_id, events_t, total_t, events_c, total_c, **extra_fields):
    study = {
        "record_id": record_id, "author_year": record_id, "study_design": "RCT",
        "outcomes_measured": ["accuracy"],
        "risk_of_bias": {"tool": "RoB1", "overall_judgement": "low risk"},
        "effect_data": [{"outcome": "accuracy", "measure_type": "RR", "timepoint": "test set",
                          "intervention_arm": {"label": "model", "events": events_t, "total": total_t},
                          "comparator_arm": {"label": "baseline", "events": events_c, "total": total_c}}],
    }
    study.update(extra_fields)
    return study


def _write_fixture(tmp, studies):
    fixture = {"framework_version": "1.0.0", "topic": "t", "studies": studies}
    path = os.path.join(tmp, "extraction_table.json")
    with open(path, "w") as f:
        json.dump(fixture, f)
    return path


class CheckPoolingUnitIdentityTests(unittest.TestCase):
    """Direct unit tests of the predicate function, independent of run()."""

    def _rows(self, *pairs):
        return [{"study_id": sid, "study": study} for sid, study in pairs]

    def test_no_identity_fields_declared_is_a_no_op(self):
        rows = self._rows(("s1", {"dataset_id": "A"}), ("s2", {"dataset_id": "B"}))
        self.assertIsNone(check_pooling_unit_identity(rows, None))
        self.assertIsNone(check_pooling_unit_identity(rows, []))

    def test_matching_values_pool_normally(self):
        rows = self._rows(("s1", {"dataset_id": "A"}), ("s2", {"dataset_id": "A"}))
        self.assertIsNone(check_pooling_unit_identity(rows, ["dataset_id"]))

    def test_mismatched_values_refuse_naming_field_and_studies(self):
        rows = self._rows(("s1", {"dataset_id": "A"}), ("s2", {"dataset_id": "B"}))
        reason = check_pooling_unit_identity(rows, ["dataset_id"])
        self.assertIsNotNone(reason)
        self.assertIn("dataset_id", reason)
        self.assertIn("s1", reason)
        self.assertIn("s2", reason)

    def test_study_missing_the_field_entirely_refuses_with_a_distinct_message(self):
        # s2 never recorded dataset_id at all -- must not be silently treated
        # as "agreeing" with s1 just because neither has a mismatching value.
        rows = self._rows(("s1", {"dataset_id": "A"}), ("s2", {}))
        reason = check_pooling_unit_identity(rows, ["dataset_id"])
        self.assertIsNotNone(reason)
        self.assertIn("not recorded", reason)
        self.assertIn("s2", reason)
        self.assertNotIn("s1", reason.split("not recorded")[1])  # only the missing study is named as missing

    def test_two_studies_both_missing_the_field_still_refuses(self):
        # The dangerous silent-pass case: None == None must never read as "identical".
        rows = self._rows(("s1", {}), ("s2", {}))
        reason = check_pooling_unit_identity(rows, ["dataset_id"])
        self.assertIsNotNone(reason)
        self.assertIn("not recorded", reason)


class RunWiredIdentityCheckTests(unittest.TestCase):
    """End-to-end through run()/process_outcome_group() -- proves the
    refusal surfaces via the same narrative-fallback channel
    (pooled: False + reason) an ordinary k_min/structured_narrative
    refusal already uses, not a second, separate refusal path."""

    def test_backward_compatible_no_identity_fields_pools_as_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(tmp, [
                _rr_study("s1", 12, 60, 25, 60, dataset_id="A"),
                _rr_study("s2", 8, 50, 20, 50, dataset_id="B"),
                _rr_study("s3", 15, 55, 22, 55, dataset_id="C"),
            ])
            result = run(path, os.path.join(tmp, "out"), model="fixed")  # no identity_fields passed
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "accuracy")
            self.assertTrue(het["pooled"])

    def test_matching_identity_fields_pool_normally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(tmp, [
                _rr_study("s1", 12, 60, 25, 60, dataset_id="A"),
                _rr_study("s2", 8, 50, 20, 50, dataset_id="A"),
                _rr_study("s3", 15, 55, 22, 55, dataset_id="A"),
            ])
            result = run(path, os.path.join(tmp, "out"), model="fixed", identity_fields=["dataset_id"])
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "accuracy")
            self.assertTrue(het["pooled"])

    def test_mismatched_identity_fields_refuse_via_narrative_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(tmp, [
                _rr_study("s1", 12, 60, 25, 60, dataset_id="A"),
                _rr_study("s2", 8, 50, 20, 50, dataset_id="B"),
                _rr_study("s3", 15, 55, 22, 55, dataset_id="A"),
            ])
            result = run(path, os.path.join(tmp, "out"), model="fixed", identity_fields=["dataset_id"])
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "accuracy")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "accuracy")
            self.assertFalse(het["pooled"])
            self.assertIn("dataset_id", het["reason"])
            self.assertFalse(es["pooled"])  # never silently pools despite the mismatch

    def test_missing_identity_field_on_one_study_refuses_not_silently_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_fixture(tmp, [
                _rr_study("s1", 12, 60, 25, 60, dataset_id="A"),
                _rr_study("s2", 8, 50, 20, 50),  # never recorded dataset_id
                _rr_study("s3", 15, 55, 22, 55, dataset_id="A"),
            ])
            result = run(path, os.path.join(tmp, "out"), model="fixed", identity_fields=["dataset_id"])
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "accuracy")
            self.assertFalse(het["pooled"])
            self.assertIn("not recorded", het["reason"])
            self.assertIn("s2", het["reason"])


if __name__ == "__main__":
    unittest.main()
