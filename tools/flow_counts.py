#!/usr/bin/env python3
"""PRISMA flow-diagram box counts, aggregated fresh from the pipeline's own
ledgers every time -- never hand-typed, never recalled from memory.

Ported, behavior-preserving except for the "reports not retrieved" box (see
below), from the inline `python3 -c` heredoc `.claude/commands/
prisma-report.md` Step 8 used to embed directly in the prompt (Phase 0
correctness fix, docs/PLAN.md defect #3).

Behavior change from the original heredoc: the decision enum gained
"not_retrieved" (docs/PLAN.md decision 4), so this module can now compute
PRISMA 2020's "Reports not retrieved" box directly from the ledger instead
of the original's documented workaround ("ask the reviewer for it
directly, the ledger has no field for it"). A full-text record decided
"not_retrieved" no longer counts toward "assessed for eligibility",
"excluded", or "included" -- it was never actually assessed.

Usage:
    python3 tools/flow_counts.py --topic <slug>
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

from tools.ledger import latest_decisions, load_ledger  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


def flow_counts(topic_dir):
    topic_dir = Path(topic_dir)

    # --- Identification ---
    latest_raw = {}
    for p in sorted(glob.glob(str(topic_dir / "raw" / "*.json"))):
        source = os.path.basename(p).rsplit("-", 1)[0]
        latest_raw[source] = p  # lexicographic date sort -> last write per source wins
    per_source = {}
    truncated_sources = []
    for s, p in latest_raw.items():
        with open(p) as f:
            meta = json.load(f)["meta"]
        per_source[s] = {"retrieved": meta["retrieved"], "total_available": meta["total_available"], "truncated": meta["truncated"]}
        if meta["truncated"]:
            truncated_sources.append(s)
    identified_total = sum(v["retrieved"] for v in per_source.values())

    records_path = topic_dir / "records.jsonl"
    records = []
    if records_path.exists():
        with open(records_path) as f:
            records = [json.loads(l) for l in f if l.strip()]
    duplicates_removed = sum(1 for r in records if r.get("duplicate_of"))
    canonical = [r for r in records if not r.get("duplicate_of")]
    records_screened = len(canonical)

    # --- Screening / Included (latest decision per (record_id, stage)) ---
    entries = load_ledger(topic_dir)
    latest = latest_decisions(entries)

    ta = {rid: e for (rid, stage), e in latest.items() if stage == "title_abstract"}
    excluded_ta = sum(1 for e in ta.values() if e["decision"] == "exclude")
    sought_for_retrieval = sum(1 for e in ta.values() if e["decision"] == "include")

    ft = {rid: e for (rid, stage), e in latest.items() if stage == "full_text"}
    not_retrieved_ft = {rid: e for rid, e in ft.items() if e["decision"] == "not_retrieved"}
    assessed_ft = {rid: e for rid, e in ft.items() if e["decision"] != "not_retrieved"}
    # A record that passed title/abstract but has no full_text-stage entry at
    # all yet is still awaiting full-text screening -- distinct from
    # not_retrieved, which is an explicit ledger decision.
    pending_full_text = sought_for_retrieval - len(ft)
    assessed_for_eligibility = len(assessed_ft)
    excluded_ft = [e for e in assessed_ft.values() if e["decision"] == "exclude"]
    included_final = sum(1 for e in assessed_ft.values() if e["decision"] == "include")

    reason_required_missing = [
        e["record_id"] for e in list(excluded_ft) + list(not_retrieved_ft.values())
        if not e.get("reason")
    ]
    reason_counts = {}
    for e in excluded_ft:
        r = e.get("reason")
        if r:
            reason_counts[r] = reason_counts.get(r, 0) + 1

    return {
        "per_source_identified": per_source,
        "truncated_sources": truncated_sources,
        "identified_total": identified_total,
        "duplicates_removed": duplicates_removed,
        "records_screened": records_screened,
        "excluded_title_abstract": excluded_ta,
        "sought_for_retrieval": sought_for_retrieval,
        "reports_not_retrieved": len(not_retrieved_ft),
        "assessed_for_eligibility": assessed_for_eligibility,
        "pending_full_text": pending_full_text,
        "excluded_full_text_total": len(excluded_ft),
        "excluded_full_text_reasons": reason_counts,
        "included_final": included_final,
        "full_text_excludes_missing_reason": reason_required_missing,
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

    print(json.dumps(flow_counts(topic_dir), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
