"""Unit tests for tools/dedup.py -- the exact-key dedup pass (formerly the
inline heredoc in .claude/commands/litreview-search.md Step 7) and the fuzzy
near-duplicate pass (formerly Step 7b). Phase 0 correctness fix, see
docs/PLAN.md defect #3.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import dedup, path_policy


def _write_raw(topic_dir, filename, source, results):
    raw_dir = Path(topic_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with open(raw_dir / filename, "w") as f:
        json.dump({"meta": {"source": source, "retrieved": len(results), "total_available": len(results),
                             "truncated": False, "fetched_at": "2026-01-01T00:00:00Z"}, "results": results}, f)


def _read_records(topic_dir):
    path = Path(topic_dir) / "records.jsonl"
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class NormalizeDoiTests(unittest.TestCase):
    def test_strips_url_prefixes_case_and_trailing_slash(self):
        expected = "10.1234/abcd"
        for raw in ("https://doi.org/10.1234/abcd", "http://doi.org/10.1234/ABCD",
                    "https://dx.doi.org/10.1234/abcd/", "doi:10.1234/abcd", "10.1234/abcd"):
            self.assertEqual(dedup.normalize_doi(raw), expected, raw)

    def test_none_and_empty(self):
        self.assertIsNone(dedup.normalize_doi(None))
        self.assertIsNone(dedup.normalize_doi(""))


class NormalizePmidTests(unittest.TestCase):
    """normalize_pmid takes the constructed record shape (record_id =
    "<source>:<native_id>"), never a bare "id" field -- see the bug fixed
    in normalize_pmid's docstring/comment: the original heredoc's version
    read a field ("id") that never existed on this shape, so its PMID tier
    was dead code."""

    def test_pubmed_bare_id(self):
        self.assertEqual(dedup.normalize_pmid({"source": "pubmed", "record_id": "pubmed:12345678"}), "12345678")

    def test_europepmc_med_prefix(self):
        self.assertEqual(dedup.normalize_pmid({"source": "europepmc", "record_id": "europepmc:MED:12345678"}), "12345678")

    def test_europepmc_non_med_prefix_ignored(self):
        self.assertIsNone(dedup.normalize_pmid({"source": "europepmc", "record_id": "europepmc:PPR:98765"}))

    def test_other_source_ignored(self):
        self.assertIsNone(dedup.normalize_pmid({"source": "openalex", "record_id": "openalex:W123"}))


class FirstAuthorSurnameTests(unittest.TestCase):
    def test_medline_style(self):
        self.assertEqual(dedup.first_author_surname(["Kim JH"]), "kim")

    def test_surname_comma_given_style(self):
        self.assertEqual(dedup.first_author_surname(["Kim, Jae-Ho"]), "kim")

    def test_given_surname_style(self):
        self.assertEqual(dedup.first_author_surname(["Jae-Ho Kim"]), "kim")

    def test_empty_authors(self):
        self.assertEqual(dedup.first_author_surname([]), "")
        self.assertEqual(dedup.first_author_surname(None), "")


class DedupeRawFilesTierPriorityTests(unittest.TestCase):
    def test_doi_tier_wins_over_title_author_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "src-a.json", "crossref", [
                {"id": "10.1/x", "title": "A Study Of Things", "authors": ["Kim JH"], "year": 2020,
                 "doi": "10.1/x", "url": "https://doi.org/10.1/x"},
            ])
            _write_raw(tmp, "src-b.json", "openalex", [
                {"id": "W1", "title": "A completely different title", "authors": ["Kim JH"], "year": 2020,
                 "doi": "https://doi.org/10.1/X", "url": "https://openalex.org/W1"},  # same DOI, different case+URL form
            ])
            stats = dedup.dedupe_raw_files(tmp)
            self.assertEqual(stats["new_canonical"], 1)
            self.assertEqual(stats["new_duplicates"], 1)
            self.assertEqual(stats["duplicates_by_tier"]["doi"], 1)
            records = _read_records(tmp)
            dup = next(r for r in records if r["record_id"] == "openalex:W1")
            self.assertEqual(dup["duplicate_of"], "crossref:10.1/x")

    def test_pmid_tier_matches_pubmed_and_europepmc(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "src-a.json", "pubmed", [
                {"id": "555", "title": "Unrelated Title One", "authors": ["Lee S"], "year": 2019, "doi": None},
            ])
            _write_raw(tmp, "src-b.json", "europepmc", [
                {"id": "MED:555", "title": "Unrelated Title Two Entirely", "authors": ["Lee S"], "year": 2019, "doi": None},
            ])
            stats = dedup.dedupe_raw_files(tmp)
            self.assertEqual(stats["duplicates_by_tier"]["pmid"], 1)

    def test_title_author_year_tier_is_last_resort(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "src-a.json", "arxiv", [
                {"id": "2001.00001", "title": "Deep Learning for MRI Reconstruction", "authors": ["Kim JH"], "year": 2021, "doi": None},
            ])
            _write_raw(tmp, "src-b.json", "openalex", [
                {"id": "W99", "title": "Deep Learning for MRI Reconstruction!!", "authors": ["Kim, Jae-Ho"], "year": 2021, "doi": None},
            ])
            stats = dedup.dedupe_raw_files(tmp)
            self.assertEqual(stats["duplicates_by_tier"]["title_author_year"], 1)


class DedupeRawFilesCanonicalChainTests(unittest.TestCase):
    def test_duplicate_of_a_duplicate_resolves_to_root_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            # First run: canonical + one duplicate matched on doi.
            _write_raw(tmp, "run1.json", "crossref", [
                {"id": "10.1/x", "title": "Root Study", "authors": ["Kim JH"], "year": 2020, "doi": "10.1/x"},
            ])
            dedup.dedupe_raw_files(tmp)
            _write_raw(tmp, "run2.json", "openalex", [
                {"id": "W1", "title": "Root Study", "authors": ["Kim JH"], "year": 2020, "doi": "10.1/x"},
            ])
            dedup.dedupe_raw_files(tmp)
            # Third arrival matches only on title|author|year against the
            # *duplicate* record (imagine it lacks a doi itself) -- must
            # still resolve to the original root canonical, not W1.
            _write_raw(tmp, "run3.json", "semanticscholar", [
                {"id": "S1", "title": "Root Study", "authors": ["Kim JH"], "year": 2020, "doi": None},
            ])
            dedup.dedupe_raw_files(tmp)
            records = {r["record_id"]: r for r in _read_records(tmp)}
            self.assertIsNone(records["crossref:10.1/x"]["duplicate_of"])
            self.assertEqual(records["openalex:W1"]["duplicate_of"], "crossref:10.1/x")
            self.assertEqual(records["semanticscholar:S1"]["duplicate_of"], "crossref:10.1/x")


class DedupeRawFilesIdempotencyTests(unittest.TestCase):
    def test_rerun_does_not_duplicate_or_reappend(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "run1.json", "crossref", [
                {"id": "10.1/x", "title": "Study A", "authors": ["Kim JH"], "year": 2020, "doi": "10.1/x"},
            ])
            first = dedup.dedupe_raw_files(tmp)
            self.assertEqual(first["new_lines_appended"], 1)
            second = dedup.dedupe_raw_files(tmp)
            self.assertEqual(second["new_lines_appended"], 0)
            self.assertEqual(second["raw_files_processed"], 1)
            self.assertEqual(len(_read_records(tmp)), 1)

    def test_rerun_after_new_raw_file_only_appends_new_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "run1.json", "crossref", [
                {"id": "10.1/x", "title": "Study A", "authors": ["Kim JH"], "year": 2020, "doi": "10.1/x"},
            ])
            dedup.dedupe_raw_files(tmp)
            _write_raw(tmp, "run2.json", "openalex", [
                {"id": "W2", "title": "Study B", "authors": ["Lee S"], "year": 2021, "doi": None},
            ])
            second = dedup.dedupe_raw_files(tmp)
            self.assertEqual(second["new_lines_appended"], 1)
            self.assertEqual(second["raw_files_processed"], 2)
            self.assertEqual(len(_read_records(tmp)), 2)


class DedupeRawFilesSkippedNoIdTests(unittest.TestCase):
    def test_id_less_result_is_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_raw(tmp, "run1.json", "crossref", [
                {"id": None, "title": "No Id Study", "authors": [], "year": 2020, "doi": None},
                {"id": "10.1/y", "title": "Has Id Study", "authors": [], "year": 2020, "doi": "10.1/y"},
            ])
            stats = dedup.dedupe_raw_files(tmp)
            self.assertEqual(stats["skipped_no_native_id"], 1)
            self.assertEqual(stats["new_canonical"], 1)


class FlagNearDuplicatesTests(unittest.TestCase):
    def _seed_records(self, tmp, records):
        with open(Path(tmp) / "records.jsonl", "w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def test_above_threshold_pair_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed_records(tmp, [
                {"record_id": "a:1", "title": "Deep Learning for MRI Reconstruction Methods", "year": 2021, "duplicate_of": None},
                {"record_id": "b:2", "title": "Deep Learning for MRI Reconstruction Method", "year": 2021, "duplicate_of": None},
            ])
            stats = dedup.flag_near_duplicates(tmp)
            self.assertEqual(stats["new_possible_duplicates_flagged"], 1)
            with open(Path(tmp) / "possible_duplicates.jsonl") as f:
                pairs = [json.loads(l) for l in f if l.strip()]
            self.assertEqual({pairs[0]["record_id_a"], pairs[0]["record_id_b"]}, {"a:1", "b:2"})
            self.assertGreaterEqual(pairs[0]["similarity"], dedup.SIMILARITY_THRESHOLD)

    def test_below_threshold_pair_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed_records(tmp, [
                {"record_id": "a:1", "title": "Deep Learning for MRI Reconstruction", "year": 2021, "duplicate_of": None},
                {"record_id": "b:2", "title": "A Totally Unrelated Paper About Cats", "year": 2021, "duplicate_of": None},
            ])
            stats = dedup.flag_near_duplicates(tmp)
            self.assertEqual(stats["new_possible_duplicates_flagged"], 0)

    def test_different_years_are_not_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed_records(tmp, [
                {"record_id": "a:1", "title": "Deep Learning for MRI Reconstruction Methods", "year": 2020, "duplicate_of": None},
                {"record_id": "b:2", "title": "Deep Learning for MRI Reconstruction Methods", "year": 2021, "duplicate_of": None},
            ])
            stats = dedup.flag_near_duplicates(tmp)
            self.assertEqual(stats["new_possible_duplicates_flagged"], 0)

    def test_already_duplicate_records_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed_records(tmp, [
                {"record_id": "a:1", "title": "Deep Learning for MRI Reconstruction Methods", "year": 2021, "duplicate_of": None},
                {"record_id": "b:2", "title": "Deep Learning for MRI Reconstruction Method", "year": 2021, "duplicate_of": "a:1"},
            ])
            stats = dedup.flag_near_duplicates(tmp)
            self.assertEqual(stats["canonical_records_checked"], 1)
            self.assertEqual(stats["new_possible_duplicates_flagged"], 0)

    def test_rerun_does_not_reflag_existing_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed_records(tmp, [
                {"record_id": "a:1", "title": "Deep Learning for MRI Reconstruction Methods", "year": 2021, "duplicate_of": None},
                {"record_id": "b:2", "title": "Deep Learning for MRI Reconstruction Method", "year": 2021, "duplicate_of": None},
            ])
            dedup.flag_near_duplicates(tmp)
            second = dedup.flag_near_duplicates(tmp)
            self.assertEqual(second["new_possible_duplicates_flagged"], 0)
            with open(Path(tmp) / "possible_duplicates.jsonl") as f:
                self.assertEqual(len([l for l in f if l.strip()]), 1)


class MainCliTests(unittest.TestCase):
    """Exercises the real safe_topic_path containment via a disposable slug
    under the actual results/ directory (same convention test_path_policy.py
    uses) -- cleaned up in tearDown regardless of outcome."""

    SLUG = "dedup-cli-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_exact_pass_end_to_end(self):
        _write_raw(self.topic_dir, "run1.json", "crossref", [
            {"id": "10.1/z", "title": "CLI Study", "authors": ["Kim JH"], "year": 2022, "doi": "10.1/z"},
        ])
        rc = dedup.main(["--topic", self.SLUG, "--pass", "exact"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.topic_dir / "records.jsonl").exists())

    def test_fuzzy_pass_without_records_jsonl_fails_clearly(self):
        os.makedirs(self.topic_dir, exist_ok=True)
        rc = dedup.main(["--topic", self.SLUG, "--pass", "fuzzy"])
        self.assertEqual(rc, 1)

    def test_both_passes_in_one_invocation(self):
        _write_raw(self.topic_dir, "run1.json", "crossref", [
            {"id": "10.1/a", "title": "Near Duplicate Title Test Alpha", "authors": ["Kim JH"], "year": 2022, "doi": "10.1/a"},
        ])
        _write_raw(self.topic_dir, "run2.json", "openalex", [
            {"id": "W1", "title": "Near Duplicate Title Test Alpha!", "authors": ["Lee S"], "year": 2022, "doi": None},
        ])
        rc = dedup.main(["--topic", self.SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.topic_dir / "possible_duplicates.jsonl").exists())

    def test_unsafe_slug_rejected(self):
        rc = dedup.main(["--topic", "Has-Upper-Case"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
