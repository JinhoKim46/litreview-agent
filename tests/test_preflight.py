"""Unit tests for tools/preflight.py -- the aggregator gate for
/prisma-synthesize and /prisma-report. Phase 0 correctness addition,
docs/PLAN.md decision 4.
"""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import ledger, preflight


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


class RunChecksTests(unittest.TestCase):
    """Uses a real disposable topic dir under results/ (same convention as
    tools/ledger.py, tools/search_preflight.py's own tests) since preflight
    composes those modules' file-reading logic directly."""

    SLUG = "preflight-test-topic"

    def setUp(self):
        from tools import path_policy
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            import shutil
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(self.topic_dir / "protocol.json", {})

    def tearDown(self):
        if self.topic_dir.exists():
            import shutil
            shutil.rmtree(self.topic_dir)

    def test_clean_topic_passes_report_stage(self):
        checks = preflight.run_checks(self.topic_dir, "report")
        names = {c["name"] for c in checks}
        self.assertEqual(names, {"ledger_reason_gate", "ledger_hash_chain", "search_completeness_and_recall"})
        self.assertTrue(all(c["ok"] for c in checks))

    def test_synthesize_stage_adds_plan_check_and_fails_without_one(self):
        checks = preflight.run_checks(self.topic_dir, "synthesize")
        names = {c["name"] for c in checks}
        self.assertIn("synthesis_plan_present", names)
        plan_check = next(c for c in checks if c["name"] == "synthesis_plan_present")
        self.assertFalse(plan_check["ok"])

    def test_synthesize_stage_passes_once_plan_exists(self):
        _write_json(self.topic_dir / "synthesis_plan.json", {"model": "fixed", "signed_at": "2026-01-01T00:00:00Z"})
        checks = preflight.run_checks(self.topic_dir, "synthesize")
        plan_check = next(c for c in checks if c["name"] == "synthesis_plan_present")
        self.assertTrue(plan_check["ok"])

    def test_synthesize_stage_skips_plan_check_for_a_method_that_never_pools(self):
        # A real bug found while building M3's scoping-review golden fixture
        # (tests/test_golden_scoping_pipeline.py): scoping_review's
        # synthesis.plan_required_for is [] (pooling forbidden by design),
        # so it can never satisfy this check -- it must be skipped, not
        # fail every such review forever.
        _write_json(self.topic_dir / "protocol.json", {"method": {"id": "scoping_review"}})
        checks = preflight.run_checks(self.topic_dir, "synthesize")
        names = {c["name"] for c in checks}
        self.assertNotIn("synthesis_plan_present", names)
        self.assertTrue(all(c["ok"] for c in checks))

    def test_ledger_reason_gate_failure_surfaces(self):
        ledger.append_decisions(self.topic_dir, [
            {"record_id": "r1", "stage": "full_text", "decision": "exclude", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
        ])
        checks = preflight.run_checks(self.topic_dir, "report")
        gate_check = next(c for c in checks if c["name"] == "ledger_reason_gate")
        self.assertFalse(gate_check["ok"])
        self.assertEqual(gate_check["detail"], [{"record_id": "r1", "decision": "exclude"}])

    def test_tampered_ledger_fails_hash_chain_check(self):
        ledger.append_decisions(self.topic_dir, [
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
        ])
        path = self.topic_dir / "screening_decisions.jsonl"
        lines = path.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["decision"] = "exclude"  # tamper after hashing
        path.write_text(json.dumps(entry) + "\n")
        checks = preflight.run_checks(self.topic_dir, "report")
        chain_check = next(c for c in checks if c["name"] == "ledger_hash_chain")
        self.assertFalse(chain_check["ok"])

    def test_unacknowledged_search_gap_surfaces(self):
        _write_json(self.topic_dir / "search_plan.json", {"sources": {"openalex": {"query_string": "x"}}})
        checks = preflight.run_checks(self.topic_dir, "report")
        search_check = next(c for c in checks if c["name"] == "search_completeness_and_recall")
        self.assertFalse(search_check["ok"])
        self.assertIn("openalex", search_check["detail"]["unacknowledged_incomplete_sources"])


class MainCliTests(unittest.TestCase):
    SLUG = "preflight-cli-test-topic"

    def setUp(self):
        from tools import path_policy
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            import shutil
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(self.topic_dir / "protocol.json", {})

    def tearDown(self):
        if self.topic_dir.exists():
            import shutil
            shutil.rmtree(self.topic_dir)

    def test_report_stage_passes_on_clean_topic(self):
        rc = preflight.main(["--topic", self.SLUG, "--stage", "report"])
        self.assertEqual(rc, 0)

    def test_synthesize_stage_fails_without_plan(self):
        rc = preflight.main(["--topic", self.SLUG, "--stage", "synthesize"])
        self.assertEqual(rc, 1)

    def test_unsafe_slug_rejected(self):
        rc = preflight.main(["--topic", "Bad Slug", "--stage", "report"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
