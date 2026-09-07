"""Golden end-to-end pipeline test for a reconnaissance topic (docs/
ROADMAP.md's M4 exit criterion, "a brief never claims no prior work or
saturation; a promoted review's gold set is flagged as non-independent
until an external item is added"): frozen inputs under
tests/fixtures/golden/gig-worker-wellbeing-recon/ (a protocol with no PCC/
PICO framing and no eligibility block at all -- reconnaissance has neither;
raw/ connector output for 3 candidates across 2 sources with no planted
duplicates; a frozen, tagged relevance_tags_table.json; a clean
manuscript/landscape_brief.md draft) are run through the real
deterministic pipeline: dedup -> corpus-description tally -> forbidden-
form lint on the actual brief draft -> label + blockers -> same-topic
promotion to scoping_review -> the promoted method's own fresh search
rerun -> known-item recall with and without an externally-sourced item.

Chosen topic ("gig economy worker wellbeing") is deliberately unrelated to
any reviewer's own research field and to any other topic already used as
a demo/fixture in this repository (ponv-drug-a-review,
youth-digital-literacy-scoping), per this project's own topic-genericity
discipline for validation fixtures.

Every stage's output is compared against a frozen
tests/fixtures/golden/gig-worker-wellbeing-recon/expected/ snapshot, by
direct JSON comparison.

If a fixture input or a module's output shape legitimately changes,
regenerate expected/ by rerunning the (uncommitted-to-test-discovery)
build script that produced it -- never hand-edit a file under expected/:

    python3 tests/fixtures/golden/gig-worker-wellbeing-recon/_build_expected.py

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

from tools import dedup, label_gate, path_policy, promote_reconnaissance, relevance_tags_gate, search_preflight
from tools.method import list_manifests

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden", "gig-worker-wellbeing-recon")
EXPECTED_DIR = os.path.join(FIXTURE_DIR, "expected")
SLUG = "golden-reconnaissance-pipeline-test-run"


def _load_expected(name):
    with open(os.path.join(EXPECTED_DIR, name)) as f:
        return json.load(f)


def _redact_amendment_dates(protocol):
    """tools/promote_reconnaissance.py's promote() stamps each amendment
    with today's real wall-clock date -- must be redacted before an
    actual-vs-frozen-expected comparison means anything, same reasoning as
    tests/test_golden_living_mode_pack_pipeline.py's own _redact_dates."""
    redacted = dict(protocol)
    redacted["amendments"] = [
        {**a, "date": "REDACTED-FOR-GOLDEN-TEST"} if "date" in a else a
        for a in redacted.get("amendments", [])
    ]
    return redacted


class GoldenReconnaissancePipelineTest(unittest.TestCase):
    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        shutil.copytree(FIXTURE_DIR, self.topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_full_reconnaissance_pipeline_matches_frozen_golden_snapshot(self):
        # ---- Stage 1: dedup -- 3 distinct candidates, none marked duplicate ----
        rc = dedup.main(["--topic", SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)
        with open(self.topic_dir / "records.jsonl") as f:
            records = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r.get("duplicate_of") is None for r in records))
        with open(os.path.join(EXPECTED_DIR, "records.jsonl")) as f:
            self.assertEqual(f.read(), (self.topic_dir / "records.jsonl").read_text())

        # ---- Stage 2: corpus-description tally, computed deterministically
        # from relevance_tags_table.json, not hand-tallied ----
        table = relevance_tags_gate.load_relevance_tags_table(self.topic_dir, SLUG)
        corpus = {
            "n_tagged": len(table["studies"]),
            "corpus_description": relevance_tags_gate.corpus_description(table),
        }
        self.assertEqual(corpus, _load_expected("corpus_description.json"))
        self.assertEqual(corpus["n_tagged"], 3)
        self.assertEqual(corpus["corpus_description"]["population"], 2)

        # ---- Stage 3: forbidden-form lint on the real landscape_brief.md
        # draft -- the exit criterion's literal wording: never claims "no
        # prior work" or "saturation" ----
        manifest = list_manifests()["reconnaissance"]
        brief_text = (self.topic_dir / "manuscript" / "landscape_brief.md").read_text()
        lint_result = label_gate.lint_text(brief_text, manifest, context="templated_output")
        self.assertEqual(lint_result, _load_expected("brief_lint.json"))
        self.assertEqual(lint_result["hard_failures"], [])

        # A version that slipped into forbidden vocabulary does fail --
        # proving the lint is actually wired to this manifest, not just
        # vacuously passing because reconnaissance declares nothing.
        bad_text = brief_text + "\nNo prior work was found on this exact topic, and the search reached saturation."
        bad_result = label_gate.lint_text(bad_text, manifest, context="templated_output")
        self.assertTrue(bad_result["hard_failures"])
        forms_hit = {v["form"] for v in bad_result["hard_failures"]}
        self.assertIn("no_prior_work", forms_hit)
        self.assertIn("novelty", forms_hit)  # covers "saturation"

        # ---- Stage 4: label + blockers -- unconditional label regardless
        # of screening/reviewer count, since label_rules.requires is empty ----
        label_result = label_gate.compute_label(SLUG)
        self.assertEqual(label_result, _load_expected("label.json"))
        self.assertEqual(label_result["label"], "exploratory literature brief (non-systematic)")
        self.assertEqual(label_result["missing"], [])

        blockers = label_gate.compute_blockers(SLUG)
        self.assertEqual(blockers, _load_expected("blockers.json"))
        self.assertEqual(blockers, [])

        # ---- Stage 5: same-topic promotion to a real method ----
        promotion = promote_reconnaissance.promote(self.topic_dir, SLUG, "scoping_review",
                                                     "enough prior work found to warrant a fuller map of the space")
        self.assertEqual(promotion, _load_expected("promotion.json"))
        self.assertEqual(promotion["gold_set_candidates"], 2)  # O1 and O2 have claims; C1 does not
        self.assertEqual(promotion["known_items_added"], 2)

        # The M4 exit criterion's literal wording: recon records never
        # enter the promoted method's records.jsonl without a fresh run --
        # enforced by the archive, not merely disclosed in prose.
        self.assertFalse((self.topic_dir / "records.jsonl").exists())
        self.assertTrue((self.topic_dir / "recon" / "records.jsonl").exists())
        self.assertTrue((self.topic_dir / "handoff" / "gold_set_candidates.json").exists())
        self.assertTrue((self.topic_dir / "handoff" / "disclosure.md").exists())

        protocol_after = json.loads((self.topic_dir / "protocol.json").read_text())
        self.assertEqual(_redact_amendment_dates(protocol_after), _load_expected("protocol_after_promotion.json"))
        self.assertEqual(protocol_after["method"]["id"], "scoping_review")
        self.assertIsNone(protocol_after["method"]["signed_at"])
        self.assertTrue(all(i["provenance"] == "recon-db" for i in protocol_after["known_items"]))

        # ---- Stage 6: the promoted method's own fresh search rerun --
        # records.jsonl does not exist post-promotion, so this is a genuine
        # fresh dedup pass over new raw/ input, not the archived one ----
        fresh_raw = {
            "meta": {"source": "openalex", "query": "gig economy AND wellbeing", "retrieved": 2, "total_available": 2,
                      "truncated": False, "fetched_at": "2026-02-01T00:00:00Z", "purpose": "protocol_driven"},
            "results": [
                {"id": "O1", "title": "Algorithmic Management and Gig Worker Mental Health: A Systematic Review",
                 "authors": ["Alvarez R", "Tan WK"], "year": 2023, "venue": "Journal of Occupational Health Psychology",
                 "doi": "10.3333/gw001", "abstract": "...", "url": "https://doi.org/10.3333/gw001"},
                {"id": "O2", "title": "Platform Work and Burnout: A Survey of Ride-Hailing Drivers",
                 "authors": ["Mensah K"], "year": 2022, "venue": "Work & Stress",
                 "doi": "10.3333/gw002", "abstract": "...", "url": "https://doi.org/10.3333/gw002"},
            ],
        }
        (self.topic_dir / "raw").mkdir(exist_ok=True)
        (self.topic_dir / "raw" / "openalex-20260201.json").write_text(json.dumps(fresh_raw))
        rc = dedup.main(["--topic", SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)

        status_before = search_preflight.search_status(self.topic_dir)
        self.assertEqual(status_before, _load_expected("search_status_before_external.json"))
        self.assertTrue(status_before["known_item_recall"]["non_independent_gold_set"])
        self.assertIn("non_independent_gold_set_notice", status_before)
        self.assertEqual(status_before["known_item_recall"]["found_excluding_recon_seeds"], 0)
        self.assertEqual(len(status_before["known_item_recall"]["found"]), 2)  # both recon-db seeds re-found
        # search_plan.json still lists crossref as enabled, but this fresh
        # rerun deliberately only re-searched openalex -- crossref is
        # legitimately flagged "missing" here, proving the search-
        # completeness gate still applies to a promoted review, not a
        # fixture bug.
        self.assertEqual(status_before["unacknowledged_incomplete_sources"], ["crossref"])

        # ---- Stage 7: an externally-sourced known item clears the notice ----
        protocol = json.loads((self.topic_dir / "protocol.json").read_text())
        protocol["known_items"].append({
            "id_type": "doi", "id": "10.4444/external-item",
            "note": "cited by a related paper, found independently of the recon search",
        })
        (self.topic_dir / "protocol.json").write_text(json.dumps(protocol, indent=2))
        with open(self.topic_dir / "records.jsonl", "a") as f:
            f.write(json.dumps({"record_id": "openalex:O3", "doi": "10.4444/external-item"}) + "\n")

        status_after = search_preflight.search_status(self.topic_dir)
        self.assertEqual(status_after, _load_expected("search_status_after_external.json"))
        self.assertFalse(status_after["known_item_recall"]["non_independent_gold_set"])
        self.assertNotIn("non_independent_gold_set_notice", status_after)
        self.assertEqual(status_after["known_item_recall"]["found_excluding_recon_seeds"], 1)


if __name__ == "__main__":
    unittest.main()
