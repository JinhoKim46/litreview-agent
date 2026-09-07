# OpenAlex — API Reference

Maintainer reference for `connectors/openalex.py`. If OpenAlex changes its API, this is the doc to check against; the mapper this doc describes is `work_to_result()`.

## Endpoints

- **Search:** `GET https://api.openalex.org/works?filter=...` or `?search=...`
- **Detail:** `GET https://api.openalex.org/works/<id>` — a real, single-record endpoint.

## Query dispatch

`--query` is routed by the connector, not the API: a value containing `:` is sent as `filter=` (OpenAlex's native field-selector syntax, e.g. `title_and_abstract.search:cancer,type:article` — what `search_plan.json` stores per-source); a bare keyword phrase with no `:` is sent as OpenAlex's relevance-ranked `search=` param instead.

## Parameters

| Param | Meaning |
|---|---|
| `filter` / `search` | see Query dispatch above |
| `per-page` | page size, max 200 |
| `cursor` | `cursor=*` for the first page, then the response's `meta.next_cursor` |
| `page` | basic offset paging, capped at 10,000 results total by the API itself — the connector switches to cursor paging automatically past that cap |
| `mailto` | optional contact email (env `OPENALEX_MAILTO`, falls back to `PRISMA_CONTACT_EMAIL`) for OpenAlex's "polite pool": a higher, steadier rate limit, no signup |

## Pagination

Cursor-based is the primary mechanism (`cursor=*` → follow `meta.next_cursor` until it's `null`). Basic `page=` paging works but is hard-capped by OpenAlex at 10,000 total results — the connector never relies on it beyond that cap.

## Auth / rate limits

No API key. `mailto=` (see above) is the only rate-limit lever. `meta.count` in every response is OpenAlex's true total match count — never understated by `--limit`.

## Response structure / field mapping (`work_to_result()`)

- `work.primary_location.source.display_name` → `venue`
- `work.open_access.is_oa` / `.oa_url` → bonus open-access fields
- `abstract` is **not** returned as plain text — OpenAlex ships `abstract_inverted_index` (a position-indexed term map); `work_to_result()` calls `reconstruct_abstract()` to rebuild readable text from it. If OpenAlex ever changes this shape, `reconstruct_abstract()` is the function to check first.
- `id` accepts a raw OpenAlex ID (`Wxxxxxxxxx`) or a prefixed external ID: `doi:`, `pmid:`, `pmcid:`, `mag:`.

## Error mapping

`429` → `RATE_LIMITED`; `400`/`404`/`422` → `INVALID_QUERY`; any other 4xx/5xx → `UPSTREAM_ERROR`.
