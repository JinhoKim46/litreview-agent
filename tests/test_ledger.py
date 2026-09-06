"""Unit tests for tools/ledger.py: hash-chained append, the PRISMA Item 16b
gate (exclude/not_retrieved need a reason), and the candidate-set join.
Phase 0 correctness fix, docs/PLAN.md defect #3 + decision 4.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import ledger


def _entry(record_id, stage, decision, reason=None, ai_suggestion=None, decided_at="2026-01-01T00:00:00Z"):
    return {"record_id": record_id, "stage": stage, "decision": decision, "reason": reason,
            "ai_suggestion": ai_suggestion, "decided_at": decided_at}


class ComputeEntryHashTests(unittest.TestCase):
    def test_deterministic_regardless_of_key_order(self):
        a = {"z": 1, "a": 2}
        b = {"a": 2, "z": 1}
        self.assertEqual(ledger.compute_entry_hash(None, a), ledger.compute_entry_hash(None, b))

    def test_different_prev_hash_changes_result(self):
        entry = {"record_id": "x", "decision": "include"}
        self.assertNotEqual(ledger.compute_entry_hash(None, entry), ledger.compute_entry_hash("abc", entry))

    def test_different_content_changes_result(self):
        self.assertNotEqual(
            ledger.compute_entry_hash(None, {"decision": "include"}),
            ledger.compute_entry_hash(None, {"decision": "exclude"}),
        )


class AppendDecisionsTests(unittest.TestCase):
    def test_first_entry_has_null_prev_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = ledger.append_decisions(tmp, [_entry("r1", "title_abstract", "include")])
            self.assertIsNone(written[0]["prev_hash"])
            self.assertTrue(written[0]["entry_hash"])

    def test_chain_links_sequential_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = ledger.append_decisions(tmp, [
                _entry("r1", "title_abstract", "include"),
                _entry("r2", "title_abstract", "exclude", reason="wrong population"),
            ])
            self.assertEqual(written[1]["prev_hash"], written[0]["entry_hash"])

    def test_defaults_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = ledger.append_decisions(tmp, [_entry("r1", "title_abstract", "include")])
            self.assertIsNone(written[0]["by"])
            self.assertEqual(written[0]["role"], "decision")
            self.assertIsNone(written[0]["eligibility_version"])

    def test_explicit_fields_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = _entry("r1", "title_abstract", "include")
            row["by"] = "reviewer-1"
            row["role"] = "verification"
            row["eligibility_version"] = 2
            written = ledger.append_decisions(tmp, [row])
            self.assertEqual(written[0]["by"], "reviewer-1")
            self.assertEqual(written[0]["role"], "verification")
            self.assertEqual(written[0]["eligibility_version"], 2)

    def test_second_call_chains_onto_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = ledger.append_decisions(tmp, [_entry("r1", "title_abstract", "include")])
            second = ledger.append_decisions(tmp, [_entry("r2", "title_abstract", "include")])
            self.assertEqual(second[0]["prev_hash"], first[0]["entry_hash"])

    def test_appends_never_rewrites_existing_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger.append_decisions(tmp, [_entry("r1", "title_abstract", "include")])
            ledger.append_decisions(tmp, [_entry("r2", "title_abstract", "exclude", reason="x")])
            entries = ledger.load_ledger(tmp)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["record_id"], "r1")


class LatestDecisionsTests(unittest.TestCase):
    def test_last_line_in_file_order_wins_not_decided_at(self):
        entries = [
            _entry("r1", "title_abstract", "exclude", decided_at="2026-06-01T00:00:00Z"),
            _entry("r1", "title_abstract", "include", decided_at="2020-01-01T00:00:00Z"),  # earlier timestamp, later in file
        ]
        latest = ledger.latest_decisions(entries)
        self.assertEqual(latest[("r1", "title_abstract")]["decision"], "include")

    def test_verification_role_excluded_by_default(self):
        entries = [_entry("r1", "title_abstract", "include")]
        entries[0]["role"] = "verification"
        latest = ledger.latest_decisions(entries)
        self.assertEqual(latest, {})

    def test_role_filter_selects_verification(self):
        entries = [dict(_entry("r1", "title_abstract", "include"), role="verification")]
        latest = ledger.latest_decisions(entries, role="verification")
        self.assertIn(("r1", "title_abstract"), latest)

    def test_missing_role_field_defaults_to_decision(self):
        entries = [_entry("r1", "title_abstract", "include")]  # no "role" key at all (legacy line)
        latest = ledger.latest_decisions(entries)
        self.assertIn(("r1", "title_abstract"), latest)


class FullTextReasonRequiredTests(unittest.TestCase):
    def test_exclude_without_reason_flagged(self):
        latest = {("r1", "full_text"): _entry("r1", "full_text", "exclude")}
        missing = ledger.full_text_reason_required_missing(latest)
        self.assertEqual([rid for rid, _ in missing], ["r1"])

    def test_not_retrieved_without_reason_flagged(self):
        latest = {("r1", "full_text"): _entry("r1", "full_text", "not_retrieved")}
        missing = ledger.full_text_reason_required_missing(latest)
        self.assertEqual([rid for rid, _ in missing], ["r1"])

    def test_exclude_with_reason_not_flagged(self):
        latest = {("r1", "full_text"): _entry("r1", "full_text", "exclude", reason="wrong design")}
        self.assertEqual(ledger.full_text_reason_required_missing(latest), [])

    def test_include_never_flagged(self):
        latest = {("r1", "full_text"): _entry("r1", "full_text", "include")}
        self.assertEqual(ledger.full_text_reason_required_missing(latest), [])

    def test_title_abstract_stage_never_flagged(self):
        latest = {("r1", "title_abstract"): _entry("r1", "title_abstract", "exclude")}
        self.assertEqual(ledger.full_text_reason_required_missing(latest), [])

    def test_blank_reason_string_still_flagged(self):
        latest = {("r1", "full_text"): _entry("r1", "full_text", "exclude", reason="   ")}
        missing = ledger.full_text_reason_required_missing(latest)
        self.assertEqual([rid for rid, _ in missing], ["r1"])


class CandidateSetTests(unittest.TestCase):
    def test_extracted_and_pending_status(self):
        latest = {
            ("r1", "full_text"): _entry("r1", "full_text", "include"),
            ("r2", "full_text"): _entry("r2", "full_text", "include"),
            ("r3", "full_text"): _entry("r3", "full_text", "exclude", reason="x"),
        }
        records = {"r1": {"title": "One", "year": 2020, "url": "u1", "doi": "d1"},
                   "r2": {"title": "Two", "year": 2021, "url": "u2", "doi": "d2"}}
        rows = ledger.candidate_set(records, latest, extracted_record_ids={"r1"})
        by_id = {r["record_id"]: r for r in rows}
        self.assertEqual(by_id["r1"]["status"], "extracted")
        self.assertEqual(by_id["r2"]["status"], "PENDING")
        self.assertNotIn("r3", by_id)  # excluded at full-text is not a candidate

    def test_missing_record_reports_placeholder(self):
        latest = {("ghost", "full_text"): _entry("ghost", "full_text", "include")}
        rows = ledger.candidate_set({}, latest, extracted_record_ids=set())
        self.assertEqual(rows[0]["title"], "(record missing from records.jsonl)")


class VerifyChainTests(unittest.TestCase):
    def test_valid_chain_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger.append_decisions(tmp, [
                _entry("r1", "title_abstract", "include"),
                _entry("r2", "title_abstract", "exclude", reason="x"),
            ])
            result = ledger.verify_chain(ledger.load_ledger(tmp))
            self.assertTrue(result["ok"])
            self.assertEqual(result["legacy_unhashed_prefix"], 0)
            self.assertEqual(result["entries_checked"], 2)

    def test_all_legacy_unhashed_is_ok(self):
        entries = [_entry("r1", "title_abstract", "include"), _entry("r2", "title_abstract", "include")]
        result = ledger.verify_chain(entries)
        self.assertTrue(result["ok"])
        self.assertEqual(result["legacy_unhashed_prefix"], 2)
        self.assertEqual(result["entries_checked"], 0)

    def test_legacy_prefix_then_hashed_suffix_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screening_decisions.jsonl"
            with open(path, "w") as f:
                f.write(json.dumps(_entry("legacy1", "title_abstract", "include")) + "\n")
            ledger.append_decisions(tmp, [_entry("r2", "title_abstract", "include")])
            result = ledger.verify_chain(ledger.load_ledger(tmp))
            self.assertTrue(result["ok"])
            self.assertEqual(result["legacy_unhashed_prefix"], 1)
            self.assertEqual(result["entries_checked"], 1)

    def test_tampered_entry_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger.append_decisions(tmp, [
                _entry("r1", "title_abstract", "include"),
                _entry("r2", "title_abstract", "include"),
            ])
            entries = ledger.load_ledger(tmp)
            entries[0]["decision"] = "exclude"  # tamper after the fact, hash now stale
            result = ledger.verify_chain(entries)
            self.assertFalse(result["ok"])
            self.assertEqual(result["index"], 0)  # the tampered entry's own recomputed hash no longer matches

    def test_broken_prev_hash_link_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger.append_decisions(tmp, [_entry("r1", "title_abstract", "include")])
            entries = ledger.load_ledger(tmp)
            entries.append(dict(_entry("r2", "title_abstract", "include"), prev_hash="wrong", entry_hash="also-wrong"))
            result = ledger.verify_chain(entries)
            self.assertFalse(result["ok"])
            self.assertEqual(result["index"], 1)

    def test_unhashed_entry_after_hashing_began_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger.append_decisions(tmp, [_entry("r1", "title_abstract", "include")])
            entries = ledger.load_ledger(tmp)
            entries.append(_entry("r2", "title_abstract", "include"))  # no hash fields at all
            result = ledger.verify_chain(entries)
            self.assertFalse(result["ok"])
            self.assertEqual(result["index"], 1)


class MainCliTests(unittest.TestCase):
    SLUG = "ledger-cli-test-topic"

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

    def test_gate_refuses_then_passes(self):
        ledger.append_decisions(self.topic_dir, [_entry("r1", "full_text", "exclude")])
        rc = ledger.main(["--topic", self.SLUG, "gate"])
        self.assertEqual(rc, 1)
        ledger.append_decisions(self.topic_dir, [_entry("r1", "full_text", "exclude", reason="fixed now")])
        rc = ledger.main(["--topic", self.SLUG, "gate"])
        self.assertEqual(rc, 0)

    def test_verify_cli_ok_on_fresh_ledger(self):
        ledger.append_decisions(self.topic_dir, [_entry("r1", "title_abstract", "include")])
        rc = ledger.main(["--topic", self.SLUG, "verify"])
        self.assertEqual(rc, 0)

    def test_candidates_cli_runs(self):
        ledger.append_decisions(self.topic_dir, [_entry("r1", "full_text", "include")])
        rc = ledger.main(["--topic", self.SLUG, "candidates"])
        self.assertEqual(rc, 0)

    def test_unsafe_slug_rejected(self):
        rc = ledger.main(["--topic", "Bad Slug", "gate"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
