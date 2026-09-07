# Crossref — API Reference

Maintainer reference for `connectors/crossref.py`. If Crossref changes its API, this is the doc to check against; the mapper this doc describes is `item_to_result()`.

## Endpoints

- **Search:** `GET https://api.crossref.org/works?query.bibliographic=...`
- **Detail:** `GET https://api.crossref.org/works/<doi>` — a real, single-record endpoint (Crossref's own primary key is the DOI).

## Parameters

| Param | Meaning |
|---|---|
| `query.bibliographic` | free-text bibliographic query |
| `rows` | page size, default 20, max 1000 (`MAX_ROWS`) |
| `offset` | offset paging, capped at 10,000 (`MAX_OFFSET`) |
| `cursor` | `cursor=*` for the first page, then the response's `message.next-cursor` |
| `filter` | **date bounds are a single comma-joined value**, e.g. `filter=from-pub-date:2020-01-01,until-pub-date:2024-12-31` — two separate `filter` params does *not* work; this is a documented Crossref footgun, not a connector bug |
| `mailto` | optional contact email (env `PRISMA_CONTACT_EMAIL`) for Crossref's polite pool |

## Pagination

`rows` + either `offset` (≤10,000) or `cursor` (unbounded, follow `message.next-cursor`).

## Auth / rate limits

No API key. `mailto=` is the only rate-limit lever. `message.total-results` is the true total match count.

## Response structure / field mapping (`item_to_result()`)

- `item.title[0]` → `title`
- `item.container-title[0]` → `venue`
- `item.author[].given`/`.family` → authors (falls back to `.name` for organizational authors with no given/family split)
- `abstract` ships as **JATS XML**, not plain text — `item_to_result()` calls `strip_jats_abstract()` (regex `<[^>]+>` strip + `html.unescape`) to produce readable text. If Crossref changes its abstract markup, this is the function to check first.
- `item.is-referenced-by-count` → bonus `cited_by_count` field

## Error mapping

`429` → `RATE_LIMITED`; `404` on detail → an empty result (not an error); `400`/`422` → `INVALID_QUERY`; other 4xx/5xx → `UPSTREAM_ERROR`.
