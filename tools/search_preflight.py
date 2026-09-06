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
   "expected_missing_reason": "...", "provenance": "..."}`) are DOIs/PMIDs
   the reviewer already knows are relevant, checked against `records.jsonl`
   by the same normalization `tools/dedup.py` uses for its doi/pmid dedup
   tiers. A known item that isn't found is "unacknowledged" unless its own
   `expected_missing_reason` is set (e.g. "grey-literature report, not
   indexed by any enabled source"). A known item promoted from a
   reconnaissance topic (docs/ROADMAP.md M4; `tools/promote_reconnaissance.py`)
   carries `provenance: "recon-db"` -- checking recall against those alone
   would be circular (they were found by the same search being evaluated),
   so they're reported separately and excluded from the "real" recall
   count; `non_independent_gold_set` is true whenever every known item on
   record is `recon-db`-sourced, cleared once at least one externally
   sourced known item exists.

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
    """{"checked": int, "found": [...], "missing": [...],
    "checked_excluding_recon_seeds": int, "found_excluding_recon_seeds":
    int, "non_independent_gold_set": bool} -- each found/missing entry
    carries id_type/id/note/provenance (and matched_record_id for "found",
    or the original expected_missing_reason for "missing").

    `_excluding_recon_seeds` counts and `non_independent_gold_set` treat a
    known item with `provenance: "recon-db"` (promoted from a
    reconnaissance topic, tools/promote_reconnaissance.py) as a seed, not
    independent evidence the search actually works: checking recall
    against seeds alone would be circular, since the same search that
    produced them is the one being evaluated. `non_independent_gold_set`
    is true exactly when every known item on record is a recon-db seed
    (and at least one known item exists at all)."""
    topic_dir = Path(topic_dir)
    protocol = _load_json(topic_dir / "protocol.json") or {}
    known_items = protocol.get("known_items") or []
    if not known_items:
        return {"checked": 0, "found": [], "missing": [],
                "checked_excluding_recon_seeds": 0, "found_excluding_recon_seeds": 0,
                "non_independent_gold_set": False}

    records = []
    records_path = topic_dir / "records.jsonl"
    if records_path.exists():
        with open(records_path) as f:
            records = [json.loads(l) for l in f if l.strip()]
    index = _index_records_by_doi_and_pmid(records)

    found, missing = [], []
    for item in known_items:
        id_type, raw_id, provenance = item.get("id_type"), item.get("id"), item.get("provenance")
        if id_type == "doi":
            key = ("doi", normalize_doi(raw_id))
        elif id_type == "pmid":
            key = ("pmid", str(raw_id) if raw_id is not None else None)
        else:
            key = (None, None)  # unrecognized id_type -- can never match, reported as missing
        matched_record_id = index.get(key)
        if matched_record_id:
            found.append({"id_type": id_type, "id": raw_id, "provenance": provenance, "matched_record_id": matched_record_id})
        else:
            missing.append({"id_type": id_type, "id": raw_id, "provenance": provenance, "note": item.get("note"),
                             "expected_missing_reason": item.get("expected_missing_reason")})

    non_seed_items = [i for i in known_items if i.get("provenance") != "recon-db"]
    non_seed_found = [f for f in found if f.get("provenance") != "recon-db"]
    return {
        "checked": len(known_items), "found": found, "missing": missing,
        "checked_excluding_recon_seeds": len(non_seed_items),
        "found_excluding_recon_seeds": len(non_seed_found),
        "non_independent_gold_set": bool(known_items) and not non_seed_items,
    }


def search_status(topic_dir):
    topic_dir = Path(topic_dir)
    protocol = _load_json(topic_dir / "protocol.json") or {}
    coverage_gaps = (protocol.get("scope") or {}).get("coverage_gaps") or []

    statuses = source_completeness(topic_dir)
    unacknowledged_sources = unacknowledged_incomplete_sources(statuses, coverage_gaps)
    recall = known_item_recall(topic_dir)
    unacknowledged_items = [i for i in recall["missing"] if not i.get("expected_missing_reason")]

    result = {
        "sources": statuses,
        "unacknowledged_incomplete_sources": sorted(unacknowledged_sources),
        "known_item_recall": recall,
        "unacknowledged_missing_known_items": unacknowledged_items,
    }
    if recall["non_independent_gold_set"]:
        result["non_independent_gold_set_notice"] = (
            "non-independent gold set: every known item on record came from this topic's own "
            "reconnaissance search (provenance: \"recon-db\") -- recall is not yet validated against "
            "anything external. Add an externally-sourced known item to clear this notice."
        )
    return result


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
