---
name: keyword-expansion
description: >
  Expands a systematic review's PICO/PICo/SPIDER seed terms into a full search
  vocabulary, then translates that vocabulary into each enabled database's own
  native Boolean/field-tag query syntax and persists it to search_plan.json —
  the literal content of PRISMA 2020 Item 7's search-strategy appendix. Every
  candidate term (synonym, spelling variant, MeSH descriptor, broader/narrower
  term) is presented back to the reviewer for confirmation or pruning before
  it is used anywhere; nothing is added to a search string silently. Also
  handles national/regional scope: offers an optional keyword-translation step
  and records any source with no native local-language index as a
  coverage_gaps entry in protocol.json rather than dropping it silently.
  Triggers on: keyword expansion, expand search terms, expand my search,
  build the search string, Boolean search string, MeSH terms, MeSH lookup,
  search strategy, translate search terms, search terms for other databases,
  PRISMA Item 7, and as the term-building sub-step of /litreview-init and
  /litreview-search.
framework_version: 1.1.1
allowed-tools: Read, Write, Edit, WebFetch, WebSearch, AskUserQuestion, Bash(python3 -m connectors.*:*)
---

# Keyword Expansion

## How It Works

This skill turns a short PICO/PICo/SPIDER seed-term list into the per-database search strings PRISMA Item 7 requires — synonyms, spelling variants, and MeSH descriptors are proposed by the model but **confirmed or pruned by the reviewer** before anything is used, the confirmed vocabulary is then translated into each enabled source's own native query syntax (never one "universal" string reused everywhere), and the result is written to `results/<TOPIC>/search_plan.json` — the file `/litreview-search` reads verbatim and `rerun_search.sh` replays. See `01-expansion-methodology.md` for the full methodology, the per-source syntax cheat sheet, the JSON schemas, and worked examples.

## Invocation

Runs as a sub-step of `/litreview-init` (first pass, right after the PICO/PICo/ SPIDER interview) and `/litreview-search` (whenever the reviewer wants to revise terms before a re-run). Also triggers standalone on requests like:
- "Expand my search terms"
- "Build the Boolean search string for PubMed/OpenAlex/..."
- "What MeSH terms should I use for X?"
- "This review is Korea-scoped, do I need translated keywords?"
- "/litreview-init" (as its keyword step) or "/litreview-search" (to revise terms)

## Execution Steps

### Step 1: Collect Seed Terms

Read `results/<TOPIC>/protocol.json` for the PICO/PICo/SPIDER record written during the `/litreview-init` interview. Pull one or more seed terms per concept (Population, Intervention, Comparison, Outcome for PICO; substitute the framework's own concept labels for PICo/SPIDER). If `protocol.json` doesn't exist yet or a concept has no seed term, ask the reviewer directly rather than inventing one — seed terms are the reviewer's clinical/domain judgment, not the model's to originate. Read `protocol.json.field_domain` too (set during `review-protocol`'s elicitation) — it decides the MeSH axis's default in Step 2. Do **not** read or use `protocol.json.objective` here or anywhere in this skill: it drives PICO/PICo/SPIDER framework selection and PRISMA Item 4 manuscript text, never which concepts get searched or how broadly.

### Step 2: LLM-Assisted Expansion Pass

For each seed term, propose candidate expansions across four categories — synonyms/spelling variants, MeSH descriptors, broader terms, narrower/related terms — per the method in `01-expansion-methodology.md` §1-2. Whether the MeSH axis is proposed by default, offered as an ask, or skipped depends on `protocol.json.field_domain` (see `01-expansion-methodology.md` §2 for the three-way rule) — `field_domain: clinical_medicine` defaults MeSH in, `biomedical_technical` (e.g. imaging/reconstruction/bioinformatics tooling) asks once rather than defaulting it in, `non_biomedical` skips the axis. **Present every candidate to the reviewer as a confirm/prune table before any of them are used** — this applies even when the reviewer is in a hurry and says "just pick good ones"; give a sensible default selection *within* the table (pre-checked vs. unchecked) but still show the table. Nothing here is applied silently: a term that is not confirmed does not go into `search_plan.json`.

### Step 3: Per-Database Syntax Translation

Once the reviewer confirms a term set per concept, combine concepts with Boolean `AND`/`OR` in **each enabled source's own native query syntax** — PubMed's `[MeSH]`/`[tiab]` field tags, OpenAlex's `filter=` clauses, Crossref's `query.bibliographic`, Semantic Scholar's plain-text boolean-ish query, Europe PMC's Lucene-style query with field qualifiers, arXiv's `all:`/`cat:` fields — never one shared string copy-pasted six times. Full per-source rules and worked translations are in `01-expansion-methodology.md` §3. Show the reviewer the resulting string per source before persisting it, since a mistranslation here silently narrows or breaks a whole database's search.

### Step 4: Scope Check — National/Regional Keyword Translation

Read `protocol.json.scope.mode`. If `mode` is `"national"` or `"regional"` (not `"global"`), offer the optional keyword-translation step described in `01-expansion-methodology.md` §4: translate the confirmed English term set into the region's language(s), confirm the translations with the reviewer (machine translation of technical/clinical terms is not trustworthy unverified), and add them as additional native-language query strings per source where that source indexes non-English content at all. Record whether translation was used in `protocol.json.scope.translation_used` and `translation_languages`. Skip this step for `mode: "global"` reviews.

### Step 5: Coverage Gaps

For any enabled source that has **no native local-language index** for the review's region (e.g. arXiv for a Korea-scoped clinical topic — STEM preprints only; PubMed for a topic where the region's journals aren't MEDLINE-indexed), do not silently under-search it. Write a `coverage_gaps` entry to `protocol.json.scope.coverage_gaps` per §5 of `01-expansion-methodology.md`, naming the source and the specific gap. This is what lets `/litreview-report` draft an honest Limitations sentence instead of the manuscript silently under-claiming search coverage.

### Step 6: Persist

Write (or update) `results/<TOPIC>/search_plan.json` with the confirmed seed terms, the full expansion trail (candidate → accepted/rejected, so the audit trail survives even for terms the reviewer pruned), and the final `sources.<name>.query_string` per enabled source — the exact key path `connectors/_shared.py`'s `resolve_query()` reads via `--query-file search_plan.json --source-key <name>`. This file is also the direct source for the manuscript's Methods §2.4 search-strategy appendix; never re-typed from memory at report time.

### Step 7 (optional): Self-audit

Offer to run `references/press-inspired-search-audit.md`'s six-domain self-audit against the just-persisted `search_plan.json` before the reviewer treats the search as final. This is optional and never blocking — a reviewer in a hurry can decline — but if run, note the result in `search_plan.json` or the reviewer-facing summary so `/litreview-report` can mention it in Methods §2.4.

## Important Rules

1. **Never apply an expansion candidate silently.** Every synonym, MeSH term, or related term the model proposes is shown to the reviewer for confirmation or pruning before it reaches `search_plan.json` — no exception for "obviously right" terms.
2. **Never write one query string and reuse it across sources.** Each source's `query_string` must be valid in that source's own syntax; a string that happens to work as a bare keyword search everywhere is not translation, it's avoiding the work Item 7 requires.
3. **Never silently under-search a scope.** A national/regional review that skips keyword translation, or that includes a source with no local-language coverage, must say so in `protocol.json.scope` — either `translation_used: true` with the languages used, or a `coverage_gaps` entry naming the source and the specific limitation.
4. **Never fabricate a MeSH descriptor.** If MeSH lookup can't be verified (see `01-expansion-methodology.md` §2 for the verification path), say so and fall back to free-text `[tiab]` terms rather than inventing a plausible-looking MeSH heading.
5. **Keep the rejected candidates, don't delete them.** `search_plan.json`'s expansion trail records both accepted and rejected candidates — a reviewer revising the search later (or a peer reviewer asking "why didn't you search for X") needs to see what was considered, not just what was kept.
6. **Never let `protocol.json.objective` (or any restated goal/purpose sentence) narrow which concepts get searched.** Build every per-source string from confirmed PICO/PICo/SPIDER concept terms only. Comprehensiveness across those concepts is the default to search from, not a stance to argue for against a stated goal — narrowing belongs solely to the explicit mechanisms this skill and `/litreview-search` already use (eligibility date/language fields, population/design gates applied at screening), never to an inferred sense of "what this review is really about."
