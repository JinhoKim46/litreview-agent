"""Unit tests for tools/status.py -- the /prisma-status pipeline-progress
report and next-command recommendation, ported from the inline heredoc
.claude/commands/prisma-status.md Step 3 used to embed.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import ledger, path_policy, status


def _write_protocol(topic_dir, **overrides):
    data = {"title": "Test Review", "framework": "PICO", "review_type": "systematic_review",
            "scope": {"mode": "global", "coverage_gaps": []}}
    data.update(overrides)
    with open(Path(topic_dir) / "protocol.json", "w") as f:
        json.dump(data, f)


def _write_search_plan(topic_dir):
    with open(Path(topic_dir) / "search_plan.json", "w") as f:
        json.dump({"sources": ["openalex"]}, f)


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


def _write_extraction(topic_dir, studies):
    with open(Path(topic_dir) / "extraction_table.json", "w") as f:
        json.dump({"studies": studies}, f)


def _write_heterogeneity(topic_dir, outcomes):
    synth_dir = Path(topic_dir) / "synthesis"
    synth_dir.mkdir(parents=True, exist_ok=True)
    with open(synth_dir / "heterogeneity.json", "w") as f:
        json.dump(outcomes, f)


def _write_manuscript(topic_dir, words=10):
    manuscript_dir = Path(topic_dir) / "manuscript"
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    with open(manuscript_dir / "manuscript.md", "w") as f:
        f.write(" ".join(["word"] * words))


class AsListTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual(status.as_list(None), [])

    def test_bare_list(self):
        self.assertEqual(status.as_list([1, 2]), [1, 2])

    def test_studies_key(self):
        self.assertEqual(status.as_list({"studies": [1, 2]}), [1, 2])

    def test_dict_without_studies_key_uses_values(self):
        self.assertEqual(sorted(status.as_list({"a": 1, "b": 2})), [1, 2])


class StudyIdTests(unittest.TestCase):
    def test_prefers_record_id(self):
        self.assertEqual(status.study_id({"record_id": "r1", "study_id": "s1"}), "r1")

    def test_falls_back_to_study_id(self):
        self.assertEqual(status.study_id({"study_id": "s1"}), "s1")

    def test_falls_back_to_author_year(self):
        self.assertEqual(status.study_id({"author_year": "Smith2020"}), "Smith2020")

    def test_unknown_when_nothing_present(self):
        self.assertEqual(status.study_id({}), "UNKNOWN_STUDY")


class SinceLastVersionTests(unittest.TestCase):
    """docs/ROADMAP.md M5's "reports what changed" delta, computed from
    protocol.json.versions[] (tools/versioning.py's own snapshots)."""

    def test_none_with_fewer_than_two_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp, versions=[{"version": 1, "date": "2026-01-01", "record_ids": ["a"], "n_records": 1, "n_included": 0}])
            self.assertIsNone(status.since_last_version(Path(tmp)))

    def test_none_with_no_protocol_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(status.since_last_version(Path(tmp)))

    def test_diffs_the_last_two_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp, versions=[
                {"version": 1, "date": "2026-01-01", "record_ids": ["a", "b"], "n_records": 2, "n_included": 1},
                {"version": 2, "date": "2026-02-01", "record_ids": ["a", "b", "c"], "n_records": 3, "n_included": 2},
            ])
            delta = status.since_last_version(Path(tmp))
            self.assertEqual(delta["from_version"], 1)
            self.assertEqual(delta["to_version"], 2)
            self.assertEqual(delta["new_records"], 1)
            self.assertEqual(delta["new_record_ids"], ["c"])
            self.assertEqual(delta["removed_records"], 0)
            self.assertEqual(delta["included_delta"], 1)

    def test_only_compares_the_most_recent_pair_not_the_full_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp, versions=[
                {"version": 1, "date": "2026-01-01", "record_ids": ["a"], "n_records": 1, "n_included": 0},
                {"version": 2, "date": "2026-02-01", "record_ids": ["a", "b"], "n_records": 2, "n_included": 0},
                {"version": 3, "date": "2026-03-01", "record_ids": ["a", "b", "c"], "n_records": 3, "n_included": 0},
            ])
            delta = status.since_last_version(Path(tmp))
            self.assertEqual((delta["from_version"], delta["to_version"]), (2, 3))
            self.assertEqual(delta["new_record_ids"], ["c"])

    def test_records_reclassified_as_duplicates_show_as_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp, versions=[
                {"version": 1, "date": "2026-01-01", "record_ids": ["a", "b"], "n_records": 2, "n_included": 0},
                {"version": 2, "date": "2026-02-01", "record_ids": ["a"], "n_records": 1, "n_included": 0},
            ])
            delta = status.since_last_version(Path(tmp))
            self.assertEqual(delta["removed_records"], 1)
            self.assertEqual(delta["removed_record_ids"], ["b"])

    def test_included_delta_can_be_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp, versions=[
                {"version": 1, "date": "2026-01-01", "record_ids": ["a"], "n_records": 1, "n_included": 3},
                {"version": 2, "date": "2026-02-01", "record_ids": ["a"], "n_records": 1, "n_included": 1},
            ])
            delta = status.since_last_version(Path(tmp))
            self.assertEqual(delta["included_delta"], -2)


class ComputeStageTests(unittest.TestCase):
    def test_not_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "not_started")
            self.assertIn("prisma-init", s["next_cmd"])

    def test_protocol_defined_no_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "protocol_defined")
            self.assertEqual(s["next_cmd"], "/prisma-search")

    def test_search_incomplete_no_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 5, 5)
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "search_incomplete")

    def test_screening_title_abstract_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 2, 2)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}, {"record_id": "a:2", "duplicate_of": None}])
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "screening_title_abstract")
            self.assertEqual(s["undecided_title_abstract"], 2)

    def test_screening_full_text_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
            ])
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "screening_full_text")
            self.assertEqual(s["pending_full_text"], 1)

    def test_screening_complete_zero_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "exclude", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
            ])
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "screening_complete_zero_included")
            self.assertIsNone(s["next_cmd"])

    def test_extraction_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "extraction_incomplete")
            self.assertEqual(s["next_cmd"], "/prisma-extract")

    def test_extraction_complete_no_synthesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            _write_extraction(tmp, [{"record_id": "a:1"}])
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "extraction_complete")
            self.assertEqual(s["next_cmd"], "/prisma-synthesize")

    def test_synthesis_complete_no_manuscript(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            _write_extraction(tmp, [{"record_id": "a:1"}])
            _write_heterogeneity(tmp, [{"outcome": "x", "pooled": True}, {"outcome": "y", "pooled": False}])
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "synthesis_complete")
            self.assertEqual(s["next_cmd"], "/prisma-report")
            self.assertEqual(s["pooled_outcomes"], 1)
            self.assertEqual(s["narrative_outcomes"], 1)

    def test_manuscript_stale_when_extraction_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            _write_extraction(tmp, [{"record_id": "a:1"}])
            _write_heterogeneity(tmp, [{"outcome": "x", "pooled": True}])
            _write_manuscript(tmp)
            _write_extraction(tmp, [{"record_id": "a:1"}])  # rewritten after the manuscript -> newer mtime
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "manuscript_drafted")
            self.assertEqual(s["next_cmd"], "/prisma-report")

    def test_manuscript_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            _write_extraction(tmp, [{"record_id": "a:1"}])
            _write_heterogeneity(tmp, [{"outcome": "x", "pooled": True}])
            _write_manuscript(tmp, words=250)
            s = status.compute(Path(tmp))
            self.assertEqual(s["stage"], "manuscript_drafted")
            self.assertIsNone(s["next_cmd"])
            self.assertEqual(s["manuscript_words"], 250)


class ComputeWarningTests(unittest.TestCase):
    def test_missing_reason_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "exclude", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            s = status.compute(Path(tmp))
            self.assertEqual(s["full_text_excludes_missing_reason"], ["a:1"])

    def test_orphaned_decision_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:2", "duplicate_of": None}])  # a:1 no longer canonical
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
            ])
            s = status.compute(Path(tmp))
            self.assertEqual(s["orphaned_title_abstract"], ["a:1"])

    def test_unextracted_included_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            s = status.compute(Path(tmp))
            self.assertEqual(s["unextracted_included"], ["a:1"])

    def test_truncated_source_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 5, 10, truncated=True)
            s = status.compute(Path(tmp))
            self.assertEqual(s["truncated_sources"], ["openalex"])


class PrintFullTests(unittest.TestCase):
    def test_warnings_and_stage_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 5, 10, truncated=True)
            s = status.compute(Path(tmp))
            buf = io.StringIO()
            with redirect_stdout(buf):
                status.print_full(s)
            out = buf.getvalue()
            self.assertIn("PRISMA review status", out)
            self.assertIn("WARNING: Search coverage", out)
            self.assertIn("Current stage: search_incomplete", out)

    def test_no_delta_section_with_fewer_than_two_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            s = status.compute(Path(tmp))
            self.assertIsNone(s["delta"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                status.print_full(s)
            self.assertNotIn("Living-mode delta", buf.getvalue())

    def test_delta_section_printed_once_two_versions_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp, versions=[
                {"version": 1, "date": "2026-01-01", "record_ids": ["a"], "n_records": 1, "n_included": 0},
                {"version": 2, "date": "2026-02-01", "record_ids": ["a", "b"], "n_records": 2, "n_included": 1},
            ])
            s = status.compute(Path(tmp))
            self.assertIsNotNone(s["delta"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                status.print_full(s)
            out = buf.getvalue()
            self.assertIn("Living-mode delta (version 1 [2026-01-01] -> version 2 [2026-02-01])", out)
            self.assertIn("New records since last version: 1", out)
            self.assertIn("- b", out)
            self.assertIn("Included count change since last version: +1", out)


class PrintCondensedTests(unittest.TestCase):
    def test_shows_next_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = status.compute(Path(tmp))
            buf = io.StringIO()
            with redirect_stdout(buf):
                status.print_condensed(s)
            self.assertIn("-> next: /prisma-init", buf.getvalue())

    def test_shows_nothing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_protocol(tmp)
            _write_search_plan(tmp)
            _write_raw(tmp, "openalex-20260101.json", "openalex", 1, 1)
            _write_records(tmp, [{"record_id": "a:1", "duplicate_of": None}])
            ledger.append_decisions(tmp, [
                {"record_id": "a:1", "stage": "title_abstract", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
                {"record_id": "a:1", "stage": "full_text", "decision": "include", "reason": None,
                 "ai_suggestion": None, "decided_at": "2026-01-02T00:00:00Z"},
            ])
            _write_extraction(tmp, [{"record_id": "a:1"}])
            _write_heterogeneity(tmp, [{"outcome": "x", "pooled": True}])
            _write_manuscript(tmp)
            s = status.compute(Path(tmp))
            buf = io.StringIO()
            with redirect_stdout(buf):
                status.print_condensed(s)
            self.assertIn("-> nothing pending", buf.getvalue())


class MainCliTests(unittest.TestCase):
    SLUG = "status-cli-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_cli_single_topic_runs_on_empty_topic(self):
        rc = status.main(["--topic", self.SLUG])
        self.assertEqual(rc, 0)

    def test_cli_unsafe_slug_rejected(self):
        rc = status.main(["--topic", "Bad Slug"])
        self.assertEqual(rc, 1)

    def test_cli_list_all_mode_runs(self):
        rc = status.main([])
        self.assertEqual(rc, 0)

    def test_cli_missing_topic_dir_reports_and_returns_zero(self):
        rc = status.main(["--topic", "no-such-topic-at-all"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
