"""connectors/europepmc.py -- Europe PMC REST API connector (search|detail).

Implements the fixed connector contract from connectors/_shared.py and the
plan's search_plan.json schema:
    python3 -m connectors.europepmc <search|detail> [flags]

API reference (confirmed live against the real endpoint, 2026-09-04):
    GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
        ?query=<lucene-syntax query>
        &format=json
        &resultType=core        ('core' is required for abstractText / full
                                  metadata -- 'lite' omits abstracts)
        &cursorMark=<token|*>   (cursor-based pagination; '*' = first page)
        &pageSize=<1-1000>      (upstream hard-errors above 1000)
    Response shape: {"hitCount": int, "nextCursorMark": str,
                      "resultList": {"result": [...]}}.
    Date-range filtering is expressed *inside* the query string, not as a
    separate param: FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD] (either bound may
    be '*' for an open range) -- confirmed live: a query with this clause
    returned only records within the given range.

    There is no GET-a-single-record-by-arbitrary-id endpoint in the public
    REST API (the /{SRC}/{id}/fullTextXML path only serves open-access full
    text and 404s for anything else -- it is not a metadata lookup). So
    `detail <id>` is implemented as a `search` scoped to
    `EXT_ID:<id> AND SRC:<source>`, confirmed live to return exactly the one
    matching record. Accepts a composite "<SOURCE>:<id>" (e.g.
    "MED:25883531", the same form our own `search` emits as record ids) or a
    bare id, which defaults to SRC:MED (PubMed/MEDLINE, the common case).

    Europe PMC's own per-record `source` field (MED/PMC/PPR/PAT/AGR/...)
    disambiguates records across its sub-databases -- id alone is not unique
    without it (a preprint "PPR12345" and a MEDLINE record can collide on
    bare numeric id). It is NOT the same thing as the connector contract's
    `source` field (always "europepmc", the connector name), so it is folded
    into our composite `id` instead and otherwise dropped. Europe PMC also
    exposes a full-text-availability flag (isOpenAccess/inEPMC/inPMC) on each
    record; per the task notes it is surfaced "if easy, otherwise omit" --
    omitted here to keep the {meta, results} shape identical across all six
    connectors, which is what tools/check_connector_contract.py asserts.
"""
from __future__ import annotations

import html
import re
import sys
from typing import Any

import requests

from ._shared import (
    build_arg_parser,
    http_get_with_backoff,
    resolve_query,
    utc_now_iso,
    write_error,
    write_output,
)

SOURCE = "europepmc"
BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAX_PAGE_SIZE = 1000

_TAG_RE = re.compile(r"<[^>]+>")


class EuropePmcError(Exception):
    """Maps to the connector contract's stderr {"error", "code"} shape."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _strip_html(text: str | None) -> str | None:
    """abstractText comes back with inline HTML tags (e.g. <h4>, <i>); strip them."""
    if not text:
        return None
    cleaned = html.unescape(_TAG_RE.sub("", text)).strip()
    return cleaned or None


def _apply_date_range(query: str, since: str | None, until: str | None) -> str:
    if not since and not until:
        return query
    lo = since or "*"
    hi = until or "*"
    return f"({query}) AND FIRST_PDATE:[{lo} TO {hi}]"


def _record_to_result(record: dict[str, Any]) -> dict[str, Any]:
    src = record.get("source") or "MED"
    ext_id = record.get("id") or record.get("pmid") or record.get("pmcid") or ""

    authors: list[str] = []
    for a in ((record.get("authorList") or {}).get("author")) or []:
        name = a.get("fullName")
        if name:
            authors.append(name)
    if not authors and record.get("authorString"):
        authors = [a.strip() for a in record["authorString"].split(",") if a.strip()]

    year = None
    pub_year = record.get("pubYear")
    if pub_year:
        try:
            year = int(pub_year)
        except (TypeError, ValueError):
            year = None

    journal = (record.get("journalInfo") or {}).get("journal") or {}
    venue = journal.get("title") or journal.get("medlineAbbreviation")

    url = None
    full_text_urls = ((record.get("fullTextUrlList") or {}).get("fullTextUrl")) or []
    if full_text_urls:
        url = full_text_urls[0].get("url")
    if not url and ext_id:
        url = f"https://europepmc.org/article/{src}/{ext_id}"

    return {
        "id": f"{src}:{ext_id}",
        "title": record.get("title") or None,
        "authors": authors,
        "year": year,
        "venue": venue or None,
        "doi": record.get("doi") or None,
        "abstract": _strip_html(record.get("abstractText")),
        "url": url,
        "source": SOURCE,
    }


def _fetch(query: str, *, page_size: int, cursor: str) -> dict[str, Any]:
    params = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "cursorMark": cursor,
        "pageSize": page_size,
    }
    try:
        resp = http_get_with_backoff(BASE_URL, params=params)
    except requests.RequestException as exc:
        raise EuropePmcError(f"network error calling Europe PMC: {exc}", "UPSTREAM_ERROR") from exc

    if resp.status_code == 429:
        raise EuropePmcError("rate limited by Europe PMC after retries", "RATE_LIMITED")
    if resp.status_code == 400:
        raise EuropePmcError(f"invalid query rejected by Europe PMC: {resp.text[:300]}", "INVALID_QUERY")
    if resp.status_code >= 400:
        raise EuropePmcError(f"upstream error {resp.status_code}: {resp.text[:300]}", "UPSTREAM_ERROR")
    try:
        return resp.json()
    except ValueError as exc:
        raise EuropePmcError(f"could not parse upstream JSON: {exc}", "UPSTREAM_ERROR") from exc


def _hit_count(data: dict[str, Any]) -> int:
    if "hitCount" not in data:
        raise EuropePmcError(f"unexpected upstream response: missing hitCount ({data!r})", "UPSTREAM_ERROR")
    return data["hitCount"]


def _make_meta(query: str, retrieved: int, total_available: int, truncated: bool) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "query": query,
        "retrieved": retrieved,
        "total_available": total_available,
        "truncated": truncated,
        "fetched_at": utc_now_iso(),
    }


def run_search(query: str, *, limit: int, cursor: str | None, since: str | None, until: str | None) -> dict[str, Any]:
    if not query or not query.strip():
        raise EuropePmcError("empty query", "INVALID_QUERY")
    page_size = max(1, min(limit, MAX_PAGE_SIZE))
    full_query = _apply_date_range(query, since, until)

    data = _fetch(full_query, page_size=page_size, cursor=cursor or "*")
    hit_count = _hit_count(data)
    raw_results = ((data.get("resultList") or {}).get("result")) or []
    results = [_record_to_result(r) for r in raw_results]

    meta = _make_meta(query, len(results), hit_count, len(results) < hit_count)
    return {"meta": meta, "results": results}


def run_detail(record_id: str) -> dict[str, Any]:
    if not record_id or not record_id.strip():
        raise EuropePmcError("empty id", "INVALID_QUERY")
    if ":" in record_id:
        src, ext_id = record_id.split(":", 1)
    else:
        src, ext_id = "MED", record_id
    scoped_query = f"EXT_ID:{ext_id} AND SRC:{src.upper()}"

    data = _fetch(scoped_query, page_size=1, cursor="*")
    hit_count = _hit_count(data)
    raw_results = ((data.get("resultList") or {}).get("result")) or []
    results = [_record_to_result(r) for r in raw_results[:1]]

    meta = _make_meta(scoped_query, len(results), hit_count, False)
    return {"meta": meta, "results": results}


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser(SOURCE)
    args = parser.parse_args(argv)

    try:
        if args.command == "search":
            try:
                query = resolve_query(args)
            except ValueError as exc:
                raise EuropePmcError(str(exc), "INVALID_QUERY") from exc
            # Europe PMC paginates by cursorMark, not by page number, so
            # --page (present in the shared scaffold for sources that do
            # page-number pagination) is not used here.
            payload = run_search(
                query,
                limit=args.limit,
                cursor=args.cursor,
                since=args.since,
                until=args.until,
            )
        else:
            payload = run_detail(args.id)

        try:
            write_output(payload, args.format, args.out)
        except ValueError as exc:
            raise EuropePmcError(f"internal error: output shape invalid: {exc}", "UPSTREAM_ERROR") from exc
    except EuropePmcError as exc:
        write_error(str(exc), exc.code)
        sys.exit(1)


if __name__ == "__main__":
    main()
