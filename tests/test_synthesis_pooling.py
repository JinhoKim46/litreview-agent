"""Unit tests for synthesis/pooling.py.

Worked example: the two forest plots in
references/papers/kjae-2018-71-2-103.pdf (Ahn & Kang, "Introduction to
systematic review and meta-analysis"), Figs. 3 and 4 -- the same
per-study events/totals used by tests/test_synthesis_heterogeneity.py,
converted to log-RR effects/variances with the standard formula (Cochrane
Handbook 10.4.3.1):
    logRR = ln((a/n1) / (c/n2))
    Var(logRR) = 1/a - 1/n1 + 1/c - 1/n2

Two kinds of expected values are checked against pool_effects()'s output:

1. Hand-derived plain inverse-variance / DerSimonian-Laird arithmetic,
   computed independently in this file (not by calling pool_effects or
   re-deriving statsmodels' own formula) -- an exact regression check.
2. The paper's own printed pooled RR / 95% CI / tau2 -- a sanity check
   only, with a generous delta, since the paper pools with Mantel-Haenszel
   weights (RevMan's default for dichotomous data) while pool_effects
   uses generic inverse-variance weights; the two methods agree closely
   but not exactly. Fig. 3's random-effects line is the standout case:
   IV and DerSimonian-Laird weighting happen to land almost exactly on
   the paper's printed 0.83 [0.39, 1.76], tau2 = 0.91, so that one gets a
   tight delta too.
"""
import math
import os
import sys
import unittest

from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis.pooling import pool_effects

# Fig. 3: "Forest plot analyzed by two different models using the same data"
# -- heterogeneous data. (experimental_events, experimental_total, control_events, control_total)
# Paper's Total (95% CI): fixed 0.81 [0.67, 0.99]; random 0.83 [0.39, 1.76], Tau2 = 0.91.
FIG3_STUDIES = [
    (5, 60, 12, 60),
    (16, 40, 8, 40),
    (3, 36, 6, 38),
    (42, 150, 3, 150),
    (7, 78, 50, 80),
    (25, 120, 50, 120),
    (1, 6, 2, 7),
    (32, 62, 32, 63),
]

# Fig. 4: "Forest plot representing homogeneous data."
# Paper's Total (95% CI): fixed 0.52 [0.40, 0.69] (only a fixed-effect model reported).
FIG4_STUDIES = [
    (3, 37, 6, 24),
    (7, 106, 15, 104),
    (17, 52, 36, 36),
    (3, 30, 7, 48),
    (6, 36, 5, 28),
    (16, 96, 17, 95),
    (3, 66, 5, 68),
]


def _log_rr_inputs(studies):
    effects, variances = [], []
    for a, n1, c, n2 in studies:
        rr = (a / n1) / (c / n2)
        effects.append(math.log(rr))
        variances.append(1 / a - 1 / n1 + 1 / c - 1 / n2)
    return effects, variances


def _hand_pooled(effects, variances):
    """Independent plain inverse-variance / DerSimonian-Laird arithmetic,
    mirroring pooling.py's own __main__ self-check but against this file's
    worked-example data instead of synthetic numbers."""
    w = [1 / v for v in variances]
    sum_w = sum(w)
    fixed = sum(wi * e for wi, e in zip(w, effects)) / sum_w
    fixed_se = (1 / sum_w) ** 0.5

    Q = sum(wi * (e - fixed) ** 2 for wi, e in zip(w, effects))
    df = len(effects) - 1
    C = sum_w - sum(wi ** 2 for wi in w) / sum_w
    tau2 = max(0.0, (Q - df) / C)

    w_re = [1 / (v + tau2) for v in variances]
    sum_w_re = sum(w_re)
    random = sum(wi * e for wi, e in zip(w_re, effects)) / sum_w_re
    random_se = (1 / sum_w_re) ** 0.5

    return {
        "fixed": fixed, "fixed_se": fixed_se,
        "tau2": tau2, "random": random, "random_se": random_se,
    }


class PoolEffectsWorkedExampleTests(unittest.TestCase):
    def test_fig4_fixed_matches_hand_calc_and_paper(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES)
        expected = _hand_pooled(effects, variances)

        result = pool_effects(effects, variances, "fixed")
        self.assertEqual(result["model"], "fixed")
        self.assertEqual(result["k"], 7)
        self.assertEqual(result["tau2"], 0.0)
        # Exact against independently hand-derived inverse-variance arithmetic.
        self.assertAlmostEqual(result["pooled_effect"], expected["fixed"], places=9)
        self.assertAlmostEqual(result["se"], expected["fixed_se"], places=9)
        # Loose sanity check against the paper's M-H-pooled 0.52 [0.40, 0.69]
        # (IV weighting differs from M-H, so only the ballpark should agree).
        rr = math.exp(result["pooled_effect"])
        self.assertAlmostEqual(rr, 0.52, delta=0.06)
        self.assertAlmostEqual(math.exp(result["ci_low"]), 0.40, delta=0.06)
        self.assertAlmostEqual(math.exp(result["ci_high"]), 0.69, delta=0.07)

    def test_fig4_random_has_nonzero_tau2_from_moderate_heterogeneity(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES)
        expected = _hand_pooled(effects, variances)

        result = pool_effects(effects, variances, "random")
        self.assertEqual(result["model"], "random")
        self.assertAlmostEqual(result["tau2"], expected["tau2"], places=9)
        self.assertAlmostEqual(result["pooled_effect"], expected["random"], places=6)
        self.assertAlmostEqual(result["se"], expected["random_se"], places=6)
        self.assertGreater(result["tau2"], 0.0)

    def test_fig3_random_matches_hand_calc_and_paper_closely(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        expected = _hand_pooled(effects, variances)

        result = pool_effects(effects, variances, "random")
        self.assertEqual(result["k"], 8)
        # Exact against independently hand-derived DerSimonian-Laird arithmetic.
        self.assertAlmostEqual(result["tau2"], expected["tau2"], places=9)
        self.assertAlmostEqual(result["pooled_effect"], expected["random"], places=6)
        self.assertAlmostEqual(result["se"], expected["random_se"], places=6)
        # This is the case where IV/DL weighting lands almost exactly on the
        # paper's printed M-H random-effects line: 0.83 [0.39, 1.76], tau2=0.91.
        self.assertAlmostEqual(result["tau2"], 0.91, delta=0.01)
        self.assertAlmostEqual(math.exp(result["pooled_effect"]), 0.83, delta=0.01)
        self.assertAlmostEqual(math.exp(result["ci_low"]), 0.39, delta=0.01)
        self.assertAlmostEqual(math.exp(result["ci_high"]), 1.76, delta=0.02)

    def test_fig3_fixed_matches_hand_calc(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        expected = _hand_pooled(effects, variances)

        result = pool_effects(effects, variances, "fixed")
        self.assertEqual(result["tau2"], 0.0)
        self.assertAlmostEqual(result["pooled_effect"], expected["fixed"], places=9)
        self.assertAlmostEqual(result["se"], expected["fixed_se"], places=9)
        # Sanity check against the paper's fixed-effect line 0.81 [0.67, 0.99].
        self.assertAlmostEqual(math.exp(result["pooled_effect"]), 0.81, delta=0.06)

    def test_ci_brackets_pooled_effect(self):
        for studies in (FIG3_STUDIES, FIG4_STUDIES):
            effects, variances = _log_rr_inputs(studies)
            for model in ("fixed", "random"):
                result = pool_effects(effects, variances, model)
                self.assertLess(result["ci_low"], result["pooled_effect"])
                self.assertLess(result["pooled_effect"], result["ci_high"])


class PauleMandelTests(unittest.TestCase):
    """Paule-Mandel tau2 has no closed form -- it's defined as the tau2 that
    solves Q(tau2) = k-1 (DerSimonian & Kacker 2007 Appendix 8). Rather than
    re-implementing the iterative solver independently (duplicating
    statsmodels' own algorithm risks the same bug in both places), these
    tests verify the returned tau2_pm actually satisfies that defining
    equation -- an independent correctness check on the *property* PM tau2
    must have, not a re-derivation of how to compute it."""

    def _q_at(self, effects, variances, tau2):
        w = [1 / (v + tau2) for v in variances]
        sum_w = sum(w)
        mean = sum(wi * e for wi, e in zip(w, effects)) / sum_w
        return sum(wi * (e - mean) ** 2 for wi, e in zip(w, effects))

    def test_pm_tau2_satisfies_defining_equation_fig3(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        result = pool_effects(effects, variances, "random", tau2_estimator="pm")
        self.assertEqual(result["tau2_estimator"], "pm")
        df = len(effects) - 1
        self.assertAlmostEqual(self._q_at(effects, variances, result["tau2"]), df, delta=1e-4)

    def test_pm_tau2_satisfies_defining_equation_fig4(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES)
        result = pool_effects(effects, variances, "random", tau2_estimator="pm")
        df = len(effects) - 1
        self.assertAlmostEqual(self._q_at(effects, variances, result["tau2"]), df, delta=1e-4)

    def test_pm_differs_from_dl_on_heterogeneous_data(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        dl = pool_effects(effects, variances, "random", tau2_estimator="dl")
        pm = pool_effects(effects, variances, "random", tau2_estimator="pm")
        # Not required to differ by any particular amount, but on this
        # genuinely heterogeneous worked example they should not coincide --
        # if they did, that would suggest tau2_estimator is being ignored.
        self.assertNotAlmostEqual(dl["tau2"], pm["tau2"], places=3)

    def test_pm_fixed_effect_pool_still_reports_zero_tau2(self):
        # tau2_estimator only matters for the random branch -- a fixed pool
        # has no between-study variance to estimate either way.
        effects, variances = _log_rr_inputs(FIG4_STUDIES)
        result = pool_effects(effects, variances, "fixed", tau2_estimator="pm")
        self.assertEqual(result["tau2"], 0.0)

    def test_invalid_tau2_estimator_raises(self):
        with self.assertRaises(ValueError):
            pool_effects([0.1, 0.2], [0.01, 0.02], "random", tau2_estimator="reml")


class NegativeTau2TruncationTests(unittest.TestCase):
    """statsmodels' DL/chi2 branch does not floor tau2 at 0 internally
    (unlike its Paule-Mandel iterative solver, which does) -- for
    sufficiently homogeneous data this can produce a negative raw tau2.
    Cochrane Handbook 10.10.4.2 (and every widely used implementation)
    truncates a negative between-study-variance estimate to 0, at which
    point the random-effects weights equal the fixed-effects weights
    exactly -- so the truncated random pool must equal the fixed pool."""

    def test_homogeneous_subset_truncates_and_matches_fixed(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:4])  # triggers negative raw DL tau2
        fixed = pool_effects(effects, variances, "fixed")
        random = pool_effects(effects, variances, "random")
        self.assertTrue(random["tau2_truncated"])
        self.assertEqual(random["tau2"], 0.0)
        self.assertEqual(random["pooled_effect"], fixed["pooled_effect"])
        self.assertEqual(random["se"], fixed["se"])
        self.assertEqual(random["ci_low"], fixed["ci_low"])
        self.assertEqual(random["ci_high"], fixed["ci_high"])

    def test_fixed_model_tau2_truncated_always_false(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:4])
        result = pool_effects(effects, variances, "fixed")
        self.assertFalse(result["tau2_truncated"])

    def test_heterogeneous_data_not_truncated(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)  # genuinely heterogeneous -- tau2 > 0
        result = pool_effects(effects, variances, "random")
        self.assertFalse(result["tau2_truncated"])
        self.assertGreater(result["tau2"], 0.0)

    def test_pm_estimator_never_reports_truncation(self):
        # Paule-Mandel's own iterative solver already floors at 0 -- this
        # module's truncation logic only ever fires for tau2_estimator="dl".
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:4])
        result = pool_effects(effects, variances, "random", tau2_estimator="pm")
        self.assertFalse(result["tau2_truncated"])
        self.assertGreaterEqual(result["tau2"], 0.0)


class HksjConfidenceIntervalTests(unittest.TestCase):
    """The modified HKSJ CI uses an estimated-scale SE (statsmodels'
    var_hksj_re/var_hksj_fe) and a t-distribution critical value with
    df=k-1, instead of the fixed-scale SE + normal critical value the
    "normal" ci_method uses. Verified against the exact formula statsmodels
    documents for var_hksj_re/var_hksj_fe (Hartung & Knapp; Sidik & Jonkman),
    independently recomputed here from the same raw effects/variances."""

    def _hksj_se(self, effects, variances, tau2):
        w = [1 / (v + tau2) for v in variances]
        sum_w = sum(w)
        w_rel = [wi / sum_w for wi in w]
        mean = sum(wi * e for wi, e in zip(w, effects)) / sum_w
        df = len(effects) - 1
        var_hksj = sum(wi * (e - mean) ** 2 for wi, e in zip(w_rel, effects)) / df
        return var_hksj ** 0.5

    def test_hksj_se_matches_independent_formula_random(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        result = pool_effects(effects, variances, "random", ci_method="hksj")
        expected_se = self._hksj_se(effects, variances, result["tau2"])
        self.assertAlmostEqual(result["se"], expected_se, places=9)

    def test_hksj_se_differs_from_normal_se(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        normal = pool_effects(effects, variances, "random", ci_method="normal")
        hksj = pool_effects(effects, variances, "random", ci_method="hksj")
        self.assertNotAlmostEqual(normal["se"], hksj["se"], places=6)

    def test_hksj_uses_t_distribution_not_normal(self):
        # With df=k-1 and k=8 (FIG3), t.isf(0.025, 7) > norm.isf(0.025) --
        # the HKSJ half-width-to-SE ratio must exceed the normal 1.959964
        # multiplier, confirming the t-critical value (not the normal one)
        # is actually being used.
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        result = pool_effects(effects, variances, "random", ci_method="hksj")
        half_width = (result["ci_high"] - result["ci_low"]) / 2
        implied_multiplier = half_width / result["se"]
        self.assertGreater(implied_multiplier, 1.959964)

    def test_ci_caution_below_five_studies(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:4])  # k=4
        result = pool_effects(effects, variances, "random", ci_method="hksj")
        self.assertIsNotNone(result["ci_caution"])
        self.assertIn("k=4", result["ci_caution"])

    def test_no_ci_caution_at_or_above_five_studies(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES)  # k=7
        result = pool_effects(effects, variances, "random", ci_method="hksj")
        self.assertIsNone(result["ci_caution"])

    def test_no_ci_caution_for_normal_method_regardless_of_k(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:3])  # k=3, would warn under hksj
        result = pool_effects(effects, variances, "random", ci_method="normal")
        self.assertIsNone(result["ci_caution"])

    def test_invalid_ci_method_raises(self):
        with self.assertRaises(ValueError):
            pool_effects([0.1, 0.2], [0.01, 0.02], "random", ci_method="bootstrap")


class PredictionIntervalTests(unittest.TestCase):
    """95% prediction interval for a new study's true effect (Higgins,
    Thompson & Spiegelhalter 2009): pooled +/- t(df=k-2, 0.025) *
    sqrt(tau2 + se^2). Verified against that formula, independently applied
    here with scipy directly rather than via pool_effects' own computation."""

    def test_pi_matches_formula_when_k_at_least_three(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES)  # k=7
        result = pool_effects(effects, variances, "random")
        expected_half_width = stats.t.isf(0.025, len(effects) - 2) * math.sqrt(result["tau2"] + result["se"] ** 2)
        self.assertAlmostEqual(result["pi_high"] - result["pooled_effect"], expected_half_width, places=9)
        self.assertAlmostEqual(result["pooled_effect"] - result["pi_low"], expected_half_width, places=9)

    def test_pi_none_below_three_studies(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:2])  # k=2
        result = pool_effects(effects, variances, "random")
        self.assertIsNone(result["pi_low"])
        self.assertIsNone(result["pi_high"])

    def test_pi_present_at_exactly_three_studies(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES[:3])  # k=3, df=1
        result = pool_effects(effects, variances, "random")
        self.assertIsNotNone(result["pi_low"])
        self.assertIsNotNone(result["pi_high"])

    def test_pi_none_for_fixed_effect_model(self):
        # A fixed-effect model assumes no between-study variance -- predicting
        # a new study's true effect from it is not a meaningful question.
        effects, variances = _log_rr_inputs(FIG4_STUDIES)
        result = pool_effects(effects, variances, "fixed")
        self.assertIsNone(result["pi_low"])
        self.assertIsNone(result["pi_high"])

    def test_pi_brackets_pooled_effect(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        result = pool_effects(effects, variances, "random")
        self.assertLess(result["pi_low"], result["pooled_effect"])
        self.assertLess(result["pooled_effect"], result["pi_high"])

    def test_pi_wider_than_ci(self):
        # The PI must always be wider than the CI for the mean -- it adds
        # tau2 (between-study variance) on top of the CI's se^2 alone.
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        result = pool_effects(effects, variances, "random")
        self.assertGreater(result["pi_high"] - result["pi_low"], result["ci_high"] - result["ci_low"])


class DlRegressionUnchangedTests(unittest.TestCase):
    """Explicit defaults (tau2_estimator="dl", ci_method="normal") must be
    byte-identical to calling pool_effects with the old 3-positional-arg
    signature -- the new keyword-only parameters must never change existing
    callers' behavior."""

    def test_explicit_defaults_match_bare_call(self):
        for studies in (FIG3_STUDIES, FIG4_STUDIES):
            effects, variances = _log_rr_inputs(studies)
            for model in ("fixed", "random"):
                bare = pool_effects(effects, variances, model)
                explicit = pool_effects(effects, variances, model, tau2_estimator="dl", ci_method="normal")
                for key in ("pooled_effect", "se", "ci_low", "ci_high", "tau2"):
                    self.assertEqual(bare[key], explicit[key], key)


class PoolEffectsEdgeCaseTests(unittest.TestCase):
    def test_invalid_model_raises(self):
        with self.assertRaises(ValueError):
            pool_effects([0.1, 0.2], [0.01, 0.02], "bogus")

    def test_single_study_raises(self):
        with self.assertRaises(ValueError):
            pool_effects([0.2], [0.05], "fixed")

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            pool_effects([], [], "fixed")

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            pool_effects([0.1, 0.2, 0.3], [0.01, 0.02], "fixed")

    def test_nonpositive_variance_raises(self):
        with self.assertRaises(ValueError):
            pool_effects([0.1, 0.2], [0.01, 0.0], "fixed")
        with self.assertRaises(ValueError):
            pool_effects([0.1, 0.2], [0.01, -0.01], "random")

    def test_nan_or_inf_raises_instead_of_computing(self):
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                pool_effects([0.2, 0.3], [0.02, bad], "fixed")

    def test_two_studies_is_the_minimum_allowed(self):
        result = pool_effects([0.1, 0.3], [0.02, 0.03], "fixed")
        self.assertEqual(result["k"], 2)


if __name__ == "__main__":
    unittest.main()
