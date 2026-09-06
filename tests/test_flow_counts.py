"""Unit tests for tools/flow_counts.py -- PRISMA flow-diagram box counts,
including the reports_not_retrieved box the decision enum's "not_retrieved"
value (docs/PLAN.md decision 4) makes computable that the original inline
heredoc in .claude/commands/litreview-report.md documented as impossible.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import flow_counts, ledger


def _write_raw(topic_dir, filename, source, retrieved, total_available, truncated=False):
    raw_dir = Path(topic_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with open(raw_dir / filename, "w") as f:
        json.dump({"meta": {"source": source, "retrieved": retrieved, "total_available": total_available,
                             "truncated": truncated, "fetched_at": "2026-01-01T00:00:00Z"}, "results": []}, f)


def _write_records(topic_dir, records):
    with open(Path(topic_dir) / "records.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class FlowCountsTests(unittest.TestCase):
    def test_full_pipeline_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "openalex-20260101.json", "openalex", retrieved=10, total_available=10)
            _write_raw(tmp, "crossref-20260101.json", "crossref", retrieved=5, total_available=8, truncated=True)
            _write_records(tmp, [
                {"record_id": "a:1", "duplicate_of": None},
                {"record_id": "a:2", "duplicate_of": "a:1"},  # duplicate
                {"record_id": "a:3", "duplicate_of": None},
                {"record_id": "a:4", "duplicate_of": None},
                {"record_id": "a:5", "duplicate_of": None},
            ])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "exclude", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:3", "stage": "title_abstract", "decision": "include", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:4", "stage": "title_abstract", "decision": "include", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:5", "stage": "title_abstract", "decision": "include", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:3", "stage": "full_text", "decision": "include", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
                {"record_id": "a:4", "stage": "full_text", "decision": "exclude", "reason": "wrong population", "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
                # a:5 sought but not yet full-text decided -> pending_full_text
            ])
            counts = flow_counts.flow_counts(tmp)

            self.assertEqual(counts["identified_total"], 15)
            self.assertEqual(counts["truncated_sources"], ["crossref"])
            self.assertEqual(counts["duplicates_removed"], 1)
            self.assertEqual(counts["records_screened"], 4)
            self.assertEqual(counts["excluded_title_abstract"], 1)
            self.assertEqual(counts["sought_for_retrieval"], 3)
            self.assertEqual(counts["reports_not_retrieved"], 0)
            self.assertEqual(counts["assessed_for_eligibility"], 2)
            self.assertEqual(counts["pending_full_text"], 1)
            self.assertEqual(counts["excluded_full_text_total"], 1)
            self.assertEqual(counts["excluded_full_text_reasons"], {"wrong population": 1})
            self.assertEqual(counts["included_final"], 1)
            self.assertEqual(counts["full_text_excludes_missing_reason"], [])

    def test_not_retrieved_excluded_from_assessed_and_needs_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "not_retrieved", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            counts = flow_counts.flow_counts(tmp)
            self.assertEqual(counts["reports_not_retrieved"], 1)
            self.assertEqual(counts["assessed_for_eligibility"], 0)
            self.assertEqual(counts["pending_full_text"], 0)
            self.assertEqual(counts["full_text_excludes_missing_reason"], ["a:1"])

    def test_not_retrieved_with_reason_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "not_retrieved", "reason": "paywalled, no institutional access", "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            counts = flow_counts.flow_counts(tmp)
            self.assertEqual(counts["full_text_excludes_missing_reason"], [])

    def test_empty_topic_has_zero_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts = flow_counts.flow_counts(tmp)
            self.assertEqual(counts["identified_total"], 0)
            self.assertEqual(counts["records_screened"], 0)
            self.assertEqual(counts["sought_for_retrieval"], 0)
            self.assertEqual(counts["reports_not_retrieved"], 0)


class MainCliTests(unittest.TestCase):
    SLUG = "flow-counts-cli-test-topic"

    def setUp(self):
        from tools import path_policy
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            import shutil
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            import shutil
            shutil.rmtree(self.topic_dir)

    def test_cli_runs_on_empty_topic(self):
        rc = flow_counts.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)

    def test_unsafe_slug_rejected(self):
        rc = flow_counts.main(["--topic", "Bad Slug"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
