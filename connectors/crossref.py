"""Crossref connector: `python3 -m connectors.crossref <search|detail> [flags]`.

Crossref (https://api.crossref.org) is the DOI registration agency's free,
keyless metadata index (~160M works, strongest on DOIs/bibliographic
metadata; many records — especially older ones — lack an abstract).
Verified against the current REST API docs (github.com/CrossRef/rest-api-doc,
Sep 2026):
  - List works:   GET https://api.crossref.org/works?query.bibliographic=...
  - Single work:  GET https://api.crossref.org/works/<doi>
                  Crossref genuinely supports single-DOI lookup, so `detail`
                  fetches it directly — no search-fallback needed here.
  - No API key. A `mailto=` request param (on top of the honest User-Agent
    _shared.py already builds from PRISMA_CONTACT_EMAIL) opts into the
    "polite pool" — a higher, steadier rate limit.
  - Pagination: `rows` (default 20, max 1000) + either `offset` (Crossref
    caps offset-based paging at 10,000 total results) or `cursor` (start
    with cursor=*, then reuse message.next-cursor for deep pagination).
    This connector uses --cursor when given, else plain offset paging via
    --page (one `rows`-sized page per invocation, matching --page's shared
    "0-based page number" contract).
  - message.total-results is the true total match count, used directly as
    this connector's total_available — never understated even when --limit
    caps what's actually retrieved.
  - Date filters are a single comma-joined `filter` param, e.g.
    "from-pub-date:2020-01-01,until-pub-date:2023-12-31" — NOT two separate
    filter params (a documented gotcha).

--query is passed to Crossref's `query.bibliographic` param (titles, authors,
ISSNs, publication years — the field Crossref recommends for literature
search relevance) rather than the bare `query` param, which is a weaker
full-text-everywhere match. This is the "native syntax" for this source per
the plan's per-database search_plan.json convention.
"""

import html
import os
import re
import sys

from connectors._shared import (
    build_arg_parser,
    build_user_agent,
    http_get_with_backoff,
    resolve_query,
    utc_now_iso,
    write_error,
    write_output,
)

SOURCE_KEY = "crossref"
BASE_URL = "https://api.crossref.org/works"
MAX_ROWS = 1000
MAX_OFFSET = 10000

_JATS_TAG_RE = re.compile(r"<[^>]+>")


def _fail(message, code):
    write_error(message, code)
    sys.exit(1)


def _normalize_doi(raw):
    if not raw:
        return None
    return raw.removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def strip_jats_abstract(raw_abstract):
    """Crossref abstracts are JATS XML fragments (e.g. '<jats:p>...</jats:p>',
    sometimes with a leading '<jats:title>Abstract</jats:title>'). Strip tags
    and unescape entities; an empty result means no real abstract text, so
    return None rather than fabricating an empty string."""
    if not raw_abstract:
        return None
    text = html.unescape(_JATS_TAG_RE.sub(" ", raw_abstract))
    text = " ".join(text.split())
    return text or None


def _extract_year(item):
    for key in ("published", "issued", "published-print", "published-online"):
        date_parts = (item.get(key) or {}).get("date-parts")
        if date_parts and date_parts[0] and date_parts[0][0]:
            return date_parts[0][0]
    return None


def _extract_authors(item):
    authors = []
    for a in item.get("author") or []:
        given, family = a.get("given"), a.get("family")
        if given or family:
            name = " ".join(p for p in (given, family) if p)
        else:
            name = a.get("name")  # organizational author, e.g. "World Trade Organization"
        if name:
            authors.append(name)
    return authors


def item_to_result(item):
    titles = item.get("title") or []
    container_titles = item.get("container-title") or []
    doi = item.get("DOI")
    return {
        "id": doi or item.get("URL"),
        "title": titles[0] if titles else None,
        "authors": _extract_authors(item),
        "year": _extract_year(item),
        "venue": container_titles[0] if container_titles else None,
        "doi": doi,
        "abstract": strip_jats_abstract(item.get("abstract")),
        "url": item.get("URL"),
        "source": SOURCE_KEY,
        # Bonus field (allowed on top of the fixed shape): citation count.
        "cited_by_count": item.get("is-referenced-by-count"),
    }


def _build_meta(query, retrieved, total_available, truncated):
    return {
        "source": SOURCE_KEY,
        "query": query,
        "retrieved": retrieved,
        "total_available": total_available,
        "truncated": truncated,
        "fetched_at": utc_now_iso(),
    }


def _request(params, headers, url=BASE_URL):
    try:
        resp = http_get_with_backoff(url, params=params, headers=headers)
    except Exception as exc:  # network-level failure after retries exhausted
        _fail(f"Crossref request failed: {exc}", "UPSTREAM_ERROR")

    if resp.status_code == 429:
        _fail("Crossref rate limit exceeded (retries exhausted)", "RATE_LIMITED")
    if resp.status_code == 404:
        return None
    if resp.status_code in (400, 422):
        _fail(f"Crossref rejected the query (HTTP {resp.status_code}): {resp.text[:300]}", "INVALID_QUERY")
    if resp.status_code >= 400:
        _fail(f"Crossref upstream error (HTTP {resp.status_code}): {resp.text[:300]}", "UPSTREAM_ERROR")
    try:
        return resp.json()
    except ValueError as exc:
        _fail(f"Crossref returned non-JSON response: {exc}", "UPSTREAM_ERROR")


def _build_filter(since, until):
    clauses = []
    if since:
        clauses.append(f"from-pub-date:{since}")
    if until:
        clauses.append(f"until-pub-date:{until}")
    return ",".join(clauses) if clauses else None


def cmd_search(args):
    try:
        query = resolve_query(args)
    except ValueError as exc:
        _fail(str(exc), "INVALID_QUERY")

    headers = {"User-Agent": build_user_agent(os.environ.get("PRISMA_CONTACT_EMAIL"))}
    limit = max(args.limit, 0)

    base_params = {"query.bibliographic": query}
    filter_str = _build_filter(args.since, args.until)
    if filter_str:
        base_params["filter"] = filter_str
    contact_email = os.environ.get("PRISMA_CONTACT_EMAIL", "").strip()
    if contact_email:
        base_params["mailto"] = contact_email

    collected = []
    total_available = None

    if args.cursor:
        cursor = args.cursor
        while len(collected) < limit or limit == 0:
            rows = min(MAX_ROWS, limit - len(collected)) if limit else MAX_ROWS
            if rows <= 0:
                break
            params = dict(base_params, rows=rows, cursor=cursor)
            data = _request(params, headers)
            message = data["message"]
            if total_available is None:
                total_available = message["total-results"]
            batch = message.get("items") or []
            collected.extend(item_to_result(it) for it in batch)
            cursor = message.get("next-cursor")
            if not cursor or not batch or limit == 0:
                break
    else:
        offset = (args.page or 0) * limit
        if offset > MAX_OFFSET:
            _fail(
                f"offset {offset} exceeds Crossref's {MAX_OFFSET}-result offset-paging limit; use --cursor instead",
                "INVALID_QUERY",
            )
        params = dict(base_params, rows=min(limit, MAX_ROWS) or 20, offset=offset)
        data = _request(params, headers)
        message = data["message"]
        total_available = message["total-results"]
        collected = [item_to_result(it) for it in message["items"]][:limit] if limit else []

    retrieved = len(collected)
    truncated = total_available is not None and retrieved < total_available
    payload = {
        "meta": _build_meta(query, retrieved, total_available, truncated),
        "results": collected,
    }
    write_output(payload, args.format, args.out)


def cmd_detail(args):
    headers = {"User-Agent": build_user_agent(os.environ.get("PRISMA_CONTACT_EMAIL"))}
    params = {}
    contact_email = os.environ.get("PRISMA_CONTACT_EMAIL", "").strip()
    if contact_email:
        params["mailto"] = contact_email

    doi = _normalize_doi(args.id)
    url = f"{BASE_URL}/{doi}"
    data = _request(params, headers, url=url)

    if data is None:  # 404: no such DOI in Crossref
        results, retrieved, total = [], 0, 0
    else:
        results = [item_to_result(data["message"])]
        retrieved, total = 1, 1

    payload = {
        "meta": _build_meta(args.id, retrieved, total, False),
        "results": results,
    }
    write_output(payload, args.format, args.out)


def main(argv=None):
    parser = build_arg_parser(SOURCE_KEY)
    args = parser.parse_args(argv)
    if args.command == "search":
        cmd_search(args)
    elif args.command == "detail":
        cmd_detail(args)
    else:
        parser.error(f"unknown command {args.command!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
