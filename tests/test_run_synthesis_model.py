"""Unit tests for synthesis/run_synthesis.py's prespecified pooling model:
resolve_synthesis_plan (reading/validating synthesis_plan.json, deciding
model_source) and run()'s always-compute-both-models sensitivity reporting.
Phase 0 correctness fix -- see docs/PLAN.md decision 6 and
schemas/synthesis_plan.schema.json. The automatic I2/Q model-selection rule
this replaces is covered by tests/test_synthesis_heterogeneity.py's
regression guard.
"""
import json
import os
import sys
import tempfile
import unittest

import jsonschema

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis.run_synthesis import SynthesisPlanError, resolve_synthesis_plan, run


def _fake_safe_topic_path(base_dir):
    """A stand-in for tools.path_policy.safe_topic_path that just joins
    under a tempdir -- resolve_synthesis_plan only needs the callable
    contract (slug, *parts) -> path, not the real slug/containment checks
    (those are tools/path_policy.py's own, already-tested job)."""
    def _fn(_slug, *parts):
        return os.path.join(base_dir, *parts)
    return _fn


def _write_plan(base_dir, **fields):
    with open(os.path.join(base_dir, "synthesis_plan.json"), "w") as f:
        json.dump(fields, f)


def _write_raw(base_dir, source_name, fetched_at):
    raw_dir = os.path.join(base_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, f"{source_name}.json"), "w") as f:
        json.dump({"meta": {"source": source_name, "fetched_at": fetched_at}, "results": []}, f)


class ResolveSynthesisPlanTests(unittest.TestCase):
    def test_missing_plan_and_no_override_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SynthesisPlanError):
                resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))

    def test_override_without_any_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = resolve_synthesis_plan("t", "fixed", _fake_safe_topic_path(tmp))
            self.assertEqual(plan["model"], "fixed")
            self.assertEqual(plan["model_source"], "cli_override")

    def test_plan_signed_before_first_run_is_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_plan(tmp, model="random", signed_at="2026-01-01T00:00:00Z")
            _write_raw(tmp, "src1", "2026-01-02T00:00:00Z")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["model"], "random")
            self.assertEqual(plan["model_source"], "protocol")

    def test_plan_signed_after_first_run_is_post_hoc(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "src1", "2026-01-01T00:00:00Z")
            _write_plan(tmp, model="random", signed_at="2026-01-02T00:00:00Z")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["model_source"], "post_hoc")

    def test_no_raw_files_yet_is_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            _write_plan(tmp, model="fixed", signed_at="2026-01-01T00:00:00Z")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["model_source"], "protocol")

    def test_retrospective_flag_forces_protocol_even_after_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "src1", "2020-01-01T00:00:00Z")
            _write_plan(tmp, model="fixed", signed_at="2026-01-02T00:00:00Z", retrospective=True)
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["model_source"], "protocol")

    def test_cli_override_wins_over_post_hoc_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "src1", "2020-01-01T00:00:00Z")
            _write_plan(tmp, model="fixed", signed_at="2026-01-02T00:00:00Z")
            plan = resolve_synthesis_plan("t", "random", _fake_safe_topic_path(tmp))
            self.assertEqual(plan["model"], "random")
            self.assertEqual(plan["model_source"], "cli_override")

    def test_invalid_model_value_in_plan_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_plan(tmp, model="banana", signed_at="2026-01-01T00:00:00Z")
            with self.assertRaises(jsonschema.exceptions.ValidationError):
                resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))

    def test_missing_signed_at_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_plan(tmp, model="fixed")
            with self.assertRaises(jsonschema.exceptions.ValidationError):
                resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))

    def test_defaults_filled_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            _write_plan(tmp, model="random", signed_at="2026-01-01T00:00:00Z")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["tau2_estimator"], "dl")
            self.assertEqual(plan["ci_method"], "normal")
            self.assertEqual(plan["k_min"], 2)

    def test_explicit_k_min_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            _write_plan(tmp, model="fixed", signed_at="2026-01-01T00:00:00Z", k_min=5)
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["k_min"], 5)


def _rr_study(record_id, events_t, total_t, events_c, total_c):
    return {
        "record_id": record_id, "author_year": record_id, "study_design": "RCT",
        "outcomes_measured": ["PONV"],
        "risk_of_bias": {"tool": "RoB1", "overall_judgement": "low risk"},
        "effect_data": [{"outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
                          "intervention_arm": {"label": "drug", "events": events_t, "total": total_t},
                          "comparator_arm": {"label": "placebo", "events": events_c, "total": total_c}}],
    }


class RunModelAndSensitivityTests(unittest.TestCase):
    def _fixture_path(self, tmp):
        fixture = {"framework_version": "1.0.0", "topic": "t", "studies": [
            _rr_study("s1", 12, 60, 25, 60),
            _rr_study("s2", 8, 50, 20, 50),
            _rr_study("s3", 15, 55, 22, 55),
        ]}
        path = os.path.join(tmp, "extraction_table.json")
        with open(path, "w") as f:
            json.dump(fixture, f)
        return path

    def test_run_rejects_invalid_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            with self.assertRaises(ValueError):
                run(path, os.path.join(tmp, "out"), model="banana")

    def test_pooled_outcome_carries_model_source_and_sensitivity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="fixed", model_source="protocol")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertEqual(es["model"], "fixed")
            self.assertEqual(es["model_source"], "protocol")
            self.assertEqual(es["sensitivity"]["model"], "random")
            for key in ("pooled_effect", "se", "ci_low", "ci_high", "tau2", "display_estimate", "display_ci_low", "display_ci_high"):
                self.assertIn(key, es["sensitivity"])
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "PONV")
            self.assertEqual(het["model"], "fixed")
            self.assertEqual(het["model_source"], "protocol")

    def test_switching_primary_model_swaps_sensitivity_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="random", model_source="cli_override")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertEqual(es["model"], "random")
            self.assertEqual(es["sensitivity"]["model"], "fixed")

    def test_k_min_override_forces_narrative_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="fixed", k_min=5)
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "PONV")
            self.assertFalse(het["pooled"])
            self.assertIn("need >= 5", het["reason"])


if __name__ == "__main__":
    unittest.main()
