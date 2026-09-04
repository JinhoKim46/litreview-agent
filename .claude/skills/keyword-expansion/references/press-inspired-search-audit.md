---
framework_version: 1.0.1
---

# Search-strategy self-audit (PRESS-inspired)

A self-audit checklist for `results/<TOPIC>/search_plan.json` before a review's search is declared final (PRISMA Item 7). Offered as an optional step in `/prisma-search` — never blocking, since a solo reviewer without a second peer reviewer is still better served by auditing their own strategy than skipping the check entirely.

**Provenance note:** this document is organised around the six domain categories used by the published PRESS 2015 Guideline Statement (McGowan J, Sampson M, Salzwedel DM, Cogo E, Foerster V, Lefebvre C. "PRESS Peer Review of Electronic Search Strategies: 2015 Guideline Statement." *J Clin Epidemiol*. 2016 Jul;75:40–46) — a well-established framework for structuring a search-strategy peer review. It is an **original, independently-worded adaptation** of that structure to this framework's own file schema and connectors, not a reproduction of the PRESS checklist's actual text: PRESS itself is licensed CC BY-NC-ND (no-derivatives), so its wording is deliberately not reused here. A reviewer who wants the authoritative instrument itself (e.g. for a Cochrane or JBI-registered protocol that requires citing PRESS specifically) should obtain it directly from the publisher.

---

## 1. Translation of the research question

- Does every PICO/PICo/SPIDER concept from `protocol.json` appear as at least one clause in every enabled source's `query_string`? A concept silently dropped from one database's string (but present in another's) is a coverage gap worth naming explicitly, not an accident to discover after the search runs.
- Is the *relationship* between concepts (AND between distinct PICO elements, OR within a single element's synonym set) reflected correctly in each source's native syntax — not just copy-pasted from one source's Boolean structure into another's, which routinely produces silently-wrong results (e.g. a `filter=` clause on OpenAlex is not interchangeable with a MeSH-tagged PubMed term list one-for-one).

## 2. Boolean and proximity operators

- Are `AND`/`OR`/`NOT` used correctly for each source's actual syntax (some APIs are case-sensitive on operators, some use different tokens for phrase/proximity search)? `keyword-expansion/01-expansion-methodology.md` documents each of the six shipped connectors' native syntax — cross-check the generated string against that reference, not against a different source's convention.
- Is `NOT` used sparingly and only to exclude clearly out-of-scope material? An overly broad exclusion clause silently removes relevant records before they ever reach `records.jsonl`, which no later screening step can recover.

## 3. Subject headings / controlled vocabulary

- For biomedical topics, does the PubMed string actually use `[MeSH]`-tagged terms (via the `mesh-lookup` helper) rather than only free-text `[tiab]` terms? A MeSH-only or free-text-only strategy each misses studies the other would catch — the expansion pass in `01-expansion-methodology.md` should have produced both, combined with `OR`.
- For non-biomedical topics with no controlled vocabulary available in the chosen sources, confirm this was a deliberate scoping decision (recorded in `search_plan.json` or `protocol.json`), not an oversight from defaulting to the biomedical-source workflow.

## 4. Text-word (free-text) searching

- Does the free-text term set cover spelling variants (British/American English), acronyms and their expansions, and plural/singular forms? A term list with only one spelling of a key concept is the single most common way a systematic search under-retrieves.
- Were candidate synonyms actually **shown to the reviewer for confirmation** during expansion, per `01-expansion-methodology.md`'s rule that nothing is added silently — spot check that the final `search_plan.json` doesn't contain a term the reviewer never saw.

## 5. Spelling, syntax, and line numbers

- Does each source's `query_string` in `search_plan.json` actually parse without an `INVALID_QUERY` error from that connector? This is directly testable — a syntax error a human proofreader might miss is caught immediately by `rerun_search.sh` returning a non-zero exit and a `{"error", "code"}` line naming exactly what's wrong.
- Are parentheses balanced and operator precedence unambiguous, especially where OR-joined synonym groups are combined with AND across PICO concepts (a missing parenthesis silently changes which studies match, without producing a syntax error at all).

## 6. Limits and filters

- Are date range, language, and publication-type filters (`search_plan.json`'s per-source `filters` object) applied consistently across every enabled source, or does one source silently lack an equivalent filter the reviewer assumed was universal? Record any such gap in `protocol.json.scope.coverage_gaps` rather than letting it pass unnoticed.
- Does a language filter match the review's actual scope decision (global vs. national/ regional, and any keyword-translation step taken per §5 of `01-expansion-methodology.md`), rather than defaulting to English-only when the review's scope explicitly calls for broader coverage?

---

## How `/prisma-search` uses this

Run through the six sections above against the current `search_plan.json` before executing Step 6 (or after, before declaring the search "final" for Item 7 reporting). Note any finding directly in the reviewer-facing summary — a clean self-audit is worth stating explicitly in the manuscript's Methods §2.4 ("the search strategy was self-audited against a PRESS-inspired checklist prior to execution"), the same way a real peer-reviewed search strategy would be reported.
