"""Pooled effect-size estimation for /prisma-synthesize.

Wraps statsmodels.stats.meta_analysis.combine_effects, which already
implements inverse-variance fixed-effect pooling and DerSimonian-Laird
random-effects pooling correctly -- the pooling formulas are not
reimplemented here. `model` ("fixed" or "random") is prespecified by the
reviewer in synthesis_plan.json (schemas/synthesis_plan.schema.json), never
chosen from this pair's own heterogeneity statistics; synthesis/run_synthesis.py
calls this function once for the prespecified (primary) model and once more
for the other model, reporting the latter as a sensitivity analysis.
"""
import numpy as np
from statsmodels.stats.meta_analysis import combine_effects


def pool_effects(effects, variances, model):
    """Pool per-study effect sizes into a single summary estimate.

    Args:
        effects: per-study point estimates (e.g. log-OR, mean difference), same scale.
        variances: per-study variance of each effect estimate. Must be > 0.
        model: "fixed" or "random" -- prespecified in synthesis_plan.json, never
            derived from this same (effects, variances) pair's own statistics.

    Returns:
        dict with keys:
            model: echoes the `model` argument.
            k: number of studies pooled.
            pooled_effect: the summary effect estimate.
            se: standard error of the pooled effect.
            ci_low, ci_high: 95% confidence interval (normal-approximation, as
                combine_effects reports with use_t=False).
            tau2: DerSimonian-Laird between-study variance estimate. 0.0 for
                model="fixed" (a fixed-effect pool assumes no between-study
                variance, so there is nothing to report).
    """
    if model not in ("fixed", "random"):
        raise ValueError(f"model must be 'fixed' or 'random', got {model!r}")

    effects = np.asarray(effects, dtype=float)
    variances = np.asarray(variances, dtype=float)
    if effects.shape != variances.shape:
        raise ValueError("effects and variances must be the same length")
    if effects.ndim != 1 or effects.size < 2:
        raise ValueError("pool_effects needs at least 2 studies")
    if not np.all(np.isfinite(effects)) or not np.all(np.isfinite(variances)):
        raise ValueError("effects and variances must all be finite (no NaN/inf)")
    if np.any(variances <= 0):
        raise ValueError("all variances must be > 0")

    result = combine_effects(effects, variances, method_re="dl")
    ci_fe, ci_re, _, _ = result.conf_int()  # (fixed-scale) fixed, random, then HKSJ variants

    if model == "fixed":
        pooled, se, ci_low, ci_high, tau2 = (
            result.mean_effect_fe, result.sd_eff_w_fe, ci_fe[0], ci_fe[1], 0.0,
        )
    else:
        pooled, se, ci_low, ci_high, tau2 = (
            result.mean_effect_re, result.sd_eff_w_re, ci_re[0], ci_re[1], float(result.tau2),
        )

    return {
        "model": model,
        "k": int(effects.size),
        "pooled_effect": float(pooled),
        "se": float(se),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "tau2": float(tau2),
    }


if __name__ == "__main__":
    # Same worked example as synthesis/heterogeneity.py's self-check (5 studies),
    # so the two modules' checks are cross-consistent. Expected fixed-effect
    # pooled estimate and DerSimonian-Laird tau2 are computed independently by
    # hand (plain inverse-variance formulas) rather than re-deriving them from
    # statsmodels, so this actually checks the wrapper against known values.
    effects = [0.10, 0.55, 0.35, 0.80, 0.15]
    variances = [0.02, 0.03, 0.02, 0.02, 0.02]

    w = [1 / v for v in variances]
    sum_w = sum(w)
    expected_fixed = sum(wi * e for wi, e in zip(w, effects)) / sum_w
    expected_fixed_se = (1 / sum_w) ** 0.5

    Q = sum(wi * (e - expected_fixed) ** 2 for wi, e in zip(w, effects))
    df = len(effects) - 1
    C = sum_w - sum(wi ** 2 for wi in w) / sum_w
    expected_tau2 = max(0.0, (Q - df) / C)

    w_re = [1 / (v + expected_tau2) for v in variances]
    sum_w_re = sum(w_re)
    expected_random = sum(wi * e for wi, e in zip(w_re, effects)) / sum_w_re
    expected_random_se = (1 / sum_w_re) ** 0.5

    fixed = pool_effects(effects, variances, "fixed")
    assert fixed["model"] == "fixed"
    assert fixed["k"] == 5
    assert abs(fixed["pooled_effect"] - expected_fixed) < 1e-9, (fixed, expected_fixed)
    assert abs(fixed["se"] - expected_fixed_se) < 1e-9, (fixed, expected_fixed_se)
    assert fixed["tau2"] == 0.0
    assert fixed["ci_low"] < fixed["pooled_effect"] < fixed["ci_high"]
    # 95% CI is pooled +/- 1.96*se under the normal approximation.
    assert abs(fixed["ci_high"] - fixed["ci_low"] - 2 * 1.959964 * fixed["se"]) < 1e-6

    random = pool_effects(effects, variances, "random")
    assert random["model"] == "random"
    assert abs(random["tau2"] - expected_tau2) < 1e-9, (random, expected_tau2)
    assert abs(random["pooled_effect"] - expected_random) < 1e-6, (random, expected_random)
    assert abs(random["se"] - expected_random_se) < 1e-6, (random, expected_random_se)
    assert random["ci_low"] < random["pooled_effect"] < random["ci_high"]

    # A single fixed-effect study is meaningless to pool.
    try:
        pool_effects([0.2], [0.05], "fixed")
        raise AssertionError("expected ValueError for k < 2")
    except ValueError:
        pass

    print(f"fixed:  effect={fixed['pooled_effect']:.4f} se={fixed['se']:.4f} "
          f"95% CI [{fixed['ci_low']:.4f}, {fixed['ci_high']:.4f}] tau2={fixed['tau2']:.4f}")
    print(f"random: effect={random['pooled_effect']:.4f} se={random['se']:.4f} "
          f"95% CI [{random['ci_low']:.4f}, {random['ci_high']:.4f}] tau2={random['tau2']:.4f}")
    print("self-check OK")
