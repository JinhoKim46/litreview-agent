#!/usr/bin/env python3
"""Dev tool, not part of the automated suite (tests/ discovery only picks
up test_*.py -- this is named _build_expected.py precisely so it never
runs as a test): (re)generates this fixture's expected/ directory by
actually running the full pipeline once against the frozen inputs in this
same directory.

Run from the repo root whenever the frozen INPUT files here change, or a
Phase 0 module's output shape legitimately changes:

    python3 tests/fixtures/golden/ponv-drug-a-review/_build_expected.py

Never hand-edit a file under expected/ -- regenerate it with this script
and let tests/test_golden_pipeline.py's own byte/hash comparisons tell you
whether the change was expected.

Reuses tests/test_golden_pipeline.py's own SLUG constant and normalization
helpers so the fixture this script writes and the test that reads it back
can never drift out of sync with each other.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO_ROOT)

from synthesis import run_synthesis
from tests.test_golden_pipeline import EXPECTED_DIR, FIXTURE_DIR, SLUG, _normalize_possible_duplicates, _normalize_svg_paths
from tools import dedup, flow_counts, ledger, path_policy, preflight, search_preflight


def main():
    topic_dir = path_policy.RESULTS_ROOT / SLUG
    if topic_dir.exists():
        shutil.rmtree(topic_dir)
    shutil.copytree(FIXTURE_DIR, topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))

    if os.path.exists(EXPECTED_DIR):
        shutil.rmtree(EXPECTED_DIR)
    os.makedirs(os.path.join(EXPECTED_DIR, "synthesis"))

    # Stage 1: dedup (exact + fuzzy)
    dedup.dedupe_raw_files(topic_dir)
    dedup.flag_near_duplicates(topic_dir)

    # Stage 2: ledger gate + candidates + verify (captured as JSON -- these
    # are stdout-only in the real CLI, no on-disk artifact of their own)
    entries = ledger.load_ledger(topic_dir)
    latest = ledger.latest_decisions(entries)
    gate_missing = ledger.full_text_reason_required_missing(latest)
    n_full_text_includes = sum(1 for (_, stage), e in latest.items() if stage == "full_text" and e["decision"] == "include")
    with open(os.path.join(EXPECTED_DIR, "ledger_gate.json"), "w") as f:
        json.dump({"missing_reason": gate_missing, "n_full_text_includes": n_full_text_includes}, f, indent=2)

    with open(topic_dir / "records.jsonl") as f:
        records = [json.loads(l) for l in f if l.strip()]
    records_by_id = {r["record_id"]: r for r in records if r.get("duplicate_of") is None}
    with open(topic_dir / "extraction_table.json") as f:
        extracted_ids = {s["record_id"] for s in json.load(f)["studies"]}
    candidates = ledger.candidate_set(records_by_id, latest, extracted_ids)
    with open(os.path.join(EXPECTED_DIR, "ledger_candidates.json"), "w") as f:
        json.dump(candidates, f, indent=2)

    verify_result = ledger.verify_chain(entries)
    with open(os.path.join(EXPECTED_DIR, "ledger_verify.json"), "w") as f:
        json.dump(verify_result, f, indent=2)

    # Stage 3: flow counts (stdout-only -- capture the dict)
    fc = flow_counts.flow_counts(topic_dir)
    with open(os.path.join(EXPECTED_DIR, "flow_counts.json"), "w") as f:
        json.dump(fc, f, indent=2)

    # Stage 4: search preflight (writes search_status.json itself)
    status = search_preflight.search_status(topic_dir)
    with open(topic_dir / "search_status.json", "w") as f:
        json.dump(status, f, indent=2)

    # Stage 5: aggregated preflight (both stages, stdout-only -- capture)
    with open(os.path.join(EXPECTED_DIR, "preflight_synthesize.json"), "w") as f:
        json.dump(preflight.run_checks(topic_dir, "synthesize"), f, indent=2)
    with open(os.path.join(EXPECTED_DIR, "preflight_report.json"), "w") as f:
        json.dump(preflight.run_checks(topic_dir, "report"), f, indent=2)

    # Stage 6: run_synthesis
    stderr = io.StringIO()
    synth_out_dir = topic_dir / "synthesis"
    with contextlib.redirect_stderr(stderr):
        plan = run_synthesis.resolve_synthesis_plan(SLUG, None, path_policy.safe_topic_path)
        run_synthesis.run(
            str(topic_dir / "extraction_table.json"), str(synth_out_dir),
            model=plan["model"], model_source=plan["model_source"], k_min=plan["k_min"],
            tau2_estimator=plan["tau2_estimator"], ci_method=plan["ci_method"],
        )
    with open(os.path.join(EXPECTED_DIR, "stderr_warnings.txt"), "w") as f:
        f.write(stderr.getvalue())

    # Copy the deterministic on-disk outputs into expected/ (SVGs excluded
    # from the frozen set -- matplotlib's SVG output is not guaranteed
    # byte-identical across matplotlib versions/fonts).
    shutil.copy(topic_dir / "records.jsonl", os.path.join(EXPECTED_DIR, "records.jsonl"))
    shutil.copy(topic_dir / "search_status.json", os.path.join(EXPECTED_DIR, "search_status.json"))
    dup_path = topic_dir / "possible_duplicates.jsonl"
    if dup_path.exists():
        shutil.copy(dup_path, os.path.join(EXPECTED_DIR, "possible_duplicates.jsonl"))
        normalized = _normalize_possible_duplicates(os.path.join(EXPECTED_DIR, "possible_duplicates.jsonl"))
        with open(os.path.join(EXPECTED_DIR, "possible_duplicates.jsonl"), "w") as f:
            f.write(normalized or "")

    with open(synth_out_dir / "effect_sizes.json") as f:
        effect_sizes = _normalize_svg_paths(json.load(f), str(topic_dir))
    with open(os.path.join(EXPECTED_DIR, "synthesis", "effect_sizes.json"), "w") as f:
        json.dump(effect_sizes, f, indent=2)
    for name in ("heterogeneity.json", "rob_table.json", "grade_table.json"):
        shutil.copy(synth_out_dir / name, os.path.join(EXPECTED_DIR, "synthesis", name))

    # sha256 manifest of every frozen expected/ file (sha256sum-compatible format).
    manifest_lines = []
    for root, _dirs, files in sorted(os.walk(EXPECTED_DIR)):
        for name in sorted(files):
            if name == "manifest.sha256":
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, EXPECTED_DIR)
            with open(full, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            manifest_lines.append(f"{digest}  {rel}")
    with open(os.path.join(EXPECTED_DIR, "manifest.sha256"), "w") as f:
        f.write("\n".join(sorted(manifest_lines)) + "\n")

    shutil.rmtree(topic_dir)
    print(f"Wrote {len(manifest_lines)} expected files + manifest.sha256 under {EXPECTED_DIR}")


if __name__ == "__main__":
    main()
