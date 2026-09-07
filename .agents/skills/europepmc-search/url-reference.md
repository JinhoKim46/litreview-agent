# Europe PMC — API Reference

Maintainer reference for `connectors/europepmc.py`. If Europe PMC changes its API, this is the doc to check against; the mapper this doc describes is `_record_to_result()`.

## Endpoint

`GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=...&format=json&resultType=core&cursorMark=...&pageSize=...`

**`resultType=core` is required.** The API's default, `resultType=lite`, omits abstract text entirely — a connector that forgets this param silently ships records with no abstracts.

## Parameters

| Param | Meaning |
|---|---|
| `query` | free-text search. **Date bounds go inside the query string itself**, not a separate param: `FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD]` (either bound may be `*`) |
| `format` | fixed to `json` |
| `resultType` | fixed to `core` (see above) |
| `cursorMark` | `cursorMark=*` for the first page, then the response's `nextCursorMark` |
| `pageSize` | 1–1000 (`MAX_PAGE_SIZE`); the API hard-errors above 1000 |

## Pagination

**Cursor-based only** (`cursorMark`). There is no offset-paging mode for this source — `--page` is accepted by the connector's shared CLI shape but explicitly unused here (documented in code).

## Auth / rate limits

No API key required.

## No standalone detail endpoint

Europe PMC's public REST API has no real single-record-by-id endpoint (the `/{SRC}/{id}/fullTextXML` path only serves open-access full text and 404s otherwise). `connectors.europepmc detail <id>` is implemented as a **scoped search** — `EXT_ID:<id> AND SRC:<source>` — confirmed to return exactly one match for a valid id. This is a real API limitation, not a connector shortcut to fix later.

## Response structure / field mapping (`_record_to_result()`)

- Europe PMC spans multiple sub-databases (MEDLINE, PMC, preprints, patents, agricultural literature); its own `source` field (`MED`/`PMC`/`PPR`/`PAT`/`AGR`/...) disambiguates across them. This connector folds that into its own `id` as `"<SRC>:<ext_id>"` (e.g. `MED:25883531`) — distinct from the connector-contract's own top-level `source` field, which is always the fixed string `"europepmc"`.
- `authorList.author[].fullName` → authors (falls back to splitting `authorString` on commas if `authorList` is absent)
- `journalInfo.journal.title` / `.medlineAbbreviation` → `venue`
- `abstractText` → `abstract`, HTML-tag-stripped (regex + `html.unescape`) — Europe PMC abstracts commonly carry inline tags like `<h4>`/`<i>`.

## Error mapping

`429` → `RATE_LIMITED`; `400` → `INVALID_QUERY`; other 4xx/5xx → `UPSTREAM_ERROR`.
