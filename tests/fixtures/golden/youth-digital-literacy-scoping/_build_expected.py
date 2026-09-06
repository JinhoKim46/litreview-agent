#!/usr/bin/env python3
"""Dev tool, not part of the automated suite (named _build_expected.py so
tests/ discovery, which only picks up test_*.py, never runs it): (re)generates
this fixture's expected/ directory by actually running the real scoping-review
pipeline once against the frozen inputs in this same directory.

Run from the repo root whenever a frozen input here changes, or a module's
output shape legitimately changes:

    python3 tests/fixtures/golden/youth-digital-literacy-scoping/_build_expected.py

Never hand-edit a file under expected/ -- regenerate it with this script and
let tests/test_golden_scoping_pipeline.py's own comparisons tell you whether
the change was expected.

Companion to tests/fixtures/golden/ponv-drug-a-review/ (docs/PLAN.md M1's
systematic-review golden fixture): this is M3's "second golden test" --
docs/PLAN.md M3's exit criterion -- for method.id: scoping_review, covering
what M1's fixture cannot: charting-mode capture, the freeze gate, the
descriptive-synthesis dispatch (pooling refused, not chosen), and a
not_retrieved full-text record with its own PRISMA flow box.
"""
import json
import os
import shutil
import sys
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO_ROOT)

from tests.test_golden_scoping_pipeline import EXPECTED_DIR, FIXTURE_DIR, SLUG, _normalize_topic_dir
from tools import charting_gate, dedup, flow_counts, label_gate, ledger, path_policy, preflight, search_preflight


def main():
    topic_dir = path_policy.RESULTS_ROOT / SLUG
    if topic_dir.exists():
        shutil.rmtree(topic_dir)
    shutil.copytree(FIXTURE_DIR, topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))

    if os.path.exists(EXPECTED_DIR):
        shutil.rmtree(EXPECTED_DIR)
    os.makedirs(EXPECTED_DIR)

    # Stage 1: dedup (no planted duplicates in this fixture -- already
    # exercised thoroughly by the M1 fixture; this one's job is the
    # scoping-specific stages below).
    dedup.dedupe_raw_files(topic_dir)

    # Stage 2: ledger gate + verify
    entries = ledger.load_ledger(topic_dir)
    latest = ledger.latest_decisions(entries)
    gate_missing = ledger.full_text_reason_required_missing(latest)
    with open(os.path.join(EXPECTED_DIR, "ledger_gate.json"), "w") as f:
        json.dump({"missing_reason": gate_missing}, f, indent=2)
    verify_result = ledger.verify_chain(entries)
    with open(os.path.join(EXPECTED_DIR, "ledger_verify.json"), "w") as f:
        json.dump(verify_result, f, indent=2)

    # Stage 3: flow counts (must show the not_retrieved record in its own box)
    fc = flow_counts.flow_counts(topic_dir)
    with open(os.path.join(EXPECTED_DIR, "flow_counts.json"), "w") as f:
        json.dump(fc, f, indent=2)

    # Stage 4: search preflight
    status = search_preflight.search_status(topic_dir)
    with open(topic_dir / "search_status.json", "w") as f:
        json.dump(status, f, indent=2)

    # Stage 5: aggregated preflight (report stage only -- "synthesize" stage's
    # synthesis_plan_present check assumes pooling applies to every method,
    # which a scoping review never does; a real, separate gap, not this
    # fixture's job to paper over).
    with open(os.path.join(EXPECTED_DIR, "preflight_report.json"), "w") as f:
        json.dump(preflight.run_checks(topic_dir, "report"), f, indent=2)

    # Stage 6: charting freeze-gate verification (no drift)
    table = charting_gate.load_charting_table(topic_dir, SLUG)
    offending = charting_gate.verify_table(table)
    with open(os.path.join(EXPECTED_DIR, "charting_verify.json"), "w") as f:
        json.dump({"offending_record_ids": offending}, f, indent=2)

    # Stage 7: run_synthesis's real CLI dispatch (descriptive, pooling refused)
    with mock.patch.object(sys, "argv", ["run_synthesis.py", "--topic", SLUG]):
        from synthesis import run_synthesis
        import io
        import contextlib

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = run_synthesis.main()
    with open(os.path.join(EXPECTED_DIR, "run_synthesis_cli.json"), "w") as f:
        json.dump({"rc": rc, "stdout": _normalize_topic_dir(stdout.getvalue(), str(topic_dir))}, f, indent=2)
    shutil.copy(topic_dir / "synthesis" / "descriptive_summary.json", os.path.join(EXPECTED_DIR, "descriptive_summary.json"))

    # Stage 8: label + blockers (the M3 exit criterion's "zero label_gate
    # blockers" check)
    label_result = label_gate.compute_label(SLUG)
    with open(os.path.join(EXPECTED_DIR, "label.json"), "w") as f:
        json.dump(label_result, f, indent=2)
    blockers = label_gate.compute_blockers(SLUG)
    with open(os.path.join(EXPECTED_DIR, "blockers.json"), "w") as f:
        json.dump(blockers, f, indent=2)

    shutil.copy(topic_dir / "records.jsonl", os.path.join(EXPECTED_DIR, "records.jsonl"))
    shutil.copy(topic_dir / "search_status.json", os.path.join(EXPECTED_DIR, "search_status.json"))

    shutil.rmtree(topic_dir)
    print(f"Wrote expected/ snapshot under {EXPECTED_DIR}")


if __name__ == "__main__":
    main()
