import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import build_screening_sheet as bss


RECORDS = [
    # Deliberately out of year order so grouping+sorting must reorder these.
    {"record_id": "src:1", "title": 'A title, with "quotes" and, a comma', "year": 2020,
     "authors": ["Kim S"], "source": "pubmed", "doi": "10.1/a", "url": "https://a",
     "abstract": "abstract one", "duplicate_of": None},
    {"record_id": "src:2", "title": "Newest record", "year": 2024,
     "authors": ["Park J"], "source": "pubmed", "doi": "10.1/b", "url": "https://b",
     "abstract": None, "duplicate_of": None},
    {"record_id": "src:3", "title": "No year record", "year": None,
     "authors": ["Lee K"], "source": "openalex", "doi": None, "url": "https://c",
     "abstract": "abstract three", "duplicate_of": None},
    {"record_id": "src:already-decided", "title": "Already decided", "year": 2021,
     "authors": [], "source": "pubmed", "doi": None, "url": "https://d",
     "abstract": "x", "duplicate_of": None},
    {"record_id": "src:dup", "title": "A duplicate", "year": 2021,
     "authors": [], "source": "pubmed", "doi": None, "url": "https://e",
     "abstract": "x", "duplicate_of": "src:1"},
]

DECISIONS = [
    {"record_id": "src:already-decided", "stage": "title_abstract", "decision": "exclude",
     "reason": None, "ai_suggestion": None, "decided_at": "2026-01-01T00:00:00Z"},
]

POSSIBLE_DUPLICATES = [
    {"record_id_a": "src:2", "record_id_b": "src:3", "similarity": 0.87,
     "detected_at": "2026-01-01T00:00:00Z"},
]


class BuildScreeningSheetTests(unittest.TestCase):
    def _write_topic(self, tmp: Path) -> Path:
        topic_dir = tmp / "topic"
        topic_dir.mkdir()
        (topic_dir / "records.jsonl").write_text(
            "\n".join(json.dumps(r) for r in RECORDS) + "\n", encoding="utf-8")
        (topic_dir / "screening_decisions.jsonl").write_text(
            "\n".join(json.dumps(d) for d in DECISIONS) + "\n", encoding="utf-8")
        (topic_dir / "possible_duplicates.jsonl").write_text(
            "\n".join(json.dumps(d) for d in POSSIBLE_DUPLICATES) + "\n", encoding="utf-8")
        return topic_dir

    def test_export_produces_row_aligned_csv_keyed_by_record_id(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            topic_dir = self._write_topic(tmp)

            rc = bss.main(["--topic-dir", str(topic_dir), "--stage", "title_abstract"])
            self.assertEqual(rc, 0)

            csv_path = topic_dir / "screening" / "title_abstract_sheet.csv"
            self.assertTrue(csv_path.exists())

            by_id = {r["record_id"]: r for r in RECORDS}
            with csv_path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            # Already-decided and duplicate records must be excluded from export.
            exported_ids = {row["record_id"] for row in rows}
            self.assertNotIn("src:already-decided", exported_ids)
            self.assertNotIn("src:dup", exported_ids)
            self.assertEqual(exported_ids, {"src:1", "src:2", "src:3"})

            # The property that actually catches row/column misalignment: every
            # row's factual columns must match the source record looked up by
            # record_id, never by file/row position.
            for row in rows:
                record = by_id[row["record_id"]]
                self.assertEqual(row["title"], record["title"])
                self.assertEqual(row["source"], record["source"])
                self.assertEqual(row["doi"], record["doi"] or "")
                self.assertEqual(row["url"], record["url"])
                self.assertEqual(row["authors"], "; ".join(record["authors"]))
                self.assertEqual(row["year"], "" if record["year"] is None else str(record["year"]))

            # possible_duplicate is attributed to the correct record_id, not a neighbor.
            row2 = next(r for r in rows if r["record_id"] == "src:2")
            row3 = next(r for r in rows if r["record_id"] == "src:3")
            self.assertIn("src:3 (similarity 0.87)", row2["possible_duplicate"])
            self.assertIn("src:2 (similarity 0.87)", row3["possible_duplicate"])
            row1 = next(r for r in rows if r["record_id"] == "src:1")
            self.assertEqual(row1["possible_duplicate"], "")

            # A title containing a comma and a quote survived the CSV round-trip intact.
            self.assertEqual(row1["title"], 'A title, with "quotes" and, a comma')

    def test_no_candidates_exits_zero_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            topic_dir = tmp / "topic"
            topic_dir.mkdir()
            (topic_dir / "records.jsonl").write_text(
                json.dumps(RECORDS[3]) + "\n", encoding="utf-8")  # only the already-decided one
            (topic_dir / "screening_decisions.jsonl").write_text(
                json.dumps(DECISIONS[0]) + "\n", encoding="utf-8")

            rc = bss.main(["--topic-dir", str(topic_dir), "--stage", "title_abstract"])
            self.assertEqual(rc, 0)
            self.assertFalse((topic_dir / "screening").exists())


if __name__ == "__main__":
    unittest.main()
