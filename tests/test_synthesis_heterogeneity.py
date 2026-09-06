"""Unit tests for synthesis/heterogeneity.py.

Worked example: the two forest plots in references/papers/kjae-2018-71-2-103.pdf
(Ahn & Kang, "Introduction to systematic review and meta-analysis"), Figs. 3
and 4 -- the classic Cochrane magnesium-and-myocardial-infarction dichotomous
data, given as per-study events/totals with RevMan's own reported
Heterogeneity line (Chi2, df, P, I2) as ground truth.

compute_heterogeneity() takes effects+variances on an additive scale (e.g.
log-RR), not raw events/totals, so each study's risk ratio is converted with
the standard log-RR variance formula (Cochrane Handbook 10.4.3.1):
    logRR = ln((a/n1) / (c/n2))
    Var(logRR) = 1/a - 1/n1 + 1/c - 1/n2
RevMan's own heterogeneity test also runs on generic inverse-variance
weights regardless of the pooling method (Mantel-Haenszel here), so the
module's Q/I2 should land close to -- not bit-identical to, different
software/rounding -- the paper's printed values.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis import heterogeneity
from synthesis.heterogeneity import compute_heterogeneity

# Fig. 3: "Forest plot analyzed by two different models using the same data"
# -- heterogeneous data. (experimental_events, experimental_total, control_events, control_total)
# Paper reports: Chi2 = 60.69, df = 7, P < 0.00001, I2 = 88%
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
# Paper reports: Chi2 = 10.45, df = 6, P = 0.11, I2 = 43%
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


class ComputeHeterogeneityWorkedExampleTests(unittest.TestCase):
    def test_fig3_heterogeneous_data_matches_paper(self):
        effects, variances = _log_rr_inputs(FIG3_STUDIES)
        result = compute_heterogeneity(effects, variances)

        self.assertEqual(result["df"], 7)
        self.assertAlmostEqual(result["Q"], 60.69, delta=1.0)
        self.assertAlmostEqual(result["I2"], 88.0, delta=1.0)
        self.assertLess(result["p_value"], 0.00001)

    def test_fig4_homogeneous_data_matches_paper(self):
        effects, variances = _log_rr_inputs(FIG4_STUDIES)
        result = compute_heterogeneity(effects, variances)

        self.assertEqual(result["df"], 6)
        self.assertAlmostEqual(result["Q"], 10.45, delta=1.0)
        self.assertAlmostEqual(result["I2"], 43.0, delta=1.5)
        self.assertAlmostEqual(result["p_value"], 0.11, delta=0.02)


class ComputeHeterogeneityEdgeCaseTests(unittest.TestCase):
    def test_single_study_has_no_testable_heterogeneity(self):
        result = compute_heterogeneity([0.2], [0.05])
        self.assertEqual(result["df"], 0)
        self.assertEqual(result["p_value"], 1.0)
        self.assertEqual(result["I2"], 0.0)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            compute_heterogeneity([0.1, 0.2], [0.01])

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            compute_heterogeneity([], [])

    def test_nonpositive_variance_raises(self):
        with self.assertRaises(ValueError):
            compute_heterogeneity([0.1, 0.2], [0.01, 0.0])
        with self.assertRaises(ValueError):
            compute_heterogeneity([0.1, 0.2], [0.01, -0.01])

    def test_nan_or_inf_raises_instead_of_computing(self):
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                compute_heterogeneity([0.2, 0.3], [0.02, bad])


class NoModelSelectionSymbolTests(unittest.TestCase):
    """Regression guard for the Phase 0 correctness fix (docs/PLAN.md): the
    module must never re-offer a function that picks fixed vs random from
    I2/Q -- that decision is prespecified in synthesis_plan.json instead
    (schemas/synthesis_plan.schema.json)."""

    def test_choose_model_removed(self):
        self.assertFalse(hasattr(heterogeneity, "choose_model"))


if __name__ == "__main__":
    unittest.main()
