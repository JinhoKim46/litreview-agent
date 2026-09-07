# Semantic Scholar — API Reference

Maintainer reference for `connectors/semanticscholar.py`. If Semantic Scholar changes its API, this is the doc to check against; the mapper this doc describes is `_to_result()`.

## Endpoints

- **Search:** `GET https://api.semanticscholar.org/graph/v1/paper/search?query=...&offset=...&limit=...&fields=...&year=...`
- **Detail:** `GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=...` — accepts a bare Semantic Scholar paper ID / CorpusId, or a prefixed external ID: `DOI:`, `ARXIV:`, `PMID:`, `PMCID:`, `MAG:`, `ACL:`.

## Parameters

| Param | Meaning |
|---|---|
| `query` | free-text search |
| `offset` / `limit` | offset paging; `limit` maxes at 100 per call |
| `fields` | fixed by the connector's `FIELDS` constant: `paperId,title,abstract,year,venue,authors,externalIds,url` |
| `year` | optional year filter |

## Pagination

Offset + limit, but the endpoint enforces **`offset + limit <= 1000` total** (`SEARCH_OFFSET_LIMIT_CEILING`). The connector reports zero new results honestly once that ceiling is reached, rather than letting the API return a 400. Semantic Scholar's `/paper/search/bulk` endpoint (token-based pagination, no 1000-result ceiling) is the documented escape hatch past this limit — **not implemented** by this connector.

## Auth / rate limits

**Optional** `x-api-key` header (env `S2_API_KEY`) raises the rate limit. The unauthenticated pool is aggressive — `429 RATE_LIMITED` is routine here, not exceptional. `data.total` in the search response is the true total match count.

**Known quirk (see also USER_GUIDE.md's Troubleshooting section):** Semantic Scholar can return `401`/`403` even on a fully keyless, correctly-formed request if its unauthenticated pool momentarily rejects it. `_to_result()`'s caller maps any `401`/`403` to `MISSING_CREDENTIALS` — this does **not** always mean a bad key; it can mean "retry, and consider setting `S2_API_KEY`."

## Response structure / field mapping (`_to_result()`)

- `paper.externalIds.DOI` → `doi`
- `paper.authors[].name` → authors (Semantic Scholar does not split given/family names)
- `paper.venue` → `venue` (may be empty; Semantic Scholar's venue field is inconsistently populated upstream)

## Error mapping

`400` → `INVALID_QUERY`; `401`/`403` → `MISSING_CREDENTIALS` (see quirk above); `429` → `RATE_LIMITED`; `404` on detail → an empty result; other → `UPSTREAM_ERROR`.
