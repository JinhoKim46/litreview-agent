"""Heterogeneity statistics for pooled effect sizes.

Cochrane's Q and the Higgins I^2 statistic tell /prisma-synthesize how much a
set of per-study effects disagrees with itself -- they are reported
alongside a pooled estimate, never used to pick the pooling model. Which
model (fixed or random effects) is primary is prespecified by the reviewer
at protocol time and recorded in synthesis_plan.json
(schemas/synthesis_plan.schema.json); synthesis/run_synthesis.py always
computes both models and reports the non-primary one as a sensitivity
analysis. This module previously exposed a choose_model(I2, q_p_value)
helper that auto-selected the model from these statistics -- that was a
Phase 0 correctness defect (docs/PLAN.md), and the function has been
removed; do not reintroduce a model-selection rule here.

Q and I^2 are plain inverse-variance-weighted formulas with no numerically
tricky parts, so they're computed directly here with numpy; only the Q
statistic's p-value (a chi-square tail probability) is delegated to scipy
rather than hand-rolled. The actual pooled-effect estimate belongs in
synthesis/pooling.py (statsmodels.stats.meta_analysis.combine_effects), not
here -- this module only characterizes how much the per-study effects
disagree with each other.
"""
import numpy as np
from scipy.stats import chi2


def compute_heterogeneity(effects, variances):
    """Cochrane's Q and Higgins I^2 for a set of study effect sizes.

    Args:
        effects: per-study point estimates (e.g. log-OR, mean difference), same scale.
        variances: per-study variance of each effect estimate. Must be > 0.

    Returns:
        dict with keys:
            Q: Cochrane's Q statistic (inverse-variance-weighted sum of squared
               deviations from the fixed-effect pooled mean).
            df: degrees of freedom, k - 1 for k studies.
            p_value: upper-tail p-value of Q against chi-square(df). 1.0 when
               df == 0 (a single study has no heterogeneity to test).
            I2: Higgins I^2 in percent, clipped to [0, 100].
    """
    effects = np.asarray(effects, dtype=float)
    variances = np.asarray(variances, dtype=float)
    if effects.shape != variances.shape:
        raise ValueError("effects and variances must be the same length")
    k = effects.size
    if k < 1:
        raise ValueError("need at least one study")
    if not (np.all(np.isfinite(effects)) and np.all(np.isfinite(variances))):
        raise ValueError("effects and variances must all be finite")
    if np.any(variances <= 0):
        raise ValueError("all variances must be > 0")

    weights = 1.0 / variances
    pooled_fixed = np.sum(weights * effects) / np.sum(weights)
    Q = float(np.sum(weights * (effects - pooled_fixed) ** 2))
    df = k - 1

    if df == 0:
        p_value = 1.0
    else:
        p_value = float(chi2.sf(Q, df))

    I2 = 100.0 * max(0.0, (Q - df) / Q) if Q > 0 else 0.0

    return {"Q": Q, "df": df, "p_value": p_value, "I2": I2}


if __name__ == "__main__":
    # Worked example: 5 studies, deliberately mixed effects/precisions so Q
    # and I2 land somewhere non-trivial. Expected Q/df/p/I2 are hardcoded
    # golden values (by hand: weights = 1/variance, pooled = weighted mean,
    # Q = sum(w*(e-pooled)**2), I2 = 100*max(0,(Q-df)/Q)), not re-derived
    # with the function's own formula, so a formula regression actually fails
    # this check instead of just re-confirming numpy arithmetic.
    effects = [0.10, 0.55, 0.35, 0.80, 0.15]
    variances = [0.02, 0.03, 0.02, 0.02, 0.02]

    result = compute_heterogeneity(effects, variances)

    assert abs(result["Q"] - 16.3929) < 1e-3, result["Q"]
    assert result["df"] == 4
    assert abs(result["p_value"] - 0.0025) < 1e-3, result["p_value"]
    assert abs(result["I2"] - 75.60) < 1e-1, result["I2"]

    print(f"Q={result['Q']:.4f} df={result['df']} p={result['p_value']:.4f} I2={result['I2']:.2f}%")

    # Single-study edge case: no heterogeneity is testable.
    single = compute_heterogeneity([0.2], [0.05])
    assert single["df"] == 0 and single["p_value"] == 1.0 and single["I2"] == 0.0

    # A NaN/inf slipping in from a malformed extraction_table.json entry must
    # raise, never silently compute (nan <= 0 is False, so a naive positivity
    # check alone would let it through and produce a bogus "I2=0, fixed").
    for bad in (float("nan"), float("inf")):
        try:
            compute_heterogeneity([0.2, 0.3], [0.02, bad])
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for variance={bad}")

    print("self-check OK")
