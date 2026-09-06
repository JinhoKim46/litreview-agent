"""arXiv connector: python3 -m connectors.arxiv <search|detail> [flags]

Source: the arXiv API (Atom 1.0 XML), base endpoint
http://export.arxiv.org/api/query. Confirmed against arXiv's own API user
manual (info.arxiv.org/help/api/user-manual.html) at implementation time:

  - search_query / id_list, start (0-based offset), max_results
    (<=2000 per call, <=30000 total result window), sortBy/sortOrder.
  - Response is an Atom feed with opensearch:totalResults/startIndex/
    itemsPerPage at the feed level, and per-entry <id>, <title>, <summary>,
    <published>, <author><name>, plus the arxiv: namespace extensions
    (arxiv:doi, arxiv:journal_ref, arxiv:comment, arxiv:primary_category).
  - A malformed/out-of-range query comes back as a normal HTTP 200 Atom feed
    containing exactly one <entry> whose <id> is under .../api/errors --
    there is no HTTP error status for this case, so it must be detected by
    inspecting the parsed feed (see _check_error_feed).
  - The docs ask implementers to "incorporate a 3 second delay" between
    successive calls; see _respect_courtesy_rate.

PREPRINTS ONLY: every record's venue is hardcoded to "arXiv preprint" --
none of these have undergone peer review, which matters downstream for
dedup (an arXiv preprint and its later peer-reviewed version merge via
title+author+year, since the preprint usually lacks a DOI) and for
risk-of-bias/GRADE bookkeeping.

"detail <id>": arXiv's id_list parameter supports fetching a single record
directly (e.g. id_list=2401.01234, or a versioned id like 2401.01234v2), so
detail is a real one-record fetch -- no scoped-search workaround is needed.
"""
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from connectors import _shared

SOURCE = "arxiv"
BASE_URL = "http://export.arxiv.org/api/query"

ATOM_NS = "{http://www.w3.org/2005/Atom}"
OPENSEARCH_NS = "{http://a9.com/-/spec/opensearch/1.1/}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

ARXIV_MAX_RESULTS = 2000       # API ceiling per call
ARXIV_RESULT_WINDOW = 30000    # API ceiling on start + max_results

_COURTESY_DELAY_SECONDS = 3.0
# ponytail: best-effort file-based cross-process throttle (one arXiv request
# per CLI invocation is typical; /litreview-search's rerun_search.sh is what
# actually chains many). Not concurrency-safe against parallel processes
# racing the same file -- upgrade to fcntl.flock if that ever matters.
_RATE_LIMIT_STATE_FILE = os.path.join(tempfile.gettempdir(), "litreview_agent_arxiv_last_request")


class ArxivError(Exception):
    """Coded error mapped to the connector contract's stderr {"error","code"} shape."""

    def __init__(self, message, code):
        super().__init__(message)
        self.message = message
        self.code = code


def _respect_courtesy_rate():
    try:
        with open(_RATE_LIMIT_STATE_FILE, encoding="utf-8") as fh:
            last = float(fh.read().strip())
    except (OSError, ValueError):
        last = 0.0
    elapsed = time.time() - last
    if elapsed < _COURTESY_DELAY_SECONDS:
        time.sleep(_COURTESY_DELAY_SECONDS - elapsed)
    try:
        with open(_RATE_LIMIT_STATE_FILE, "w", encoding="utf-8") as fh:
            fh.write(repr(time.time()))
    except OSError:
        pass  # best-effort only; must never break the search itself


def _parse_entry(entry):
    id_url = (entry.findtext(f"{ATOM_NS}id") or "").strip()
    arxiv_id = id_url.rsplit("/abs/", 1)[-1] if "/abs/" in id_url else id_url

    title = " ".join((entry.findtext(f"{ATOM_NS}title") or "").split()) or None
    summary = " ".join((entry.findtext(f"{ATOM_NS}summary") or "").split()) or None

    published = entry.findtext(f"{ATOM_NS}published") or ""
    year = int(published[:4]) if published[:4].isdigit() else None

    authors = [
        (author.findtext(f"{ATOM_NS}name") or "").strip()
        for author in entry.findall(f"{ATOM_NS}author")
    ]
    authors = [a for a in authors if a]

    doi_raw = entry.findtext(f"{ARXIV_NS}doi")
    doi = doi_raw.strip() if doi_raw else None

    return {
        "id": arxiv_id or None,
        "title": title,
        "authors": authors,
        "year": year,
        "venue": "arXiv preprint",
        "doi": doi,
        "abstract": summary,
        "url": id_url or None,
        "source": SOURCE,
    }


def _check_error_feed(root):
    """arXiv reports a bad query as a 200 Atom feed with one <entry> under
    .../api/errors instead of an HTTP error status -- detect that shape."""
    entries = root.findall(f"{ATOM_NS}entry")
    if len(entries) != 1:
        return
    entry_id = entries[0].findtext(f"{ATOM_NS}id") or ""
    if "api/errors" in entry_id:
        summary = (entries[0].findtext(f"{ATOM_NS}summary") or "arXiv API rejected the query").strip()
        raise ArxivError(summary, "INVALID_QUERY")


def _date_bound(date_str, end_of_day):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ArxivError(f"invalid date {date_str!r}, expected YYYY-MM-DD", "INVALID_QUERY") from exc
    return dt.strftime("%Y%m%d") + ("2359" if end_of_day else "0000")


def _apply_date_filter(query, since, until):
    if not since and not until:
        return query
    start = _date_bound(since, False) if since else "199101010000"
    end = _date_bound(until, True) if until else datetime.now(timezone.utc).strftime("%Y%m%d") + "2359"
    clause = f"submittedDate:[{start} TO {end}]"
    return f"({query}) AND {clause}" if query else clause


def _build_meta(query, retrieved, total_available, truncated):
    return {
        "source": SOURCE,
        "query": query,
        "retrieved": retrieved,
        "total_available": total_available,
        "truncated": truncated,
        "fetched_at": _shared.utc_now_iso(),
    }


def _fetch(params):
    _respect_courtesy_rate()
    try:
        resp = _shared.http_get_with_backoff(BASE_URL, params=params)
    except requests.RequestException as exc:
        raise ArxivError(f"network error calling arXiv: {exc}", "UPSTREAM_ERROR") from exc

    if resp.status_code == 429:
        raise ArxivError("rate limited by arXiv after retries", "RATE_LIMITED")
    if resp.status_code >= 500:
        raise ArxivError(f"arXiv server error {resp.status_code}", "UPSTREAM_ERROR")
    if resp.status_code >= 400:
        raise ArxivError(f"arXiv returned {resp.status_code}: {resp.text[:300]}", "UPSTREAM_ERROR")

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise ArxivError(f"could not parse arXiv XML response: {exc}", "UPSTREAM_ERROR") from exc

    _check_error_feed(root)
    return root


def _resolve_start(args, limit):
    if args.cursor is not None:
        try:
            return int(args.cursor)
        except ValueError:
            raise ArxivError("--cursor must be an integer start offset for arXiv", "INVALID_QUERY")
    return max(0, args.page or 0) * limit


def search(args):
    try:
        query = _shared.resolve_query(args)
    except ValueError as exc:
        raise ArxivError(str(exc), "INVALID_QUERY") from exc

    if args.limit <= 0:
        raise ArxivError("--limit must be a positive integer", "INVALID_QUERY")
    limit = min(args.limit, ARXIV_MAX_RESULTS)
    start = _resolve_start(args, limit)
    if start >= ARXIV_RESULT_WINDOW:
        raise ArxivError(
            f"start offset {start} exceeds arXiv's {ARXIV_RESULT_WINDOW}-result window", "INVALID_QUERY"
        )
    if start + limit > ARXIV_RESULT_WINDOW:
        limit = ARXIV_RESULT_WINDOW - start

    effective_query = _apply_date_filter(query, args.since, args.until)
    root = _fetch({"search_query": effective_query, "start": start, "max_results": limit})

    total_el = root.findtext(f"{OPENSEARCH_NS}totalResults")
    total_available = int(total_el) if total_el and total_el.strip().isdigit() else None

    results = [_parse_entry(e) for e in root.findall(f"{ATOM_NS}entry")]
    retrieved = len(results)
    truncated = total_available is not None and (start + retrieved) < total_available

    return {"meta": _build_meta(effective_query, retrieved, total_available, truncated), "results": results}


def detail(args):
    raw_id = args.id.strip()
    if not raw_id:
        raise ArxivError("detail requires a non-empty arXiv id", "INVALID_QUERY")
    root = _fetch({"id_list": raw_id})
    results = [_parse_entry(e) for e in root.findall(f"{ATOM_NS}entry")]
    if not results:
        raise ArxivError(f"no arXiv record found for id {raw_id!r}", "UPSTREAM_ERROR")
    retrieved = len(results)
    return {"meta": _build_meta(raw_id, retrieved, retrieved, False), "results": results}


def main():
    parser = _shared.build_arg_parser(SOURCE)
    args = parser.parse_args()
    try:
        payload = search(args) if args.command == "search" else detail(args)
        _shared.write_output(payload, args.format, args.out)
    except ArxivError as exc:
        _shared.write_error(exc.message, exc.code)
        sys.exit(1)
    except ValueError as exc:
        _shared.write_error(str(exc), "INVALID_QUERY")
        sys.exit(1)


if __name__ == "__main__":
    main()
