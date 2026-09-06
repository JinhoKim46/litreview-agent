"""Golden end-to-end pipeline test for docs/ROADMAP.md's M5 exit criterion:
"a delta run screens only new records and reports what changed; a pooled
cross-dataset metric a domain pack shouldn't allow gets refused by the core
rules, not by pack-specific code."

Frozen inputs under tests/fixtures/golden/chest-xray-covid-detection-
benchmarks/ (a systematic_review protocol with no method-routing block --
this fixture only needs versioning/dedup/ledger/run_synthesis, not the full
routing interview; a search_plan.json and one raw/ fetch for two studies on
the COVIDx benchmark dataset; an extraction_table.json for those same two
studies; a synthesis_plan.json whose pooling_unit.identity_fields is
pre-filled from packs/medical_imaging_prediction.json's own
pooling_unit_identity_proposal) are run through the real deterministic
pipeline: dedup -> ledger (screening decisions) -> tools/versioning.py
(version 1) -> tools/status.py (no delta yet) -> run_synthesis (pools fine,
both studies agree on dataset_id) -> a living rerun's fresh raw/ fetch
(re-returns the same two studies plus one genuinely new one on a different
benchmark dataset, Brixia) -> dedup again (only the new record is
appended) -> build_screening_sheet (only the new record is an undecided
candidate) -> ledger + extraction_table.json updated for the new study ->
tools/versioning.py (version 2) -> tools/status.py's delta report ->
run_synthesis again, now refusing to pool across the two different
dataset_id values -> the same data re-run with no identity_fields
declared at all, pooling exactly as it would have before this milestone
existed (backward compatibility).

Chosen topic ("chest X-ray COVID-19 detection benchmarks") is deliberately
unrelated to any reviewer's own research field (MRI reconstruction /
Magnetic Resonance in Medicine, per CLAUDE.local.md) and to every other
topic already used as a demo/fixture in this repository this session
(ponv-drug-a-review, youth-digital-literacy-scoping,
gig-worker-wellbeing-recon), per this project's own topic-genericity
discipline for validation fixtures -- even though the *pack* it exercises
(medical_imaging_prediction) is a close sibling of image_reconstruction,
which does match the reviewer's own field; shipping that pack is a real
milestone deliverable, not a test-topic choice.

Every stage's output that has a genuinely deterministic shape is compared
against a frozen tests/fixtures/golden/chest-xray-covid-detection-
benchmarks/expected/ snapshot, by direct JSON comparison; simpler
counts/fields are asserted directly inline.

If a fixture input or a module's output shape legitimately changes,
regenerate expected/ by rerunning the (uncommitted-to-test-discovery)
build script that produced it -- never hand-edit a file under expected/:

    python3 tests/fixtures/golden/chest-xray-covid-detection-benchmarks/_build_expected.py

Writes to a throwaway topic directory under the real (gitignored) results/
tree, using the same tools every command actually uses, and removes it in
tearDown.
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis import run_synthesis
from tools import build_screening_sheet, dedup, ledger, method, path_policy, status, versioning

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden", "chest-xray-covid-detection-benchmarks")
EXPECTED_DIR = os.path.join(FIXTURE_DIR, "expected")
SLUG = "golden-living-mode-pack-pipeline-test-run"


def _load_expected(name):
    with open(os.path.join(EXPECTED_DIR, name)) as f:
        return json.load(f)


def _redact_dates(entry):
    """tools/versioning.py's record_version() and tools/status.py's
    since_last_version() both stamp today's real wall-clock date -- must be
    redacted before an actual-vs-frozen-expected comparison means anything,
    same reasoning as tests/test_golden_pipeline.py's own detected_at
    redaction for possible_duplicates.jsonl."""
    redacted = dict(entry)
    for key in ("date", "from_date", "to_date"):
        if key in redacted:
            redacted[key] = "REDACTED-FOR-GOLDEN-TEST"
    return redacted


def _brixia_study_entry():
    """The third study, CX3 -- arrives only via the living rerun, on a
    different benchmark dataset (Brixia, not COVIDx). Not part of the
    frozen extraction_table.json fixture input -- appended live in the
    test body, mirroring how tests/test_golden_reconnaissance_pipeline.py's
    Stage 6 injects its own fresh raw/ fetch directly rather than as a
    frozen file."""
    return {
        "record_id": "openalex:CX3", "author_year": "Rossi (2022)", "country": "Italy",
        "study_design": "diagnostic accuracy study",
        "population": "Chest radiographs from the Brixia benchmark dataset",
        "intervention": "Pretrained CNN classifier for COVID-19 vs. non-COVID-19, externally validated",
        "comparator": "ResNet-50 baseline classifier",
        "outcomes_measured": ["diagnostic accuracy"],
        "sample_size": {"total": 100, "intervention": 100, "comparator": 100},
        "key_findings": "External validation on Brixia showed lower but still above-baseline performance.",
        "funding_source": None, "notes": None,
        "dataset_id": "brixia", "test_split": "test",
        "reports": [{"citation": "Rossi F (2022). External Validation of COVID-19 Detection Models on the "
                                  "Brixia Chest Radiograph Dataset. Medical Image Analysis.",
                     "doi": "10.9000/cx003", "url": "https://doi.org/10.9000/cx003"}],
        "effect_data": [{
            "outcome": "diagnostic accuracy", "measure_type": "RR", "timepoint": "held-out test split",
            "intervention_arm": {"label": "pretrained CNN", "events": 90, "total": 100},
            "comparator_arm": {"label": "ResNet-50 baseline", "events": 70, "total": 100},
            "source": {"quote": "The pretrained model correctly classified 90/100 Brixia test cases versus "
                                 "70/100 for the ResNet-50 baseline.", "locator": "Table 1", "notes": None},
        }],
        "risk_of_bias": {"tool": "RoB1", "overall_judgement": "unclear risk"},
        "extraction_source": {"method": "interview", "url": None, "fetched_at": None},
        "extracted_at": "2026-02-20T00:00:00Z", "by": "claude (single extractor pass)", "verified_by": None,
    }


def _living_rerun_raw():
    return {
        "meta": {"source": "openalex", "query": "(\"COVID-19\" OR \"SARS-CoV-2\") AND (\"chest radiograph\" OR "
                 "\"chest X-ray\") AND (\"deep learning\" OR \"convolutional neural network\")",
                 "retrieved": 3, "total_available": 3, "truncated": False, "fetched_at": "2026-02-15T00:00:00Z"},
        "results": [
            {"id": "CX1", "title": "Deep Learning for COVID-19 Detection on the COVIDx Chest Radiograph Dataset",
             "authors": ["Nguyen T", "Park S"], "year": 2021, "venue": "IEEE Access",
             "doi": "10.9000/cx001", "abstract": "...", "url": "https://doi.org/10.9000/cx001"},
            {"id": "CX2", "title": "A Convolutional Neural Network Benchmark on the COVIDx Dataset for COVID-19 Screening",
             "authors": ["Silva R"], "year": 2021, "venue": "Scientific Reports",
             "doi": "10.9000/cx002", "abstract": "...", "url": "https://doi.org/10.9000/cx002"},
            {"id": "CX3", "title": "External Validation of COVID-19 Detection Models on the Brixia Chest Radiograph Dataset",
             "authors": ["Rossi F"], "year": 2022, "venue": "Medical Image Analysis",
             "doi": "10.9000/cx003", "abstract": "...", "url": "https://doi.org/10.9000/cx003"},
        ],
    }


class GoldenLivingModePackPipelineTest(unittest.TestCase):
    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        shutil.copytree(FIXTURE_DIR, self.topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_full_living_mode_and_pack_pipeline_matches_frozen_golden_snapshot(self):
        # ---- Stage 1: the first search's dedup pass -- 2 canonical records ----
        rc = dedup.main(["--topic", SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)
        with open(self.topic_dir / "records.jsonl") as f:
            records = [json.loads(l) for l in f if l.strip()]
        self.assertEqual({r["record_id"] for r in records}, {"openalex:CX1", "openalex:CX2"})

        # ---- Stage 2: both studies screened in (title_abstract + full_text) ----
        ledger.append_decisions(self.topic_dir, [
            {"record_id": "openalex:CX1", "stage": "title_abstract", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-16T00:00:00Z"},
            {"record_id": "openalex:CX2", "stage": "title_abstract", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-16T00:00:00Z"},
            {"record_id": "openalex:CX1", "stage": "full_text", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-18T00:00:00Z"},
            {"record_id": "openalex:CX2", "stage": "full_text", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-01-18T00:00:00Z"},
        ])

        # ---- Stage 3: record version 1 (docs/ROADMAP.md M5) ----
        version_1 = versioning.record_version(self.topic_dir, SLUG)
        self.assertEqual(_redact_dates(version_1), _load_expected("version_1.json"))
        self.assertEqual(version_1["version"], 1)
        self.assertEqual(version_1["n_records"], 2)
        self.assertEqual(version_1["n_included"], 2)

        # ---- Stage 4: before a second version exists, there is no delta to report ----
        self.assertIsNone(status.since_last_version(self.topic_dir))

        # ---- Stage 5: pooling succeeds before the living rerun -- both
        # studies agree on dataset_id="covidx" -- proves the identity
        # predicate is a real check, not a blanket refusal ----
        result_before = run_synthesis.run(
            str(self.topic_dir / "extraction_table.json"), str(self.topic_dir / "synthesis"),
            model="fixed", identity_fields=["dataset_id", "test_split"],
        )
        het_before = next(h for h in result_before["heterogeneity"] if h["outcome"] == "diagnostic accuracy")
        self.assertTrue(het_before["pooled"])

        # ---- Stage 6: living rerun -- a fresh raw fetch re-returns CX1/CX2
        # (the source's own idempotent behavior) plus one genuinely new
        # record, CX3, on a different benchmark dataset (Brixia, not COVIDx) ----
        (self.topic_dir / "raw" / "openalex-20260215.json").write_text(json.dumps(_living_rerun_raw()))
        rc = dedup.main(["--topic", SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)
        with open(self.topic_dir / "records.jsonl") as f:
            records_after = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(records_after), 3)  # not 5 -- CX1/CX2 were never re-appended
        self.assertEqual({r["record_id"] for r in records_after}, {"openalex:CX1", "openalex:CX2", "openalex:CX3"})

        # ---- Stage 7: the exit criterion's literal wording -- "a delta run
        # screens only new records": CX3 is the only undecided candidate for
        # title_abstract screening; CX1/CX2 stay decided, never re-surfaced ----
        all_records = build_screening_sheet.load_records(self.topic_dir)
        latest_decisions = build_screening_sheet.load_latest_decisions(self.topic_dir)
        candidates = build_screening_sheet.select_candidates(all_records, latest_decisions, "title_abstract")
        candidate_ids = sorted(r["record_id"] for r in candidates)
        self.assertEqual(candidate_ids, _load_expected("screening_candidates.json"))
        self.assertEqual(candidate_ids, ["openalex:CX3"])

        # ---- CX3 is screened in and extracted ----
        ledger.append_decisions(self.topic_dir, [
            {"record_id": "openalex:CX3", "stage": "title_abstract", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-02-16T00:00:00Z"},
            {"record_id": "openalex:CX3", "stage": "full_text", "decision": "include", "reason": None,
             "ai_suggestion": None, "decided_at": "2026-02-18T00:00:00Z"},
        ])
        extraction = json.loads((self.topic_dir / "extraction_table.json").read_text())
        extraction["studies"].append(_brixia_study_entry())
        (self.topic_dir / "extraction_table.json").write_text(json.dumps(extraction, indent=2))

        # ---- Stage 8: record version 2 and check the delta report --
        # "reports what changed" ----
        version_2 = versioning.record_version(self.topic_dir, SLUG)
        self.assertEqual(_redact_dates(version_2), _load_expected("version_2.json"))
        self.assertEqual(version_2["version"], 2)
        self.assertEqual(version_2["n_records"], 3)
        self.assertEqual(version_2["n_included"], 3)

        delta = status.since_last_version(self.topic_dir)
        self.assertEqual(_redact_dates(delta), _load_expected("delta.json"))
        self.assertEqual(delta["new_records"], 1)
        self.assertEqual(delta["new_record_ids"], ["openalex:CX3"])
        self.assertEqual(delta["removed_records"], 0)
        self.assertEqual(delta["included_delta"], 1)

        # ---- Stage 9: pack provenance -- the signed plan's identity_fields
        # is exactly this pack's own pooling_unit_identity_proposal, never
        # hand-invented for this fixture ----
        pack = method.load_pack("medical_imaging_prediction")
        signed_plan = json.loads((self.topic_dir / "synthesis_plan.json").read_text())
        self.assertEqual(signed_plan["pooling_unit"]["identity_fields"], pack["pooling_unit_identity_proposal"])

        # ---- Stage 10: the exit criterion's other half -- "a pooled
        # cross-dataset metric a domain pack shouldn't allow gets refused by
        # the core rules, not by pack-specific code." No pack-specific code
        # runs anywhere in this call -- identity_fields is read straight off
        # the signed plan by synthesis/run_synthesis.py's generic predicate ----
        result_after = run_synthesis.run(
            str(self.topic_dir / "extraction_table.json"), str(self.topic_dir / "synthesis"),
            model="fixed", identity_fields=signed_plan["pooling_unit"]["identity_fields"],
        )
        het_after = next(h for h in result_after["heterogeneity"] if h["outcome"] == "diagnostic accuracy")
        self.assertEqual(het_after, _load_expected("refused_heterogeneity.json"))
        self.assertFalse(het_after["pooled"])
        self.assertIn("dataset_id", het_after["reason"])
        self.assertIn("openalex:CX3", het_after["reason"])

        # ---- Stage 11: backward compatibility -- the exact same 3-study
        # data, with no identity_fields declared at all, pools exactly as it
        # would have before this milestone existed ----
        result_no_identity = run_synthesis.run(
            str(self.topic_dir / "extraction_table.json"), str(self.topic_dir / "synthesis"), model="fixed",
        )
        het_no_identity = next(h for h in result_no_identity["heterogeneity"] if h["outcome"] == "diagnostic accuracy")
        self.assertEqual(het_no_identity, _load_expected("backward_compatible_heterogeneity.json"))
        self.assertTrue(het_no_identity["pooled"])


if __name__ == "__main__":
    unittest.main()
