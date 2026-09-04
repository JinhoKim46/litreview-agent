---
name: citation-chase-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to snowball a systematic review's
  reference list — backward (what an included study cites) or forward
  (what cites it) — via OpenAlex. This is a real PRISMA "other methods"
  identification source, distinct from the six keyword-search connectors.
  Trigger phrases: citation chasing, snowballing, backward citation search,
  forward citation search, chase references, chase citations, what cites
  this study, what does this study cite.
context: fork
---

# Citation-Chasing Skill

Backward (references) and forward (citing works) snowballing from a set of seed studies,
via this repo's Python connector:

```bash
python3 -m connectors.citation_chase chase --seed-ids "<id1>,<id2>,..." --direction backward|forward|both
```

## When to use this skill

- After initial screening, chasing the reference lists of the reviewer's included studies
  to catch relevant work the six keyword-search connectors missed (a real, PRISMA-recognised
  "other methods" identification source — see `flow-diagram.md`'s Template B/D).
- Finding what more-recent work cites an already-included key study (forward chasing).

This is **not** a keyword search — it takes seed study identifiers, not a query string, and
has no `detail` command.

## Commands

### Chase

```bash
python3 -m connectors.citation_chase chase --seed-ids "10.1234/abcd,W2741809807" --direction both [flags]
```

Each seed id is a bare DOI or a raw OpenAlex work id — the same two forms
`connectors.openalex detail` accepts. A seed OpenAlex can't resolve (typo, not indexed) is
skipped, not fatal — check `meta.unresolved_seeds` in the output.

Flags: `--direction backward|forward|both` (default `both`), `--limit <n>` (default 200,
applies per direction), `--format json|table|plain` (default `json`), `--out <path>`.

## Usage examples

```bash
# Both directions from three included studies, JSON to a file
python3 -m connectors.citation_chase chase --seed-ids "10.1001/jama.2020.1585,10.1056/NEJMoa2001017,W3005423540" --direction both --out raw/citation_chase-20260904.json

# Backward only (what these studies cite), capped to 50
python3 -m connectors.citation_chase chase --seed-ids "10.1001/jama.2020.1585" --direction backward --limit 50

# Forward only (what cites this key study), human-readable table
python3 -m connectors.citation_chase chase --seed-ids "W3005423540" --direction forward --format table
```

## Output

Fixed `{meta, results}` JSON shape shared by every connector in this repo — `meta.source`
is `"citation_chase"` (not `"openalex"`, even though it queries OpenAlex under the hood),
so chased records flow into `raw/citation_chase-<date>.json` and Step 7's dedup exactly
like any other source. `meta.unresolved_seeds` lists any seed that couldn't be resolved.
`meta.total_available` for backward chasing is the true unique-reference count before any
`--limit` cap (references are fully enumerable from the seed record); for forward chasing
it's OpenAlex's own match count for the `cites:` filter. Errors go to stderr as
`{"error", "code"}` with exit code 1. No API key required; set `OPENALEX_MAILTO` for
OpenAlex's polite pool, same as the `openalex-search` skill.
