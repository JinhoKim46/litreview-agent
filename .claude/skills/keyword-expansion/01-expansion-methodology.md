---
framework_version: 1.1.0
---

# Keyword Expansion Methodology

This document is the full methodology behind `SKILL.md`'s six steps: how candidate terms are generated and verified (§1-2), how the confirmed vocabulary becomes a per-source Boolean string (§3), how national/regional scope changes the process (§4), how coverage gaps are recorded (§5), and the exact JSON schemas involved (§6).

---

## 1. Seed Terms → Candidate Expansions

For each PICO/PICo/SPIDER concept, the seed term(s) the reviewer supplied during `/prisma-init` are expanded along four independent axes. Generate candidates for **all four axes for every seed term** — don't skip an axis because the first one already found something.

**a. Synonyms and spelling variants.** Draw on general domain knowledge: American/British spelling (`randomized`/`randomised`, `anesthesia`/ `anaesthesia`), common abbreviations and their expansions (`COPD` ↔ `chronic obstructive pulmonary disease`), brand/generic naming where relevant, and near-synonyms actually used in the literature (`exercise therapy` / `physical therapy` / `physiotherapy` are not interchangeable in every domain — propose them separately, let the reviewer judge fit rather than merging them into one bucket for the model).

**b. MeSH descriptors.** Whether this axis is proposed at all, and whether it's the *default* vocabulary or an opt-in one, is keyed on `protocol.json.field_domain` (set during `review-protocol`'s field-domain elicitation — see that skill's Phase 1) rather than a single "biomedical or not" test. A binary test collapses two genuinely different cases: clinical/hospital medicine, where MeSH is the primary indexing convention the literature was built around, and a biomedical-*adjacent* technical/engineering field (MRI reconstruction, biosensor design, bioinformatics tooling, etc.), where MeSH headings exist for some vocabulary but free-text `[tiab]`/keyword terms are how that literature actually gets found and indexed.

- `field_domain: clinical_medicine` — propose the MeSH axis **by default**, same as every other axis; the reviewer still prunes per-term as usual.
- `field_domain: biomedical_technical` — MeSH terms may exist for part of the vocabulary (e.g. a disease or anatomical term nested in an otherwise technical concept) but are not this literature's primary index. Ask once, up front, before generating candidates: *"MeSH headings exist for some of this vocabulary but aren't the primary index for this literature — include them alongside free-text terms, or free-text only?"* Don't default MeSH in silently just because the topic sounds biomedical-adjacent.
- `field_domain: non_biomedical` — skip this axis entirely, as before.

If `protocol.json.field_domain` is missing (e.g. an older review from before this field existed), ask the reviewer which of the three applies before generating this axis's candidates — never infer it from the topic string alone.

Whichever path proposes MeSH terms, propose the MeSH heading(s) that most plausibly match the seed term, **flagged as unverified** until checked. This repo's `connectors/pubmed.py` does not currently expose a `mesh-lookup` subcommand, so verify by one of:
  - `WebFetch` against NCBI's public MeSH browser, `https://www.ncbi.nlm.nih.gov/mesh/?term=<term>` (or `WebSearch` for the term plus `"MeSH"` if WebFetch is unavailable) — confirm the descriptor exists and read its scope note before proposing it as confirmed;
  - or, when neither tool can reach the network, present the candidate explicitly labeled `(unverified — please confirm this MeSH heading exists)` and let the reviewer confirm or reject it directly. Never present a MeSH heading as fact without one of these two checks — MeSH tree structure is exactly the kind of detail an LLM can misremember or invent plausibly.

**c. Broader terms.** One level up the concept hierarchy — useful mainly for scoping decisions (a broader term proposed but rejected still tells the reviewer their eligibility criteria are appropriately narrow), rarely added to the actual search string unless the review's PICO is itself broad.

**d. Narrower / related terms.** Sibling and child concepts the reviewer's seed term might be under-capturing — the axis most likely to catch a real recall gap (e.g. a seed term "diabetes" missing "type 2 diabetes mellitus" / "T2DM" as an indexed near-synonym in some databases).

### Confirmation table

Present all candidates for one PICO concept at a time, not the whole term set at once (a wall of forty checkboxes gets rubber-stamped; four separate concept-scoped decisions get read). Use a checklist the reviewer can answer with keep/drop per row, pre-marking a sensible default:

```markdown
### Population: "older adults with type 2 diabetes"

| # | Candidate | Type | Default | Note |
|---|-----------|------|---------|------|
| 1 | elderly | synonym | keep | common in older literature |
| 2 | aged | synonym | keep | matches MeSH heading below |
| 3 | Aged [MeSH] | MeSH | keep | verified: NCBI MeSH, "65+ years" |
| 4 | Diabetes Mellitus, Type 2 [MeSH] | MeSH | keep | verified: NCBI MeSH |
| 5 | T2DM | abbreviation | keep | frequent in titles/abstracts |
| 6 | geriatric | related | drop? | broader than "older adults" — your call |
| 7 | non-insulin-dependent diabetes | narrower (historic) | drop? | outdated term, rarely indexed post-1990s |

Reply with row numbers to flip (e.g. "keep 6, drop 3") or "confirm defaults".
```

Only rows the reviewer confirms (explicitly, or implicitly via "confirm defaults" after seeing the table) become `status: "accepted"` in `search_plan.json`'s expansion trail; every other row is kept as `status: "rejected"` — visible, never deleted (SKILL.md Rule 5).

---

## 2. Concept Combination Logic

Within one PICO/PICo/SPIDER concept, confirmed terms combine with `OR` (they're alternative expressions of the same idea). Across concepts, they combine with `AND` (the search needs all the concepts present, e.g. Population AND Intervention AND Outcome). Comparison/Control terms are **usually left out of the search string entirely** unless the review is specifically restricted to studies with a named comparator — most systematic reviews search Population+Intervention(+Outcome) and apply the Comparison criterion during screening instead, since requiring the comparator in the search string itself is a common cause of false-negative misses. Flag this choice to the reviewer rather than deciding it silently.

---

## 3. Per-Source Native Syntax Translation

Each source's connector (`connectors/<name>.py`) already defines exactly how `--query`/`query_string` is interpreted — translate into the syntax that connector actually expects, not a generic guess. Current behavior per source:

**PubMed** (`connectors/pubmed.py`, via NCBI E-utilities `esearch`) — standard PubMed field-tag syntax: `[MeSH]` for a MeSH descriptor (add `[MeSH]` for the tree including narrower terms, `[MeSH:noexp]` to pin to that heading exactly), `[tiab]` for title/abstract free text, `[MeSH] OR [tiab]` combinations per concept are standard practice (a MeSH term alone under-captures very recent literature not yet indexed). Example:
```
(("Aged"[MeSH] OR elderly[tiab] OR aged[tiab]) AND ("Diabetes Mellitus, Type 2"[MeSH] OR "type 2 diabetes"[tiab] OR T2DM[tiab]) AND (exercise[tiab] OR "physical activity"[tiab]))
```

**OpenAlex** (`connectors/openalex.py`) — a query string containing a `:` field selector is sent straight through as the native `filter=` parameter (e.g. `title_and_abstract.search:...`); a bare phrase with no `:` is instead sent as `search=` (OpenAlex's relevance search across title/abstract/ fulltext), which does **not** support `[MeSH]`-style field tags or nested Boolean field syntax the way PubMed does. Build the query as a plain Boolean-in-prose phrase for `search=`, or as an explicit `filter=` clause (e.g. `title_and_abstract.search:diabetes AND title_and_abstract.search:exercise`) when you need field-scoped precision — pick one form per source string and say which in the search string's accompanying note, don't mix syntaxes in one string.

**Crossref** (`connectors/crossref.py`) — sent to the `query.bibliographic` param (titles/authors/etc., Crossref's stronger relevance field), not the bare `query` param. Crossref's query parser does not support explicit Boolean operators the way PubMed does; express the concept combination as a natural-language phrase covering the required concepts (Crossref's citation metadata is comparatively thin — it is the weakest of the six sources for title/abstract-only Boolean precision, useful mainly for DOI/venue metadata and citation-linking rather than as a primary recall source).

**Semantic Scholar** (`connectors/semanticscholar.py`) — sent as the `query` param to `/paper/search`, S2's own relevance-ranked free-text search. Like Crossref, it has no field-tag Boolean syntax; combine concepts as a natural phrase, and rely on Semantic Scholar's own quoted-phrase support (`"exact phrase"`) where precision matters.

**Europe PMC** (`connectors/europepmc.py`) — Lucene-style query syntax with real field qualifiers: `TITLE:`, `ABSTRACT:`, `MESH:`, boolean `AND`/`OR`/ `NOT`, and quoted phrases. This is the source closest to PubMed's expressiveness among the non-PubMed sources — use it, don't flatten it to a bare phrase:
```
(MESH:"Diabetes Mellitus, Type 2" OR ABSTRACT:"type 2 diabetes") AND (ABSTRACT:exercise OR ABSTRACT:"physical activity")
```

**arXiv** (`connectors/arxiv.py`) — Atom API `search_query` syntax: `all:` for all-fields, `ti:`/`abs:`/`cat:` for title/abstract/category, joined with `AND`/`OR` inside the single `search_query` string, e.g. `all:"large language models" AND cat:cs.CL`. Preprints only, STEM categories only — irrelevant to most clinical/health topics and to any topic outside arXiv's covered categories (physics, CS/math, quantitative biology/finance, some econ/stats); skip generating an arXiv string entirely for a clinical or social-science review rather than forcing an empty-yield source into the plan.

Show every resulting string back to the reviewer before writing `search_plan.json` (SKILL.md Step 3) — a translation mistake here (e.g. a stray unescaped quote, or `AND`/`OR` precedence that doesn't mean what it looks like) silently corrupts one entire database's recall, and the reviewer's domain judgment is often the only thing that catches it.

---

## 4. National/Regional Scope: Optional Keyword Translation

Triggered by `protocol.json.scope.mode` being `"national"` or `"regional"` (read during SKILL.md Step 4). When triggered:

1. Ask the reviewer which language(s) the region's literature is likely published in (don't guess from the region name alone — e.g. a Switzerland-scoped review may need German, French, and Italian terms).
2. Machine-translate the **confirmed** English term set (never untranslated candidates) into each language, then say so explicitly — present the translations as a draft requiring confirmation, exactly like Step 2's expansion candidates, since a mistranslated clinical or technical term is a silent recall failure that's much harder to notice than a missing English synonym. Prefer having the reviewer (or a collaborator fluent in the language) confirm rather than trusting machine translation of technical vocabulary unverified.
3. Add the confirmed translated terms as **additional** query strings per source — only for sources that actually index non-English content at all (Europe PMC and OpenAlex have real multilingual coverage; PubMed indexes some non-English journals but is still English-abstract-biased; arXiv and Semantic Scholar are effectively English-only in practice). Do not silently drop the English string when adding a translated one — run both, since the region's authors may publish in either language.
4. Record the outcome on `protocol.json.scope`:
   ```json
   "translation_used": true,
   "translation_languages": ["ko"]
   ```
Set `translation_used: false` (and leave `translation_languages: []`) when the reviewer declines translation for a national/regional review — this is a legitimate choice (e.g. a review restricted to English-language publications by explicit eligibility criterion) but it must be visible in `protocol.json`, not silently absent, since `/prisma-report` drafts the Methods §2.4 language-scope sentence directly from this field.

---

## 5. Coverage Gaps

A source can have no meaningful local-language index for a region even after translation is applied to the query string — the gap is in the *index*, not the *query*. Do not paper over this by running a translated query against a source that won't return meaningful results anyway; name it instead. Known, well-documented gaps to check against for any national/regional review (verify current specifics rather than assuming these never change):

- **arXiv** — STEM preprints only (physics, CS/math, quantitative biology/ finance, some econ/stats categories). No coverage at all for clinical, social-science, or humanities regional literature — this is a scope gap, not a language gap, and applies regardless of language.
- **PubMed** — indexes primarily English-language biomedical journals; non-English journals are included only when MEDLINE has assessed them, and even then usually only their English abstract is indexed, not full-text in the local language. A country whose clinical journals are not MEDLINE-indexed (common for smaller national journals) is under-represented regardless of query translation.
- **Crossref** — coverage is a function of which publishers register DOIs with Crossref; many national, society-run, or non-commercial journals (especially local-language ones) never register there, independent of query language.
- **Semantic Scholar** — strongest for English-language CS/biomedical literature; regional/local-language journals outside major aggregators are inconsistently crawled.
- **OpenAlex** and **Europe PMC** — the broadest multilingual coverage of the six, but still aggregate from upstream sources (Crossref, PubMed, institutional repositories) and inherit those sources' regional gaps rather than independently indexing local journals.

When a gap applies, write it to `protocol.json.scope.coverage_gaps` (schema in §6) naming the specific source and the specific limitation — not a generic "may have limited coverage" note. If the reviewer has (or can get) access to a source that does cover the gap (e.g. a national database like KoreaMed, LILACS, or a Scopus/Web of Science institutional subscription), suggest `/prisma-add-source` rather than leaving the gap unaddressed; if not, the gap entry itself becomes the manuscript's honest Limitations sentence.

---

## 6. JSON Schemas

### `protocol.json.scope` (this skill writes/updates this block only —
the rest of `protocol.json` belongs to `review-protocol`)

```json
{
  "scope": {
    "mode": "national",
    "region": "South Korea",
    "translation_used": true,
    "translation_languages": ["ko"],
    "coverage_gaps": [
      {
        "source": "arxiv",
        "gap": "STEM preprints only; no coverage of clinical/health literature regardless of language",
        "mitigation": "arXiv excluded from this review's source list"
      },
      {
        "source": "pubmed",
        "gap": "Korean-language journals indexed only when MEDLINE has assessed them; most carry only an English abstract, not full Korean text",
        "mitigation": "supplemented by manual review of KoreaMed for this topic; noted as a Limitations item"
      }
    ]
  }
}
```

### `search_plan.json` (this skill owns this file in full)

```json
{
  "topic": "exercise therapy for older adults with type 2 diabetes",
  "generated_at": "2026-09-04T12:00:00Z",
  "seed_terms": {
    "population": ["older adults with type 2 diabetes"],
    "intervention": ["exercise therapy"],
    "outcome": ["glycemic control"]
  },
  "expansion_trail": [
    {
      "concept": "population",
      "seed": "older adults with type 2 diabetes",
      "candidates": [
        {"term": "Aged [MeSH]", "type": "mesh", "verified": true, "status": "accepted"},
        {"term": "Diabetes Mellitus, Type 2 [MeSH]", "type": "mesh", "verified": true, "status": "accepted"},
        {"term": "elderly", "type": "synonym", "status": "accepted"},
        {"term": "T2DM", "type": "abbreviation", "status": "accepted"},
        {"term": "geriatric", "type": "related", "status": "rejected", "reason": "broader than reviewer's intended population"}
      ]
    }
  ],
  "translation": {
    "applied": true,
    "languages": ["ko"],
    "confirmed_by": "reviewer"
  },
  "sources": {
    "pubmed": {
      "enabled": true,
      "query_string": "((\"Aged\"[MeSH] OR elderly[tiab] OR aged[tiab]) AND (\"Diabetes Mellitus, Type 2\"[MeSH] OR \"type 2 diabetes\"[tiab] OR T2DM[tiab]) AND (exercise[tiab] OR \"physical activity\"[tiab]))",
      "syntax": "pubmed-field-tags"
    },
    "openalex": {
      "enabled": true,
      "query_string": "older adults type 2 diabetes exercise therapy glycemic control",
      "syntax": "openalex-search-param"
    },
    "crossref": {
      "enabled": true,
      "query_string": "older adults type 2 diabetes exercise therapy",
      "syntax": "crossref-bibliographic"
    },
    "semanticscholar": {
      "enabled": true,
      "query_string": "type 2 diabetes exercise therapy older adults glycemic control",
      "syntax": "s2-free-text"
    },
    "europepmc": {
      "enabled": true,
      "query_string": "(MESH:\"Diabetes Mellitus, Type 2\" OR ABSTRACT:\"type 2 diabetes\") AND (ABSTRACT:exercise OR ABSTRACT:\"physical activity\") AND (ABSTRACT:elderly OR ABSTRACT:aged)",
      "syntax": "europepmc-lucene"
    },
    "arxiv": {
      "enabled": false,
      "reason": "STEM preprints only; not applicable to this clinical topic"
    }
  }
}
```

`sources.<name>.query_string` is the exact field `connectors/_shared.py`'s `resolve_query()` reads when a connector is invoked with `--query-file results/<TOPIC>/search_plan.json --source-key <name>` — keep the key names identical to the connector module names (`pubmed`, `openalex`, `crossref`, `semanticscholar`, `europepmc`, `arxiv`) so `/prisma-search` and `rerun_search.sh` can address them without a lookup table.
