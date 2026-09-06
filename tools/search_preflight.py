#!/usr/bin/env python3
"""Search-completeness status and known-item recall check.

Phase 0 correctness addition (docs/PLAN.md decision 4 / "adopted from
open-source peers"): turns "the search felt comprehensive" into two
measured checks instead of an unverified impression.

1. **Source completeness** — for every source enabled in `search_plan.json`,
   classify its latest `raw/<source>-*.json` run as `complete`, `truncated`
   (a `--limit` cap left `retrieved` below `total_available`), or `missing`
   (no raw file for it yet). A non-complete source is "unacknowledged"
   unless `protocol.json.scope.coverage_gaps` names that source (the
   review-protocol/keyword-expansion skills already write this field for
   exactly this purpose).

2. **Known-item recall** — `protocol.json.known_items` (optional; a list
   of `{"id_type": "doi"|"pmid", "id": "...", "note": "...",
   "expected_missing_reason": "..."}`) are DOIs/PMIDs the reviewer already
   knows are relevant, checked against `records.jsonl` by the same
   normalization `tools/dedup.py` uses for its doi/pmid dedup tiers. A
   known item that isn't found is "unacknowledged" unless its own
   `expected_missing_reason` is set (e.g. "grey-literature report, not
   indexed by any enabled source").

Recall classification here is deliberately simple (found vs missing):
richer index-miss-vs-string-miss classification (was this a translation
gap or a coverage gap?) and a new-records-per-query series are noted as
future work (docs/PLAN.md), not implemented here without the additional
per-run instrumentation they would need.

Usage:
    python3 tools/search_preflight.py --topic <slug>

Writes results/<slug>/search_status.json, prints it, and exits 1 if any
source or known item is unacknowledged.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.dedup import normalize_doi, normalize_pmid  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


def _latest_raw_by_source(topic_dir):
    latest = {}
    for p in sorted(glob.glob(str(Path(topic_dir) / "raw" / "*.json"))):
        source = os.path.basename(p).rsplit("-", 1)[0]
        latest[source] = p
    return latest


def _load_json(path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def source_completeness(topic_dir):
    """{source: {"status": "complete"|"truncated"|"missing", "retrieved":
    int|None, "total_available": int|None}} for every source enabled in
    search_plan.json (a source with no "enabled" key is enabled by
    default, matching /prisma-search's own convention)."""
    topic_dir = Path(topic_dir)
    plan = _load_json(topic_dir / "search_plan.json")
    if not plan:
        return {}
    enabled = [name for name, cfg in (plan.get("sources") or {}).items() if cfg.get("enabled", True)]
    latest_raw = _latest_raw_by_source(topic_dir)

    statuses = {}
    for name in enabled:
        path = latest_raw.get(name)
        if not path:
            statuses[name] = {"status": "missing", "retrieved": None, "total_available": None}
            continue
        with open(path) as f:
            meta = json.load(f).get("meta", {})
        status = "truncated" if meta.get("truncated") else "complete"
        statuses[name] = {"status": status, "retrieved": meta.get("retrieved"), "total_available": meta.get("total_available")}
    return statuses


def unacknowledged_incomplete_sources(statuses, coverage_gaps):
    acknowledged = {g.get("source") for g in (coverage_gaps or [])}
    return {name: info for name, info in statuses.items() if info["status"] != "complete" and name not in acknowledged}


def _index_records_by_doi_and_pmid(records):
    index = {}
    for r in records:
        doi = normalize_doi(r.get("doi"))
        if doi:
            index.setdefault(("doi", doi), r["record_id"])
        pmid = normalize_pmid(r)
        if pmid:
            index.setdefault(("pmid", pmid), r["record_id"])
    return index


def known_item_recall(topic_dir):
    """{"checked": int, "found": [...], "missing": [...]} -- each entry
    carries id_type/id/note (and matched_record_id for "found", or the
    original expected_missing_reason for "missing")."""
    topic_dir = Path(topic_dir)
    protocol = _load_json(topic_dir / "protocol.json") or {}
    known_items = protocol.get("known_items") or []
    if not known_items:
        return {"checked": 0, "found": [], "missing": []}

    records = []
    records_path = topic_dir / "records.jsonl"
    if records_path.exists():
        with open(records_path) as f:
            records = [json.loads(l) for l in f if l.strip()]
    index = _index_records_by_doi_and_pmid(records)

    found, missing = [], []
    for item in known_items:
        id_type, raw_id = item.get("id_type"), item.get("id")
        if id_type == "doi":
            key = ("doi", normalize_doi(raw_id))
        elif id_type == "pmid":
            key = ("pmid", str(raw_id) if raw_id is not None else None)
        else:
            key = (None, None)  # unrecognized id_type -- can never match, reported as missing
        matched_record_id = index.get(key)
        if matched_record_id:
            found.append({"id_type": id_type, "id": raw_id, "matched_record_id": matched_record_id})
        else:
            missing.append({"id_type": id_type, "id": raw_id, "note": item.get("note"),
                             "expected_missing_reason": item.get("expected_missing_reason")})
    return {"checked": len(known_items), "found": found, "missing": missing}


def search_status(topic_dir):
    topic_dir = Path(topic_dir)
    protocol = _load_json(topic_dir / "protocol.json") or {}
    coverage_gaps = (protocol.get("scope") or {}).get("coverage_gaps") or []

    statuses = source_completeness(topic_dir)
    unacknowledged_sources = unacknowledged_incomplete_sources(statuses, coverage_gaps)
    recall = known_item_recall(topic_dir)
    unacknowledged_items = [i for i in recall["missing"] if not i.get("expected_missing_reason")]

    return {
        "sources": statuses,
        "unacknowledged_incomplete_sources": sorted(unacknowledged_sources),
        "known_item_recall": recall,
        "unacknowledged_missing_known_items": unacknowledged_items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="review slug; derives results/<topic>/ itself")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    status = search_status(topic_dir)
    out_path = Path(topic_dir) / "search_status.json"
    with open(out_path, "w") as f:
        json.dump(status, f, indent=2)
    print(json.dumps(status, indent=2))

    ok = not status["unacknowledged_incomplete_sources"] and not status["unacknowledged_missing_known_items"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
