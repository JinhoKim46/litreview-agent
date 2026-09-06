---
framework_version: 1.1.0
---

# Risk of Bias Assessment

Two tools cover the study designs a systematic review typically includes: the **original Cochrane Collaboration's tool for assessing risk of bias** (2011, informally called "RoB1" to distinguish it from its 2019 successor) for randomized controlled trials, and the **Newcastle-Ottawa Scale (NOS)** for non-randomized studies. Use exactly one per study, matched to its actual design — never mix domains from the two tools on a single study.

**This is the legacy 2011 tool, not the current Cochrane RoB 2 (Sterne et al., BMJ 2019).** RoB 2 uses five different, result-specific domains (randomization process; deviations from intended interventions; missing outcome data; measurement of the outcome; selection of the reported result), signalling questions, and an algorithm-supported overall judgement, and is now the Cochrane-recommended tool for RCTs. This framework implements RoB1 only; adopting real RoB 2 is tracked as future work (see `docs/ROADMAP.md`) rather than something silently substituted here.

## Part 1 — Cochrane Risk of Bias Tool (RCTs)

Source: Higgins JP, Altman DG, Sterne JA. Chapter 8: Assessing risk of bias in included studies. In: *Cochrane Handbook for Systematic Reviews of Interventions*. The Cochrane Collaboration, 2011 (updated 2017). Six domains, each judged **low / high / unclear**, each requiring a written "support of judgement" — a specific quote or paraphrase from the study, never a bare label with no evidence behind it.

| Domain | Support of judgement — what to look for | What the judgement is protecting against |
|---|---|---|
| **Sequence generation** | Describe the method used to generate the allocation sequence in sufficient detail to allow an assessment of whether it should produce comparable groups (e.g. computer random-number generator, random-number table, coin toss — vs. alternation, date of birth, admission order). | Selection bias (biased allocation to interventions) due to inadequate generation of a randomized sequence. |
| **Allocation concealment** | Describe the method used to conceal the allocation sequence in sufficient detail to determine whether intervention allocations could have been foreseen in advance of, or during, enrollment (e.g. central randomization, sequentially numbered sealed opaque envelopes — vs. an open allocation list, unsealed envelopes). | Selection bias (biased allocation to interventions) due to inadequate concealment of allocations prior to assignment. |
| **Blinding of participants and personnel** | Describe all measures used, if any, to blind study participants and personnel from knowledge of which intervention a participant received, and whether the intended blinding was likely effective. | Performance bias due to knowledge of the allocated interventions by participants and personnel during the study. |
| **Blinding of outcome assessment** | Describe all measures used, if any, to blind study outcome assessors from knowledge of which intervention a participant received. For objective outcomes (e.g. mortality, lab values) blinding matters less than for subjective/patient-reported outcomes (e.g. pain scores, quality of life). | Detection bias due to knowledge of the allocated interventions by outcome assessors. |
| **Incomplete outcome data** | Describe the completeness of outcome data for each main outcome, including attrition and exclusions from the analysis. State whether attrition/exclusions were reported, the numbers in each intervention group, reasons for attrition/exclusions where reported, and any re-inclusions performed by the review authors. Look for imbalanced dropout between arms and dropout related to the outcome itself. | Attrition bias due to the amount, nature, or handling of incomplete outcome data. |
| **Selective reporting** | State how the possibility of selective outcome reporting was examined, and what was found — ideally by comparing the published outcomes against a registered protocol or trial registry entry (e.g. ClinicalTrials.gov). | Reporting bias due to selective outcome reporting. |
| **Other bias** | State any important concerns about bias not addressed in the other domains (e.g. early stopping for benefit, baseline imbalance, a conflict of interest that plausibly shaped the reported result, deviation from a registered protocol, vested-interest funding). If particular questions were prespecified in the review's own protocol, answer each one explicitly here. | Bias due to problems not covered elsewhere in the tool. |

*(Adapted from Higgins JP, Altman DG, Sterne JA, Cochrane Handbook for Systematic Reviews of Interventions, Chapter 8, as tabulated in Ahn E, Kang H. Introduction to systematic review and meta-analysis. Korean J Anesthesiol 2018;71(2):103-112, Table 1.)*

### Judgement categories

- **Low risk of bias** — the domain's description makes it unlikely that bias materially affected the result.
- **High risk of bias** — the domain's description makes it plausible that bias materially affected the result (e.g. no blinding on a patient-reported pain outcome; large, unexplained, imbalanced attrition).
- **Unclear risk of bias** — the study does not report enough detail on this domain to make a low/high judgement either way. This is a valid, common, and honest judgement — never upgrade "unclear" to "low" because a study is otherwise well conducted, and never invent detail the paper doesn't state.

### Overall risk-of-bias judgement per study

RoB1 has no official algorithm for rolling domain-level judgements up into one overall rating (that algorithmic rollup, including a "some concerns" middle tier, is a RoB 2 feature — do not borrow it here). Summarize instead with a plain, conservative rule across the six domains:

- **Low risk of bias** — every domain judged low risk.
- **High risk of bias** — one or more domains judged high risk in a way that plausibly undermines confidence in the result.
- **Unclear risk of bias** — no domain judged high risk, but one or more domains judged unclear.

Different outcomes in the same trial can carry different judgements when blinding matters more for one outcome than another (e.g. blinding of outcome assessment is "low" for a lab value but "high" for a self-reported pain score in the same unblinded-personnel trial) — record the overall judgement per outcome when domain judgements genuinely differ by outcome; otherwise one overall judgement per study is sufficient.

## Part 2 — Newcastle-Ottawa Scale (non-randomized studies)

For cohort, case-control, before-after, and cross-sectional studies — where RoB1's "allocation concealment" and "sequence generation" domains do not apply because there was no randomization — use the **Newcastle-Ottawa Scale** (Ottawa Hospital Research Institute; referenced as the standard alternative for non-randomized studies in the GRADE/RoB1 literature, e.g. Ahn & Kang 2018, kjae-2018-71-2-103, "Quality of evidence" section). NOS awards **stars** (maximum 9) across three categories, using the **cohort-study** version (adapt item wording for case-control per the official OHRI case-control form when a study is case-control rather than cohort):

| Category | Items (1 star each unless noted) | Max stars |
|---|---|---|
| **Selection** | (1) Representativeness of the exposed cohort; (2) Selection of the non-exposed cohort; (3) Ascertainment of exposure; (4) Demonstration that the outcome of interest was not present at the start of the study | 4 |
| **Comparability** | (5) Comparability of cohorts on the basis of the design or analysis controlling for the most important confounder (1 star) and a second important confounder (a further star, 2 max) | 2 |
| **Outcome** | (6) Assessment of outcome; (7) Was follow-up long enough for outcomes to occur; (8) Adequacy of follow-up of cohorts | 3 |

Total NOS score guidance commonly used to bucket study quality (used only as a descriptive summary alongside the itemized stars, never as the sole reported number — always report the itemized breakdown too):

- **Good quality**: 3-4 stars in Selection AND 1-2 stars in Comparability AND 2-3 stars in Outcome.
- **Fair quality**: 2 stars in Selection AND 1-2 stars in Comparability AND 2-3 stars in Outcome.
- **Poor quality**: 0-1 stars in Selection, OR 0 stars in Comparability, OR 0-1 stars in Outcome.

Write the NOS assessment into a study's `risk_of_bias` block with `"tool": "NOS"` and one entry per category carrying `stars_awarded`/`stars_possible` and a `support` string naming the specific item(s) that earned or lost a star — the same evidence-based discipline as RoB1's "support of judgement," not a bare number.

## Rolling up to the outcome level

`/prisma-synthesize` aggregates the per-study overall judgements contributing to one outcome into `synthesis/rob_table.json` (see `SKILL.md`'s schema) and computes `proportion_low_risk` — the fraction of studies judged low risk / good quality. This proportion, together with whether *any* high-risk/poor-quality study drives the pooled result, is the direct input to the risk-of-bias domain of the GRADE rating in `02-grade-certainty.md`: a preponderance of high-risk-of-bias or poor-quality studies contributing to an outcome is grounds to rate down certainty by one or two levels on that domain alone.
