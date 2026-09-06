#!/usr/bin/env python3
"""Dev tool, not part of the automated suite (named _build_expected.py so
tests/ discovery, which only picks up test_*.py, never runs it): (re)generates
this fixture's expected/ directory by actually running the real M5 living-
mode + pooling-unit-identity pipeline once against the frozen inputs in this
same directory.

Run from the repo root whenever a frozen input here changes, or a module's
output shape legitimately changes:

    python3 tests/fixtures/golden/chest-xray-covid-detection-benchmarks/_build_expected.py

Never hand-edit a file under expected/ -- regenerate it with this script and
let tests/test_golden_living_mode_pack_pipeline.py's own comparisons tell you
whether the change was expected.

Companion to tests/fixtures/golden/ponv-drug-a-review/ (M1, systematic
review), tests/fixtures/golden/youth-digital-literacy-scoping/ (M3, scoping
review), and tests/fixtures/golden/gig-worker-wellbeing-recon/ (M4,
reconnaissance): this is M5's golden test -- living-mode delta reruns plus
the first domain pack's pooling_unit_identity_proposal driving a real,
pack-agnostic pooling refusal.
"""
import json
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO_ROOT)

from tests.test_golden_living_mode_pack_pipeline import (
    EXPECTED_DIR, FIXTURE_DIR, SLUG, _brixia_study_entry, _living_rerun_raw, _redact_dates,
)
from synthesis import run_synthesis
from tools import build_screening_sheet, dedup, ledger, path_policy, status, versioning


def main():
    topic_dir = path_policy.RESULTS_ROOT / SLUG
    if topic_dir.exists():
        shutil.rmtree(topic_dir)
    shutil.copytree(FIXTURE_DIR, topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))

    if os.path.exists(EXPECTED_DIR):
        shutil.rmtree(EXPECTED_DIR)
    os.makedirs(EXPECTED_DIR)

    # Stage 1: first search's dedup pass
    dedup.dedupe_raw_files(topic_dir)

    # Stage 2: both studies screened in
    ledger.append_decisions(topic_dir, [
        {"record_id": "openalex:CX1", "stage": "title_abstract", "decision": "include", "reason": None,
         "ai_suggestion": None, "decided_at": "2026-01-16T00:00:00Z"},
        {"record_id": "openalex:CX2", "stage": "title_abstract", "decision": "include", "reason": None,
         "ai_suggestion": None, "decided_at": "2026-01-16T00:00:00Z"},
        {"record_id": "openalex:CX1", "stage": "full_text", "decision": "include", "reason": None,
         "ai_suggestion": None, "decided_at": "2026-01-18T00:00:00Z"},
        {"record_id": "openalex:CX2", "stage": "full_text", "decision": "include", "reason": None,
         "ai_suggestion": None, "decided_at": "2026-01-18T00:00:00Z"},
    ])

    # Stage 3: version 1
    version_1 = versioning.record_version(topic_dir, SLUG)
    with open(os.path.join(EXPECTED_DIR, "version_1.json"), "w") as f:
        json.dump(_redact_dates(version_1), f, indent=2)

    # Stage 5 (before living rerun): pools fine
    run_synthesis.run(str(topic_dir / "extraction_table.json"), str(topic_dir / "synthesis"),
                       model="fixed", identity_fields=["dataset_id", "test_split"])

    # Stage 6: living rerun's fresh raw fetch
    (topic_dir / "raw" / "openalex-20260215.json").write_text(json.dumps(_living_rerun_raw()))
    dedup.dedupe_raw_files(topic_dir)

    # Stage 7: screening candidates -- only the new record
    all_records = build_screening_sheet.load_records(topic_dir)
    latest_decisions = build_screening_sheet.load_latest_decisions(topic_dir)
    candidates = build_screening_sheet.select_candidates(all_records, latest_decisions, "title_abstract")
    with open(os.path.join(EXPECTED_DIR, "screening_candidates.json"), "w") as f:
        json.dump(sorted(r["record_id"] for r in candidates), f, indent=2)

    ledger.append_decisions(topic_dir, [
        {"record_id": "openalex:CX3", "stage": "title_abstract", "decision": "include", "reason": None,
         "ai_suggestion": None, "decided_at": "2026-02-16T00:00:00Z"},
        {"record_id": "openalex:CX3", "stage": "full_text", "decision": "include", "reason": None,
         "ai_suggestion": None, "decided_at": "2026-02-18T00:00:00Z"},
    ])
    extraction = json.loads((topic_dir / "extraction_table.json").read_text())
    extraction["studies"].append(_brixia_study_entry())
    (topic_dir / "extraction_table.json").write_text(json.dumps(extraction, indent=2))

    # Stage 8: version 2 + delta
    version_2 = versioning.record_version(topic_dir, SLUG)
    with open(os.path.join(EXPECTED_DIR, "version_2.json"), "w") as f:
        json.dump(_redact_dates(version_2), f, indent=2)
    delta = status.since_last_version(topic_dir)
    with open(os.path.join(EXPECTED_DIR, "delta.json"), "w") as f:
        json.dump(_redact_dates(delta), f, indent=2)

    # Stage 10: refused pool (cross-dataset mismatch)
    signed_plan = json.loads((topic_dir / "synthesis_plan.json").read_text())
    result_after = run_synthesis.run(str(topic_dir / "extraction_table.json"), str(topic_dir / "synthesis"),
                                      model="fixed", identity_fields=signed_plan["pooling_unit"]["identity_fields"])
    het_after = next(h for h in result_after["heterogeneity"] if h["outcome"] == "diagnostic accuracy")
    with open(os.path.join(EXPECTED_DIR, "refused_heterogeneity.json"), "w") as f:
        json.dump(het_after, f, indent=2)

    # Stage 11: backward-compatible pool (no identity_fields declared)
    result_no_identity = run_synthesis.run(str(topic_dir / "extraction_table.json"), str(topic_dir / "synthesis"), model="fixed")
    het_no_identity = next(h for h in result_no_identity["heterogeneity"] if h["outcome"] == "diagnostic accuracy")
    with open(os.path.join(EXPECTED_DIR, "backward_compatible_heterogeneity.json"), "w") as f:
        json.dump(het_no_identity, f, indent=2)

    shutil.rmtree(topic_dir)
    print(f"Wrote expected/ snapshot under {EXPECTED_DIR}")


if __name__ == "__main__":
    main()
