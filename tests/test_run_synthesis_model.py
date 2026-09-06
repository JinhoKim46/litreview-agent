"""Unit tests for synthesis/run_synthesis.py's prespecified pooling model:
resolve_synthesis_plan (reading/validating synthesis_plan.json, deciding
model_source) and run()'s always-compute-both-models sensitivity reporting.
Phase 0 correctness fix -- see docs/PLAN.md decision 6 and
schemas/synthesis_plan.schema.json. The automatic I2/Q model-selection rule
this replaces is covered by tests/test_synthesis_heterogeneity.py's
regression guard.
"""
import json
import math
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

    def test_explicit_pm_and_hksj_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            _write_plan(tmp, model="random", signed_at="2026-01-01T00:00:00Z",
                        tau2_estimator="pm", ci_method="hksj")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["tau2_estimator"], "pm")
            self.assertEqual(plan["ci_method"], "hksj")

    def test_invalid_tau2_estimator_in_plan_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_plan(tmp, model="random", signed_at="2026-01-01T00:00:00Z", tau2_estimator="reml")
            with self.assertRaises(jsonschema.exceptions.ValidationError):
                resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))

    def test_invalid_ci_method_in_plan_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_plan(tmp, model="random", signed_at="2026-01-01T00:00:00Z", ci_method="bootstrap")
            with self.assertRaises(jsonschema.exceptions.ValidationError):
                resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))


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

    def test_tau2_estimator_and_ci_method_threaded_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="random", tau2_estimator="pm", ci_method="hksj")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertEqual(es["tau2_estimator"], "pm")
            self.assertEqual(es["ci_method"], "hksj")
            self.assertEqual(es["pooled_effect"]["tau2_estimator"], "pm")
            self.assertEqual(es["pooled_effect"]["ci_method"], "hksj")
            # the sensitivity (fixed) pool uses the same prespecified
            # estimator/ci_method -- never silently reverts to defaults
            self.assertEqual(es["sensitivity"]["tau2_estimator"], "pm")
            self.assertEqual(es["sensitivity"]["ci_method"], "hksj")
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "PONV")
            self.assertEqual(het["tau2_estimator"], "pm")
            self.assertEqual(het["ci_method"], "hksj")

    def test_default_tau2_estimator_and_ci_method_are_dl_and_normal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="fixed")  # no override -- defaults
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertEqual(es["tau2_estimator"], "dl")
            self.assertEqual(es["ci_method"], "normal")

    def test_prediction_interval_present_for_random_model_at_k_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)  # 3 studies -- k=3 >= PI_MIN_K
            result = run(path, os.path.join(tmp, "out"), model="random")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertIsNotNone(es["pooled_effect"]["pi_low"])
            self.assertIsNotNone(es["pooled_effect"]["pi_high"])
            self.assertIsNotNone(es["display_pi_low"])
            self.assertIsNotNone(es["display_pi_high"])
            # RR scale -- display PI must be exponentiated like the CI/estimate
            self.assertAlmostEqual(math.exp(es["pooled_effect"]["pi_low"]), es["display_pi_low"], places=9)

    def test_prediction_interval_absent_for_fixed_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="fixed")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertIsNone(es["pooled_effect"]["pi_low"])
            self.assertIsNone(es["display_pi_low"])

    def test_forest_plot_svg_written_when_prediction_interval_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="random")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertTrue(os.path.exists(es["forest_plot_svg"]))
            with open(es["forest_plot_svg"]) as f:
                svg = f.read()
            self.assertIn("Prediction Interval", svg)


class SynthesisFamilyDispatchTests(unittest.TestCase):
    """docs/PLAN.md M1: run()'s synthesis_family dispatch."""

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

    def test_default_family_is_pairwise_iv_and_pools_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            result = run(path, os.path.join(tmp, "out"), model="fixed")  # no synthesis_family -- default
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            self.assertTrue(es["pooled"])

    def test_structured_narrative_never_pools_regardless_of_k(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)  # k=3 -- would pool under pairwise_iv
            result = run(path, os.path.join(tmp, "out"), model="fixed", synthesis_family="structured_narrative")
            es = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
            het = next(h for h in result["heterogeneity"] if h["outcome"] == "PONV")
            self.assertFalse(es["pooled"])
            self.assertFalse(het["pooled"])
            self.assertIn("structured_narrative", het["reason"])
            self.assertEqual(len(es["studies"]), 3)  # rows are still recorded, just never pooled

    def test_swim_refuses_cleanly_rather_than_fabricate_statistics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            with self.assertRaises(SynthesisPlanError) as ctx:
                run(path, os.path.join(tmp, "out"), model="fixed", synthesis_family="swim")
            self.assertIn("swim", str(ctx.exception).lower())

    def test_descriptive_refuses_cleanly_rather_than_fabricate_statistics(self):
        # docs/PLAN.md M3: a scoping review's manifest allows only
        # "descriptive" -- pooling is forbidden by design, so this must
        # refuse cleanly (never crash on an unrecognized family, never
        # silently fall back to another family's pooling logic).
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            with self.assertRaises(SynthesisPlanError) as ctx:
                run(path, os.path.join(tmp, "out"), model="fixed", synthesis_family="descriptive")
            self.assertIn("descriptive", str(ctx.exception).lower())

    def test_invalid_synthesis_family_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fixture_path(tmp)
            with self.assertRaises(SynthesisPlanError):
                run(path, os.path.join(tmp, "out"), model="fixed", synthesis_family="not_a_real_family")

    def test_resolve_synthesis_plan_defaults_synthesis_family_to_pairwise_iv(self):
        # A plan predating this field (retrospective-plan path, docs/PLAN.md
        # M1) must behave exactly as before -- pairwise_iv, not a crash.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            _write_plan(tmp, model="fixed", signed_at="2026-01-01T00:00:00Z")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["synthesis_family"], "pairwise_iv")

    def test_resolve_synthesis_plan_preserves_explicit_synthesis_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            _write_plan(tmp, model="fixed", signed_at="2026-01-01T00:00:00Z", synthesis_family="structured_narrative")
            plan = resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))
            self.assertEqual(plan["synthesis_family"], "structured_narrative")

    def test_invalid_synthesis_family_in_plan_raises_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_plan(tmp, model="fixed", signed_at="2026-01-01T00:00:00Z", synthesis_family="not_a_real_family")
            with self.assertRaises(jsonschema.exceptions.ValidationError):
                resolve_synthesis_plan("t", None, _fake_safe_topic_path(tmp))


if __name__ == "__main__":
    unittest.main()
