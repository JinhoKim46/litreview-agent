---
name: arxiv-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search arXiv for a systematic
  review or literature search — a free preprint repository covering physics,
  math, computer science, quantitative biology, and related fields, before
  peer review. Trigger phrases: search arXiv, arXiv search, preprint search,
  literature search, systematic review search, database search, run the
  search plan against arXiv.
context: fork
---

# arXiv Search Skill

Searches the arXiv API (Atom XML, http://export.arxiv.org/api/query), a free
preprint repository covering physics, math, computer science, quantitative
biology and related fields, via this repo's Python connector:

```bash
python3 -m connectors.arxiv search --query "..." --format json
```

## When to use this skill

- Running one source of a systematic-review search plan against arXiv
- Preprint coverage in physics/CS/math/quant-bio, including work not yet
  peer-reviewed
- Fetching a single preprint's record by its arXiv ID

**Preprints only**: every record's `venue` is hardcoded to `"arXiv preprint"`
— none have undergone peer review. This matters downstream for dedup (an
arXiv preprint and its later peer-reviewed version, found via OpenAlex or
Crossref, are the same study and must merge via title+author+year, since the
preprint usually lacks a DOI) and for risk-of-bias/GRADE bookkeeping.

## Commands

### Search

```bash
python3 -m connectors.arxiv search --query "<query>" [flags]
```

`--query` is arXiv's own `search_query` syntax, using field prefixes joined
with boolean operators, e.g. `"all:transformer AND cat:cs.CL"` or
`"ti:diffusion models"` — this is the native syntax `search_plan.json` stores
for this source.

Shared flags (see `connectors/_shared.py`): `--limit <n>` (`max_results`, up
to 2000 per call, 30000-result total window), `--page <n>` (`start` offset),
`--format json|table|plain` (default `json`), `--out <path>`. The connector
respects arXiv's documented courtesy delay between calls. Reproducible
reruns read the query straight out of `search_plan.json`:

```bash
python3 -m connectors.arxiv search --query-file results/<TOPIC>/search_plan.json --source-key arxiv
```

### Detail

```bash
python3 -m connectors.arxiv detail <id> [--format json|plain]
```

`<id>` is an arXiv ID (`2401.01234`), optionally versioned (`2401.01234v2`) —
fetched directly via `id_list`.

## Usage examples

```bash
# Field-scoped boolean search, capped at 100 results
python3 -m connectors.arxiv search --query "all:federated learning AND cat:cs.LG" --limit 100 --out raw/arxiv-20260904.json

# Title-only search, table output
python3 -m connectors.arxiv search --query "ti:large language model evaluation" --format table

# Fetch one preprint by arXiv ID
python3 -m connectors.arxiv detail 2401.01234 --format plain
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo.
Errors go to stderr as `{"error", "code"}` (`RATE_LIMITED`, `INVALID_QUERY`,
`UPSTREAM_ERROR`) with exit code 1. No API key or contact email required. A
malformed or out-of-range query does not return an HTTP error — arXiv
answers with a normal 200 containing a single error entry, which this
connector detects and reports as `INVALID_QUERY`.
