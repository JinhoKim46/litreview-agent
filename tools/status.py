#!/usr/bin/env python3
"""Report exactly where a review currently stands, and the single next
command to run.

Ported, behavior-preserving, from the inline `python3 -` heredoc
`.claude/commands/litreview-status.md` Step 3 used to embed directly in the
prompt (Phase 0 correctness fix, docs/PLAN.md defect #3).

Reuses tools/ledger.py's `load_ledger`/`latest_decisions` for the
title-abstract/full-text aggregation, so this command and
tools/flow_counts.py's PRISMA flow-diagram counts can never silently
disagree about how a screening decision is reduced (same reasoning
flow_counts.py itself documents relative to /litreview-status).

Usage:
    python3 tools/status.py                # list every review under results/
    python3 tools/status.py --topic <slug> # full report for one review
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
from tools.path_policy import RESULTS_ROOT, UnsafePathError, safe_topic_path  # noqa: E402


def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def as_list(x, list_key="studies"):
    """extraction_table.json has been written under two different top-level
    shapes in this repo's history (a bare JSON array, and {"studies": [...]})
    -- accept either rather than assuming one. The synthesis/*.json files
    are always bare lists (one entry per outcome group), which this also
    handles correctly."""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        if isinstance(x.get(list_key), list):
            return x[list_key]
        return list(x.values())
    return []


def study_id(study):
    return study.get("record_id") or study.get("study_id") or study.get("author_year") or "UNKNOWN_STUDY"


def latest_raw_meta(topic_dir):
    """Most recent dated raw/<source>-<YYYYMMDD>.json per source --
    lexicographic filename sort means the last write per source wins, same
    rule /litreview-report Step 3/Step 8 and tools/flow_counts.py use."""
    latest = {}
    for p in sorted(glob.glob(str(topic_dir / "raw" / "*.json"))):
        source = os.path.basename(p).rsplit("-", 1)[0]
        latest[source] = p
    per_source = {}
    for s, p in latest.items():
        data = load_json(Path(p))
        meta = (data or {}).get("meta") if isinstance(data, dict) else None
        if not meta:
            continue
        per_source[s] = {
            "retrieved": meta.get("retrieved", 0),
            "total_available": meta.get("total_available"),
            "truncated": bool(meta.get("truncated", False)),
        }
    return per_source


def since_last_version(topic_dir):
    """{"from_version", "to_version", "from_date", "to_date", "new_records",
    "new_record_ids", "removed_records", "removed_record_ids",
    "included_delta"} comparing this topic's last two recorded
    protocol.json.versions[] entries (tools/versioning.py, docs/ROADMAP.md
    M5's living-review mode) -- None if fewer than two versions have been
    recorded yet (nothing to diff against). Reuses each version's own
    stored record_id snapshot rather than re-deriving a historical record
    set from records.jsonl, which only ever holds the *current* state --
    a record present in an earlier version but reclassified as a
    duplicate since would otherwise be invisible to this diff."""
    protocol = load_json(topic_dir / "protocol.json")
    versions = (protocol or {}).get("versions") or []
    if len(versions) < 2:
        return None
    prev, latest = versions[-2], versions[-1]
    prev_ids, latest_ids = set(prev.get("record_ids", [])), set(latest.get("record_ids", []))
    new_ids = sorted(latest_ids - prev_ids)
    removed_ids = sorted(prev_ids - latest_ids)
    return {
        "from_version": prev["version"], "to_version": latest["version"],
        "from_date": prev["date"], "to_date": latest["date"],
        "new_records": len(new_ids), "new_record_ids": new_ids,
        "removed_records": len(removed_ids), "removed_record_ids": removed_ids,
        "included_delta": latest.get("n_included", 0) - prev.get("n_included", 0),
    }


def compute(topic_dir):
    protocol = load_json(topic_dir / "protocol.json")
    search_plan = load_json(topic_dir / "search_plan.json")

    per_source = latest_raw_meta(topic_dir)
    truncated_sources = sorted(s for s, v in per_source.items() if v["truncated"])
    identified_total = sum(v["retrieved"] for v in per_source.values())

    records_path = topic_dir / "records.jsonl"
    records = []
    if records_path.exists():
        with open(records_path) as f:
            records = [json.loads(line) for line in f if line.strip()]
    duplicates_removed = sum(1 for r in records if r.get("duplicate_of"))
    canonical = [r for r in records if not r.get("duplicate_of")]
    canonical_ids = {r["record_id"] for r in canonical}
    records_screened = len(canonical)

    entries = load_ledger(topic_dir)
    latest = latest_decisions(entries)

    ta = {rid: e for (rid, stage), e in latest.items() if stage == "title_abstract"}
    orphaned_ta = sorted(rid for rid in ta if rid not in canonical_ids)
    excluded_ta = sum(1 for e in ta.values() if e["decision"] == "exclude")
    ft_candidates = {rid for rid, e in ta.items() if e["decision"] == "include"}
    sought_for_retrieval = len(ft_candidates)
    undecided_ta = len(canonical_ids - set(ta.keys()))

    ft = {rid: e for (rid, stage), e in latest.items() if stage == "full_text"}
    orphaned_ft = sorted(rid for rid in ft if rid not in ft_candidates)
    assessed_for_eligibility = len(ft)
    pending_full_text = len(ft_candidates - set(ft.keys()))
    excluded_ft = [e for e in ft.values() if e["decision"] == "exclude"]
    included_final = sum(1 for e in ft.values() if e["decision"] == "include")
    missing_reason = sorted(e["record_id"] for e in excluded_ft if not (e.get("reason") or "").strip())

    extraction = as_list(load_json(topic_dir / "extraction_table.json"))
    extracted_count = len(extraction)
    extracted_ids = {study_id(s) for s in extraction}
    unextracted_included = sorted(rid for rid in ft if ft[rid]["decision"] == "include" and rid not in extracted_ids)

    heterogeneity = as_list(load_json(topic_dir / "synthesis" / "heterogeneity.json"))
    pooled_outcomes = [o for o in heterogeneity if o.get("pooled") is True]
    narrative_outcomes = [o for o in heterogeneity if o.get("pooled") is False]
    synth_present = (topic_dir / "synthesis" / "heterogeneity.json").exists()

    manuscript_path = topic_dir / "manuscript" / "manuscript.md"
    manuscript_exists = manuscript_path.exists()
    manuscript_words = len(manuscript_path.read_text().split()) if manuscript_exists else 0
    manuscript_mtime = manuscript_path.stat().st_mtime if manuscript_exists else 0
    extraction_path = topic_dir / "extraction_table.json"
    extraction_mtime = extraction_path.stat().st_mtime if extraction_path.exists() else 0
    synth_dir = topic_dir / "synthesis"
    synth_mtime = max((f.stat().st_mtime for f in synth_dir.glob("*.json")), default=0) if synth_dir.exists() else 0

    # ---- current stage + single next-command recommendation ----
    if protocol is None:
        stage, next_cmd = "not_started", f'/litreview-init "{topic_dir.name}"'
        why = "no protocol.json yet"
    elif not search_plan or not per_source:
        stage, next_cmd = "protocol_defined", "/litreview-search"
        why = "protocol is defined but no search has been run yet"
    elif not records:
        stage, next_cmd = "search_incomplete", "/litreview-search"
        why = "raw search results exist but records.jsonl was never written"
    elif undecided_ta > 0:
        stage, next_cmd = "screening_title_abstract", "/litreview-screen export --stage title_abstract"
        why = f"{undecided_ta} record(s) still undecided at title/abstract"
    elif pending_full_text > 0:
        stage, next_cmd = "screening_full_text", "/litreview-screen export --stage full_text"
        why = f"{pending_full_text} record(s) passed title/abstract but have no full-text decision yet"
    elif included_final == 0:
        stage, next_cmd = "screening_complete_zero_included", None
        why = "screening is complete but zero studies were included -- revisit protocol.json's eligibility criteria"
    elif extracted_count < included_final:
        stage, next_cmd = "extraction_incomplete", "/litreview-extract"
        why = f"{extracted_count}/{included_final} included studies extracted"
    elif not synth_present:
        stage, next_cmd = "extraction_complete", "/litreview-synthesize"
        why = "extraction is complete, synthesis has not run yet"
    elif not manuscript_exists:
        stage, next_cmd = "synthesis_complete", "/litreview-report"
        why = f"{len(pooled_outcomes)} outcome(s) pooled, {len(narrative_outcomes)} narrative-fallback -- manuscript not yet drafted"
    elif max(extraction_mtime, synth_mtime) > manuscript_mtime:
        stage, next_cmd = "manuscript_drafted", "/litreview-report"
        why = "extraction_table.json or a synthesis/ file is newer than manuscript.md -- the manuscript may be stale"
    else:
        stage, next_cmd = "manuscript_drafted", None
        why = "manuscript is drafted and up to date -- review it, or re-run /litreview-report after any further pipeline change"

    return dict(
        topic=topic_dir.name, protocol=protocol, per_source=per_source,
        delta=since_last_version(topic_dir),
        truncated_sources=truncated_sources, identified_total=identified_total,
        duplicates_removed=duplicates_removed, records_screened=records_screened,
        excluded_title_abstract=excluded_ta, sought_for_retrieval=sought_for_retrieval,
        undecided_title_abstract=undecided_ta, assessed_for_eligibility=assessed_for_eligibility,
        pending_full_text=pending_full_text, excluded_full_text_total=len(excluded_ft),
        included_final=included_final, full_text_excludes_missing_reason=missing_reason,
        orphaned_title_abstract=orphaned_ta, orphaned_full_text=orphaned_ft,
        extracted_count=extracted_count, unextracted_included=unextracted_included,
        pooled_outcomes=len(pooled_outcomes), narrative_outcomes=len(narrative_outcomes),
        synth_present=synth_present, manuscript_exists=manuscript_exists,
        manuscript_words=manuscript_words, stage=stage, next_cmd=next_cmd, why=why,
    )


def print_full(s):
    print(f"# PRISMA review status: {s['topic']}")
    print()
    p = s["protocol"]
    if p:
        print(f"Title: {p.get('title', '(untitled)')}")
        print(f"Framework: {p.get('framework', '?')}  |  Review type: {p.get('review_type', '?')}")
        scope = p.get("scope", {}) or {}
        region = f" ({scope.get('region')})" if scope.get("region") else ""
        print(f"Scope: {scope.get('mode', '?')}{region}  |  coverage gaps noted: {len(scope.get('coverage_gaps', []) or [])}")
    else:
        print("(no protocol.json yet)")
    print()
    print("## Pipeline counts")
    print(f"  Records identified (latest run per source): {s['identified_total']}")
    for src, meta in sorted(s["per_source"].items()):
        flag = "  [TRUNCATED]" if meta["truncated"] else ""
        print(f"    - {src}: retrieved={meta['retrieved']} total_available={meta['total_available']}{flag}")
    print(f"  Records deduplicated (unique, screenable): {s['records_screened']}  "
          f"(duplicates removed: {s['duplicates_removed']})")
    print(f"  Screened - title/abstract: include={s['sought_for_retrieval']} "
          f"exclude={s['excluded_title_abstract']} undecided={s['undecided_title_abstract']}")
    print(f"  Screened - full-text: include={s['included_final']} "
          f"exclude={s['excluded_full_text_total']} pending={s['pending_full_text']} "
          f"(assessed so far: {s['assessed_for_eligibility']})")
    print(f"  Included (final): {s['included_final']}")
    print(f"  Extracted: {s['extracted_count']}/{s['included_final']}")
    if s["synth_present"]:
        print(f"  Synthesized: {s['pooled_outcomes']} outcome(s) pooled, "
              f"{s['narrative_outcomes']} narrative-fallback")
    else:
        print("  Synthesized: not yet run")
    ms = f"drafted ({s['manuscript_words']} words)" if s["manuscript_exists"] else "not drafted"
    print(f"  Manuscript: {ms}")
    print()

    if s["delta"]:
        d = s["delta"]
        print(f"## Living-mode delta (version {d['from_version']} [{d['from_date']}] -> "
              f"version {d['to_version']} [{d['to_date']}])")
        print(f"  New records since last version: {d['new_records']}")
        for rid in d["new_record_ids"][:20]:
            print(f"    - {rid}")
        if len(d["new_record_ids"]) > 20:
            print(f"    ... and {len(d['new_record_ids']) - 20} more")
        if d["removed_records"]:
            print(f"  Records no longer canonical since last version (e.g. reclassified as duplicates): {d['removed_records']}")
        print(f"  Included count change since last version: {d['included_delta']:+d}")
        print()

    warnings = []
    if s["full_text_excludes_missing_reason"]:
        warnings.append(
            ("Data integrity: full-text excludes missing a required reason (PRISMA Item 16b)",
             s["full_text_excludes_missing_reason"],
             "Fix by appending a corrected line to screening_decisions.jsonl (never edit history) "
             "before running /litreview-extract."))
    if s["orphaned_title_abstract"] or s["orphaned_full_text"]:
        warnings.append(
            ("Data integrity: screening decisions reference a record_id no longer canonical in records.jsonl",
             sorted(set(s["orphaned_title_abstract"]) | set(s["orphaned_full_text"])),
             "These records were likely reclassified as duplicates after being screened, or removed by "
             "a hand-edit. They are still counted in the include/exclude tallies above -- this script "
             "deliberately mirrors /litreview-report's own flow-diagram aggregation, which does not filter "
             "them either -- so the two commands never disagree. Confirm the reclassification was "
             "intentional; a record that turned out to be a duplicate after screening may need its "
             "decision reconsidered against whichever record it is now a duplicate of."))
    if s["unextracted_included"]:
        warnings.append(
            ("Extraction gap: full-text includes with no extraction_table.json entry",
             s["unextracted_included"],
             "Run /litreview-extract to pick these up."))
    if s["truncated_sources"]:
        warnings.append(
            ("Search coverage: source(s) truncated by a --limit cap",
             s["truncated_sources"],
             "retrieved < total_available for these -- consider re-running rerun_search.sh uncapped "
             "before treating identified_total as final."))

    for title, ids, fix in warnings:
        print(f"## WARNING: {title}")
        for rid in ids[:20]:
            print(f"    - {rid}")
        if len(ids) > 20:
            print(f"    ... and {len(ids) - 20} more")
        print(f"  {fix}")
        print()

    print(f"## Current stage: {s['stage']}")
    if s["next_cmd"]:
        print(f"## Next command: {s['next_cmd']}")
    print(f"  ({s['why']})")


def print_condensed(s):
    tag = f" -> next: {s['next_cmd']}" if s["next_cmd"] else " -> nothing pending"
    print(f"{s['topic']}: stage={s['stage']}  identified={s['identified_total']} "
          f"dedup={s['records_screened']} included={s['included_final']} "
          f"extracted={s['extracted_count']} synth_pooled={s['pooled_outcomes']}{tag}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", help="review slug; omit to list every review under results/")
    args = parser.parse_args(argv)

    if not RESULTS_ROOT.exists():
        print("No reviews found -- results/ does not exist yet. Run /litreview-init \"<topic>\" to start one.")
        return 0
    topics = sorted(d for d in RESULTS_ROOT.iterdir() if d.is_dir())
    if not topics:
        print("No reviews found under results/. Run /litreview-init \"<topic>\" to start one.")
        return 0

    if not args.topic:
        print(f"{len(topics)} review(s) under results/:\n")
        for d in topics:
            print_condensed(compute(d))
        return 0

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not topic_dir.is_dir():
        print(f"No review at results/{args.topic}/.")
        return 0
    print_full(compute(topic_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
