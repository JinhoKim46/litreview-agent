---
name: evidence-mapping
description: "Chart a scoping review's included studies into results/<TOPIC>/charting_table.json: pilot a co-developed form on a handful of records, freeze it (G-Freeze), then chart every remaining study against the frozen form with full provenance. Use whenever a review's resolved method manifest declares capture.mode: \"charting\" (methods/scoping_review.json) -- /litreview-extract's Step 0.5 routes here instead of running extraction for that manifest. Does not cover a systematic review's risk-of-bias-weighted extraction (see litreview-extract.md's own steps for that) or a systematic mapping study's classification-scheme workflow (capture.mode: \"classification\" -- see .claude/skills/study-classification/SKILL.md for that)."
framework_version: 1.2.1
---

# Evidence Mapping (Charting)

A scoping review answers "what has been studied, how, and where" -- not "does it work." Charting records what each included source says about a set of characteristics, without judging risk of bias or pooling anything (`methods/scoping_review.json`'s `synthesis.families_allowed: ["descriptive"]` forbids pooling by design). This skill is the charting-stage counterpart to `litreview-extract.md`'s extraction steps, sharing the same provenance discipline but a different data shape (`schemas/charting_table.schema.json`, not `extraction_table.json`).

## Before you begin

Confirm `tools/method.py --topic <TOPIC> --require-capture-mode charting` exits `0` before starting (the calling command's own Step 0.5 already does this -- this skill assumes it, never re-derives the check itself). If it refuses, this skill does not apply to this review; stop and say so.

## Phase 1: Co-develop the charting form

The form is a list of field names every study will be charted against (e.g. `year`, `venue`, `publication_type`, `population`, `concept`, `context`, `outcomes_reported`) -- PRISMA-ScR item 10's "piloted/calibrated forms." No `packs/*.json` field pack ships yet (`docs/PLAN.md` M3 leaves packs for a later PR), so there is no pack default to start from today -- say so plainly and build the form directly with the reviewer instead of pretending a pack informed it.

1. Ask the reviewer what characteristics they need charted, grouped the way `review-protocol`'s interview does (bibliographic fields first, then PCC-shaped fields: population, concept, context; then outcome/finding fields specific to this review's question).
2. Propose a field list back for confirmation before charting a single record -- never start charting against an unconfirmed guess at the form.

## Phase 2: Pilot (unfrozen)

Chart records against the proposed form, same per-record discipline as `litreview-extract.md`'s Step 4-6 (obtain the source, extract only what it actually states, record `quote`/`page`/provenance, never fabricate a value). Before charting **each** record, run:

```bash
python3 tools/charting_gate.py --topic <TOPIC>
```

(Pre-allowlisted -- `Bash(python3 tools/charting_gate.py:*)`.) While `"frozen": false` and `"must_freeze_now": false`, proceed. The moment `"must_freeze_now": true` (the manifest's `capture.pilot_records` quota is met -- 8 for `scoping_review`), **stop charting further records** and move to Phase 3 -- charting must never silently continue past the pilot without the reviewer agreeing the form is right.

Write each piloted record directly into `results/<TOPIC>/charting_table.json` (`Write` tool, matching `litreview-extract.md`'s own convention of a command writing this file directly rather than through a dedicated append script) with `charting_form_frozen: false` and `fields: []` until Phase 3 freezes it.

## Phase 3: G-Freeze

Review the piloted records with the reviewer: did every field get useful, comparable answers? Does a field need splitting, renaming, or dropping? This is a human gate -- present the pilot data and the proposed final field list, and get an explicit go-ahead before freezing.

Once agreed, write the final field list to a file and freeze:

```bash
python3 tools/charting_gate.py --topic <TOPIC> freeze --fields-json <path-to-a-json-file-holding-the-field-list>
```

This sets `charting_form_frozen: true` and `fields: [...]` in `charting_table.json`. **Never hand-edit these two fields directly** -- `charting_gate.py freeze` is the only path that sets them, so every freeze is auditable the same way. A frozen form cannot be silently changed later (re-freezing with a different field list raises an error); a genuine post-freeze scope change is a documented amendment the reviewer must explicitly request, not yet automated by this skill.

## Phase 4: Chart every remaining record against the frozen form

For each remaining candidate (same candidate-set computation as `litreview-extract.md` Step 2: full-text includes not yet charted), before writing the record's `data`:

```bash
python3 tools/charting_gate.py --topic <TOPIC> --row-data-json <path-to-the-drafted-row's-data-dict>
```

If this refuses (`row_field_mismatch` non-null), the drafted data's keys don't exactly match the frozen `fields[]` -- fix the draft (never silently drop or invent a field to make it match) and check again before writing. Once it passes, append the row to `charting_table.json`'s `studies[]` (`Write` tool), with:

- `data`: one value per frozen field.
- `source`: `{quote, page, hash}` -- the exact text the value came from, mirroring `litreview-extract.md` Step 6's "refuse to write a value whose quote does not actually appear in the retrieved text" rule. `hash` may be `null` if not computed.
- `suggested_by`: `"connector"` only for a field filled straight from `records.jsonl` (year, venue, publication type) needing no reviewer confirmation; `"llm"` for everything charted from the source text, which does need confirmation (PRISMA-ScR item 10 / §3.1 S5's G-Values gate).
- `by`: who charted this record (`"claude (single coder pass)"` unless the reviewer charted it directly).
- `verified_by`: `null` unless a second person has independently checked this specific record's charted data.

Confirm every `suggested_by: "llm"` value with the reviewer before persisting, same discipline as extraction's G-Values gate -- connector-sourced fields need no confirmation.

## What this skill does not do

- **Appraisal**: optional for a scoping review (`appraisal.requirement: "optional_with_justification"`). If the reviewer wants it, that's `quality-appraisal`'s job, with a recorded justification for why (§3.3) -- not this skill's.
- **Synthesis**: descriptive tabulation/charting summary only, never pooling (`synthesis.families_allowed: ["descriptive"]`). `/litreview-synthesize` runs `tools/chart_summary.py` for this, producing `synthesis/descriptive_summary.json` (category frequencies per charted field) -- this skill never computes or writes that itself.
- **Classification** (systematic mapping study's `capture.mode: "classification"` -- scheme freeze, keywording, calibration re-code) is a distinct workflow this skill does not cover.
