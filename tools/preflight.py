#!/usr/bin/env python3
"""One aggregator gate for /prisma-synthesize and /prisma-report: runs
every deterministic Phase 0 gate in a single call and prints a pass/fail
checklist, so neither command has to remember which script to call in
which order, or interpret each one's exit code separately.

Idea from O0000-code/meta-analysis-skill's exit-code sign-off gates
(docs/PLAN.md "Landscape") -- reimplemented from scratch here rather than
vendored, since that project's own code is PolyForm-Noncommercial licensed
and this repo is not.

Usage:
    python3 tools/preflight.py --topic <slug> --stage synthesize|report

Checks (both stages): the screening ledger's Item 16b reason gate, the
ledger's hash-chain integrity, and search completeness / known-item recall
(docs/PLAN.md decision 4 / tools/search_preflight.py). `--stage synthesize`
additionally checks that a synthesis_plan.json exists, but only when the
resolved method manifest's synthesis.plan_required_for is non-empty
(synthesis/run_synthesis.py will refuse to pool anything without one or an
explicit --model override, but failing this early -- before
/prisma-extract's own work -- saves a wasted extraction pass). A method
that never pools at all (docs/PLAN.md M3: scoping_review,
systematic_mapping_study -- synthesis.plan_required_for: []) has nothing
this check could ever require, so it is skipped entirely rather than
failing every such review forever: a real bug found and fixed while
building M3's scoping-review golden fixture (tests/test_golden_scoping_
pipeline.py), which otherwise had no synthesis_plan.json to ever satisfy
this check with.

Exit code 0 if every check passes, 1 if any fails (each failing check's
name and detail are printed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import ledger, search_preflight  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


def run_checks(topic_dir, stage):
    topic_dir = Path(topic_dir)
    checks = []

    entries = ledger.load_ledger(topic_dir)
    latest = ledger.latest_decisions(entries)
    reason_gate_missing = ledger.full_text_reason_required_missing(latest)
    checks.append({
        "name": "ledger_reason_gate", "ok": not reason_gate_missing,
        "detail": [{"record_id": rid, "decision": e["decision"]} for rid, e in reason_gate_missing] or None,
    })

    verify_result = ledger.verify_chain(entries)
    checks.append({"name": "ledger_hash_chain", "ok": verify_result["ok"], "detail": None if verify_result["ok"] else verify_result})

    status = search_preflight.search_status(topic_dir)
    search_ok = not status["unacknowledged_incomplete_sources"] and not status["unacknowledged_missing_known_items"]
    checks.append({
        "name": "search_completeness_and_recall", "ok": search_ok,
        "detail": None if search_ok else {
            "unacknowledged_incomplete_sources": status["unacknowledged_incomplete_sources"],
            "unacknowledged_missing_known_items": status["unacknowledged_missing_known_items"],
        },
    })

    if stage == "synthesize" and _method_ever_requires_a_plan(topic_dir):
        plan_exists = (topic_dir / "synthesis_plan.json").exists()
        checks.append({
            "name": "synthesis_plan_present", "ok": plan_exists,
            "detail": None if plan_exists else (
                "no synthesis_plan.json -- run_synthesis.py will refuse to pool anything without "
                "one or an explicit --model override (see review-protocol/SKILL.md Phase 1 step 5)"
            ),
        })

    return checks


def _method_ever_requires_a_plan(topic_dir) -> bool:
    """Whether this topic's resolved method manifest can ever need a
    synthesis_plan.json at all (synthesis.plan_required_for non-empty).
    Methods that never pool (scoping_review, systematic_mapping_study --
    synthesis.plan_required_for: []) have nothing this check could require;
    treated as "not applicable", never as a failure. Falls back to True on
    any resolution error (an unresolvable/legacy topic keeps today's
    fail-closed behavior rather than silently skipping the check)."""
    from tools.method import MethodError
    from tools.method import resolve as resolve_method

    try:
        manifest = resolve_method(Path(topic_dir).name)["manifest"]
    except MethodError:
        return True
    return bool(manifest["synthesis"].get("plan_required_for"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="review slug; derives results/<topic>/ itself")
    parser.add_argument("--stage", required=True, choices=["synthesize", "report"])
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    checks = run_checks(topic_dir, args.stage)
    for check in checks:
        mark = "✓" if check["ok"] else "✗"
        print(f"{mark} {check['name']}")
        if not check["ok"]:
            print(f"    {json.dumps(check['detail'], indent=2, default=str)}")

    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
