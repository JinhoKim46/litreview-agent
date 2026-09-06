"""Pooled effect-size estimation for /prisma-synthesize.

Wraps statsmodels.stats.meta_analysis.combine_effects, which already
implements inverse-variance fixed-effect pooling, DerSimonian-Laird and
Paule-Mandel random-effects pooling, and the modified Hartung-Knapp-Sidik-
Jonkman (HKSJ) confidence interval correctly -- the pooling formulas are not
reimplemented here. `model` ("fixed" or "random"), `tau2_estimator`
("dl" or "pm"), and `ci_method` ("normal" or "hksj") are all prespecified
by the reviewer in synthesis_plan.json (schemas/synthesis_plan.schema.json),
never chosen from this pair's own heterogeneity statistics;
synthesis/run_synthesis.py calls this function once for the prespecified
(primary) model and once more for the other model, reporting the latter as
a sensitivity analysis.
"""
import warnings

import numpy as np
from scipy import stats
from statsmodels.stats.meta_analysis import combine_effects

TAU2_ESTIMATORS = ("dl", "pm")
CI_METHODS = ("normal", "hksj")
HKSJ_CAUTION_MAX_K = 5  # IntHout et al. 2014 / Röver et al. 2015: modified
                        # HKSJ can be anti-conservative (CI too narrow) with
                        # few studies -- flag it, never withhold the estimate.
PI_MIN_K = 3  # Higgins/Thompson/Spiegelhalter 2009: prediction interval
              # needs df = k - 2 >= 1.


def pool_effects(effects, variances, model, tau2_estimator="dl", ci_method="normal"):
    """Pool per-study effect sizes into a single summary estimate.

    Args:
        effects: per-study point estimates (e.g. log-OR, mean difference), same scale.
        variances: per-study variance of each effect estimate. Must be > 0.
        model: "fixed" or "random" -- prespecified in synthesis_plan.json, never
            derived from this same (effects, variances) pair's own statistics.
        tau2_estimator: "dl" (DerSimonian-Laird, one-step) or "pm" (Paule-Mandel,
            iterative) -- prespecified alongside `model`. Only affects the
            random-effects branch; a fixed-effect pool has no between-study
            variance to estimate either way.
        ci_method: "normal" (fixed-scale, normal-approximation CI -- the
            historical default) or "hksj" (modified Hartung-Knapp-Sidik-Jonkman:
            an estimated-scale CI using a t-distribution with df = k - 1).
            Applies to whichever `model` was requested.

    Returns:
        dict with keys:
            model: echoes the `model` argument.
            tau2_estimator, ci_method: echo the corresponding arguments.
            k: number of studies pooled.
            pooled_effect: the summary effect estimate.
            se: standard error of the pooled effect, consistent with `ci_method`
                (the HKSJ-scale SE when ci_method="hksj", the fixed-scale SE
                otherwise).
            ci_low, ci_high: 95% confidence interval, consistent with `ci_method`.
            tau2: between-study variance estimate (0.0 for model="fixed" -- a
                fixed-effect pool assumes no between-study variance).
            tau2_truncated: True if model="random" and the raw tau2_estimator="dl"
                estimate came out negative (possible for sufficiently homogeneous
                data -- statsmodels' DL branch, unlike its Paule-Mandel solver,
                does not floor at 0 internally) and was truncated to 0 per
                Cochrane Handbook 10.10.4.2, making this pool's pooled_effect/se/
                ci_low/ci_high identical to the fixed-effect ones. Always False
                for model="fixed" (tau2 is already forced to 0 there regardless).
            ci_caution: a warning string if ci_method="hksj" and k < 5 (the
                correction can be anti-conservative with few studies), else None.
            pi_low, pi_high: 95% prediction interval for a new study's true
                effect (Higgins/Thompson/Spiegelhalter 2009), or None if
                model="fixed" (a fixed-effect model assumes no between-study
                variance, so predicting a new study's effect is not meaningful)
                or k < 3 (needs df = k - 2 >= 1).
    """
    if model not in ("fixed", "random"):
        raise ValueError(f"model must be 'fixed' or 'random', got {model!r}")
    if tau2_estimator not in TAU2_ESTIMATORS:
        raise ValueError(f"tau2_estimator must be one of {TAU2_ESTIMATORS}, got {tau2_estimator!r}")
    if ci_method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}, got {ci_method!r}")

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

    k = int(effects.size)
    # A negative raw DL tau2 (see the truncation note below) makes several
    # of statsmodels' own random-effects intermediates (computed
    # unconditionally inside combine_effects/CombineResults/conf_int,
    # regardless of which fields this wrapper goes on to use) take sqrt()
    # of a negative number -- np.sqrt(negative) is NaN, not an error, and
    # this wrapper discards every one of those NaN fields in favor of the
    # fixed-effects ones once truncation is detected below, so the warning
    # is expected noise here, not a sign of a miscomputation.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="invalid value encountered in sqrt", category=RuntimeWarning)
        result = combine_effects(effects, variances, method_re=tau2_estimator)
        use_t = ci_method == "hksj"
        ci_normal_fe, ci_normal_re, ci_hksj_fe, ci_hksj_re = result.conf_int(use_t=use_t)

    # statsmodels' DL/chi2 branch (unlike its Paule-Mandel iterative solver,
    # which floors at 0 internally) can return a negative tau2 for
    # sufficiently homogeneous data (Q < df) -- the standard convention
    # (Cochrane Handbook 10.10.4.2 and every widely used implementation) is
    # to truncate a negative between-study-variance estimate to 0. At
    # tau2=0, the random-effects weights are identical to the fixed-effects
    # weights (1/(var+0) == 1/var), so the random-effects pooled estimate,
    # SE, and CI are then exactly the fixed-effects ones -- not an
    # approximation, a mathematical identity -- so this reuses the _fe
    # fields rather than recomputing anything.
    raw_tau2 = float(result.tau2)
    tau2_truncated = raw_tau2 < 0

    if model == "fixed" or (model == "random" and tau2_truncated):
        pooled, tau2 = result.mean_effect_fe, 0.0
        se = result.sd_eff_w_fe_hksj if ci_method == "hksj" else result.sd_eff_w_fe
        ci_low, ci_high = (ci_hksj_fe if ci_method == "hksj" else ci_normal_fe)
    else:
        pooled, tau2 = result.mean_effect_re, raw_tau2
        se = result.sd_eff_w_re_hksj if ci_method == "hksj" else result.sd_eff_w_re
        ci_low, ci_high = (ci_hksj_re if ci_method == "hksj" else ci_normal_re)

    ci_caution = None
    if ci_method == "hksj" and k < HKSJ_CAUTION_MAX_K:
        ci_caution = (
            f"k={k} < {HKSJ_CAUTION_MAX_K}: the modified HKSJ confidence interval can be "
            "anti-conservative (narrower than its nominal coverage) with this few studies "
            "(IntHout et al. 2014; Röver et al. 2015) -- interpret with caution."
        )

    pi_low = pi_high = None
    if model == "random" and k >= PI_MIN_K:
        df_pi = k - 2
        crit_pi = stats.t.isf(0.025, df_pi)
        half_width = crit_pi * float(np.sqrt(tau2 + se ** 2))
        pi_low, pi_high = pooled - half_width, pooled + half_width

    return {
        "model": model,
        "tau2_estimator": tau2_estimator,
        "ci_method": ci_method,
        "k": k,
        "pooled_effect": float(pooled),
        "se": float(se),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "tau2": float(tau2),
        "tau2_truncated": tau2_truncated if model == "random" else False,
        "ci_caution": ci_caution,
        "pi_low": float(pi_low) if pi_low is not None else None,
        "pi_high": float(pi_high) if pi_high is not None else None,
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
    assert fixed["tau2_estimator"] == "dl" and fixed["ci_method"] == "normal"
    assert fixed["k"] == 5
    assert abs(fixed["pooled_effect"] - expected_fixed) < 1e-9, (fixed, expected_fixed)
    assert abs(fixed["se"] - expected_fixed_se) < 1e-9, (fixed, expected_fixed_se)
    assert fixed["tau2"] == 0.0
    assert fixed["ci_low"] < fixed["pooled_effect"] < fixed["ci_high"]
    # 95% CI is pooled +/- 1.96*se under the normal approximation.
    assert abs(fixed["ci_high"] - fixed["ci_low"] - 2 * 1.959964 * fixed["se"]) < 1e-6
    assert fixed["pi_low"] is None and fixed["pi_high"] is None  # no PI for a fixed-effect model

    random = pool_effects(effects, variances, "random")
    assert random["model"] == "random"
    assert abs(random["tau2"] - expected_tau2) < 1e-9, (random, expected_tau2)
    assert abs(random["pooled_effect"] - expected_random) < 1e-6, (random, expected_random)
    assert abs(random["se"] - expected_random_se) < 1e-6, (random, expected_random_se)
    assert random["ci_low"] < random["pooled_effect"] < random["ci_high"]
    assert random["pi_low"] < random["pooled_effect"] < random["pi_high"]  # k=5 >= PI_MIN_K

    # A single fixed-effect study is meaningless to pool.
    try:
        pool_effects([0.2], [0.05], "fixed")
        raise AssertionError("expected ValueError for k < 2")
    except ValueError:
        pass

    # Paule-Mandel tau2 satisfies its own defining equation: Q(tau2_pm) == k-1.
    pm = pool_effects(effects, variances, "random", tau2_estimator="pm")
    w_pm = [1 / (v + pm["tau2"]) for v in variances]
    sum_w_pm = sum(w_pm)
    mean_pm = sum(wi * e for wi, e in zip(w_pm, effects)) / sum_w_pm
    q_at_pm = sum(wi * (e - mean_pm) ** 2 for wi, e in zip(w_pm, effects))
    assert abs(q_at_pm - df) < 1e-4, (q_at_pm, df)

    # k=5 is NOT below HKSJ_CAUTION_MAX_K (5) -- no caution note.
    hksj = pool_effects(effects, variances, "random", ci_method="hksj")
    assert hksj["ci_caution"] is None

    # k=4 (< HKSJ_CAUTION_MAX_K) must carry the caution note.
    hksj_k4 = pool_effects(effects[:4], variances[:4], "random", ci_method="hksj")
    assert hksj_k4["ci_caution"] is not None and "k=4" in hksj_k4["ci_caution"]

    print(f"fixed:  effect={fixed['pooled_effect']:.4f} se={fixed['se']:.4f} "
          f"95% CI [{fixed['ci_low']:.4f}, {fixed['ci_high']:.4f}] tau2={fixed['tau2']:.4f}")
    print(f"random: effect={random['pooled_effect']:.4f} se={random['se']:.4f} "
          f"95% CI [{random['ci_low']:.4f}, {random['ci_high']:.4f}] tau2={random['tau2']:.4f} "
          f"PI [{random['pi_low']:.4f}, {random['pi_high']:.4f}]")
    print("self-check OK")
