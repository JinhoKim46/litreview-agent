"""Unit tests for tools/search_preflight.py -- source completeness status
and known-item recall. Phase 0 correctness addition, docs/PLAN.md
decision 4.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import search_preflight


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _write_raw(topic_dir, filename, source, retrieved, total_available, truncated=False):
    _write_json(Path(topic_dir) / "raw" / filename, {
        "meta": {"source": source, "retrieved": retrieved, "total_available": total_available,
                  "truncated": truncated, "fetched_at": "2026-01-01T00:00:00Z"},
        "results": [],
    })


class SourceCompletenessTests(unittest.TestCase):
    def test_no_search_plan_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(search_preflight.source_completeness(tmp), {})

    def test_missing_raw_file_is_missing_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "search_plan.json", {"sources": {"openalex": {"query_string": "x"}}})
            statuses = search_preflight.source_completeness(tmp)
            self.assertEqual(statuses["openalex"]["status"], "missing")

    def test_truncated_raw_file_is_truncated_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "search_plan.json", {"sources": {"crossref": {"query_string": "x"}}})
            _write_raw(tmp, "crossref-20260101.json", "crossref", retrieved=5, total_available=20, truncated=True)
            statuses = search_preflight.source_completeness(tmp)
            self.assertEqual(statuses["crossref"]["status"], "truncated")
            self.assertEqual(statuses["crossref"]["total_available"], 20)

    def test_complete_raw_file_is_complete_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "search_plan.json", {"sources": {"pubmed": {"query_string": "x"}}})
            _write_raw(tmp, "pubmed-20260101.json", "pubmed", retrieved=10, total_available=10)
            statuses = search_preflight.source_completeness(tmp)
            self.assertEqual(statuses["pubmed"]["status"], "complete")

    def test_disabled_source_is_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "search_plan.json", {"sources": {"arxiv": {"query_string": "x", "enabled": False}}})
            statuses = search_preflight.source_completeness(tmp)
            self.assertEqual(statuses, {})


class UnacknowledgedIncompleteSourcesTests(unittest.TestCase):
    def test_missing_source_flagged_without_coverage_gap(self):
        statuses = {"arxiv": {"status": "missing"}}
        self.assertEqual(list(search_preflight.unacknowledged_incomplete_sources(statuses, [])), ["arxiv"])

    def test_acknowledged_source_not_flagged(self):
        statuses = {"arxiv": {"status": "missing"}}
        gaps = [{"source": "arxiv", "gap": "STEM preprints only", "mitigation": "excluded"}]
        self.assertEqual(search_preflight.unacknowledged_incomplete_sources(statuses, gaps), {})

    def test_complete_source_never_flagged(self):
        statuses = {"openalex": {"status": "complete"}}
        self.assertEqual(search_preflight.unacknowledged_incomplete_sources(statuses, []), {})


class KnownItemRecallTests(unittest.TestCase):
    def _write_records(self, tmp, records):
        with open(Path(tmp) / "records.jsonl", "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_no_known_items_returns_zero_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {})
            result = search_preflight.known_item_recall(tmp)
            self.assertEqual(result["checked"], 0)

    def test_doi_known_item_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {"known_items": [{"id_type": "doi", "id": "https://doi.org/10.1/x"}]})
            self._write_records(tmp, [{"record_id": "crossref:10.1/x", "doi": "10.1/x"}])
            result = search_preflight.known_item_recall(tmp)
            self.assertEqual(len(result["found"]), 1)
            self.assertEqual(result["found"][0]["matched_record_id"], "crossref:10.1/x")
            self.assertEqual(result["missing"], [])

    def test_pmid_known_item_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {"known_items": [{"id_type": "pmid", "id": "555"}]})
            self._write_records(tmp, [{"record_id": "pubmed:555", "source": "pubmed", "doi": None}])
            result = search_preflight.known_item_recall(tmp)
            self.assertEqual(len(result["found"]), 1)

    def test_missing_known_item_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {"known_items": [{"id_type": "doi", "id": "10.1/missing", "note": "seminal paper"}]})
            self._write_records(tmp, [])
            result = search_preflight.known_item_recall(tmp)
            self.assertEqual(len(result["missing"]), 1)
            self.assertEqual(result["missing"][0]["note"], "seminal paper")

    def test_expected_missing_reason_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {"known_items": [
                {"id_type": "doi", "id": "10.1/grey", "expected_missing_reason": "grey literature, not indexed"},
            ]})
            self._write_records(tmp, [])
            result = search_preflight.known_item_recall(tmp)
            self.assertEqual(result["missing"][0]["expected_missing_reason"], "grey literature, not indexed")

    def test_unrecognized_id_type_reported_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {"known_items": [{"id_type": "isbn", "id": "123"}]})
            self._write_records(tmp, [])
            result = search_preflight.known_item_recall(tmp)
            self.assertEqual(len(result["missing"]), 1)


class SearchStatusTests(unittest.TestCase):
    def test_unacknowledged_missing_known_items_excludes_justified_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {"known_items": [
                {"id_type": "doi", "id": "10.1/a"},
                {"id_type": "doi", "id": "10.1/b", "expected_missing_reason": "not indexed anywhere"},
            ]})
            with open(Path(tmp) / "records.jsonl", "w"):
                pass
            status = search_preflight.search_status(tmp)
            missing_ids = {i["id"] for i in status["unacknowledged_missing_known_items"]}
            self.assertEqual(missing_ids, {"10.1/a"})

    def test_all_clean_topic_has_no_unacknowledged_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_json(Path(tmp) / "protocol.json", {})
            status = search_preflight.search_status(tmp)
            self.assertEqual(status["unacknowledged_incomplete_sources"], [])
            self.assertEqual(status["unacknowledged_missing_known_items"], [])


class MainCliTests(unittest.TestCase):
    SLUG = "search-preflight-cli-test-topic"

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

    def test_cli_writes_search_status_json(self):
        _write_json(self.topic_dir / "protocol.json", {})
        rc = search_preflight.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)
        self.assertTrue((self.topic_dir / "search_status.json").exists())

    def test_cli_fails_on_unacknowledged_gap(self):
        _write_json(self.topic_dir / "search_plan.json", {"sources": {"openalex": {"query_string": "x"}}})
        rc = search_preflight.main(["--topic", self.SLUG])
        self.assertEqual(rc, 1)

    def test_unsafe_slug_rejected(self):
        rc = search_preflight.main(["--topic", "Bad Slug"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
