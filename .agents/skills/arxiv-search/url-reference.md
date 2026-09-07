# arXiv — API Reference

Maintainer reference for `connectors/arxiv.py`. If arXiv changes its API, this is the doc to check against; the mapper this doc describes is `_parse_entry()`.

## Endpoint

`GET http://export.arxiv.org/api/query?search_query=...&id_list=...&start=...&max_results=...&sortBy=...&sortOrder=...`

Response is an **Atom 1.0 XML feed**, not JSON.

## Parameters

| Param | Meaning |
|---|---|
| `search_query` | free-text / field-prefixed search |
| `id_list` | one or more arXiv ids (comma-separated) — used by `detail`; supports versioned ids like `2401.01234v2` |
| `start` | 0-based offset |
| `max_results` | ≤2000 per call (`ARXIV_MAX_RESULTS`) |
| `sortBy` / `sortOrder` | relevance/date sort |

## Pagination

`start` + `max_results`, with a hard ceiling of `start + max_results <= 30000` (`ARXIV_RESULT_WINDOW`) — the connector clamps `limit` down rather than erroring when a request would exceed that window.

## Auth / rate limits

No API key. arXiv's own usage guidance asks for a **3-second delay between calls**; the connector enforces this via `_COURTESY_DELAY_SECONDS`, implemented as a best-effort file-based cross-process throttle at a fixed temp path — not concurrency-safe against truly parallel processes (a file-mtime check, not a lock); `fcntl.flock` is the upgrade path if concurrent connector invocations across processes ever becomes a real scenario.

## Known quirk: malformed queries return HTTP 200

A malformed or out-of-range query does **not** return an HTTP error status — arXiv returns a normal `200` Atom feed containing exactly one `<entry>` whose `<id>` is under `.../api/errors`. The connector detects this via `_check_error_feed()`, which inspects the parsed feed rather than the HTTP status. Any future change to arXiv's error-signaling shape should be checked against this function first.

## Response structure / field mapping (`_parse_entry()`)

- `id` is extracted from the entry's `<id>` URL's `/abs/<id>` suffix
- `<author><name>` → authors (arXiv does not split given/family names)
- `year` is the first 4 characters of `<published>`
- `doi` comes from the `arxiv:doi` Atom namespace extension (present only once a preprint is later assigned a DOI by a journal)
- **`venue` is hardcoded to `"arXiv preprint"`** for every record — arXiv is preprints only, never itself peer-reviewed. This matters downstream: an arXiv preprint and its later peer-reviewed version typically merge during dedup via title+author+year (the preprint usually has no DOI yet), and the fixed venue string is a deliberate, honest signal for RoB/GRADE bookkeeping, not a placeholder to "fix."

## Total count

`opensearch:totalResults` at the feed level.

## Error mapping

`429` → `RATE_LIMITED`; `>=500` → `UPSTREAM_ERROR`; other 4xx → `UPSTREAM_ERROR`; a malformed-query 200-feed (see quirk above) → `INVALID_QUERY`.
