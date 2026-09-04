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
