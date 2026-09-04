---
name: crossref-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search Crossref for a systematic
  review or literature search — the DOI registration agency's free index of
  ~160M works, strongest on DOIs and bibliographic metadata. Trigger phrases:
  search Crossref, Crossref search, literature search, systematic review
  search, database search, run the search plan against Crossref.
context: fork
---

# Crossref Search Skill

Searches Crossref (https://api.crossref.org), the DOI registration agency's
free, keyless metadata index of ~160M works, via this repo's Python connector:

```bash
python3 -m connectors.crossref search --query "..." --format json
```

## When to use this skill

- Running one source of a systematic-review search plan against Crossref
- Bibliographic metadata and DOI resolution — Crossref is strongest here;
  many records (especially older ones) lack an abstract, so pair it with a
  source that has better abstract coverage when abstracts matter
- Fetching a single work's record directly by DOI

## Commands

### Search

```bash
python3 -m connectors.crossref search --query "<query>" [flags]
```

`--query` is sent as Crossref's `query.bibliographic` param (titles, authors,
ISSNs, publication years — the field Crossref recommends for literature-search
relevance, and the native syntax `search_plan.json` stores for this source).

Shared flags (see `connectors/_shared.py`): `--limit <n>` (`rows`, max 1000),
`--page <n>` (offset paging, capped at 10,000 total by Crossref) or `--cursor`
for deep pagination, `--since`/`--until` (publication date bounds), `--format
json|table|plain` (default `json`), `--out <path>`. Reproducible reruns read
the query straight out of `search_plan.json`:

```bash
python3 -m connectors.crossref search --query-file results/<TOPIC>/search_plan.json --source-key crossref
```

### Detail

```bash
python3 -m connectors.crossref detail <doi> [--format json|plain]
```

Crossref supports single-DOI lookup directly — `<doi>` is fetched with no
search-fallback needed.

## Usage examples

```bash
# Bibliographic search capped at 100 results
python3 -m connectors.crossref search --query "randomized controlled trial hypertension" --limit 100 --out raw/crossref-20260904.json

# Date-bounded search, table output
python3 -m connectors.crossref search --query "climate adaptation agriculture" --since 2020-01-01 --until 2023-12-31 --format table

# Fetch one work by DOI
python3 -m connectors.crossref detail 10.1371/journal.pone.0121760 --format plain
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo —
`meta.total_available` is Crossref's `message.total-results`, the true match
count regardless of `--limit`. Errors go to stderr as `{"error", "code"}`
(`RATE_LIMITED`, `INVALID_QUERY`, `UPSTREAM_ERROR`) with exit code 1. No API
key required; set `PRISMA_CONTACT_EMAIL` to opt into Crossref's "polite pool"
for a higher, steadier rate limit.
