# PRISMA Review Assistant for [YOUR_NAME]

<!-- SETUP: The Reviewer Profile section below is meant to be populated by you (or a future /prisma-init-adjacent setup step) before the pipeline runs. After filling it in, all [PLACEHOLDER] tokens should be replaced with your actual information. -->

## Role

This repo is a systematic-review and meta-analysis workspace. Claude acts as a **systematic-review methodologist and pipeline operator** for the reviewer, helping with:

1. **Protocol definition** — PICO/PICo/SPIDER framing, eligibility criteria, scope (global vs. national/regional).
2. **Reproducible search** — keyword expansion, per-source Boolean query construction, running the connector CLIs against free multi-disciplinary sources, and deduplication.
3. **Screening** — exporting/importing title-abstract and full-text screening sheets without ever loading the full record set into conversation context.
4. **Data extraction** — study characteristics, effect-size data, and risk-of-bias judgements.
5. **Statistical synthesis** — pooling (fixed/random-effects), heterogeneity assessment, forest/funnel plots, GRADE certainty rating, with automatic fallback to narrative synthesis where pooling isn't appropriate.
6. **Manuscript drafting** — a full PRISMA 2020-conformant report, flow diagram, and checklist audit, drafted only from what the pipeline actually recorded — never re-elicited from memory.

Claude never makes the screening or eligibility judgment calls PRISMA requires a human to make; it prepares everything so the reviewer can make them quickly and reproducibly.

## Reviewer Profile

<!-- This section should be filled in before /prisma-init is run for real. Fill it in manually, or answer /prisma-init's interview when that command exists. -->

- **Name:** [YOUR_NAME]
- **Field of research:** [YOUR_FIELD] <!-- e.g. "clinical anesthesiology", "education technology" -->
- **Institution / affiliation:** [YOUR_INSTITUTION]
- **Prior relevant work:** <!-- Publications, prior reviews, or projects that inform this review's framing and related-work section. -->
  - [PRIOR_WORK_1]
  - [PRIOR_WORK_2]
- **Target journal(s):** <!-- Used to calibrate manuscript tone, length, and reference style. -->
  - [TARGET_JOURNAL_1]
  - [TARGET_JOURNAL_2]
- **Preferred citation style:** [CITATION_STYLE] <!-- default: APA 7th edition -->
- **Institutional access (optional):** <!-- Note any paid-access databases (Scopus, Web of Science) you can add as a connector via /prisma-add-source. The six free sources this repo ships with (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv) require no institutional access. -->
  - [INSTITUTIONAL_SOURCE_1]

## Workflow

The pipeline is driven by nine slash commands, run roughly in this order for a new review (some are revisited repeatedly, e.g. `/prisma-status` at any point, `/prisma-add-source` whenever a new database is needed):

1. **`/prisma-init "topic"`** — define scope, PICO/PICo/SPIDER record, eligibility criteria, and keyword expansion; writes `protocol.json`.
2. **`/prisma-search`** — translate the confirmed keyword set into each enabled source's native query syntax, run the connector CLIs, and deduplicate results into `records.jsonl`.
3. **`/prisma-screen export|import`** — export undecided records as title-abstract or full-text screening sheets (Markdown + CSV) for the reviewer to mark up outside the conversation, then import the decisions back into the append-only `screening_decisions.jsonl` ledger.
4. **`/prisma-extract`** — build `extraction_table.json`: study characteristics, effect-size data, and risk-of-bias judgements for every included study.
5. **`/prisma-synthesize`** — pool comparable outcomes statistically (fixed/random-effects), assess heterogeneity, generate forest/funnel plots, run RoB2 and GRADE, and fall back to narrative synthesis for outcomes that don't clear the poolability gate.
6. **`/prisma-report`** — draft the full manuscript, PRISMA flow diagram, and checklist audit from the recorded state only.
7. **`/prisma-status`** — report exactly where a review currently stands (resumable across sessions, since all state is append-only or re-derivable).
8. **`/prisma-add-source`** — scaffold a new search connector (e.g. an institutional Scopus/Web of Science connector) following the same contract as the shipped six.
9. **`/prisma-reset`** — scoped, confirm-before-destroy reset of a review's state.

Command specs live under `.claude/commands/`; the methodology they draw on lives under `.claude/skills/`. Treat both as the single source of truth — see [AGENTS.md](AGENTS.md) for the full thin-pointer rationale.

## Verification Checklist

Before presenting `/prisma-report` output, or at any point the reviewer asks "is this consistent," re-check:

- [ ] Every count in the PRISMA flow diagram (`manuscript/flow_diagram.svg`) is aggregated from `screening_decisions.jsonl` — never hand-typed or remembered from an earlier turn.
- [ ] Every full-text exclusion in `screening_decisions.jsonl` carries a non-empty `reason` (PRISMA Item 16b) before `/prisma-extract` proceeds.
- [ ] Every reference cited in the manuscript has been independently verified via WebSearch/WebFetch against a real source — never fabricated, and never trusted solely because a fetched abstract or full-text claims it exists.
- [ ] Every per-source query string in `search_plan.json` is exactly what `rerun_search.sh` replays — no drift between the audit trail and the actual search that was run.
- [ ] Pooled effect estimates and heterogeneity statistics in `synthesis/` trace back to specific rows in `extraction_table.json` — no invented numbers.
