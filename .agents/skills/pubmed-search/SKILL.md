---
name: pubmed-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search PubMed for a systematic
  review or literature search — NCBI's biomedical and life-sciences
  literature database, the primary source for MEDLINE-indexed clinical and
  biomedical evidence. Trigger phrases: search PubMed, PubMed search, MEDLINE
  search, literature search, systematic review search, database search, run
  the search plan against PubMed.
context: fork
---

# PubMed Search Skill

Searches PubMed via NCBI's E-utilities (esearch → efetch), the standard
biomedical/life-sciences literature database, using this repo's Python
connector:

```bash
python3 -m connectors.pubmed search --query "..." --format json
```

## When to use this skill

- Running one source of a systematic-review search plan against PubMed —
  the go-to source for clinical/biomedical evidence and MeSH-indexed terms
- Queries written in PubMed's own syntax (`[MeSH]`, `[tiab]`, boolean
  operators) — this is the native syntax `search_plan.json` stores for this
  source, per the per-database reproducibility requirement
- Fetching a single record's full data by PMID or DOI

## Commands

### Search

```bash
python3 -m connectors.pubmed search --query "<query>" [flags]
```

`--query` is PubMed's own search syntax, e.g.
`"diabetes mellitus[MeSH] AND metformin[tiab]"`. Internally this runs a
two-step esearch → efetch flow: esearch resolves the query to PMIDs (and the
true total-hit count), efetch pulls the full XML records for those PMIDs.

Shared flags (see `connectors/_shared.py`): `--limit <n>`, `--page <n>`,
`--since`/`--until` (publication date bounds), `--format json|table|plain`
(default `json`), `--out <path>`. Reproducible reruns read the query straight
out of `search_plan.json`:

```bash
python3 -m connectors.pubmed search --query-file results/<TOPIC>/search_plan.json --source-key pubmed
```

### Detail

```bash
python3 -m connectors.pubmed detail <id> [--format json|plain]
```

`<id>` is a bare PMID, fetched directly via efetch. A DOI is also accepted —
it is first resolved to a PMID via `esearch (term=<doi>[AID])`, then
efetch'd the same way.

## Usage examples

```bash
# MeSH + title/abstract search, capped at 50 results
python3 -m connectors.pubmed search --query "hypertension[MeSH] AND telemedicine[tiab]" --limit 50 --out raw/pubmed-20260904.json

# Date-bounded boolean search, table output
python3 -m connectors.pubmed search --query "(covid-19[tiab] OR sars-cov-2[tiab]) AND vaccination[tiab]" --since 2020/01/01 --until 2023/12/31 --format table

# Fetch one record by PMID
python3 -m connectors.pubmed detail 25883531 --format plain
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo.
Errors go to stderr as `{"error", "code"}` (`RATE_LIMITED`, `INVALID_QUERY`,
`UPSTREAM_ERROR`) with exit code 1. NCBI etiquette requires a contact email
on every request — set `NCBI_EMAIL` (or `PRISMA_CONTACT_EMAIL`) to your own.
Set `NCBI_API_KEY` to raise the per-IP rate limit from 3/s to 10/s; access
works without one.
