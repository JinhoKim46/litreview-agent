---
name: reconnaissance-brief
description: "Tag a reconnaissance topic's records for relevance into results/<TOPIC>/relevance_tags_table.json, then draft a landscape brief (and, optionally, a related-work section and a supplementary search log). Use whenever a review's resolved method manifest declares capture.mode: \"relevance_tags\" (methods/reconnaissance.json) -- /prisma-extract's Step 0.5 routes here instead of running extraction for that manifest. Has no freeze gate at all, unlike its two siblings: does not cover a scoping review's charting pilot/freeze workflow (capture.mode: \"charting\" -- see .claude/skills/evidence-mapping/SKILL.md) or a systematic mapping study's keywording/freeze/calibration workflow (capture.mode: \"classification\" -- see .claude/skills/study-classification/SKILL.md)."
framework_version: 1.0.1
---

# Reconnaissance Brief (Relevance Tagging)

A reconnaissance is for a reviewer who is not running a formal evidence-synthesis review at all -- just a bounded, orienting look at what's already out there before writing a protocol, or a related-work section for something else entirely. It never screens records for eligibility (`methods/reconnaissance.json`'s `forbidden_forms` include `screening_vocabulary` and `eligibility_vocabulary` -- the label is unconditional and this method makes no eligibility decision, so nothing here should ever read as if it did) and never pools or tabulates anything formally (`synthesis.families_allowed: []`). What it does instead is tag each candidate record with the relevance facets it's closest on, capture at most one quoted, provenance-backed claim per candidate worth citing, and draft a brief from that -- `schemas/relevance_tags_table.schema.json`, not `charting_table.json`/`classification_table.json`.

## Before you begin

Confirm `tools/method.py --topic <TOPIC> --require-capture-mode relevance_tags` exits `0` before starting (the calling command's own Step 0.5 already does this -- this skill assumes it, never re-derives the check itself). If it refuses, this skill does not apply to this review; stop and say so.

## Phase 1: Tag each candidate for relevance

Records come from the same `/prisma-search` + dedup pipeline every method shares (`records.jsonl`) -- reconnaissance's `search.mode: "orienting"` and `known_item_recall: "advisory"` mean this search is intentionally bounded and lighter-weight than a protocol-driven one, not a different pipeline. There is no separate include/exclude screening pass here: every record worth a look gets tagged, not sorted into included/excluded.

For each candidate:

1. Read enough of the record (title/abstract, and the source itself when a quoted claim is warranted) to name the relevance facets it's closest on -- e.g. `population`, `method`, `context`, `outcome` -- the same "closest on: [facet]" tags a prior-work-check output prints. These are free-text tags proposed per record, not a co-developed, frozen form (unlike charting/classification's own Phase 1) -- there is nothing to pilot or freeze here.
2. Before writing, check the record isn't already tagged:

```bash
python3 tools/relevance_tags_gate.py --topic <TOPIC> --check-record-id <record_id>
```

(Pre-allowlisted -- `Bash(python3 tools/relevance_tags_gate.py:*)`.) Exit `1` means this record already has a row -- do not write a second one.

3. Write the row directly into `results/<TOPIC>/relevance_tags_table.json`'s `studies[]` (`Write` tool, matching the other capture-mode skills' convention of a command writing this file directly), with:

- `facet_tags`: the relevance facets from step 1.
- `claim`: `{quote, page, hash}` for at most one claim worth citing from this record, or `null` if none -- never fabricate a quote; if nothing in the source actually supports a claim worth citing, `null` is the honest answer. `hash` may be `null` if not computed.
- `by`: who tagged this record (`"claude (single pass)"` unless the reviewer tagged it directly).

Confirm every drafted `claim` with the reviewer before persisting it, same non-fabrication discipline as extraction's G-Values gate: a quote must actually appear in the retrieved text.

## Phase 2: Corpus description

Once tagging is far enough along (or complete), compute the corpus-description table -- facet-tag frequency counts across every tagged record:

```bash
python3 tools/relevance_tags_gate.py --topic <TOPIC>
```

This prints `{"n_tagged": ..., "corpus_description": {facet_tag: count, ...}}`, computed deterministically from `relevance_tags_table.json` -- never hand-tallied while drafting, so the numbers in the brief always match the table they came from.

## Phase 3: Draft the outputs

With tagging and the corpus-description table done, draft:

- **`landscape_brief.md`** -- the primary output: a banner stating plainly this is a non-systematic exploratory brief, "prior work identified so far" (the tagged candidates grouped by facet, each with its quoted claim where one exists), "what this did not search" (the coverage gaps this bounded, orienting search left, same `packs/*.json`-driven mechanism `/prisma-init` already wires into `protocol.json.scope.coverage_gaps` for other methods), and any candidate gaps stated as templated questions -- never as claims of "no prior work" or that the search reached "saturation" (both hard-fail `label_gate.py`'s forbidden-form lint for this method; the base `no_prior_work`/`novelty` patterns already catch these, on top of the two recon-specific `screening_vocabulary`/`eligibility_vocabulary` patterns). Every templated sentence in this brief needs the reviewer's explicit approval before it's final -- the same per-sentence G-Claims discipline `prisma-manuscript` already uses for a systematic-review report, applied here to a much shorter document.
- **`related_work_draft.md`** (optional, only if the reviewer wants prose for a paper's own related-work section rather than a standalone brief): prose citing "the search log in Supplementary S1" rather than re-deriving the search description inline.
- **`supplementary_search_log.md`** (optional, alongside `related_work_draft.md`): the replayable record of what was actually searched -- same spirit as `search_plan.json`'s audit trail for a full review, in prose form.

Every reference the brief cites still needs independent verification before the brief is presented as final (CLAUDE.md's Verification Checklist; `references_verified` is this manifest's one `report_blockers` entry) -- a reconnaissance brief being lightweight does not exempt it from that.

## What this skill does not do

- **Formal eligibility screening**: this method has none -- `/prisma-screen`'s ledger-based include/exclude workflow is for methods with `capture.mode` in `{extraction, charting, classification}`, never this one.
- **Appraisal**: `appraisal.requirement: "none"` -- there is no quality-appraisal step for a reconnaissance topic at all, not even an optional one.
- **Synthesis / pooling**: `synthesis.families_allowed: []` -- nothing is ever pooled or descriptively synthesized here; the corpus-description table in Phase 2 is a simple tally, not a synthesis-family output, and `/prisma-synthesize` does not apply to this method.
- **Promotion to a full review** (same-topic hand-off via `handoff/`, the non-independent gold-set disclosure once a scoping/systematic review starts from this topic) is a distinct mechanism this skill never runs itself -- `python3 tools/promote_reconnaissance.py --topic <TOPIC> --new-method-id <id> --reason "<text>"` archives this topic's recon-stage artifacts to `recon/`, writes `handoff/`, and folds any recoverable gold-set candidate into `protocol.json.known_items[]` with `provenance: "recon-db"`.
- **Charting** (`capture.mode: "charting"`) and **classification** (`capture.mode: "classification"`) are distinct workflows covered by `.claude/skills/evidence-mapping/SKILL.md` and `.claude/skills/study-classification/SKILL.md`, not this one.
