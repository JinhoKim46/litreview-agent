# /prisma-synthesize - Pool, Assess Heterogeneity, and Grade the Included Studies

Implements architecture plan §6 (the NEW statistical-synthesis stage). Reads `results/<TOPIC>/extraction_table.json` (built by `/prisma-extract`), groups included studies by outcome, pools every outcome group that clears the poolability gate, falls back to narrative synthesis for every group that doesn't — **recording why, never silently** — and writes the four `synthesis/*.json` files plus forest/funnel SVGs that `/prisma-report` reads verbatim.

The statistics themselves are never hand-rolled here: `synthesis/pooling.py` wraps `statsmodels.stats.meta_analysis.combine_effects`, `synthesis/heterogeneity.py` computes Cochrane's Q / Higgins I², and `synthesis/plots.py` renders SVGs via matplotlib. This command's own `synthesis/run_synthesis.py` helper script does only the plumbing between them: flattening `extraction_table.json`, converting each study's raw arm data into an effect+variance pair, applying the poolability gate, and writing the output files. Risk-of-bias and GRADE judgement calls that require reading study text (not just arithmetic) are made by Claude, per `.claude/skills/quality-appraisal/`, in Steps 5-6 below — never by the script.

`$ARGUMENTS` may contain `<TOPIC>` (the `results/<TOPIC>/` slug). If absent, infer it from conversation context or ask.

Follow these steps **in order**. Do not skip any step, and do not present a result to the reviewer until Step 8.

---

## Step 1: Resolve `<TOPIC>` and Check Preconditions

1. Determine `<TOPIC>` from `$ARGUMENTS` or context. If genuinely ambiguous (more than one `results/*/` directory and none named in conversation), ask which review this is for before touching any file.
2. Confirm `results/<TOPIC>/extraction_table.json` exists and is non-empty. If it's missing: stop and tell the reviewer to run `/prisma-extract` first — this command never invents study data.
3. Confirm `results/<TOPIC>/synthesis/` exists (`mkdir -p` it if not — it's gitignored per plan §10, so it's fine for it not to exist yet on a fresh checkout).
4. Read `results/<TOPIC>/extraction_table.json` with the `Read` tool (this file is per-study structured data, not a 5,000-record ledger like `records.jsonl` — reading it directly is fine and necessary to sanity- check its shape before Step 3 shells out to it).

**Expected shape** — the exact file `/prisma-extract.md` Step 8 writes, and what `synthesis/run_synthesis.py` expects. If the file you read doesn't match this, stop and fix `extraction_table.json` (or `/prisma-extract` itself) before proceeding — never adapt this command's script to silently tolerate a different shape:

```json
{
  "framework_version": "1.0.0",
  "topic": "<TOPIC>",
  "studies": [
    {
      "record_id": "openalex:W123456789",
      "author_year": "Kim et al. (2022)",
      "study_design": "RCT",
      "outcomes_measured": ["PONV", "patient satisfaction"],
      "risk_of_bias": {"tool": "RoB2", "overall_judgement": "some concerns", "...": "per quality-appraisal/01-risk-of-bias.md"},
      "effect_data": [
        {"outcome": "PONV", "measure_type": "RR", "timepoint": "24h postoperative",
         "intervention_arm": {"label": "dexamethasone", "events": 12, "total": 60},
         "comparator_arm": {"label": "placebo", "events": 28, "total": 60}}
      ]
    }
  ]
}
```

`effect_data[].measure_type` is one of `OR`, `RR`, `RD` (dichotomous — the arm objects carry `events`/`total`) or `MD`, `SMD` (continuous — the arm objects carry `mean`/`sd`/`n`). A study can (and usually does) contribute zero, one, or several `effect_data` entries — `effect_data` is a flat list for exactly that reason, not nested per outcome. `outcomes_measured` lists **every** outcome the study reports, including ones with no extractable numbers; an outcome name present in `outcomes_measured` but absent from every `effect_data[].outcome` for that study is narrative-only **for that study** — `synthesis/run_synthesis.py`'s `flatten_rows` derives this automatically, never by a separate flag. `risk_of_bias` is per study (written once during `/prisma-extract`, never re-derived here) — if it's missing for a study that's about to contribute to a pooled outcome, note it now; Step 5 will need it.

---

## Step 2: Group by Outcome (mechanical preview, not the final grouping)

Before running the script, skim `extraction_table.json` yourself and note, per outcome name:

- How many studies report it **quantitatively** (i.e. it appears in that study's `effect_data[].outcome`), and with which `measure_type`(s). An outcome with studies split across two different measures (e.g. 2 studies report `OR`, 1 reports `RR` for "PONV") does **not** pool as one group of 3 — `measure_type` is part of the grouping key, so that outcome yields two groups, one of which may fail the poolability gate on its own even though the outcome "has 3 studies."
- Which outcome names never appear in *any* study's `effect_data` at all (only ever in `outcomes_measured`) — these are qualitative-only across the whole review and can never pool; they go straight to narrative synthesis.
- **Naming consistency**: confirm every study using the same outcome uses the exact same string in `outcomes_measured`/`effect_data[].outcome` (per `/prisma-extract.md` Step 6's own warning: "PONV" vs. "postoperative nausea and vomiting" silently split into two one-study groups). If you spot a naming mismatch, fix it in `extraction_table.json` now, before running the script — the script groups on the literal string, it cannot detect a human synonym.

This preview is so you can sanity-check the script's output in Step 4 against what you'd expect by eye — not a substitute for the script actually doing the grouping.

---

## Step 3: Run the Synthesis Script

Run:

```bash
python3 -m synthesis.run_synthesis --topic <TOPIC>
```

(This exact invocation is pre-allowlisted in `.claude/settings.json` — `Bash(python3 -m synthesis.run_synthesis:*)`. Per PRODUCT_READINESS_AUDIT.md P0-1, the script derives `results/<TOPIC>/extraction_table.json` and `results/<TOPIC>/synthesis/` itself from the validated `<TOPIC>` slug — it no longer accepts free-form `--extraction-table`/`--out-dir` paths, so this pre-approved permission can never be used to write outside a review's own directory.)

This single call does all of the following (see `synthesis/run_synthesis.py`'s module docstring for the full algorithm; do not reimplement any of it inline):

1. Flattens every study's `effect_data` list (quantitative rows) plus every `outcomes_measured` name with no matching `effect_data` entry (narrative rows) into one row per `(study, outcome)`.
2. Groups quantitative rows by `(outcome, measure_type)`.
3. For each group, converts every study's raw `intervention_arm`/ `comparator_arm` data (`a`/`n1` = intervention `events`/`total`, `c`/`n2` = comparator `events`/`total`; or `mean`/`sd`/`n` per arm for continuous measures) into an effect + variance on the scale `synthesis/heterogeneity.py` and `synthesis/pooling.py` expect:
   - `OR`: log odds ratio, `Var(logOR) = 1/a + 1/b + 1/c + 1/d`.
   - `RR`: log risk ratio, `Var(logRR) = 1/a - 1/n1 + 1/c - 1/n2`.
   - `RD`: raw risk difference, `Var(RD) = p1(1-p1)/n1 + p2(1-p2)/n2`.
   - `MD`: raw mean difference, `Var(MD) = sd1²/n1 + sd2²/n2`.
   - `SMD`: Hedges' g (small-sample-corrected standardized mean difference) with its Cochrane-Handbook variance approximation. Any study with a zero cell in a dichotomous 2×2 table gets the standard 0.5-continuity correction applied to all four cells automatically (Cochrane Handbook 10.4.4.1) — this is recorded per study as `continuity_correction_applied: true` in `effect_sizes.json`, never applied silently. Any study whose data is unusable after conversion (non-positive variance, missing fields, implausible counts) is **excluded from that group with a recorded reason** in `effect_sizes.json`'s `excluded` list — it does not silently vanish and it does not crash the group's processing.
4. **Poolability gate**, applied per `(outcome, measure_type)` group: fewer than 2 studies with usable converted effect data (whether because the group started small or because conversion excluded studies down to fewer than 2) → **narrative fallback** for that group, recorded in `heterogeneity.json` as `{"pooled": false, "reason": "..."}`. Every outcome that is qualitative-only across all studies (no `effect_data` anywhere) also gets a `heterogeneity.json` entry with `"reason": "qualitative/narrative-only outcome..."` — it is listed explicitly, never simply absent from the file.
5. For every group that clears the gate: calls `heterogeneity.compute_heterogeneity` (Q, df, p-value, I²), then `heterogeneity.choose_model` (the standard rule: I² > 50% or Q-test p < 0.10 → random-effects is the primary reported model, else fixed-effect), then `pooling.pool_effects` with that model.
6. Renders a forest plot (`plots.forest_plot`, one row per study plus the pooled diamond) for every pooled group, written to `results/<TOPIC>/synthesis/forest_<outcome-slug>.svg`. **Note the deliberate generalization from plan §6's illustrative single `forest_plot.svg`**: a review with multiple pooled outcomes needs one forest plot per outcome, so the actual filenames are per-outcome-slug and their paths are recorded in `effect_sizes.json`'s `forest_plot_svg`/`funnel_plot_svg` fields — this is what to cite when drafting Results/Figures in `/prisma-report`, not a hardcoded filename. Forest plots are drawn on the **pooling scale** (log scale for OR/RR, natural scale for RD/MD/SMD) with the null line at 0 — the human-readable exponentiated numbers (for OR/RR) live alongside in each entry's `display_estimate`/`display_ci_low`/`display_ci_high` fields for prose and tables, not on the plot axis itself.
7. Renders a funnel plot (`plots.funnel_plot`) for every pooled group with **k ≥ 10 studies contributing to that specific outcome** — not 10 studies in the review overall. Groups below that count get no funnel plot and this feeds directly into Step 6's GRADE publication-bias domain.
8. Aggregates each contributing study's existing `risk_of_bias` block (from `extraction_table.json` — never recomputed) into `results/<TOPIC>/synthesis/rob_table.json`, one entry per outcome (pooled and narrative-fallback outcomes alike), computing `proportion_low_risk` across **both** RoB2 ("low risk") and NOS ("good quality") studies counted the same way for that fraction, while keeping each study's `tool` field so the manuscript can still report the RCT/ non-randomized split separately. It also renders one traffic-light plot, `results/<TOPIC>/synthesis/rob_traffic_light.svg` (`plots.rob_traffic_light_plot`), covering every RoB2-assessed study that has a full seven-domain breakdown in `extraction_table.json` (NOS-assessed studies, and any RoB2 study recorded with only an `overall_judgement` and no `domains`, are excluded from this specific plot — not from `rob_table.json`, which still covers them). This is `null`/not written when no study qualifies; that is expected for an all-NOS review, not an error.
9. Writes a **draft** `results/<TOPIC>/synthesis/grade_table.json`, one entry per outcome (pooled and narrative alike): `starting_certainty` is derived from the contributing studies' `study_design` (all RCT → High; all observational, mixed, or unrecorded → Low, per GRADE's design baseline — never High from a body with no recorded design, and the `starting_certainty_note` field says which case applied); the `risk_of_bias`, `inconsistency`, and `publication_bias` domains are filled in mechanically from the numbers above; `indirectness` and `imprecision` are left as `"rating": "needs_review"` placeholders, and `final_certainty` is left as `"needs_review"` — these require reading the actual study text against the review's PICO and are Claude's job in Step 6, not the script's. **Note on `n_studies`:** it counts every row contributing to this outcome's body of evidence (every `effect_data` entry plus every narrative row in the group) — for a pooled outcome this can exceed the actual pooled `k` in `heterogeneity.json`/ `effect_sizes.json` when conversion excluded some studies. Read `k` for "how many were pooled" and `n_studies` for "how many studies discuss this outcome at all" — they answer different questions, and Step 4 already has you reconciling the two against `excluded`.

Read the script's stdout: it prints how many outcome groups were pooled vs. narrative, and flags every outcome still needing GRADE review. If the script errors (e.g. malformed JSON, an unsupported `measure_type`), fix `extraction_table.json` and re-run — do not patch around a script error by editing `run_synthesis.py` for a one-off review's malformed data.

---

## Step 4: Verify the Mechanical Output Against Step 2's Preview

1. Open `results/<TOPIC>/synthesis/heterogeneity.json`. Confirm every outcome you noted in Step 2 appears exactly once per `(outcome, measure_type)` group, with `pooled: true` (carrying `Q`, `df`, `p_value`, `I2`, `model`) or `pooled: false` (carrying a specific `reason` — never a generic one-liner that doesn't name the actual count/mismatch/exclusion).
2. Open `results/<TOPIC>/synthesis/effect_sizes.json`. For each pooled group, confirm `k` matches the number of studies you expected minus any `excluded` entries, and that every `excluded` entry has a real reason. If a study you expected to contribute is missing without an `excluded` entry explaining why, something is wrong upstream in `extraction_table.json` — fix the data, don't silently accept the gap.
3. Spot-check one pooled group's `display_estimate`/`display_ci_low`/ `display_ci_high` against the study-level numbers in `extraction_table.json` by eye (e.g. a pooled RR should land somewhere inside the spread of the individual studies' `events/total` ratios, not wildly outside it) — this is a sanity check for a data-entry error in `extraction_table.json`, not a re-derivation of the pooling math.

---

## Step 5: Roll Up Risk of Bias

Load `.claude/skills/quality-appraisal/01-risk-of-bias.md`'s "Rolling up to the outcome level" section and `results/<TOPIC>/synthesis/rob_table.json`.

1. For every outcome where `missing_assessment` is non-empty (a contributing study has no `risk_of_bias` block in `extraction_table.json`), flag it to the reviewer now — this is a gap in `/prisma-extract`'s output, not something to guess at here. Do not proceed to write a final GRADE `risk_of_bias` domain rating for that outcome until it's resolved or the reviewer explicitly accepts the gap.
2. For every other outcome, confirm `proportion_low_risk` is consistent with the individual studies' judgements you can see in `extraction_table.json` — this is the number Step 6's GRADE risk-of-bias domain reads directly; it is already computed correctly by the script, this step is a check, not a recomputation.

---

## Step 6: Complete the GRADE Table (Claude's judgement calls)

Load `.claude/skills/quality-appraisal/02-grade-certainty.md` in full before this step. For **every** entry in `results/<TOPIC>/synthesis/grade_table.json` (pooled and narrative outcomes alike — a narrative outcome still gets a full GRADE rating per that file's own guidance, with `model_used: "narrative"` and `effect: null`):

1. **Indirectness.** Compare the outcome's contributing studies against `results/<TOPIC>/protocol.json`'s PICO/PICo/SPIDER record: same population, intervention/exposure, comparator, and outcome definition as the review question actually asks? Rate `not_serious`, `serious`, or `very_serious`, with a note citing the specific mismatch if any (e.g. "2 of 3 studies used a surrogate outcome, not the patient-important one specified in protocol.json").
2. **Imprecision.** For a pooled outcome: does the 95% CI (`display_ci_low`/`display_ci_high` in `effect_sizes.json`) cross the line of no effect in a way that would change the clinical conclusion, or is the total event count/sample size small relative to what's needed for a stable estimate? For a narrative outcome: is the total sample size across contributing studies too small to draw a confident conclusion either way? Rate and cite the specific CI or sample-size number.
3. **Rate up (observational evidence only — skip entirely for RCT-only bodies of evidence, which already start at High and are never rated up).** Check the three rate-up criteria in `02-grade-certainty.md` (large effect, dose-response gradient, confounding that would bias toward the null) against the actual study data. Add any that apply to the `rate_up` list with a citation; leave it `[]` if none apply — do not rate up without a specific, cited justification.
4. **Compute `final_certainty`** with the documented arithmetic (never eyeballed): start at the level implied by `starting_certainty` (High = 3, Moderate = 2, Low = 1, Very low = 0), subtract 1 for every domain rated `serious`, subtract 2 for every domain rated `very_serious`, add back 1 per `rate_up` entry, floor at 0 (Very low), then map the resulting index back to its name. Show this arithmetic in the outcome's own `final_certainty` derivation so it's auditable later, not just the final word.
5. Write the completed `grade_table.json` back with `Edit` (every domain rated, every `needs_review` replaced, `final_certainty` computed as above). Never leave `"needs_review"` in the file you consider done — if a domain genuinely cannot be assessed from what was extracted, the correct value is a real GRADE rating with a note saying so (e.g. imprecision `serious` with note "wide CI reflects only 44 total events"), not an unresolved placeholder.

---

## Step 7: Confirm Nothing Was Dropped Silently

Cross-check, as a final gate before presenting results:

1. Every outcome name that appears anywhere in `extraction_table.json` (in any study's `outcomes_measured` or `effect_data[].outcome`) appears at least once in `heterogeneity.json`, `rob_table.json`, and `grade_table.json`. If any outcome is missing from one of the three, that is a bug in this run — find where it was dropped and fix it before proceeding, rather than presenting incomplete synthesis output.
2. Every `pooled: false` entry in `heterogeneity.json` has a non-empty, specific `reason` (never `"not poolable"` alone, never blank).
3. Every study listed in an `excluded` block in `effect_sizes.json` has a non-empty, specific `reason`.

---

## Step 8: Present the Summary

Reply to the reviewer with:

- Total outcome groups processed: how many pooled (with model — fixed or random — and k), how many fell back to narrative synthesis (with the one-line reason each).
- For each pooled outcome: the pooled effect on its natural display scale (e.g. "RR 0.92, 95% CI 0.54–1.58"), I², and the resulting GRADE certainty level.
- For each narrative outcome: its GRADE certainty level (narrative outcomes are graded too — don't imply they were skipped).
- File paths: `results/<TOPIC>/synthesis/{effect_sizes,heterogeneity, rob_table,grade_table}.json`, the per-outcome `forest_<slug>.svg`/`funnel_<slug>.svg` files actually written, and `rob_traffic_light.svg` if it was written (say plainly if it wasn't, and why — e.g. "not written: every included study was NOS-assessed").
- One line noting that `/prisma-report` will read these files verbatim for Methods §2.9/2.12, Results §3.3-3.7, and the Discussion's certainty framing — no re-elicitation needed.

Do not paste plot SVG contents into the reply — reference the file paths, the same discipline `/prisma-screen` uses for screening sheets.

---

## Design Notes

- The poolability gate exists because pooling heterogeneous or incompatible data produces a misleading single number (CASP's own guidance, echoed in plan §6) — the gate is not a formality, and a group that fails it must never be forced into `pool_effects` anyway "since we have the numbers."
- `synthesis/run_synthesis.py` is the one place the effect-size conversion formulas live; it is covered by its own `__main__` self-check (`python3 synthesis/run_synthesis.py` with no args) exercising a pooled group, a continuity-corrected zero-cell study, a single-study narrative fallback, and a qualitative-only narrative fallback — re-run that self-check after ever editing the script, before trusting it against a real review's data.
- Steps 5-6 are deliberately not automated further: GRADE's indirectness and imprecision domains require reading what a study actually measured against the review's own PICO, which is exactly the kind of judgement call `.claude/skills/quality-appraisal/SKILL.md` says Claude performs as a single first-pass rater — and says so explicitly, never claiming dual-reviewer independence it doesn't have.
