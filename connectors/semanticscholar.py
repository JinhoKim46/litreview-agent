"""Semantic Scholar connector: python3 -m connectors.semanticscholar <search|detail> [flags]

Real API confirmed live (WebSearch/WebFetch against api.semanticscholar.org's
docs, 2026-09): Academic Graph API v1, base https://api.semanticscholar.org/graph/v1

  - GET /paper/search?query=&offset=&limit=&fields=&year=
    Relevance search, offset+limit pagination. `limit` maxes at 100 per call
    and the API enforces offset+limit <= 1000 total for this endpoint (its
    deep-pagination ceiling; /paper/search/bulk with token pagination is the
    documented escape hatch past 1000, not implemented here).
    `year` accepts "YYYY", "YYYY-", "-YYYY", or "YYYY-YYYY".
  - GET /paper/{paper_id}?fields=
    Single paper by id -- genuinely supports fetch-by-id, so "detail" calls
    this directly rather than falling back to a scoped search. paper_id
    accepts a bare S2 hash/CorpusId or a prefixed external id: DOI:...,
    ARXIV:.., PMID:.., PMCID:.., MAG:.., ACL:..
  - Auth: optional `x-api-key` header (env S2_API_KEY) raises the rate limit.
    Unauthenticated traffic shares an aggressive public pool -- 429 is
    routine, not exceptional; connectors._shared.http_get_with_backoff
    already retries it with backoff+jitter before we ever see it here.
"""
import os
import sys

from connectors._shared import (
    build_arg_parser,
    http_get_with_backoff,
    resolve_query,
    utc_now_iso,
    write_error,
    write_output,
)

BASE_URL = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,title,abstract,year,venue,authors,externalIds,url"
SOURCE = "semanticscholar"
SEARCH_OFFSET_LIMIT_CEILING = 1000


def _headers():
    api_key = os.environ.get("S2_API_KEY")
    return {"x-api-key": api_key} if api_key else {}


def _to_result(paper):
    ext = paper.get("externalIds") or {}
    return {
        "id": paper.get("paperId") or "",
        "title": paper.get("title"),
        "authors": [a.get("name") for a in (paper.get("authors") or []) if a.get("name")],
        "year": paper.get("year"),
        "venue": paper.get("venue") or None,
        "doi": ext.get("DOI"),
        "abstract": paper.get("abstract"),
        "url": paper.get("url"),
        "source": SOURCE,
    }


def _request(path, params):
    """GET BASE_URL+path, mapping transport/HTTP outcomes to the contract's error codes.

    On any error this writes {"error", "code"} to stderr and exits 1 (per the
    connector contract), so callers can treat this as always returning a
    parsed JSON body (or None for a 404 the caller wants to handle specially).
    """
    try:
        resp = http_get_with_backoff(f"{BASE_URL}{path}", params=params, headers=_headers())
    except Exception as exc:  # network exhausted after retries (DNS, timeout, connection reset)
        write_error(f"could not reach Semantic Scholar: {exc}", "UPSTREAM_ERROR")
        sys.exit(1)

    if resp.status_code == 404:
        return None
    if resp.status_code == 400:
        write_error(resp.text[:500] or "invalid query", "INVALID_QUERY")
        sys.exit(1)
    if resp.status_code in (401, 403):
        write_error("Semantic Scholar rejected credentials (check S2_API_KEY)", "MISSING_CREDENTIALS")
        sys.exit(1)
    if resp.status_code == 429:
        write_error("rate limited by Semantic Scholar after retries with backoff", "RATE_LIMITED")
        sys.exit(1)
    if resp.status_code >= 400:
        write_error(f"upstream error {resp.status_code}: {resp.text[:500]}", "UPSTREAM_ERROR")
        sys.exit(1)
    return resp.json()


def _year_filter(since, until):
    since_year = since[:4] if since else ""
    until_year = until[:4] if until else ""
    if since_year and until_year:
        return f"{since_year}-{until_year}"
    if since_year:
        return f"{since_year}-"
    if until_year:
        return f"-{until_year}"
    return None


def cmd_search(args):
    try:
        query = resolve_query(args)
    except ValueError as exc:
        write_error(str(exc), "INVALID_QUERY")
        sys.exit(1)

    limit = max(1, min(args.limit, 100))
    offset = max(0, args.page) * limit
    if offset >= SEARCH_OFFSET_LIMIT_CEILING:
        # ponytail: past the API's hard offset+limit<=1000 ceiling for this endpoint;
        # report zero-new-results honestly rather than let the API 400. Upgrade path:
        # switch to /paper/search/bulk's token pagination if a review needs >1000 hits
        # from S2 for one query.
        limit = 0
    elif offset + limit > SEARCH_OFFSET_LIMIT_CEILING:
        limit = SEARCH_OFFSET_LIMIT_CEILING - offset

    params = {"query": query, "offset": offset, "limit": max(limit, 1), "fields": FIELDS}
    year = _year_filter(args.since, args.until)
    if year:
        params["year"] = year

    if limit == 0:
        papers, total = [], _request("/paper/search", {**params, "limit": 1}).get("total", 0)
    else:
        data = _request("/paper/search", params)
        papers = data.get("data") or []
        total = data.get("total", len(papers))

    retrieved = len(papers)
    output = {
        "meta": {
            "source": SOURCE,
            "query": query,
            "retrieved": retrieved,
            "total_available": total,
            "truncated": (offset + retrieved) < total,
            "fetched_at": utc_now_iso(),
        },
        "results": [_to_result(p) for p in papers],
    }
    write_output(output, args.format, args.out)


def cmd_detail(args):
    paper_id = args.id
    if paper_id.startswith("10.") and ":" not in paper_id:
        paper_id = f"DOI:{paper_id}"  # bare DOIs need the DOI: prefix S2 expects

    data = _request(f"/paper/{paper_id}", {"fields": FIELDS})
    results = [_to_result(data)] if data else []

    output = {
        "meta": {
            "source": SOURCE,
            "query": args.id,
            "retrieved": len(results),
            "total_available": len(results),
            "truncated": False,
            "fetched_at": utc_now_iso(),
        },
        "results": results,
    }
    write_output(output, args.format, args.out)


def main():
    parser = build_arg_parser(SOURCE)
    args = parser.parse_args()
    if args.command == "search":
        cmd_search(args)
    elif args.command == "detail":
        cmd_detail(args)


if __name__ == "__main__":
    main()
