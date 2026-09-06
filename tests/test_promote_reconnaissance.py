"""Unit tests for tools/promote_reconnaissance.py (docs/ROADMAP.md M4)."""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import path_policy, promote_reconnaissance


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


class PromoteTests(unittest.TestCase):
    SLUG = "promote-reconnaissance-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def _seed_recon_topic(self):
        _write_json(self.topic_dir / "protocol.json", {"method": {"id": "reconnaissance"}})
        _write_jsonl(self.topic_dir / "records.jsonl", [
            {"record_id": "crossref:10.1/x", "doi": "10.1/x"},
            {"record_id": "openalex:W1", "doi": None},
        ])
        (self.topic_dir / "raw").mkdir()
        (self.topic_dir / "raw" / "crossref-20260101.json").write_text("{}")
        _write_json(self.topic_dir / "relevance_tags_table.json", {
            "framework_version": "1.0.0", "topic": self.SLUG,
            "studies": [
                {"record_id": "crossref:10.1/x", "facet_tags": ["population"],
                 "claim": {"quote": "x", "page": "1", "hash": None}, "by": "claude"},
                {"record_id": "openalex:W1", "facet_tags": ["method"], "claim": None, "by": "claude"},
            ],
        })
        _write_json(self.topic_dir / "search_plan.json", {"sources": {"crossref": {"query_string": "term1 AND term2"}}})

    def test_refuses_non_reconnaissance_topic(self):
        _write_json(self.topic_dir / "protocol.json", {"method": {"id": "scoping_review"}})
        with self.assertRaises(promote_reconnaissance.PromotionError):
            promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason")

    def test_refuses_missing_protocol(self):
        with self.assertRaises(promote_reconnaissance.PromotionError):
            promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason")

    def test_refuses_double_promotion(self):
        self._seed_recon_topic()
        promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason")
        with self.assertRaises(promote_reconnaissance.PromotionError):
            promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason again")

    def test_archives_recon_stage_artifacts(self):
        self._seed_recon_topic()
        result = promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "found enough to map the space")
        self.assertIn("records.jsonl", result["archived"])
        self.assertIn("raw", result["archived"])
        self.assertIn("relevance_tags_table.json", result["archived"])
        # the M4 exit criterion's literal wording: recon records never
        # enter the promoted method's records.jsonl without a fresh run --
        # enforced here by the live file simply not existing any more.
        self.assertFalse((self.topic_dir / "records.jsonl").exists())
        self.assertFalse((self.topic_dir / "raw").exists())
        self.assertTrue((self.topic_dir / "recon" / "records.jsonl").exists())
        self.assertTrue((self.topic_dir / "recon" / "raw" / "crossref-20260101.json").exists())

    def test_writes_handoff_files(self):
        self._seed_recon_topic()
        promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason")
        self.assertTrue((self.topic_dir / "handoff" / "disclosure.md").exists())
        seed_terms = json.loads((self.topic_dir / "handoff" / "seed_terms.json").read_text())
        self.assertEqual(seed_terms["query_strings"], {"crossref": "term1 AND term2"})
        candidates = json.loads((self.topic_dir / "handoff" / "gold_set_candidates.json").read_text())
        self.assertEqual(len(candidates), 1)  # only the row with a non-null claim
        self.assertEqual(candidates[0]["provenance"], "recon-db")
        self.assertEqual(candidates[0]["id_type"], "doi")
        self.assertEqual(candidates[0]["id"], "10.1/x")

    def test_folds_recoverable_candidate_into_known_items(self):
        self._seed_recon_topic()
        promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason")
        protocol = json.loads((self.topic_dir / "protocol.json").read_text())
        known = protocol["known_items"]
        self.assertEqual(len(known), 1)
        self.assertEqual(known[0], {
            "id_type": "doi", "id": "10.1/x",
            "note": "reconnaissance candidate, closest on: population",
            "provenance": "recon-db",
        })

    def test_records_amendment_and_resets_signing(self):
        self._seed_recon_topic()
        promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "found enough to map the space")
        protocol = json.loads((self.topic_dir / "protocol.json").read_text())
        self.assertEqual(len(protocol["amendments"]), 1)
        self.assertIn("scoping_review", protocol["amendments"][0]["change"])
        self.assertEqual(protocol["amendments"][0]["reason"], "found enough to map the space")
        self.assertEqual(protocol["method"]["id"], "scoping_review")
        self.assertIsNone(protocol["method"]["signed_at"])
        self.assertIsNone(protocol["method"]["signed_by"])

    def test_candidate_without_recoverable_id_is_skipped_from_known_items(self):
        _write_json(self.topic_dir / "protocol.json", {"method": {"id": "reconnaissance"}})
        _write_jsonl(self.topic_dir / "records.jsonl", [{"record_id": "openalex:W1", "doi": None}])
        _write_json(self.topic_dir / "relevance_tags_table.json", {"studies": [
            {"record_id": "openalex:W1", "facet_tags": ["method"],
             "claim": {"quote": "x", "page": None, "hash": None}, "by": "claude"},
        ]})
        promote_reconnaissance.promote(self.topic_dir, self.SLUG, "scoping_review", "reason")
        protocol = json.loads((self.topic_dir / "protocol.json").read_text())
        self.assertEqual(protocol.get("known_items", []), [])
        candidates = json.loads((self.topic_dir / "handoff" / "gold_set_candidates.json").read_text())
        self.assertEqual(candidates[0]["id_type"], None)


class CliTests(unittest.TestCase):
    SLUG = "promote-reconnaissance-cli-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(self.topic_dir / "protocol.json", {"method": {"id": "reconnaissance"}})

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_cli_success(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = promote_reconnaissance.main(["--topic", self.SLUG, "--new-method-id", "scoping_review", "--reason", "x"])
        self.assertEqual(rc, 0)
        printed = json.loads(buf.getvalue())
        self.assertEqual(printed["new_method_id"], "scoping_review")

    def test_cli_refuses_for_invalid_slug(self):
        rc = promote_reconnaissance.main(["--topic", "../etc/passwd", "--new-method-id", "scoping_review", "--reason", "x"])
        self.assertEqual(rc, 1)

    def test_cli_refuses_wrong_method(self):
        _write_json(self.topic_dir / "protocol.json", {"method": {"id": "scoping_review"}})
        rc = promote_reconnaissance.main(["--topic", self.SLUG, "--new-method-id", "systematic_review", "--reason", "x"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
