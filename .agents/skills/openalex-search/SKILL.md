---
name: openalex-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search OpenAlex for a systematic
  review or literature search — a broad, free, multi-disciplinary scholarly
  index of ~250M works spanning every field, not just biomedicine. Trigger
  phrases: search OpenAlex, OpenAlex search, literature search, systematic
  review search, database search, run the search plan against OpenAlex.
context: fork
---

# OpenAlex Search Skill

Searches OpenAlex (https://api.openalex.org), a free, keyless, multi-disciplinary
index of ~250M scholarly works, via this repo's Python connector:

```bash
python3 -m connectors.openalex search --query "..." --format json
```

## When to use this skill

- Running one source of a systematic-review search plan against OpenAlex
- Broad multi-disciplinary coverage (any field, not biomedicine-only) where a
  single free, keyless index with good metadata completeness is wanted
- Fetching a single work's full record by its OpenAlex ID, DOI, PMID, or PMCID

## Commands

### Search

```bash
python3 -m connectors.openalex search --query "<query>" [flags]
```

`--query` accepts two forms:
- **OpenAlex native filter syntax** (contains a `:` field selector), e.g.
  `"title_and_abstract.search:cancer,type:article"` — this is the syntax
  `search_plan.json` stores per-source for reproducibility.
- **A bare keyword phrase** with no `:`, e.g. `"cancer immunotherapy"` — sent
  as OpenAlex's relevance-ranked `search=` param instead.

Shared flags (see `connectors/_shared.py`): `--limit <n>` (page size, max 200,
cursor-paginated automatically above one page), `--page <n>`, `--since`/
`--until` (publication date bounds), `--format json|table|plain` (default
`json`), `--out <path>`. Reproducible reruns read the query straight out of
`search_plan.json`:

```bash
python3 -m connectors.openalex search --query-file results/<TOPIC>/search_plan.json --source-key openalex
```

### Detail

```bash
python3 -m connectors.openalex detail <id> [--format json|plain]
```

`<id>` is a raw OpenAlex ID (`W2741809807`) or a prefixed external ID:
`doi:10.xxx`, `pmid:123`, `pmcid:PMCxxx`, `mag:123`.

## Usage examples

```bash
# Native filter syntax, capped to 50 results, JSON to a file
python3 -m connectors.openalex search --query "title_and_abstract.search:diabetes prevention,type:article" --limit 50 --out raw/openalex-20260904.json

# Bare keyword phrase, human-readable table
python3 -m connectors.openalex search --query "machine learning radiology" --format table

# Fetch one work by DOI
python3 -m connectors.openalex detail doi:10.1371/journal.pone.0121760 --format plain
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo —
`meta.total_available` is OpenAlex's true match count (never understated by
`--limit`), `results[].id` is the OpenAlex work ID. Errors go to stderr as
`{"error", "code"}` (`RATE_LIMITED`, `INVALID_QUERY`, `UPSTREAM_ERROR`) with
exit code 1. No API key required; set `OPENALEX_MAILTO` to a contact email
to opt into OpenAlex's "polite pool" for a higher, steadier rate limit.
