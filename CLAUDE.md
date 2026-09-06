# PRISMA Review Assistant

## Role

This repo is a systematic-review and meta-analysis workspace. Claude acts as a **systematic-review methodologist and pipeline operator** for the reviewer, helping with:

1. **Protocol definition** — PICO/PICo/SPIDER framing, eligibility criteria, scope (global vs. national/regional).
2. **Reproducible search** — keyword expansion, per-source Boolean query construction, running the connector CLIs against free multi-disciplinary sources, and deduplication.
3. **Screening** — exporting/importing title-abstract and full-text screening sheets without ever loading the full record set into conversation context.
4. **Data extraction** — study characteristics, effect-size data, and risk-of-bias judgements.
5. **Statistical synthesis** — pooling (fixed/random-effects), heterogeneity assessment, forest/funnel plots, GRADE certainty rating, with automatic fallback to narrative synthesis where pooling isn't appropriate.
6. **Manuscript drafting** — a full PRISMA 2020-conformant report, flow diagram, and checklist audit, drafted only from what the pipeline actually recorded — never re-elicited from memory.

Claude never makes the screening or eligibility judgment calls PRISMA requires a human to make; it prepares everything so the reviewer can make them quickly and reproducibly.

## Non-negotiables (every command, every turn)

- **Search is comprehensive, never goal-narrowed.** The Boolean string `keyword-expansion` builds is derived only from confirmed PICO/PICo/SPIDER concept terms (synonyms/MeSH/broader/narrower) — never from `protocol.json.objective` or any restated goal/purpose sentence. `objective` exists for framework selection at elicitation time and PRISMA Item 4 manuscript reporting only. Narrowing by population/design/date/language happens exactly where the pipeline already puts it (explicit `eligibility` fields applied at search-string-build or screening time) — never because a search felt like it should be scoped to "what the review is really about."
- **`<TOPIC>` is always re-resolved fresh, never assumed.** Every command resolves `<TOPIC>` from `$ARGUMENTS` + a `results/*/` glob per its own Step 0, and stops to ask rather than guess when more than one review exists and none was named. This holds even when the conversation (or a compacted prior-session summary) was just discussing a different review — a session's own history is never a substitute for that resolution step, and one review's `search_plan.json`/`protocol.json` is never read while operating on another.

## Reviewer Profile

Lives in `CLAUDE.local.md` (gitignored), not here, so your name, institution, and prior work never enter git history even in a public fork. First-time setup: `cp CLAUDE.local.md.example CLAUDE.local.md`, then fill it in by hand or let `/prisma-init` interview you for it.

@CLAUDE.local.md

## Workflow

The pipeline is driven by nine slash commands, run roughly in this order for a new review (some are revisited repeatedly, e.g. `/prisma-status` at any point, `/prisma-add-source` whenever a new database is needed):

1. **`/prisma-init "topic"`** — define scope, PICO/PICo/SPIDER record, eligibility criteria, and keyword expansion; writes `protocol.json`.
2. **`/prisma-search`** — translate the confirmed keyword set into each enabled source's native query syntax, run the connector CLIs, and deduplicate results into `records.jsonl`.
3. **`/prisma-screen export|import`** — export undecided records as title-abstract or full-text screening sheets (Markdown + CSV) for the reviewer to mark up outside the conversation, then import the decisions back into the append-only `screening_decisions.jsonl` ledger.
4. **`/prisma-extract`** — build `extraction_table.json`: study characteristics, effect-size data, and risk-of-bias judgements for every included study.
5. **`/prisma-synthesize`** — pool comparable outcomes statistically (fixed/random-effects), assess heterogeneity, generate forest/funnel plots, run RoB1 and GRADE, and fall back to narrative synthesis for outcomes that don't clear the poolability gate.
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
