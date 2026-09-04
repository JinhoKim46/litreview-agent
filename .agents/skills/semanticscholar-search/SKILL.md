---
name: semanticscholar-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search Semantic Scholar for a
  systematic review or literature search — a free, multi-disciplinary
  Academic Graph covering computer science, biomedicine, and beyond, with
  citation-graph data. Trigger phrases: search Semantic Scholar, Semantic
  Scholar search, S2 search, literature search, systematic review search,
  database search, run the search plan against Semantic Scholar.
context: fork
---

# Semantic Scholar Search Skill

Searches Semantic Scholar's Academic Graph API
(https://api.semanticscholar.org/graph/v1), a free, multi-disciplinary index
with strong citation-graph data, via this repo's Python connector:

```bash
python3 -m connectors.semanticscholar search --query "..." --format json
```

## When to use this skill

- Running one source of a systematic-review search plan against Semantic
  Scholar
- Multi-disciplinary relevance search, especially where citation counts or
  cross-source external IDs (DOI/PMID/PMCID/arXiv/MAG) are useful for dedup
- Fetching a single paper's full record by any of those external IDs

## Commands

### Search

```bash
python3 -m connectors.semanticscholar search --query "<query>" [flags]
```

Shared flags (see `connectors/_shared.py`): `--limit <n>` (max 100 per call;
the API enforces a hard `offset + limit <= 1000` ceiling for this endpoint —
plan multi-page reruns accordingly), `--page <n>`, `--since`/`--until`
(publication year bounds), `--format json|table|plain` (default `json`),
`--out <path>`. Reproducible reruns read the query straight out of
`search_plan.json`:

```bash
python3 -m connectors.semanticscholar search --query-file results/<TOPIC>/search_plan.json --source-key semanticscholar
```

### Detail

```bash
python3 -m connectors.semanticscholar detail <id> [--format json|plain]
```

`<id>` accepts a bare Semantic Scholar paper hash/CorpusId, or a prefixed
external ID: `DOI:...`, `ARXIV:...`, `PMID:...`, `PMCID:...`, `MAG:...`,
`ACL:...`.

## Usage examples

```bash
# Relevance search capped at 100 results (one page, the per-call max)
python3 -m connectors.semanticscholar search --query "large language models clinical decision support" --limit 100 --out raw/semanticscholar-20260904.json

# Year-bounded search, table output
python3 -m connectors.semanticscholar search --query "graph neural networks drug discovery" --since 2021 --until 2024 --format table

# Fetch one paper by DOI
python3 -m connectors.semanticscholar detail DOI:10.1371/journal.pone.0121760 --format plain
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo.
Errors go to stderr as `{"error", "code"}` (`RATE_LIMITED`, `INVALID_QUERY`,
`UPSTREAM_ERROR`) with exit code 1. Unauthenticated traffic shares an
aggressive public rate-limit pool, so `RATE_LIMITED`/429 is routine, not
exceptional — the connector already retries with backoff and jitter before
surfacing it. Set `S2_API_KEY` to raise the rate limit; access works fine
without one.
