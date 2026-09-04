"""PubMed connector: NCBI E-utilities (esearch -> efetch), stdlib XML parsing.

CLI: python3 -m connectors.pubmed <search|detail> [flags]  (see _shared.py
for the shared flag set and the fixed {meta, results} output contract).

NCBI etiquette (https://www.ncbi.nlm.nih.gov/books/NBK25497/) requires
``tool=`` and ``email=`` on every request; an optional ``api_key=`` (from
the NCBI_API_KEY env var) raises the per-IP rate limit from 3/s to 10/s.
Two-step flow: esearch resolves the query to a list of PMIDs (and the true
total-hit count), efetch pulls the full records for those PMIDs. Both
return XML, parsed with xml.etree.ElementTree.

"detail <id>" is handled with a *real* single-record fetch (efetch supports
id=<pmid> directly) rather than the search-scoped fallback the connector
contract allows for sources that lack one — PubMed does support it. When
<id> looks like a DOI instead of a bare PMID, it is first resolved to a
PMID via esearch (term=<doi>[AID]), then efetch'd the same way.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

import requests

from connectors import _shared

SOURCE = "pubmed"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"

# NCBI wants an honest contact email on every request; reviewer-configurable,
# same placeholder convention as _shared.build_user_agent's default.
CONTACT_EMAIL = os.environ.get("NCBI_EMAIL") or os.environ.get("PRISMA_CONTACT_EMAIL") or "set-a-contact-email@example.org"


class UpstreamError(Exception):
    """HTTP/XML-level failure, carrying the connector-contract error code."""

    def __init__(self, message, code="UPSTREAM_ERROR"):
        super().__init__(message)
        self.code = code


def _base_params():
    params = {"tool": "prisma-review-pubmed", "email": CONTACT_EMAIL}
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def _headers():
    return {"User-Agent": _shared.build_user_agent(CONTACT_EMAIL)}


def _get_xml(url, params):
    try:
        resp = _shared.http_get_with_backoff(url, params=params, headers=_headers())
    except requests.RequestException as exc:
        raise UpstreamError(f"pubmed: network error: {exc}", "UPSTREAM_ERROR") from exc

    if resp.status_code == 429:
        raise UpstreamError("pubmed: rate limited", "RATE_LIMITED")
    if resp.status_code == 400:
        raise UpstreamError(f"pubmed: bad request: {resp.text[:300]}", "INVALID_QUERY")
    if resp.status_code != 200:
        raise UpstreamError(f"pubmed: HTTP {resp.status_code} from {url}", "UPSTREAM_ERROR")
    try:
        return ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise UpstreamError(f"pubmed: malformed XML response: {exc}", "UPSTREAM_ERROR") from exc


def _esearch(term, retmax, retstart, since=None, until=None):
    params = _base_params()
    params.update({"db": "pubmed", "term": term, "retmax": retmax, "retstart": retstart, "retmode": "xml"})
    if since or until:
        params["datetype"] = "pdat"
        if since:
            params["mindate"] = since
        if until:
            params["maxdate"] = until
    root = _get_xml(ESEARCH_URL, params)

    count_el = root.find("Count")
    error_list = root.find("ErrorList")
    if count_el is None and error_list is not None:
        msgs = [el.text for el in error_list.iter() if el.text and el is not error_list]
        raise UpstreamError(f"pubmed: invalid query {term!r}: {'; '.join(msgs) or 'no match'}", "INVALID_QUERY")

    count = int(count_el.text) if count_el is not None and count_el.text else 0
    ids = [el.text for el in root.findall("./IdList/Id") if el.text]
    return count, ids


def _text(el):
    """Join an element's text and its children's text/tail, dropping inline
    markup tags (e.g. <i>, <sup> inside titles/abstracts)."""
    if el is None:
        return None
    joined = "".join(el.itertext()).strip()
    return joined or None


def _author_name(author_el):
    collective = author_el.find("CollectiveName")
    if collective is not None and collective.text:
        return collective.text.strip()
    last = author_el.find("LastName")
    fore = author_el.find("ForeName")
    initials = author_el.find("Initials")
    given = (fore.text if fore is not None and fore.text else None) or (
        initials.text if initials is not None and initials.text else None
    )
    if last is not None and last.text:
        return f"{last.text.strip()} {given.strip()}" if given else last.text.strip()
    return None


def _year_from(article_el):
    year_el = article_el.find("./Journal/JournalIssue/PubDate/Year")
    if year_el is not None and year_el.text:
        try:
            return int(year_el.text)
        except ValueError:
            pass
    medline_date = article_el.find("./Journal/JournalIssue/PubDate/MedlineDate")
    if medline_date is not None and medline_date.text:
        m = re.search(r"\d{4}", medline_date.text)
        if m:
            return int(m.group())
    article_date_year = article_el.find("ArticleDate/Year")
    if article_date_year is not None and article_date_year.text:
        try:
            return int(article_date_year.text)
        except ValueError:
            pass
    return None


def _doi_from(article_el, pubmed_data_el):
    for eloc in article_el.findall("ELocationID"):
        if eloc.get("EIdType") == "doi" and eloc.text:
            return eloc.text.strip()
    if pubmed_data_el is not None:
        for aid in pubmed_data_el.findall("./ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                return aid.text.strip()
    return None


def _abstract_from(article_el):
    parts = []
    for ab in article_el.findall("./Abstract/AbstractText"):
        text = _text(ab)
        if not text:
            continue
        label = ab.get("Label")
        parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts) if parts else None


def _empty_record():
    return {
        "id": None, "title": None, "authors": [], "year": None, "venue": None,
        "doi": None, "abstract": None, "url": None, "source": SOURCE,
    }


def _parse_article(pubmed_article_el):
    medline = pubmed_article_el.find("MedlineCitation")
    if medline is None:
        return None
    pubmed_data = pubmed_article_el.find("PubmedData")
    article_el = medline.find("Article")
    pmid_el = medline.find("PMID")
    pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None

    record = _empty_record()
    record["id"] = pmid
    record["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
    if article_el is None:
        return record

    record["title"] = _text(article_el.find("ArticleTitle"))
    record["authors"] = [
        name for name in (_author_name(a) for a in article_el.findall("./AuthorList/Author")) if name
    ]
    record["year"] = _year_from(article_el)
    record["venue"] = _text(article_el.find("./Journal/Title")) or _text(article_el.find("./Journal/ISOAbbreviation"))
    record["doi"] = _doi_from(article_el, pubmed_data)
    record["abstract"] = _abstract_from(article_el)
    return record


def _efetch_records(pmids):
    if not pmids:
        return []
    params = _base_params()
    params.update({"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"})
    root = _get_xml(EFETCH_URL, params)
    records = []
    for article_el in root.findall("PubmedArticle"):
        record = _parse_article(article_el)
        if record:
            records.append(record)
    return records


def _resolve_retstart(args, limit):
    if getattr(args, "cursor", None) is not None:
        try:
            return int(args.cursor)
        except ValueError:
            raise ValueError("pubmed: --cursor must be an integer retstart offset")
    if getattr(args, "page", None) is not None:
        return max(0, args.page) * limit
    return 0


def search(args):
    query = _shared.resolve_query(args)
    limit = max(0, args.limit)
    retstart = _resolve_retstart(args, limit)
    total_available, ids = _esearch(query, retmax=limit, retstart=retstart, since=args.since, until=args.until)
    records = _efetch_records(ids)
    truncated = (retstart + len(records)) < total_available
    meta = _build_meta(query, retrieved=len(records), total_available=total_available, truncated=truncated)
    return {"meta": meta, "results": records}


def detail(args):
    raw_id = args.id.strip()
    if re.fullmatch(r"\d+", raw_id):
        pmid = raw_id
    else:
        # Not a bare PMID (likely a DOI): resolve it to a PMID first via
        # esearch's Article ID field ([AID]), then efetch as usual.
        _, ids = _esearch(f"{raw_id}[AID]", retmax=1, retstart=0)
        pmid = ids[0] if ids else None

    records = _efetch_records([pmid]) if pmid else []
    meta = _build_meta(raw_id, retrieved=len(records), total_available=len(records), truncated=False)
    return {"meta": meta, "results": records}


def _build_meta(query, retrieved, total_available, truncated):
    return {
        "source": SOURCE,
        "query": query,
        "retrieved": retrieved,
        "total_available": total_available,
        "truncated": truncated,
        "fetched_at": _shared.utc_now_iso(),
    }


def main():
    parser = _shared.build_arg_parser(SOURCE)
    args = parser.parse_args()
    try:
        payload = search(args) if args.command == "search" else detail(args)
    except ValueError as exc:
        _shared.write_error(str(exc), "INVALID_QUERY")
        sys.exit(1)
    except UpstreamError as exc:
        _shared.write_error(str(exc), exc.code)
        sys.exit(1)
    _shared.write_output(payload, getattr(args, "format", "json"), getattr(args, "out", None))


if __name__ == "__main__":
    main()
