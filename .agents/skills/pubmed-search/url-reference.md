# PubMed (NCBI E-utilities) — API Reference

Maintainer reference for `connectors/pubmed.py`. If NCBI changes its E-utilities API, this is the doc to check against; the mapper this doc describes is `_parse_article()`.

## Endpoints (two-step fetch)

1. **esearch:** `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi` — resolves a query string to a list of PMIDs plus the true total match count. Does not return article content.
2. **efetch:** `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi` — fetches full XML records for a batch of PMIDs. **Response format is XML**, parsed via stdlib `xml.etree.ElementTree` — no JSON mode.

Detail (`connectors.pubmed detail <id>`) fetches one record via `efetch?id=<pmid>`; if `<id>` looks like a DOI rather than a bare PMID, it is first resolved to a PMID via `esearch?term=<doi>[AID]`.

## Parameters

| Param | Meaning |
|---|---|
| `retmax` / `retstart` | esearch paging |
| `api_key` | optional (env `NCBI_API_KEY`) — raises the rate limit from 3 req/s to 10 req/s |
| `tool` / `email` | **required by NCBI etiquette on every request** — `email` comes from `NCBI_EMAIL` or `PRISMA_CONTACT_EMAIL`, falling back to a placeholder if neither is set |

## Pagination / batching

`retmax`/`retstart` on esearch. efetch is a `GET`, so requesting content for many PMIDs at once risks an HTTP 414 (URI too long) — the connector batches efetch calls at `EFETCH_BATCH_SIZE = 200` PMIDs per call to stay well under that limit.

## Auth / rate limits

No API key required to function. `NCBI_API_KEY` (optional) raises the rate limit. `esearch`'s `Count` element is the true total match count.

## Response structure / field mapping (`_parse_article()`)

- `MedlineCitation/Article/ArticleTitle` → `title`
- `.../AuthorList/Author` → authors (`LastName`+`ForeName`/`Initials`, or `CollectiveName` for organizational authors)
- **Year resolution order** (PubMed's date fields are inconsistent across records): `Journal/JournalIssue/PubDate/Year` → `MedlineDate` (regex-extracted `\d{4}`) → `ArticleDate/Year`
- **DOI resolution order:** `ArticleTitle`'s sibling `ELocationID[@EIdType='doi']` → `PubmedData/ArticleIdList/ArticleId[@IdType='doi']`
- `abstract` joins every `Abstract/AbstractText` element, prefixing each with its `Label` attribute when present (structured abstracts, e.g. "BACKGROUND:", "METHODS:")

## Error mapping

`429` → `RATE_LIMITED`; `400` → `INVALID_QUERY`; an XML response with an `ErrorList` and no `Count` → `INVALID_QUERY`; other non-200 → `UPSTREAM_ERROR`.
