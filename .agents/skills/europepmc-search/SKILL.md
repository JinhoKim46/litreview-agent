---
name: europepmc-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search Europe PMC for a
  systematic review or literature search — a free biomedical/life-sciences
  index broader than PubMed alone, also covering preprints, patents, and
  full-text availability. Trigger phrases: search Europe PMC, EuropePMC
  search, EPMC search, literature search, systematic review search, database
  search, run the search plan against Europe PMC.
context: fork
---

# Europe PMC Search Skill

Searches Europe PMC (https://www.ebi.ac.uk/europepmc/webservices/rest), a
free, keyless biomedical/life-sciences index broader than PubMed — it also
covers preprints, patents, and agricultural literature — via this repo's
Python connector:

```bash
python3 -m connectors.europepmc search --query "..." --format json
```

## When to use this skill

- Running one source of a systematic-review search plan against Europe PMC
- Coverage beyond PubMed/MEDLINE: preprints (bioRxiv/medRxiv), patents, and
  agricultural literature that pure PubMed searches miss
- Queries in Europe PMC's Lucene-style syntax, including date-range clauses

## Commands

### Search

```bash
python3 -m connectors.europepmc search --query "<query>" [flags]
```

`--query` is Europe PMC's Lucene syntax, e.g. `"cancer AND immunotherapy"`.
Date-range filtering is expressed *inside* the query string rather than as a
separate flag: `FIRST_PDATE:[2020-01-01 TO 2023-12-31]` (either bound may be
`*` for an open range) — this is the native syntax `search_plan.json` stores
for this source.

Shared flags (see `connectors/_shared.py`): `--limit <n>` (page size, max
1000, cursor-paginated automatically above one page), `--page <n>`,
`--format json|table|plain` (default `json`), `--out <path>`. Reproducible
reruns read the query straight out of `search_plan.json`:

```bash
python3 -m connectors.europepmc search --query-file results/<TOPIC>/search_plan.json --source-key europepmc
```

### Detail

```bash
python3 -m connectors.europepmc detail <id> [--format json|plain]
```

Europe PMC has no arbitrary-ID single-record endpoint, so `detail` is
implemented as a search scoped to `EXT_ID:<id> AND SRC:<source>`, which
returns exactly the one matching record. Accepts a composite `<SOURCE>:<id>`
(e.g. `MED:25883531` — the same form `search` emits as record IDs) or a bare
numeric ID, which defaults to `SRC:MED` (PubMed/MEDLINE).

## Usage examples

```bash
# Lucene search capped at 100 results
python3 -m connectors.europepmc search --query "obesity AND bariatric surgery" --limit 100 --out raw/europepmc-20260904.json

# Search with an in-query date-range clause, table output
python3 -m connectors.europepmc search --query "long covid AND FIRST_PDATE:[2021-01-01 TO 2023-12-31]" --format table

# Fetch one record by composite source:id
python3 -m connectors.europepmc detail MED:25883531 --format plain
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo —
`meta.total_available` is Europe PMC's `hitCount`, the true match count
regardless of `--limit`. Errors go to stderr as `{"error", "code"}`
(`RATE_LIMITED`, `INVALID_QUERY`, `UPSTREAM_ERROR`) with exit code 1. No API
key or contact email required.
