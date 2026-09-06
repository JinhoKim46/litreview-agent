"""Unit tests for tools/relevance_tags_gate.py (docs/ROADMAP.md M4)."""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import path_policy, relevance_tags_gate


class LoadTableTests(unittest.TestCase):
    SLUG = "relevance-tags-gate-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_missing_file_returns_fresh_empty_table(self):
        table = relevance_tags_gate.load_relevance_tags_table(self.topic_dir, self.SLUG)
        self.assertEqual(table["studies"], [])
        self.assertEqual(table["topic"], self.SLUG)

    def test_invalid_json_raises(self):
        (self.topic_dir / "relevance_tags_table.json").write_text("{not json")
        with self.assertRaises(relevance_tags_gate.RelevanceTagsGateError):
            relevance_tags_gate.load_relevance_tags_table(self.topic_dir, self.SLUG)


class AlreadyTaggedTests(unittest.TestCase):
    def test_known_record_id_is_flagged(self):
        table = {"studies": [{"record_id": "r1", "facet_tags": ["population"], "by": "x"}]}
        self.assertTrue(relevance_tags_gate.already_tagged(table, "r1"))
        self.assertFalse(relevance_tags_gate.already_tagged(table, "r2"))

    def test_empty_table_flags_nothing(self):
        self.assertFalse(relevance_tags_gate.already_tagged({"studies": []}, "r1"))


class CorpusDescriptionTests(unittest.TestCase):
    def test_tallies_facet_tags_across_rows(self):
        table = {"studies": [
            {"record_id": "r1", "facet_tags": ["population", "method"], "by": "x"},
            {"record_id": "r2", "facet_tags": ["population"], "by": "x"},
            {"record_id": "r3", "facet_tags": [], "by": "x"},
        ]}
        self.assertEqual(relevance_tags_gate.corpus_description(table), {"population": 2, "method": 1})

    def test_empty_table_yields_empty_counts(self):
        self.assertEqual(relevance_tags_gate.corpus_description({"studies": []}), {})


class CliTests(unittest.TestCase):
    SLUG = "relevance-tags-gate-cli-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        table = {
            "framework_version": "1.0.0", "topic": self.SLUG,
            "studies": [{"record_id": "r1", "facet_tags": ["population"], "by": "x"}],
        }
        (self.topic_dir / "relevance_tags_table.json").write_text(json.dumps(table))

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_cli_default_prints_corpus_description(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = relevance_tags_gate.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)
        printed = json.loads(buf.getvalue())
        self.assertEqual(printed["n_tagged"], 1)
        self.assertEqual(printed["corpus_description"], {"population": 1})

    def test_cli_check_record_id_ok_for_new_record(self):
        rc = relevance_tags_gate.main(["--topic", self.SLUG, "--check-record-id", "r2"])
        self.assertEqual(rc, 0)

    def test_cli_check_record_id_refuses_duplicate(self):
        rc = relevance_tags_gate.main(["--topic", self.SLUG, "--check-record-id", "r1"])
        self.assertEqual(rc, 1)

    def test_cli_refuses_for_invalid_slug(self):
        rc = relevance_tags_gate.main(["--topic", "../etc/passwd"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
