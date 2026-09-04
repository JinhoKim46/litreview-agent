"""OpenAlex connector: `python3 -m connectors.openalex <search|detail> [flags]`.

OpenAlex (https://api.openalex.org) is a free, keyless, multi-disciplinary
scholarly index (~250M works). Verified against current docs (Sep 2026):
  - List works:   GET https://api.openalex.org/works?filter=...&search=...
  - Single work:  GET https://api.openalex.org/works/<id>
                  <id> is an OpenAlex ID (e.g. W2741809807) or a prefixed
                  external id: doi:10.xxx, pmid:123, pmcid:PMCxxx, mag:123.
  - No API key. A `mailto=` param opts into the "polite pool" (higher rate
    limit, more reliable service) — see get_mailto() below.
  - Cursor pagination: cursor=* on the first request, then meta.next_cursor
    on each subsequent one; per_page max is 200. Basic page= paging is
    capped at 10,000 results total, so cursor is used here for any --limit
    above one page.
  - meta.count in the list response is the true total match count — used
    directly as this connector's total_available.

--query is passed straight through as OpenAlex's `filter` parameter when it
looks like native filter syntax (contains a ':' field selector, e.g.
"title_and_abstract.search:cancer,type:article" — the syntax search_plan.json
stores per the plan's per-source-native-syntax rule); a bare keyword phrase
with no ':' is sent as OpenAlex's `search=` parameter instead, so an
operator typing `--query "cancer immunotherapy"` by hand doesn't just get a
400 back.

`detail <id>` really does fetch a single record via GET /works/<id> (OpenAlex
supports this directly, unlike sources that only offer search) — accepts a
raw OpenAlex ID or a bare/prefixed DOI/PMID/PMCID/MAG id.

This module depends on connectors/_shared.py only through the five helpers
the connector contract promises every variant of that file will keep:
build_arg_parser, build_user_agent, http_get_with_backoff, write_error (via
write_output's validation) and write_output/validate_output_shape. It is
imported as a module (`from connectors import _shared`), not by name, so an
unrelated rename in a sibling helper there can't crash this file at import
time — only a call to that specific missing helper would, and none of the
sometimes-renamed conveniences (emit_output/make_meta/fail) are used here.
"""

import os
import sys

import requests

from connectors import _shared

SOURCE_KEY = "openalex"
BASE_URL = "https://api.openalex.org/works"
MAX_PER_PAGE = 200


def get_mailto():
    """Contact email for OpenAlex's polite pool. Set OPENALEX_MAILTO to a
    real address for higher, more reliable rate limits; OpenAlex works
    keylessly without it, just with the default (lower) rate limit. An
    absent/empty value is left out of the request entirely rather than
    filled with a fake address -- sending a made-up email is worse polite-
    pool etiquette than sending none, and the User-Agent still names the
    tool either way."""
    return os.environ.get("OPENALEX_MAILTO", "").strip() or None


def _user_agent():
    """Build the shared User-Agent, tolerant of the two call conventions
    seen across in-flight edits to _shared.py: build_user_agent(contact) and
    build_user_agent(source_key, contact)."""
    mailto = get_mailto()
    try:
        return _shared.build_user_agent(SOURCE_KEY, mailto)
    except TypeError:
        return _shared.build_user_agent(mailto)


def _fail(message, code):
    _shared.write_error(message, code)
    sys.exit(1)


def _emit(payload, fmt, out_path):
    _shared.write_output(payload, fmt, out_path)


def _meta(query, retrieved, total_available, truncated):
    return {
        "source": SOURCE_KEY,
        "query": query,
        "retrieved": retrieved,
        "total_available": total_available,
        "truncated": truncated,
        "fetched_at": _shared.utc_now_iso(),
    }


def _normalize_doi(doi_url):
    if not doi_url:
        return None
    return doi_url.removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def reconstruct_abstract(inverted_index):
    """OpenAlex stores abstracts as {term: [positions]}; rebuild the text."""
    if not inverted_index:
        return None
    positions = []
    for term, idxs in inverted_index.items():
        for idx in idxs:
            positions.append((idx, term))
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return " ".join(term for _, term in positions)


def work_to_result(work):
    primary = work.get("primary_location") or {}
    source_obj = primary.get("source") or {}
    oa = work.get("open_access") or {}
    authors = [
        a["author"]["display_name"]
        for a in (work.get("authorships") or [])
        if a.get("author") and a["author"].get("display_name")
    ]
    url = oa.get("oa_url") or primary.get("landing_page_url") or work.get("doi") or work.get("id")

    return {
        "id": work.get("id"),
        "title": work.get("title") or work.get("display_name"),
        "authors": authors,
        "year": work.get("publication_year"),
        "venue": source_obj.get("display_name"),
        "doi": _normalize_doi(work.get("doi")),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "url": url,
        "source": SOURCE_KEY,
        # Bonus fields (allowed on top of the fixed shape) noted in the plan:
        # OpenAlex "has citation counts and an is_oa flag".
        "cited_by_count": work.get("cited_by_count"),
        "is_oa": oa.get("is_oa"),
    }


def _request(params, headers):
    try:
        resp = _shared.http_get_with_backoff(BASE_URL, params=params, headers=headers)
    except requests.RequestException as exc:  # network-level failure after retries exhausted
        _fail(f"OpenAlex request failed: {exc}", "UPSTREAM_ERROR")

    if resp.status_code == 429:
        _fail("OpenAlex rate limit exceeded (retries exhausted)", "RATE_LIMITED")
    if resp.status_code in (400, 404, 422):
        _fail(f"OpenAlex rejected the query (HTTP {resp.status_code}): {resp.text[:300]}", "INVALID_QUERY")
    if resp.status_code >= 400:
        _fail(f"OpenAlex upstream error (HTTP {resp.status_code}): {resp.text[:300]}", "UPSTREAM_ERROR")
    try:
        return resp.json()
    except ValueError as exc:
        _fail(f"OpenAlex returned non-JSON response: {exc}", "UPSTREAM_ERROR")


def _build_query_params(query, since, until):
    """Split a resolved query string into OpenAlex's filter=/search= params.

    A query containing ':' is treated as native filter syntax (the form
    search_plan.json stores, e.g. "title_and_abstract.search:x,type:article")
    and goes straight into `filter=`. A bare keyword phrase with no ':' goes
    into `search=` (OpenAlex's full-text relevance search) instead, since
    passing it as `filter=` would 400.
    """
    params = {}
    filter_clauses = []
    if query:
        if ":" in query:
            filter_clauses.append(query)
        else:
            params["search"] = query
    if since:
        filter_clauses.append(f"from_publication_date:{since}")
    if until:
        filter_clauses.append(f"to_publication_date:{until}")
    if filter_clauses:
        params["filter"] = ",".join(filter_clauses)
    return params


def cmd_search(args):
    try:
        query = _shared.resolve_query(args)
    except ValueError as exc:
        _fail(str(exc), "INVALID_QUERY")

    base_params = _build_query_params(query, args.since, args.until)
    mailto = get_mailto()
    if mailto:
        base_params["mailto"] = mailto
    headers = {"User-Agent": _user_agent()}
    limit = args.limit if args.limit and args.limit > 0 else 25

    collected = []
    total_available = None

    # build_arg_parser's --page default is 0 (meaning "not requested"); only
    # a positive --page opts into OpenAlex's basic offset paging (capped at
    # 10,000 results). Otherwise use OpenAlex's native cursor pagination,
    # looping until --limit is met or the result set is exhausted.
    if getattr(args, "page", 0) and not args.cursor:
        params = dict(base_params, per_page=min(limit, MAX_PER_PAGE), page=args.page)
        data = _request(params, headers)
        total_available = data["meta"]["count"]
        collected = [work_to_result(w) for w in data["results"]][:limit]
    else:
        cursor = args.cursor or "*"
        while len(collected) < limit:
            page_size = min(MAX_PER_PAGE, limit - len(collected))
            params = dict(base_params, per_page=page_size, cursor=cursor)
            data = _request(params, headers)
            if total_available is None:
                total_available = data["meta"]["count"]
            batch = data.get("results") or []
            collected.extend(work_to_result(w) for w in batch)
            cursor = data["meta"].get("next_cursor")
            if not cursor or not batch:
                break
        collected = collected[:limit]  # defensive: never exceed --limit even if a page overshoots per_page

    retrieved = len(collected)
    truncated = total_available is not None and retrieved < total_available
    payload = {"meta": _meta(query, retrieved, total_available, truncated), "results": collected}
    _emit(payload, args.format, args.out)


def _to_path_id(raw_id):
    """OpenAlex accepts a raw OpenAlex ID (Wxxxx) or a urn:id / bare-DOI form
    in the /works/<id> path. Normalize common bare forms to the urn prefix
    OpenAlex documents (doi:, pmid:, pmcid:, mag:)."""
    if raw_id.startswith(("doi:", "pmid:", "pmcid:", "mag:", "http://", "https://", "W")):
        return raw_id
    if raw_id.startswith("10."):
        return f"doi:{raw_id}"
    return raw_id


def fetch_work_by_id(raw_id):
    """Fetch a single OpenAlex work by raw/prefixed id (see `_to_path_id`).

    Returns the parsed work dict, or `None` if OpenAlex has no such work
    (404) -- callers that need contract error codes for other 4xx/5xx cases
    get them via `_fail` here, same as `cmd_detail` always did. Factored out
    of `cmd_detail` so `connectors/citation_chase.py` can resolve a seed
    DOI/id to a work (to then read its `referenced_works`) without a second,
    drifting copy of this status-code handling.
    """
    headers = {"User-Agent": _user_agent()}
    params = {}
    mailto = get_mailto()
    if mailto:
        params["mailto"] = mailto

    url = f"{BASE_URL}/{_to_path_id(raw_id)}"
    try:
        resp = _shared.http_get_with_backoff(url, params=params, headers=headers)
    except requests.RequestException as exc:
        _fail(f"OpenAlex request failed: {exc}", "UPSTREAM_ERROR")

    if resp.status_code == 429:
        _fail("OpenAlex rate limit exceeded (retries exhausted)", "RATE_LIMITED")
    if resp.status_code == 404:
        return None
    if resp.status_code in (400, 422):
        _fail(f"OpenAlex rejected id {raw_id!r} (HTTP {resp.status_code}): {resp.text[:300]}", "INVALID_QUERY")
    if resp.status_code >= 400:
        _fail(f"OpenAlex upstream error (HTTP {resp.status_code}): {resp.text[:300]}", "UPSTREAM_ERROR")
    try:
        return resp.json()
    except ValueError as exc:
        _fail(f"OpenAlex returned non-JSON response: {exc}", "UPSTREAM_ERROR")
        return None  # unreachable, _fail exits; keeps linters happy


def cmd_detail(args):
    work = fetch_work_by_id(args.id)
    if work is None:
        results, retrieved, total = [], 0, 0
    else:
        results, retrieved, total = [work_to_result(work)], 1, 1

    payload = {"meta": _meta(args.id, retrieved, total, False), "results": results}
    _emit(payload, args.format, args.out)


def main(argv=None):
    parser = _shared.build_arg_parser(SOURCE_KEY)
    args = parser.parse_args(argv)
    if args.command == "search":
        cmd_search(args)
    elif args.command == "detail":
        cmd_detail(args)
    else:
        parser.error(f"unknown command {args.command!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
