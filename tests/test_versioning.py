"""Unit tests for tools/versioning.py (docs/ROADMAP.md M5)."""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import ledger, path_policy, versioning


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


class VersioningTests(unittest.TestCase):
    SLUG = "versioning-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_latest_version_none_when_never_recorded(self):
        _write_json(self.topic_dir / "protocol.json", {})
        self.assertIsNone(versioning.latest_version(self.topic_dir))

    def test_record_version_refuses_without_protocol(self):
        with self.assertRaises(versioning.VersioningError):
            versioning.record_version(self.topic_dir, self.SLUG)

    def test_record_version_snapshots_canonical_records_excluding_duplicates(self):
        _write_json(self.topic_dir / "protocol.json", {})
        _write_jsonl(self.topic_dir / "records.jsonl", [
            {"record_id": "openalex:O1", "doi": "10.1/x"},
            {"record_id": "openalex:O2", "doi": "10.1/y", "duplicate_of": "openalex:O1"},
            {"record_id": "crossref:C1", "doi": "10.1/z"},
        ])
        entry = versioning.record_version(self.topic_dir, self.SLUG)
        self.assertEqual(entry["version"], 1)
        self.assertEqual(entry["n_records"], 2)
        self.assertEqual(sorted(entry["record_ids"]), ["crossref:C1", "openalex:O1"])
        self.assertEqual(entry["n_included"], 0)

    def test_record_version_counts_included_from_ledger(self):
        _write_json(self.topic_dir / "protocol.json", {})
        _write_jsonl(self.topic_dir / "records.jsonl", [{"record_id": "openalex:O1", "doi": "10.1/x"}])
        ledger.append_decisions(self.topic_dir, [
            {"record_id": "openalex:O1", "stage": "full_text", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
        ])
        entry = versioning.record_version(self.topic_dir, self.SLUG)
        self.assertEqual(entry["n_included"], 1)

    def test_second_recorded_version_increments_and_persists_both(self):
        _write_json(self.topic_dir / "protocol.json", {})
        _write_jsonl(self.topic_dir / "records.jsonl", [{"record_id": "openalex:O1", "doi": "10.1/x"}])
        versioning.record_version(self.topic_dir, self.SLUG)
        _write_jsonl(self.topic_dir / "records.jsonl", [
            {"record_id": "openalex:O1", "doi": "10.1/x"},
            {"record_id": "openalex:O2", "doi": "10.1/y"},
        ])
        second = versioning.record_version(self.topic_dir, self.SLUG)
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["n_records"], 2)
        protocol = json.loads((self.topic_dir / "protocol.json").read_text())
        self.assertEqual(len(protocol["versions"]), 2)
        self.assertEqual(versioning.latest_version(self.topic_dir)["version"], 2)


class CliTests(unittest.TestCase):
    SLUG = "versioning-cli-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(self.topic_dir / "protocol.json", {})

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_cli_record_then_latest(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = versioning.main(["--topic", self.SLUG, "record"])
        self.assertEqual(rc, 0)
        recorded = json.loads(buf.getvalue())
        self.assertEqual(recorded["version"], 1)

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = versioning.main(["--topic", self.SLUG, "latest"])
        self.assertEqual(rc2, 0)
        self.assertEqual(json.loads(buf2.getvalue())["version"], 1)

    def test_cli_refuses_for_invalid_slug(self):
        rc = versioning.main(["--topic", "../etc/passwd", "record"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
