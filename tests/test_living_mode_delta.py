"""Unit tests locking in docs/ROADMAP.md M5's "a delta run screens only
new records" guarantee as a documented, tested contract -- not a new
mechanism (tools/dedup.py's dedup pass was already record_id-idempotent,
and tools/build_screening_sheet.py already exports only undecided
records per stage), but this milestone's exit criterion depends on it, so
it is pinned here explicitly rather than left as an implicit side effect
of two other modules' own tests.
"""
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import build_screening_sheet, dedup, ledger, path_policy, versioning


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_raw(topic_dir, filename, records):
    path = Path(topic_dir) / "raw" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {"source": filename.split("-")[0], "query": "x", "retrieved": len(records),
                  "total_available": len(records), "truncated": False, "fetched_at": "2026-01-01T00:00:00Z"},
        "results": records,
    }
    path.write_text(json.dumps(payload))


class LivingModeDeltaTests(unittest.TestCase):
    SLUG = "living-mode-delta-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(self.topic_dir / "protocol.json", {})

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_second_dedup_pass_only_adds_genuinely_new_records(self):
        _write_raw(self.topic_dir, "openalex-20260101.json", [
            {"id": "O1", "doi": "10.1/a"}, {"id": "O2", "doi": "10.1/b"},
        ])
        dedup.dedupe_raw_files(self.topic_dir)
        with open(self.topic_dir / "records.jsonl") as f:
            first_pass = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(first_pass), 2)

        version_1 = versioning.record_version(self.topic_dir, self.SLUG)
        self.assertEqual(version_1["n_records"], 2)

        # a later "living" raw fetch re-returns the same two records (the
        # connector's own idempotent behavior) plus one genuinely new one --
        # only the new one should ever be appended.
        _write_raw(self.topic_dir, "openalex-20260201.json", [
            {"id": "O1", "doi": "10.1/a"}, {"id": "O2", "doi": "10.1/b"}, {"id": "O3", "doi": "10.1/c"},
        ])
        dedup.dedupe_raw_files(self.topic_dir)
        with open(self.topic_dir / "records.jsonl") as f:
            second_pass = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(second_pass), 3)  # not 5 -- O1/O2 were never re-appended

        version_2 = versioning.record_version(self.topic_dir, self.SLUG)
        self.assertEqual(version_2["version"], 2)
        self.assertEqual(version_2["n_records"], 3)
        new_since_v1 = set(version_2["record_ids"]) - set(version_1["record_ids"])
        self.assertEqual(new_since_v1, {"openalex:O3"})

    def test_screening_export_only_ever_surfaces_the_delta(self):
        # tools/build_screening_sheet.py already exports only undecided
        # records per stage -- a record screened before version 1 stays
        # decided and is never re-surfaced after a living rerun adds more.
        _write_raw(self.topic_dir, "openalex-20260101.json", [{"id": "O1", "doi": "10.1/a"}])
        dedup.dedupe_raw_files(self.topic_dir)
        ledger.append_decisions(self.topic_dir, [
            {"record_id": "openalex:O1", "stage": "title_abstract", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
        ])
        versioning.record_version(self.topic_dir, self.SLUG)

        _write_raw(self.topic_dir, "openalex-20260201.json", [
            {"id": "O1", "doi": "10.1/a"}, {"id": "O2", "doi": "10.1/b"},
        ])
        dedup.dedupe_raw_files(self.topic_dir)

        records = build_screening_sheet.load_records(self.topic_dir)
        latest = build_screening_sheet.load_latest_decisions(self.topic_dir)
        undecided = build_screening_sheet.select_candidates(records, latest, "title_abstract")
        undecided_ids = {r["record_id"] for r in undecided}
        self.assertEqual(undecided_ids, {"openalex:O2"})  # O1 already decided, never re-surfaced


if __name__ == "__main__":
    unittest.main()
