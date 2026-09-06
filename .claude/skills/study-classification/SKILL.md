---
name: study-classification
description: "Classify a systematic mapping study's included studies into results/<TOPIC>/classification_table.json: keyword a sample to build the classification scheme, freeze it (G-Freeze), code every remaining study against the frozen facets, then run and disclose a calibration re-code. Use whenever a review's resolved method manifest declares capture.mode: \"classification\" (methods/systematic_mapping_study.json) -- /prisma-extract's Step 0.5 routes here instead of running extraction for that manifest. Does not cover a systematic review's risk-of-bias-weighted extraction or a scoping review's charting workflow (capture.mode: \"charting\" -- see .claude/skills/evidence-mapping/SKILL.md for that)."
framework_version: 1.1.0
---

# Study Classification (Keywording)

A systematic mapping study answers "how is this field structured, and where is the evidence dense or thin" -- not "does it work" (extraction/appraisal) and not "what has been studied, in what depth" (a scoping review's charting). It classifies every included study against a small set of facets (e.g. research type, contribution type, application domain) built *from the candidate set itself*, per Petersen et al. 2015's keywording method (`.claude/skills/prisma-manuscript/references/petersen-2015-mapping-guidelines.md`, step 4). `methods/systematic_mapping_study.json`'s `synthesis.families_allowed: ["descriptive"]` forbids pooling by design, same as a scoping review.

## Before you begin

Confirm `tools/method.py --topic <TOPIC> --require-capture-mode classification` exits `0` before starting (the calling command's own Step 0.5 already does this -- this skill assumes it, never re-derives the check itself). If it refuses, this skill does not apply to this review; stop and say so.

## Phase 1: Build the classification scheme by keywording

Unlike a scoping review's charting pilot, there is no numeric quota here (`capture.pilot_records` is `0` for this method) -- the sample size for keywording is a judgment call made with the reviewer, not a fixed count.

1. Read a sample of included studies' abstracts (title/introduction/methodology/conclusion too, when the abstract alone isn't informative enough) and identify keywords/concepts describing the problem investigated and each paper's contribution.
2. Cluster those keywords into a small set of categories per facet (e.g. "research type" using Wieringa's six-way taxonomy -- validation, evaluation, solution proposal, philosophical, opinion, experience -- plus whatever domain-specific facets this review's question calls for, such as "dataset" or "metric").
3. Propose the facets and their categories back to the reviewer for confirmation before coding a single study against them -- never start bulk coding against an unconfirmed guess at the scheme.

Nothing is written to `classification_table.json` during this phase -- keywording works from the candidate set directly, not through the gate script (`capture.pilot_records: 0` means there is no unfrozen pilot state to track in the table).

## Phase 2: G-Freeze

Review the proposed scheme with the reviewer: does every facet have mutually exclusive (or explicitly multi-valued), exhaustive-enough categories? This is a human gate -- present the candidate facets and get an explicit go-ahead before freezing.

Once agreed, write the final facets list to a file and freeze:

```bash
python3 tools/classification_gate.py --topic <TOPIC> freeze --facets-json <path-to-a-json-file-holding-the-facets-list>
```

(Pre-allowlisted -- `Bash(python3 tools/classification_gate.py:*)`.) The facets file is a JSON array of `{"name": ..., "categories": [...]}` objects. This sets `scheme_frozen: true` and `facets: [...]` in `classification_table.json`. **Never hand-edit these two fields directly** -- `classification_gate.py freeze` is the only path that sets them. A frozen scheme cannot be silently changed later (re-freezing with a different facets list raises an error); a genuine post-freeze scope change is a documented amendment the reviewer must explicitly request, not yet automated by this skill.

Before this point, attempting to code any study is refused:

```bash
python3 tools/classification_gate.py --topic <TOPIC>
```

While `"scheme_frozen": false`, this only reports state -- do not attempt to write a coded row yet. **Bulk coding is blocked until the scheme is frozen** (docs/PLAN.md M3's exit criterion for this method); never work around this by drafting rows in the table with placeholder codes to "get ahead."

## Phase 3: Code every included study against the frozen scheme

For each candidate (full-text includes not yet classified), before writing the record's `codes`:

```bash
python3 tools/classification_gate.py --topic <TOPIC> --row-codes-json <path-to-the-drafted-row's-codes-dict>
```

If this refuses (`row_facet_mismatch` non-null), the drafted codes' keys don't exactly match the frozen `facets[]` names -- fix the draft (never silently drop or invent a facet to make it match) and check again before writing. Once it passes, append the row to `classification_table.json`'s `studies[]` (`Write` tool, matching `prisma-extract.md`'s own convention of a command writing this file directly), with:

- `codes`: one category (or array of categories, for a multi-valued facet) per frozen facet.
- `source`: `{quote, page, hash}` -- the exact text a code came from, mirroring `prisma-extract.md` Step 6's "refuse to write a value whose quote does not actually appear in the retrieved text" rule. `hash` may be `null` if not computed.
- `suggested_by`: `"connector"` only for a code filled straight from `records.jsonl` needing no reviewer confirmation (rare -- most facets require reading the study itself); `"llm"` for everything coded from the source text, which does need confirmation (mirroring extraction's G-Values gate).
- `by`: who coded this record (`"claude (single coder pass)"` unless the reviewer coded it directly).
- `verified_by`: `null` unless a second person has independently checked this specific record's codes.

Confirm every `suggested_by: "llm"` code with the reviewer before persisting.

## Phase 4: Calibration re-code (disclosed, never gated)

Petersen et al.'s rigor guidance (step 5): disclose a calibration check rather than silently presenting the classification as unambiguous. The manifest's own microcopy: "single-coder classification is acceptable when a delayed intra-rater re-code of at least 10 records is disclosed." This never blocks or gates coding either direction -- `schemas/classification_table.schema.json` states it plainly: "disclosed, not gated."

Once bulk coding is far enough along (or complete) that a re-code sample makes sense:

- **Two coders involved**: compute inter-rater agreement on the overlapping sample.
- **Single coder**: after a delay (so the original codes aren't simply remembered), independently re-code a sample of at least 10 already-coded records without looking at the original codes, then compare.

Either way, compute a simple agreement rate or a chance-corrected statistic (e.g. Cohen's kappa or PABAK, matching this repo's existing `label_gate.py`/ledger disclosure conventions), then record it -- disclosed even if agreement is poor, never hidden or silently improved by re-coding disagreements away:

```bash
python3 tools/classification_gate.py --topic <TOPIC> record-calibration --calibration-json <path-to-a-json-file>
```

The calibration file is `{"mode": "inter_rater"|"intra_rater_delayed", "sample_size": <int>, "agreement": <number or null>, "disagreements": [<record_id>, ...]}`. `disagreements` lists the specific records where the two codings differed -- never omitted to make the disclosure look cleaner than it was.

## What this skill does not do

- **Appraisal**: optional for a mapping study (`appraisal.requirement: "optional_with_justification"`), no default instrument -- `quality-appraisal`'s job if the reviewer wants it, not this skill's.
- **Synthesis**: descriptive facet-count tables and cross-tabulations only, never pooling (`synthesis.families_allowed: ["descriptive"]`). `/prisma-synthesize` runs `tools/chart_summary.py` for this (shared with scoping reviews), producing `synthesis/descriptive_summary.json` (facet-count tables plus the pairwise cross-tabs a bubble plot renders) -- this skill never computes or writes that itself. Rendering the actual bubble-plot SVG from those cross-tabs is not yet implemented; the underlying count data already is.
- **Charting** (a scoping review's `capture.mode: "charting"` -- pilot/freeze of a per-study data-extraction form) is a distinct workflow covered by `.claude/skills/evidence-mapping/SKILL.md`, not this one.
