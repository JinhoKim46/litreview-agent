---
name: quality-appraisal
description: Assess risk of bias in included studies and rate the certainty of evidence for each outcome. Use during /prisma-extract (per-study risk-of-bias judgements) and /prisma-synthesize (per-outcome GRADE certainty rating, after pooling or narrative fallback). Trigger phrases — "assess risk of bias", "RoB1", "risk of bias assessment", "Cochrane risk of bias tool", "Newcastle-Ottawa", "NOS score", "GRADE the evidence", "certainty of evidence", "quality of evidence", "rate down/rate up", "summary of findings table", "how reliable is this evidence", "is this study biased". Do not use for eligibility screening (that's review-protocol) or for choosing pooling models (that's synthesis/heterogeneity.py) — this skill only judges study/outcome quality, not whether data can be combined.
framework_version: 1.0.2
---

# Quality Appraisal: Risk of Bias + GRADE Certainty

Systematic reviews don't just count studies — they weigh them. A pooled estimate built from five studies at high risk of bias is not more reliable than one careful study; it can be actively misleading. This skill provides the two-stage appraisal every included study and every synthesized outcome must pass through before `/prisma-report` writes a word about strength of evidence:

1. **Study-level risk of bias** (`01-risk-of-bias.md`) — is *this individual study's* result trustworthy, given how it was designed and run?
2. **Outcome-level certainty of evidence** (`02-grade-certainty.md`) — given *all* the studies that contributed to *this outcome*, how confident can a reader be in the pooled (or narrative) conclusion?

These are different questions at different levels. A body of evidence can be built entirely from low-risk-of-bias RCTs and still merit only "moderate" certainty overall, if the studies are inconsistent with each other or the outcome estimate is imprecise. Never collapse the two into one number.

## When this runs in the pipeline

- **`/prisma-extract`**: for every included study, run the RoB1 six-domain assessment (RCTs) or the Newcastle-Ottawa Scale (non-randomized studies) and write the result into that study's `risk_of_bias` block in `extraction_table.json`.
- **`/prisma-synthesize`**: after pooling (or falling back to narrative synthesis) for each outcome, roll the per-study risk-of-bias judgements up into an outcome-level GRADE rating alongside inconsistency, indirectness, imprecision, and publication bias. Write `rob_table.json` and `grade_table.json`.

Both files are read verbatim by `/prisma-report` to draft the "Quality of evidence" methods paragraph, the risk-of-bias figure/table, the GRADE summary of findings table, and the certainty language used in the Discussion — never re-derived from memory at report time.

## Choosing the right tool

| Study design | Tool | File |
|---|---|---|
| Randomized controlled trial (individual- or cluster-randomized, parallel or crossover) | Cochrane RoB1 (six domains, per Higgins/Altman/Sterne, Cochrane Handbook Ch. 8) | `01-risk-of-bias.md` |
| Non-randomized study (cohort, case-control, before-after, cross-sectional) | Newcastle-Ottawa Scale (NOS) | `01-risk-of-bias.md`, NOS section |

Ask the reviewer to confirm study design during `/prisma-extract` if the included-study table doesn't already record it unambiguously — RoB1 and NOS are not interchangeable, and using RoB1's "allocation concealment" domain on a cohort study produces a meaningless judgement (there was no allocation to conceal).

## Independent, dual assessment

Per both the source primer (kjae-2018) and the Cochrane Handbook, risk-of-bias and GRADE judgements are ideally made by **two independent assessors**, with disagreements resolved by discussion or a third reviewer. Claude performs the assessment as a single first-pass rater and always says so explicitly in the written judgement — it does not claim dual-reviewer independence it cannot provide. When a human co-reviewer's judgements are available (e.g. imported alongside the extraction table), reconcile them and record any resolved disagreement in the `notes` field rather than silently overwriting either judgement.

## Never fabricate a judgement

A risk-of-bias or GRADE rating is only ever written when the "support for judgement" text quotes or paraphrases something actually present in the extracted study data (the methods section, the extraction table's `effect_data`, or the reviewer's own notes). If information needed for a domain is genuinely absent from what was extracted (e.g. the paper never describes randomization method), the correct judgement is **"unclear"** (RoB1) or the corresponding NOS star withheld — not a guessed "low risk." Flag missing information back to the reviewer rather than inferring it.

## Output files

**`extraction_table.json`** (per study, written during `/prisma-extract`) — each included study's entry carries a `risk_of_bias` block:

```json
{
  "tool": "RoB1",
  "domains": {
    "sequence_generation": {"judgement": "low", "support": "Computer-generated randomization sequence, described in Methods 2.2."},
    "allocation_concealment": {"judgement": "unclear", "support": "Allocation method not described."},
    "blinding_participants_personnel": {"judgement": "low", "support": "Identical-appearing placebo infusion, double-blind per Methods 2.3."},
    "blinding_outcome_assessment": {"judgement": "low", "support": "Outcome assessors blinded to group assignment."},
    "incomplete_outcome_data": {"judgement": "low", "support": "2/60 (3.3%) lost to follow-up, balanced across arms, reasons reported."},
    "selective_reporting": {"judgement": "low", "support": "Prespecified outcomes in registered protocol (NCT-------) all reported."},
    "other_bias": {"judgement": "low", "support": "No other concerns identified."}
  },
  "overall_judgement": "unclear risk",
  "assessed_by": "claude (single-rater first pass)",
  "assessed_at": "2026-01-01T00:00:00Z"
}
```

For a non-randomized study, `tool` is `"NOS"` and `domains` is replaced by the three NOS categories (`selection`, `comparability`, `outcome`) each carrying `stars_awarded`/`stars_possible` and `support`, per `01-risk-of-bias.md`.

**`synthesis/rob_table.json`** (per outcome, written during `/prisma-synthesize`) — aggregates the per-study judgements contributing to one outcome, for the manuscript's risk-of-bias summary figure:

```json
{
  "outcome": "postoperative nausea and vomiting (PONV)",
  "studies": [
    {"study_id": "smith2019", "tool": "RoB1", "overall_judgement": "low risk"},
    {"study_id": "lee2020", "tool": "RoB1", "overall_judgement": "unclear risk"}
  ],
  "proportion_low_risk": 0.5
}
```

**`synthesis/grade_table.json`** (per outcome, written during `/prisma-synthesize`) — the GRADE summary-of-findings row, per the schema in `02-grade-certainty.md`.

## See also

- `01-risk-of-bias.md` — RoB1 six-domain definitions and judgement criteria (RCTs), the Newcastle-Ottawa Scale (non-randomized studies).
- `02-grade-certainty.md` — the five GRADE domains, starting certainty by study design, rate-down/rate-up rules, and the four certainty levels.
- `../../../synthesis/heterogeneity.py` — computes the I²/Q statistics that `02-grade-certainty.md`'s inconsistency domain reads.
- `../../../results/<TOPIC>/extraction_table.json` — where per-study `risk_of_bias` blocks live.
