"""Helper script for /prisma-synthesize: turns extraction_table.json into
synthesis/{effect_sizes,heterogeneity,rob_table,grade_table}.json + SVG plots.

This is the "short helper script" plan section 6 calls for -- the actual
pooling math lives in synthesis/pooling.py and synthesis/heterogeneity.py
(imported, never reimplemented); this file only:

  1. Flattens extraction_table.json's per-study `outcomes` list into rows.
  2. Converts each row's raw arm data (events/totals or mean/sd/n) into an
     effect + variance on the scale pooling.pool_effects/heterogeneity.
     compute_heterogeneity expect, per standard Cochrane Handbook formulas
     (10.4.3 for the dichotomous log-scale measures).
  3. Applies the poolability gate per outcome group, with every excluded
     study and every non-pooled outcome carrying a recorded reason --
     never a silent drop.
  4. Calls heterogeneity.compute_heterogeneity + choose_model, then
     pooling.pool_effects, for every group that clears the gate.
  5. Renders forest/funnel plots via synthesis/plots.py.
  6. Aggregates each contributing study's `risk_of_bias` block (written by
     /prisma-extract, never re-derived here) into rob_table.json, and
     writes a grade_table.json with the objective GRADE domains (risk of
     bias, inconsistency, publication bias) computed and the two judgement
     domains (indirectness, imprecision) left as an explicit
     "needs_review" placeholder for /prisma-synthesize's next step to fill
     in per quality-appraisal/02-grade-certainty.md.

extraction_table.json contract this script expects -- the exact shape
/prisma-extract.md Step 8 writes:

    {
      "framework_version": "1.0.0",
      "topic": "<TOPIC>",
      "studies": [
        {
          "record_id": "openalex:W123456789",
          "author_year": "Kim et al. (2022)",
          "study_design": "RCT" | "cohort" | "case-control" | ...,
          "outcomes_measured": ["PONV", "patient satisfaction"],
          "risk_of_bias": {"tool": "RoB2"|"NOS", "overall_judgement": "...", ...},
          "effect_data": [
            {"outcome": "PONV", "measure_type": "OR"|"RR"|"RD", "timepoint": "...",
             "intervention_arm": {"label": "...", "events": int, "total": int},
             "comparator_arm": {"label": "...", "events": int, "total": int}},
            {"outcome": "pain score", "measure_type": "MD"|"SMD", "timepoint": "...",
             "intervention_arm": {"label": "...", "mean": float, "sd": float, "n": int},
             "comparator_arm": {"label": "...", "mean": float, "sd": float, "n": int}}
          ]
        },
        ...
      ]
    }

`outcomes_measured` names every outcome the study reports at all;
`effect_data` carries only the ones extracted quantitatively (`[]` if none).
An outcome present in `outcomes_measured` but absent from every
`effect_data[].outcome` for that study is narrative-only for that study --
see `flatten_rows`.
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis.heterogeneity import choose_model, compute_heterogeneity
from synthesis.pooling import pool_effects
from synthesis.plots import forest_plot, funnel_plot, rob_traffic_light_plot

Z95 = 1.959964  # normal-approximation 95% CI multiplier, matches pool_effects' own CI method

# Canonical RoB2 domain order (Cochrane Handbook Ch.8 / quality-appraisal/01-risk-of-bias.md),
# short headers for the traffic-light plot's columns -- the manuscript's figure caption spells
# these back out (D1=sequence generation, D2=allocation concealment, ...).
ROB2_DOMAIN_LABELS = [
    ("sequence_generation", "D1"),
    ("allocation_concealment", "D2"),
    ("blinding_participants_personnel", "D3"),
    ("blinding_outcome_assessment", "D4"),
    ("incomplete_outcome_data", "D5"),
    ("selective_reporting", "D6"),
    ("other_bias", "D7"),
]

LOG_SCALE_MEASURES = {"OR", "RR"}
DICHOTOMOUS_MEASURES = {"OR", "RR", "RD"}
CONTINUOUS_MEASURES = {"MD", "SMD"}
ALL_MEASURES = DICHOTOMOUS_MEASURES | CONTINUOUS_MEASURES

FUNNEL_MIN_K = 10
POOL_MIN_K = 2


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "outcome"


def load_studies(path):
    with open(path) as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or not isinstance(doc.get("studies"), list):
        raise ValueError(f"{path} must be a JSON object with a top-level 'studies' array (see /prisma-extract.md Step 8)")
    return doc["studies"]


def flatten_rows(studies):
    """One row per (study, outcome). Quantitative rows (one per effect_data
    entry) carry that entry's raw arm data; narrative rows (one per name in
    outcomes_measured that has no matching effect_data entry) carry none.
    Each row carries the study's risk_of_bias block verbatim -- never
    recomputed here. Also carries the study-level provenance fields
    (docs/PLAN.md PR p0-11-extraction-provenance) `reports`, `by`,
    `verified_by` -- each `effect_data` entry's own `source` (quote/
    locator/notes) is already inside that entry, so it needs no separate
    threading here."""
    rows = []
    for study in studies:
        record_id = study.get("record_id") or study.get("author_year") or "UNKNOWN_STUDY"
        author_year = study.get("author_year", record_id)
        rob = study.get("risk_of_bias")
        design = study.get("study_design")
        reports = study.get("reports")
        by = study.get("by")
        verified_by = study.get("verified_by")
        effect_data_list = study.get("effect_data") or []
        quantified_names = {e["outcome"] for e in effect_data_list}

        for entry in effect_data_list:
            rows.append({
                "study_id": record_id, "author_year": author_year, "study_design": design,
                "outcome": entry["outcome"], "type": "quantitative",
                "effect_data": entry, "risk_of_bias": rob,
                "reports": reports, "by": by, "verified_by": verified_by,
            })

        for name in study.get("outcomes_measured", []):
            if name in quantified_names:
                continue  # already covered by an effect_data row above
            rows.append({
                "study_id": record_id, "author_year": author_year, "study_design": design,
                "outcome": name, "type": "qualitative",
                "effect_data": None, "risk_of_bias": rob,
                "reports": reports, "by": by, "verified_by": verified_by,
            })
    return rows


def classify_design(study_design):
    d = (study_design or "").lower()
    if "rct" in d or "random" in d:
        return "rct"
    if d:
        return "observational"
    return "unknown"


def determine_starting_certainty(rows):
    """GRADE's design baseline (02-grade-certainty.md): RCT evidence starts
    High, observational starts Low. Never defaults to High from an empty or
    unknown-design set -- that would be a fabricated favorable baseline from
    zero evidence, exactly what quality-appraisal/SKILL.md forbids."""
    designs = {classify_design(row.get("study_design")) for row in rows}
    if designs == {"rct"}:
        return "high", "All contributing studies are RCTs."
    if designs == {"observational"}:
        return "low", "All contributing studies are non-randomized/observational."
    if designs == {"unknown"}:
        return "low", "study_design missing for every contributing study -- defaulted to the observational (Low) baseline; verify designs in extraction_table.json."
    return "low", f"Mixed or partly-unknown study designs among contributing studies ({sorted(designs)}) -- defaulted to the more conservative observational (Low) baseline."


def _continuity_corrected(a, b, c, d):
    """Cochrane Handbook 10.4.4.1: if any cell of the 2x2 table is 0, add
    0.5 to all four cells (and recompute the arm totals from the corrected
    cells) before taking logs -- otherwise log(0) or division by 0 breaks
    the variance formula."""
    if 0 in (a, b, c, d):
        return a + 0.5, b + 0.5, c + 0.5, d + 0.5, True
    return a, b, c, d, False


def convert_effect(effect_data):
    """Raw arm data -> (effect, variance, display_estimate, continuity_correction_applied).

    `effect` is on the scale pool_effects/compute_heterogeneity operate on
    (log-scale for OR/RR, natural scale for RD/MD/SMD). `display_estimate`
    is the human-readable number for effect_sizes.json/grade_table.json
    (exponentiated back for OR/RR). Raises ValueError with a human-readable
    reason -- callers must catch this and record the reason, never let a
    bad row silently vanish.
    """
    measure = effect_data.get("measure_type")
    if measure not in ALL_MEASURES:
        raise ValueError(f"unsupported or missing measure_type {measure!r} (expected one of {sorted(ALL_MEASURES)})")

    try:
        treatment = effect_data["intervention_arm"]
        control = effect_data["comparator_arm"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"effect_data missing intervention_arm/comparator_arm: {e}")

    if measure in DICHOTOMOUS_MEASURES:
        try:
            a = float(treatment["events"])
            n1 = float(treatment["total"])
            c = float(control["events"])
            n2 = float(control["total"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"incomplete dichotomous effect_data (need events/total on both intervention_arm and comparator_arm): {e}")
        if n1 <= 0 or n2 <= 0 or a > n1 or c > n2 or a < 0 or c < 0:
            raise ValueError(f"implausible dichotomous counts: events_t={a}/{n1}, events_c={c}/{n2}")
        b, d = n1 - a, n2 - c

        if measure == "RD":
            p1, p2 = a / n1, c / n2
            effect = p1 - p2
            variance = p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2
            if variance <= 0:
                raise ValueError("RD variance is zero (degenerate arm proportions) -- cannot weight this study")
            return effect, variance, effect, False

        a2, b2, c2, d2, corrected = _continuity_corrected(a, b, c, d)
        n1_2, n2_2 = a2 + b2, c2 + d2
        if measure == "OR":
            log_or = math.log((a2 * d2) / (b2 * c2))
            variance = 1 / a2 + 1 / b2 + 1 / c2 + 1 / d2
            return log_or, variance, math.exp(log_or), corrected
        else:  # RR
            log_rr = math.log((a2 / n1_2) / (c2 / n2_2))
            variance = 1 / a2 - 1 / n1_2 + 1 / c2 - 1 / n2_2
            if variance <= 0:
                raise ValueError("RR variance is non-positive after continuity correction -- degenerate cell counts")
            return log_rr, variance, math.exp(log_rr), corrected

    else:  # continuous: MD or SMD
        try:
            m1 = float(treatment["mean"]); sd1 = float(treatment["sd"]); n1 = float(treatment["n"])
            m2 = float(control["mean"]); sd2 = float(control["sd"]); n2 = float(control["n"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"incomplete continuous effect_data (need mean/sd/n on both intervention_arm and comparator_arm): {e}")
        if n1 <= 1 or n2 <= 1 or sd1 < 0 or sd2 < 0:
            raise ValueError(f"implausible continuous arm data: n_t={n1}, n_c={n2}, sd_t={sd1}, sd_c={sd2}")

        if measure == "MD":
            effect = m1 - m2
            variance = (sd1 ** 2) / n1 + (sd2 ** 2) / n2
            if variance <= 0:
                raise ValueError("MD variance is zero (both arms report sd=0) -- cannot weight this study")
            return effect, variance, effect, False

        # SMD (Hedges' g), Cochrane Handbook 10.4.3.2 / Borenstein et al.
        df = n1 + n2 - 2
        pooled_sd = math.sqrt(((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / df)
        if pooled_sd == 0:
            raise ValueError("SMD pooled SD is zero -- cannot compute a standardized effect")
        d_raw = (m1 - m2) / pooled_sd
        j = 1 - 3 / (4 * df - 1)  # small-sample bias correction (Hedges' g)
        g = j * d_raw
        variance = (n1 + n2) / (n1 * n2) + (g ** 2) / (2 * (n1 + n2))
        return g, variance, g, False


def is_low_risk(rob):
    if not rob:
        return None
    tool = rob.get("tool")
    judgement = (rob.get("overall_judgement") or "").lower()
    if tool == "RoB2":
        return "low risk" in judgement
    if tool == "NOS":
        return "good" in judgement
    return None


def build_rob_entry(outcome_name, rows):
    entries, missing = [], []
    for row in rows:
        rob = row["risk_of_bias"]
        if not rob:
            missing.append(row["study_id"])
            continue
        entries.append({"study_id": row["study_id"], "tool": rob.get("tool"), "overall_judgement": rob.get("overall_judgement")})
    assessed = [e for e in entries if is_low_risk({"tool": e["tool"], "overall_judgement": e["overall_judgement"]}) is not None]
    low_risk_n = sum(1 for e in assessed if is_low_risk({"tool": e["tool"], "overall_judgement": e["overall_judgement"]}))
    return {
        "outcome": outcome_name,
        "studies": entries,
        "proportion_low_risk": (low_risk_n / len(assessed)) if assessed else None,
        "missing_assessment": missing,
    }


def build_grade_draft(outcome_name, rows, model_used, k, het, effect_summary):
    rob_entry = build_rob_entry(outcome_name, rows)
    starting, starting_note = determine_starting_certainty(rows)

    if rob_entry["proportion_low_risk"] is None:
        rob_rating, rob_note = "not_assessed", "No risk-of-bias assessment available for any contributing study -- flag back to /prisma-extract."
    elif rob_entry["proportion_low_risk"] >= 0.75:
        rob_rating, rob_note = "not_serious", f"{rob_entry['proportion_low_risk']:.0%} of contributing studies judged low risk / good quality."
    elif rob_entry["proportion_low_risk"] >= 0.5:
        rob_rating, rob_note = "serious", f"Only {rob_entry['proportion_low_risk']:.0%} of contributing studies judged low risk / good quality."
    else:
        rob_rating, rob_note = "very_serious", f"Only {rob_entry['proportion_low_risk']:.0%} of contributing studies judged low risk / good quality."

    if het is None:
        inconsistency_rating, inconsistency_note = "not_serious", "Single study or narrative synthesis -- no statistical heterogeneity to test."
    elif het["I2"] > 75 or het["p_value"] < 0.01:
        inconsistency_rating, inconsistency_note = "very_serious", f"I2={het['I2']:.1f}%, Q p={het['p_value']:.4f}."
    elif het["I2"] > 50 or het["p_value"] < 0.10:
        inconsistency_rating, inconsistency_note = "serious", f"I2={het['I2']:.1f}%, Q p={het['p_value']:.4f}."
    else:
        inconsistency_rating, inconsistency_note = "not_serious", f"I2={het['I2']:.1f}%, Q p={het['p_value']:.4f}."

    if k >= FUNNEL_MIN_K:
        pub_bias_rating, pub_bias_note = "needs_review", f"k={k} >= {FUNNEL_MIN_K}: funnel plot generated, inspect for asymmetry and update this rating."
    else:
        pub_bias_rating, pub_bias_note = "undetected", f"k={k} < {FUNNEL_MIN_K}: insufficient power to assess publication bias, not rated as absent."

    return {
        "outcome": outcome_name,
        "n_studies": k,  # count of rows contributing to this body of evidence (effect_data + narrative rows) -- may exceed the pooled k in heterogeneity.json/effect_sizes.json when some were excluded during conversion; reconcile against effect_sizes.json's "excluded" list, never treat this as "studies actually pooled"
        "starting_certainty": starting,
        "starting_certainty_note": starting_note,
        "domains": {
            "risk_of_bias": {"rating": rob_rating, "note": rob_note},
            "inconsistency": {"rating": inconsistency_rating, "note": inconsistency_note},
            "indirectness": {"rating": "needs_review", "note": "Compare each contributing study's population/intervention/comparator/outcome against protocol.json's PICO -- fill in per quality-appraisal/02-grade-certainty.md."},
            "imprecision": {"rating": "needs_review", "note": "Compare the pooled 95% CI width against the review's a priori MCID (or, for narrative outcomes, total sample size) -- fill in per quality-appraisal/02-grade-certainty.md."},
            "publication_bias": {"rating": pub_bias_rating, "note": pub_bias_note},
        },
        "rate_up": [],
        "final_certainty": "needs_review",
        "effect": effect_summary,
        "model_used": model_used,
    }


def process_outcome_group(outcome_name, measure, rows, out_dir, slug):
    """rows: all rows for this (outcome, measure_type) pair. Returns
    (effect_sizes_entry, heterogeneity_entry, grade_entry, rob_entry)."""
    study_effects, excluded = [], []
    for row in rows:
        try:
            effect, variance, display, corrected = convert_effect(row["effect_data"])
        except ValueError as reason:
            excluded.append({"study_id": row["study_id"], "reason": str(reason)})
            continue
        study_effects.append({
            "study_id": row["study_id"], "author_year": row["author_year"],
            "effect": effect, "variance": variance, "se": math.sqrt(variance),
            "display_estimate": display, "continuity_correction_applied": corrected,
            # Provenance pass-through (docs/PLAN.md PR p0-11-extraction-provenance):
            # `source` (quote/locator/notes) is per-datapoint, already inside
            # effect_data; `reports`/`by`/`verified_by` are per-study, carried
            # here by flatten_rows.
            "source": row["effect_data"].get("source"),
            "reports": row.get("reports"), "by": row.get("by"), "verified_by": row.get("verified_by"),
        })

    rob_entry = build_rob_entry(outcome_name, rows)
    k = len(study_effects)

    if k < POOL_MIN_K:
        reason = (f"only {k} study/studies with usable effect data for this outcome+measure "
                  f"(need >= {POOL_MIN_K} to pool)" + (f"; excluded: {excluded}" if excluded else ""))
        effect_sizes_entry = {"outcome": outcome_name, "measure_type": measure, "pooled": False, "studies": study_effects, "excluded": excluded}
        heterogeneity_entry = {"outcome": outcome_name, "measure_type": measure, "pooled": False, "reason": reason}
        grade_entry = build_grade_draft(outcome_name, rows, "narrative", len(rows), None, None)
        return effect_sizes_entry, heterogeneity_entry, grade_entry, rob_entry

    effects = [s["effect"] for s in study_effects]
    variances = [s["variance"] for s in study_effects]
    het = compute_heterogeneity(effects, variances)
    model = choose_model(het["I2"], het["p_value"])
    pooled = pool_effects(effects, variances, model)

    display_pooled = math.exp(pooled["pooled_effect"]) if measure in LOG_SCALE_MEASURES else pooled["pooled_effect"]
    display_ci_low = math.exp(pooled["ci_low"]) if measure in LOG_SCALE_MEASURES else pooled["ci_low"]
    display_ci_high = math.exp(pooled["ci_high"]) if measure in LOG_SCALE_MEASURES else pooled["ci_high"]

    for s in study_effects:
        s["ci_low"] = s["effect"] - Z95 * s["se"]
        s["ci_high"] = s["effect"] + Z95 * s["se"]
        s["display_ci_low"] = math.exp(s["ci_low"]) if measure in LOG_SCALE_MEASURES else s["ci_low"]
        s["display_ci_high"] = math.exp(s["ci_high"]) if measure in LOG_SCALE_MEASURES else s["ci_high"]

    forest_path = os.path.join(out_dir, f"forest_{slug}.svg")
    forest_plot(
        studies=[{"label": s["author_year"], "effect": s["effect"], "ci_low": s["ci_low"], "ci_high": s["ci_high"]} for s in study_effects],
        pooled={"effect": pooled["pooled_effect"], "ci_low": pooled["ci_low"], "ci_high": pooled["ci_high"], "label": f"Pooled ({model}-effects)"},
        out_path=forest_path,
        null_value=0,  # always drawn on the pooling scale (log for OR/RR) -- see display_* fields for the exponentiated numbers
    )

    funnel_path = None
    if k >= FUNNEL_MIN_K:
        funnel_path = os.path.join(out_dir, f"funnel_{slug}.svg")
        funnel_plot(studies=[{"effect": s["effect"], "se": s["se"]} for s in study_effects], out_path=funnel_path)

    effect_sizes_entry = {
        "outcome": outcome_name, "measure_type": measure, "pooled": True, "model": model,
        "scale": "log" if measure in LOG_SCALE_MEASURES else "natural",
        "studies": study_effects, "excluded": excluded,
        "pooled_effect": pooled, "display_estimate": display_pooled,
        "display_ci_low": display_ci_low, "display_ci_high": display_ci_high,
        "forest_plot_svg": forest_path, "funnel_plot_svg": funnel_path,
    }
    heterogeneity_entry = {
        "outcome": outcome_name, "measure_type": measure, "pooled": True,
        "k": k, "Q": het["Q"], "df": het["df"], "p_value": het["p_value"], "I2": het["I2"], "model": model,
    }
    effect_summary = {"measure": measure, "estimate": display_pooled, "ci_low": display_ci_low, "ci_high": display_ci_high}
    grade_entry = build_grade_draft(outcome_name, rows, model, k, het, effect_summary)
    return effect_sizes_entry, heterogeneity_entry, grade_entry, rob_entry


def build_rob_traffic_light(studies, out_dir):
    """Render one traffic-light plot covering every RoB2-assessed study with a
    full domain breakdown (studies assessed with NOS, or with only an
    `overall_judgement` and no `domains`, are silently excluded -- RoB2's
    seven domains and NOS's three categories aren't the same axes, and
    rob_table.json already covers both tools' overall judgements together).
    Returns the SVG path, or None if no study qualifies (never raises)."""
    plot_studies = []
    for study in studies:
        rob = study.get("risk_of_bias")
        if not rob or rob.get("tool") != "RoB2" or not rob.get("domains"):
            continue
        domains = {key: entry.get("judgement") for key, entry in rob["domains"].items()}
        plot_studies.append({
            "label": study.get("author_year") or study["record_id"],
            "domains": domains,
            "overall": rob.get("overall_judgement"),
        })
    if not plot_studies:
        return None
    out_path = os.path.join(out_dir, "rob_traffic_light.svg")
    rob_traffic_light_plot(plot_studies, ROB2_DOMAIN_LABELS, out_path)
    return out_path


def _atomic_write_json(path, data):
    """Write `data` as JSON to `path` via a temp sibling file + os.replace, so a
    crash mid-write can never leave a partially-written file as the canonical
    artifact (PRODUCT_READINESS_AUDIT.md P0-1)."""
    tmp_path = f"{path}.tmp{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def run(extraction_table_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    studies = load_studies(extraction_table_path)
    rows = flatten_rows(studies)

    quantitative = [r for r in rows if r["type"] == "quantitative" and r.get("effect_data")]
    qualitative_names = {r["outcome"] for r in rows if r["type"] != "quantitative" or not r.get("effect_data")}
    quantitative_names = {r["outcome"] for r in quantitative}
    narrative_only_names = qualitative_names - quantitative_names

    groups = {}
    for row in quantitative:
        measure = (row["effect_data"] or {}).get("measure_type", "UNKNOWN")
        groups.setdefault((row["outcome"], measure), []).append(row)

    effect_sizes, heterogeneity, grade_table, rob_table = [], [], [], []

    for (outcome_name, measure), group_rows in sorted(groups.items()):
        slug = slugify(f"{outcome_name}-{measure}")
        es, het, grade, rob = process_outcome_group(outcome_name, measure, group_rows, out_dir, slug)
        effect_sizes.append(es)
        heterogeneity.append(het)
        grade_table.append(grade)
        rob_table.append(rob)

    for outcome_name in sorted(narrative_only_names):
        narrative_rows = [r for r in rows if r["outcome"] == outcome_name]
        heterogeneity.append({
            "outcome": outcome_name, "measure_type": None, "pooled": False,
            "reason": "qualitative/narrative-only outcome -- no study reported extractable effect data for it",
        })
        rob_table.append(build_rob_entry(outcome_name, narrative_rows))
        grade_table.append(build_grade_draft(outcome_name, narrative_rows, "narrative", len(narrative_rows), None, None))

    _atomic_write_json(os.path.join(out_dir, "effect_sizes.json"), effect_sizes)
    _atomic_write_json(os.path.join(out_dir, "heterogeneity.json"), heterogeneity)
    _atomic_write_json(os.path.join(out_dir, "rob_table.json"), rob_table)
    _atomic_write_json(os.path.join(out_dir, "grade_table.json"), grade_table)

    rob_traffic_light_svg = build_rob_traffic_light(studies, out_dir)

    return {
        "effect_sizes": effect_sizes, "heterogeneity": heterogeneity, "grade_table": grade_table,
        "rob_table": rob_table, "rob_traffic_light_svg": rob_traffic_light_svg,
    }


def main():
    # Imported lazily, not at module level: this module's __main__ self-check
    # runs via `python3 synthesis/run_synthesis.py` (script-path invocation,
    # repo root not on sys.path), while the CLI path this function serves
    # only ever runs via `python3 -m synthesis.run_synthesis` from the repo
    # root (where `tools` is importable) -- see the bottom of this file.
    from tools.path_policy import UnsafePathError, safe_topic_path

    parser = argparse.ArgumentParser(description="Group extraction_table.json by outcome, pool poolable outcomes, write synthesis/*.json + plots.")
    parser.add_argument("--topic", required=True,
                         help="review slug; derives results/<topic>/extraction_table.json "
                              "and results/<topic>/synthesis/ itself -- never accepts a free-form path "
                              "(PRODUCT_READINESS_AUDIT.md P0-1: this permission is pre-approved, so "
                              "the CLI must not let any argument direct a write outside results/<topic>/)")
    args = parser.parse_args()
    try:
        extraction_table_path = safe_topic_path(args.topic, "extraction_table.json")
        out_dir = safe_topic_path(args.topic, "synthesis")
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    result = run(str(extraction_table_path), str(out_dir))
    pooled_n = sum(1 for h in result["heterogeneity"] if h["pooled"])
    narrative_n = sum(1 for h in result["heterogeneity"] if not h["pooled"])
    rob_plot_note = f"rob_traffic_light.svg ({result['rob_traffic_light_svg']})" if result["rob_traffic_light_svg"] else \
        "rob_traffic_light.svg NOT written (no RoB2-assessed study had a full domains breakdown)"
    print(f"{len(result['heterogeneity'])} outcome group(s): {pooled_n} pooled, {narrative_n} narrative fallback. "
          f"Wrote effect_sizes.json, heterogeneity.json, rob_table.json, grade_table.json, {rob_plot_note} to {out_dir}")
    for grade in result["grade_table"]:
        if grade["final_certainty"] == "needs_review":
            print(f"  NEEDS REVIEW before report: GRADE indirectness/imprecision for outcome {grade['outcome']!r}")
    return 0


def _selfcheck():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        fixture = {"framework_version": "1.0.0", "topic": "selfcheck", "studies": [
            {  # 3 studies, dichotomous RR, poolable, no zero cells
                "record_id": "alpha2020", "author_year": "Alpha et al. 2020", "study_design": "RCT",
                "outcomes_measured": ["PONV"],
                "risk_of_bias": {"tool": "RoB2", "overall_judgement": "low risk", "domains": {
                    "sequence_generation": {"judgement": "low", "support": "computer-generated"},
                    "allocation_concealment": {"judgement": "low", "support": "sealed envelopes"},
                    "blinding_participants_personnel": {"judgement": "low", "support": "double-blind"},
                    "blinding_outcome_assessment": {"judgement": "low", "support": "blinded assessors"},
                    "incomplete_outcome_data": {"judgement": "low", "support": "no dropouts"},
                    "selective_reporting": {"judgement": "low", "support": "matches registry"},
                    "other_bias": {"judgement": "low", "support": "none identified"},
                }},
                "effect_data": [{"outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
                                  "intervention_arm": {"label": "drug", "events": 12, "total": 60},
                                  "comparator_arm": {"label": "placebo", "events": 25, "total": 60}}],
            },
            {
                "record_id": "beta2021", "author_year": "Beta et al. 2021", "study_design": "RCT",
                "outcomes_measured": ["PONV"],
                "risk_of_bias": {"tool": "RoB2", "overall_judgement": "some concerns", "domains": {
                    "sequence_generation": {"judgement": "low", "support": "random number table"},
                    "allocation_concealment": {"judgement": "unclear", "support": "not described"},
                    "blinding_participants_personnel": {"judgement": "low", "support": "double-blind"},
                    "blinding_outcome_assessment": {"judgement": "low", "support": "blinded assessors"},
                    "incomplete_outcome_data": {"judgement": "low", "support": "no dropouts"},
                    "selective_reporting": {"judgement": "low", "support": "matches registry"},
                    "other_bias": {"judgement": "low", "support": "none identified"},
                }},
                "effect_data": [{"outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
                                  "intervention_arm": {"label": "drug", "events": 8, "total": 50},
                                  "comparator_arm": {"label": "placebo", "events": 0, "total": 50}}],  # zero cell -> continuity correction
            },
            {
                "record_id": "gamma2022", "author_year": "Gamma et al. 2022", "study_design": "RCT",
                "outcomes_measured": ["PONV"],
                "risk_of_bias": {"tool": "RoB2", "overall_judgement": "low risk", "domains": {
                    "sequence_generation": {"judgement": "low", "support": "computer-generated"},
                    "allocation_concealment": {"judgement": "low", "support": "central allocation"},
                    "blinding_participants_personnel": {"judgement": "low", "support": "double-blind"},
                    "blinding_outcome_assessment": {"judgement": "low", "support": "blinded assessors"},
                    "incomplete_outcome_data": {"judgement": "low", "support": "no dropouts"},
                    "selective_reporting": {"judgement": "low", "support": "matches registry"},
                    "other_bias": {"judgement": "low", "support": "none identified"},
                }},
                "effect_data": [{"outcome": "PONV", "measure_type": "RR", "timepoint": "24h",
                                  "intervention_arm": {"label": "drug", "events": 15, "total": 55},
                                  "comparator_arm": {"label": "placebo", "events": 22, "total": 55}}],
            },
            {  # only study reporting this outcome -> narrative fallback (k<2)
                "record_id": "delta2019", "author_year": "Delta et al. 2019", "study_design": "cohort",
                "outcomes_measured": ["length of stay"],
                "risk_of_bias": {"tool": "NOS", "overall_judgement": "good quality"},
                "effect_data": [{"outcome": "length of stay", "measure_type": "MD", "timepoint": "discharge",
                                  "intervention_arm": {"label": "drug", "mean": 3.1, "sd": 1.0, "n": 40},
                                  "comparator_arm": {"label": "placebo", "mean": 3.1, "sd": 1.0, "n": 40}}],  # var>0 but k=1
            },
            {  # qualitative-only outcome, no effect_data anywhere -> narrative fallback
                "record_id": "epsilon2018", "author_year": "Epsilon et al. 2018", "study_design": "RCT",
                "outcomes_measured": ["patient satisfaction"],
                "risk_of_bias": {"tool": "RoB2", "overall_judgement": "high risk", "domains": {
                    "sequence_generation": {"judgement": "high", "support": "alternation by admission order"},
                    "allocation_concealment": {"judgement": "high", "support": "not concealed"},
                    "blinding_participants_personnel": {"judgement": "high", "support": "open-label"},
                    "blinding_outcome_assessment": {"judgement": "unclear", "support": "not described"},
                    "incomplete_outcome_data": {"judgement": "low", "support": "no dropouts"},
                    "selective_reporting": {"judgement": "low", "support": "matches registry"},
                    "other_bias": {"judgement": "low", "support": "none identified"},
                }},
                "effect_data": [],
            },
            {  # no study_design, no risk_of_bias at all -> regression guard for the
               # empty-all()-is-True starting_certainty bug (must land on "low", never "high")
                "record_id": "zeta2020", "author_year": "Zeta et al. 2020",
                "outcomes_measured": ["adverse events"],
                "risk_of_bias": None,
                "effect_data": [],
            },
        ]}
        fixture_path = os.path.join(tmp, "extraction_table.json")
        with open(fixture_path, "w") as f:
            json.dump(fixture, f)
        out_dir = os.path.join(tmp, "synthesis")

        result = run(fixture_path, out_dir)

        het_by_outcome = {h["outcome"]: h for h in result["heterogeneity"]}

        # PONV: 3 studies, pooled, one continuity-corrected.
        ponv = het_by_outcome["PONV"]
        assert ponv["pooled"] is True, ponv
        assert ponv["k"] == 3, ponv
        assert ponv["model"] in ("fixed", "random"), ponv
        es_ponv = next(e for e in result["effect_sizes"] if e["outcome"] == "PONV")
        assert any(s["continuity_correction_applied"] for s in es_ponv["studies"]), "expected beta2021's zero cell to trigger continuity correction"
        assert 0 < es_ponv["display_estimate"] < 5, es_ponv["display_estimate"]
        assert os.path.exists(es_ponv["forest_plot_svg"]) and os.path.getsize(es_ponv["forest_plot_svg"]) > 0
        assert es_ponv["funnel_plot_svg"] is None, "k=3 must not trigger a funnel plot (needs >=10)"

        # length of stay: single study -> narrative fallback with a reason.
        los = het_by_outcome["length of stay"]
        assert los["pooled"] is False and "only 1 study" in los["reason"], los

        # patient satisfaction: qualitative-only -> narrative fallback with the qualitative reason.
        satisfaction = het_by_outcome["patient satisfaction"]
        assert satisfaction["pooled"] is False and "qualitative" in satisfaction["reason"], satisfaction

        all_outcomes = {"PONV", "length of stay", "patient satisfaction", "adverse events"}

        # Every outcome must get a GRADE entry, including all narrative ones.
        grade_by_outcome = {g["outcome"]: g for g in result["grade_table"]}
        assert set(grade_by_outcome) == all_outcomes, set(grade_by_outcome)
        for name, g in grade_by_outcome.items():
            if name != "PONV":
                assert g["model_used"] == "narrative" and g["effect"] is None, g

        # PONV: all-RCT body -> High baseline.
        assert grade_by_outcome["PONV"]["starting_certainty"] == "high", grade_by_outcome["PONV"]
        # length of stay: single cohort study -> Low baseline (observational).
        assert grade_by_outcome["length of stay"]["starting_certainty"] == "low", grade_by_outcome["length of stay"]
        # adverse events: no risk_of_bias/study_design at all -> must land on Low,
        # NEVER "high" (regression guard for all()-over-empty-sequence being True).
        adverse = grade_by_outcome["adverse events"]
        assert adverse["starting_certainty"] == "low", adverse
        assert "missing" in adverse["starting_certainty_note"].lower() or "unknown" in adverse["starting_certainty_note"].lower(), adverse

        # rob_table covers every outcome too, including narrative-only ones.
        rob_outcomes = {r["outcome"] for r in result["rob_table"]}
        assert rob_outcomes == all_outcomes, rob_outcomes
        adverse_rob = next(r for r in result["rob_table"] if r["outcome"] == "adverse events")
        assert adverse_rob["proportion_low_risk"] is None and "zeta2020" in adverse_rob["missing_assessment"], adverse_rob

        # Traffic light: alpha/beta/gamma/epsilon have RoB2 domains, delta is NOS
        # (excluded), zeta has no risk_of_bias at all (excluded) -> 4 studies plotted.
        assert result["rob_traffic_light_svg"] and os.path.getsize(result["rob_traffic_light_svg"]) > 0
        assert os.path.basename(result["rob_traffic_light_svg"]) == "rob_traffic_light.svg"

        # A body of evidence with no domains-level RoB2 assessment at all must not write the file.
        no_domains_fixture = {"framework_version": "1.0.0", "topic": "selfcheck-no-domains", "studies": [
            {"record_id": "solo2020", "author_year": "Solo et al. 2020", "study_design": "cohort",
             "outcomes_measured": ["length of stay"],
             "risk_of_bias": {"tool": "NOS", "overall_judgement": "good quality"}, "effect_data": []},
        ]}
        no_domains_path = os.path.join(tmp, "extraction_table_no_domains.json")
        with open(no_domains_path, "w") as f:
            json.dump(no_domains_fixture, f)
        no_domains_result = run(no_domains_path, os.path.join(tmp, "synthesis_no_domains"))
        assert no_domains_result["rob_traffic_light_svg"] is None, no_domains_result["rob_traffic_light_svg"]

        # Zero-total edge case must raise a recorded reason, not crash the group.
        try:
            convert_effect({"measure_type": "RR",
                             "intervention_arm": {"events": 0, "total": 0},
                             "comparator_arm": {"events": 1, "total": 10}})
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for total_treatment=0")

        print("self-check OK")


if __name__ == "__main__":
    # `python3 synthesis/run_synthesis.py` with no args runs the self-check
    # (matches synthesis/pooling.py, heterogeneity.py, plots.py's convention);
    # `python3 -m synthesis.run_synthesis --topic <TOPIC>`
    # (the invocation /prisma-synthesize actually uses) runs the CLI.
    if len(sys.argv) > 1:
        sys.exit(main())
    else:
        _selfcheck()
