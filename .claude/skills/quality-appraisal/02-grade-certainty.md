---
framework_version: 1.0.2
---

# GRADE: Rating Certainty of Evidence

Risk of bias (`01-risk-of-bias.md`) judges individual studies. **GRADE** (Grading of Recommendations, Assessment, Development and Evaluations; http://www.gradeworkinggroup.org/) judges the whole **body of evidence for one outcome** — every study that contributed to that outcome's pooled or narrative estimate, taken together. Run this once per outcome, in `/prisma-synthesize`, after pooling (or after the poolability gate routes that outcome to narrative synthesis instead).

## Starting point: study design sets the baseline

- A body of evidence built from **randomized controlled trials** starts at **High** certainty.
- A body of evidence built from **non-randomized/observational studies** starts at **Low** certainty.

From that baseline, certainty is **rated down** across five domains (below) and, for observational evidence only, occasionally **rated up**.

## The five domains that rate down certainty

| Domain | Question it asks | Typical trigger for "serious" (−1) or "very serious" (−2) concern |
|---|---|---|
| **Risk of bias** | Are the contributing studies individually trustworthy? | A majority of the outcome's evidence comes from studies with an overall RoB1 judgement of "unclear risk" (serious) or "high risk" (very serious), or NOS "fair"/"poor" quality — read `synthesis/rob_table.json`'s `proportion_low_risk` and which studies drive the pooled weight. |
| **Inconsistency** | Do the studies agree with each other? | High statistical heterogeneity: I² > 50%, or Cochrane's Q test p < 0.10 (per `synthesis/heterogeneity.py`'s output), especially when point estimates point in different directions or confidence intervals barely overlap. Overlapping CIs and I² < 25-50% with the same effect direction = not serious. |
| **Indirectness** | Do the studies actually address the review's PICO, or something adjacent to it? | The population, intervention, comparator, or outcome measured in the studies differs meaningfully from what the review question asks (e.g. surrogate outcome instead of the patient-important one; a different drug class; a population outside the review's inclusion criteria used only for context). |
| **Imprecision** | Is the pooled estimate precise enough to act on? | A wide 95% confidence interval that crosses the line of no effect (RR/OR = 1, or MD/SMD = 0) in a way that would change the clinical conclusion, or a small total sample size / few events relative to what's needed for a stable estimate (optimal information size not met). |
| **Publication bias** | Is the visible evidence a biased sample of all the evidence that exists? | Funnel plot asymmetry (only generated at ≥10 studies per the synthesis gate), a statistically significant Egger's test, or a body of evidence dominated by small, industry-funded, or positive-only studies with no registered protocols found. When fewer than 10 studies contribute, publication bias is usually rated "undetected" (not "none") — the tools to detect it don't have enough power, so say so rather than implying its absence was confirmed. |

Each domain is rated **not serious**, **serious** (−1 level), or **very serious** (−2 levels). Every downgrade must cite the specific evidence behind it (the heterogeneity numbers, the RoB1 proportions, the CI width) — never a bare "serious" with no support, mirroring the risk-of-bias rule that a judgement is only as good as what backs it.

## Rating up (observational evidence only)

An observational body of evidence that started at Low can be rated **up** when:

- **Large effect** — a risk ratio or odds ratio consistently far from 1 (e.g. RR > 2 or < 0.5) with no plausible confounders that could explain an effect of that size (+1 level; +2 for a very large effect, e.g. RR > 5 or < 0.2).
- **Dose-response gradient** — increasing exposure/dose is associated with increasing effect magnitude (+1 level).
- **Plausible confounding would reduce, not create, the observed effect** — i.e. all plausible unmeasured confounders would bias the result *toward* the null, yet an effect was still observed (+1 level).

RCT evidence is never rated up under GRADE — it already starts at High.

## Final certainty levels

| Certainty | Interpretation |
|---|---|
| **High** ⨁⨁⨁⨁ | Very confident the true effect lies close to the estimate. |
| **Moderate** ⨁⨁⨁◯ | Moderately confident; the true effect is likely close to the estimate, but could be substantially different. |
| **Low** ⨁⨁◯◯ | Confidence in the estimate is limited; the true effect may be substantially different. |
| **Very low** ⨁◯◯◯ | Very little confidence in the estimate; the true effect is likely to be substantially different. |

Net rating = starting level, minus one level per domain rated "serious", minus two per domain rated "very serious" (floor at Very low), plus any rate-up levels earned for observational evidence. Apply downgrades independently per domain and sum them — do not double-count the same underlying problem across two domains (e.g. don't rate down both inconsistency and indirectness for a single population mismatch that only affects indirectness).

## Worked example (from the source primer)

The following is a real published GRADE summary-of-findings table, reproduced from Ahn E, Kang H. Introduction to systematic review and meta-analysis. Korean J Anesthesiol 2018;71(2):103-112, Table 4 — comparing palonosetron vs. ramosetron for postoperative nausea/vomiting prevention:

| Outcome | N studies | Risk of bias | Inconsistency | Indirectness | Imprecision | Other | Palonosetron | Ramosetron | RR (95% CI) | Certainty |
|---|---|---|---|---|---|---|---|---|---|---|
| Postoperative nausea (PON) | 6 | Serious | Serious | Not serious | Not serious | None | 81/304 (26.6%) | 80/305 (26.2%) | 0.92 (0.54–1.58) | Very low |
| Postoperative vomiting (POV) | 5 | Serious | Serious | Not serious | Not serious | None | 55/274 (20.1%) | 60/275 (21.8%) | 0.87 (0.48–1.57) | Very low |
| Postoperative nausea and vomiting (PONV) | 3 | Not serious | Serious | Not serious | Not serious | None | 108/184 (58.7%) | 107/186 (57.5%) | 0.92 (0.54–1.58) | Low |

Reading this table: PON and POV each carried two downgrades (risk of bias, inconsistency) from an RCT-evidence starting point of High, landing at Very low; PONV carried one downgrade (inconsistency only, since its contributing studies were judged not-serious for risk of bias), landing at Low. This is exactly the arithmetic to reproduce for every outcome group in `/prisma-synthesize` — start from the design baseline, apply each domain's downgrade independently, and land on one of the four certainty levels with every downgrade traceable to a specific number or judgement, not asserted.

## Output: `synthesis/grade_table.json`

One entry per outcome, written during `/prisma-synthesize` and read verbatim by `/prisma-report` for the Results summary-of-findings table and the certainty language used in the Discussion:

```json
{
  "outcome": "postoperative nausea and vomiting (PONV)",
  "n_studies": 3,
  "starting_certainty": "high",
  "domains": {
    "risk_of_bias": {"rating": "not_serious", "note": "All 3 contributing studies judged RoB1 'low risk'; see rob_table.json."},
    "inconsistency": {"rating": "serious", "note": "I² = 62%, Q p = 0.07 (heterogeneity.json); effect direction consistent, magnitude varies."},
    "indirectness": {"rating": "not_serious", "note": "All studies match the review's PICO population, intervention, and outcome definition exactly."},
    "imprecision": {"rating": "not_serious", "note": "95% CI (0.54–1.58) excludes a doubling of risk in either direction relative to the a priori MCID."},
    "publication_bias": {"rating": "undetected", "note": "Fewer than 10 studies; funnel plot/Egger's test not performed (insufficient power to assess)."}
  },
  "rate_up": [],
  "final_certainty": "low",
  "effect": {"measure": "RR", "estimate": 0.92, "ci_low": 0.54, "ci_high": 1.58},
  "model_used": "random-effects",
  "importance": "critical"
}
```

`domains.*.rating` is one of `not_serious`, `serious`, `very_serious` (and `undetected`/`not_assessed` for publication bias when k < 10). `final_certainty` is one of `high`, `moderate`, `low`, `very_low`. When an outcome fell back to narrative synthesis instead of pooling (per the poolability gate in `SKILL.md`'s parent `/prisma-synthesize` command), still write a `grade_table.json` entry for it with `"model_used": "narrative"` and `effect: null` — GRADE certainty applies to the underlying body of evidence regardless of whether it was statistically pooled.
