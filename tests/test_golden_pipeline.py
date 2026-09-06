"""Golden end-to-end pipeline test (docs/PLAN.md PR p0-12-golden-pipeline):
frozen inputs under tests/fixtures/golden/ponv-drug-a-review/ (a protocol
with a prespecified synthesis plan and known_items, raw/ connector output
with planted duplicates -- a cross-source exact DOI duplicate and a
same-year near-duplicate title, a hash-chained screening ledger with a
superseded full-text decision and a verification-role line, and an
extraction table of 4 studies: 3 RoB1 -- one carrying the legacy "RoB2"
label -- plus 1 NOS, contributing to two poolable outcomes and one outcome
below k_min) are run through the full deterministic pipeline this Phase 0
work built: dedup -> ledger gate/candidates/verify -> flow_counts ->
search_preflight -> preflight -> run_synthesis. Every stage's output is
compared against a frozen tests/fixtures/golden/ponv-drug-a-review/expected/
snapshot, either by sha256 (the on-disk artifacts a real review's results/
directory would carry -- SVGs excluded, since matplotlib's SVG bytes are
not guaranteed stable across matplotlib versions/fonts) or by direct JSON
comparison (the stdout-only stage outputs -- ledger gate/candidates/verify,
flow_counts, preflight -- that have no on-disk file of their own).

If a fixture input or a module's output shape legitimately changes,
regenerate expected/ by rerunning the (uncommitted) build script that
produced it -- never hand-edit a file under expected/.

Writes to a throwaway topic directory under the real (gitignored) results/
tree, using the same tools every command actually uses, and removes it in
tearDown -- this is what makes the test "golden": it exercises the exact
code paths a live review's /litreview-search -> /litreview-screen ->
/litreview-extract -> /litreview-synthesize sequence would, not a reimplementation of
them.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis import run_synthesis
from tools import dedup, flow_counts, ledger, path_policy, preflight, search_preflight

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden", "ponv-drug-a-review")
EXPECTED_DIR = os.path.join(FIXTURE_DIR, "expected")
SLUG = "golden-pipeline-test-run"


def _load_expected(name):
    with open(os.path.join(EXPECTED_DIR, name)) as f:
        return json.load(f)


def _load_expected_manifest():
    manifest = {}
    with open(os.path.join(EXPECTED_DIR, "manifest.sha256")) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            digest, rel_path = line.split("  ", 1)
            manifest[rel_path] = digest
    return manifest


def _normalize_svg_paths(data, topic_dir_str):
    """effect_sizes.json embeds forest_plot_svg/funnel_plot_svg as absolute
    paths under the live topic_dir -- replace that prefix with the same
    fixed placeholder tests/fixtures/golden/ponv-drug-a-review/expected/
    was built with, so the comparison doesn't depend on this test using
    the exact same SLUG/absolute path the fixture happened to be built
    under."""
    text = json.dumps(data)
    text = text.replace(topic_dir_str, "<TOPIC_DIR>")
    return json.loads(text)


def _normalize_possible_duplicates(path):
    """Same normalization the expected/ fixture itself was built with --
    flag_near_duplicates() stamps a live detected_at, which must be
    redacted before an actual-vs-expected byte/hash comparison means
    anything."""
    if not os.path.exists(path):
        return None
    lines = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            d["detected_at"] = "REDACTED-FOR-GOLDEN-TEST"
            lines.append(json.dumps(d, sort_keys=True))
    return "\n".join(lines) + ("\n" if lines else "")


class GoldenPipelineTest(unittest.TestCase):
    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        shutil.copytree(FIXTURE_DIR, self.topic_dir, ignore=shutil.ignore_patterns("expected"))
        self.addCleanup(self._cleanup)
        self._manifest = _load_expected_manifest()

    def _cleanup(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_full_pipeline_matches_frozen_golden_snapshot(self):
        # ---- Stage 1: dedup (exact + fuzzy), via the real CLI entry points ----
        rc = dedup.main(["--topic", SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)

        with open(self.topic_dir / "records.jsonl", "rb") as f:
            records_bytes = f.read()
        self.assertEqual(hashlib.sha256(records_bytes).hexdigest(), self._expected_hash("records.jsonl"))

        actual_dups = _normalize_possible_duplicates(self.topic_dir / "possible_duplicates.jsonl")
        with open(os.path.join(EXPECTED_DIR, "possible_duplicates.jsonl")) as f:
            expected_dups = f.read()
        self.assertEqual(actual_dups, expected_dups)

        # ---- Stage 2: ledger gate / candidates / verify ----
        entries = ledger.load_ledger(self.topic_dir)
        latest = ledger.latest_decisions(entries)
        gate_missing = ledger.full_text_reason_required_missing(latest)
        n_full_text_includes = sum(1 for (_, stage), e in latest.items() if stage == "full_text" and e["decision"] == "include")
        self.assertEqual(
            {"missing_reason": gate_missing, "n_full_text_includes": n_full_text_includes},
            _load_expected("ledger_gate.json"),
        )
        gate_rc = ledger.main(["--topic", SLUG, "gate"])
        self.assertEqual(gate_rc, 0)

        with open(self.topic_dir / "records.jsonl") as f:
            records = [json.loads(l) for l in f if l.strip()]
        records_by_id = {r["record_id"]: r for r in records if r.get("duplicate_of") is None}
        with open(self.topic_dir / "extraction_table.json") as f:
            extracted_ids = {s["record_id"] for s in json.load(f)["studies"]}
        candidates = ledger.candidate_set(records_by_id, latest, extracted_ids)
        self.assertEqual(candidates, _load_expected("ledger_candidates.json"))

        verify_result = ledger.verify_chain(entries)
        self.assertEqual(verify_result, _load_expected("ledger_verify.json"))
        self.assertTrue(verify_result["ok"])
        verify_rc = ledger.main(["--topic", SLUG, "verify"])
        self.assertEqual(verify_rc, 0)

        # ---- Stage 3: flow counts (matches /litreview-report's own aggregation) ----
        fc = flow_counts.flow_counts(self.topic_dir)
        self.assertEqual(fc, _load_expected("flow_counts.json"))
        self.assertEqual(fc["included_final"], 4)
        self.assertEqual(fc["duplicates_removed"], 1)  # the planted exact DOI duplicate
        self.assertEqual(fc["excluded_title_abstract"], 1)  # the planted fuzzy duplicate, excluded at screening

        # ---- Stage 4: search-completeness + known-item recall ----
        search_rc = search_preflight.main(["--topic", SLUG])
        self.assertEqual(search_rc, 0)  # clean fixture: both known items resolved (found or acknowledged-missing)
        with open(self.topic_dir / "search_status.json", "rb") as f:
            status_bytes = f.read()
        self.assertEqual(hashlib.sha256(status_bytes).hexdigest(), self._expected_hash("search_status.json"))

        # ---- Stage 5: aggregated preflight, both stages ----
        checks_synth = preflight.run_checks(self.topic_dir, "synthesize")
        self.assertEqual(checks_synth, _load_expected("preflight_synthesize.json"))
        self.assertTrue(all(c["ok"] for c in checks_synth))
        checks_report = preflight.run_checks(self.topic_dir, "report")
        self.assertEqual(checks_report, _load_expected("preflight_report.json"))
        self.assertTrue(all(c["ok"] for c in checks_report))

        # ---- Stage 6: run_synthesis ----
        stderr = io.StringIO()
        synth_out_dir = self.topic_dir / "synthesis"
        with contextlib.redirect_stderr(stderr):
            plan = run_synthesis.resolve_synthesis_plan(SLUG, None, path_policy.safe_topic_path)
            self.assertEqual(plan["model"], "random")
            self.assertEqual(plan["model_source"], "protocol")  # signed_at predates the earliest raw fetched_at
            self.assertEqual(plan["tau2_estimator"], "pm")
            self.assertEqual(plan["ci_method"], "hksj")
            result = run_synthesis.run(
                str(self.topic_dir / "extraction_table.json"), str(synth_out_dir),
                model=plan["model"], model_source=plan["model_source"], k_min=plan["k_min"],
                tau2_estimator=plan["tau2_estimator"], ci_method=plan["ci_method"],
            )
        # The legacy "RoB2" label on openalex:W1003 must warn, exactly once, on read.
        with open(os.path.join(EXPECTED_DIR, "stderr_warnings.txt")) as f:
            expected_warning = f.read()
        self.assertEqual(stderr.getvalue(), expected_warning)

        pooled_outcomes = {h["outcome"] for h in result["heterogeneity"] if h["pooled"]}
        narrative_outcomes = {h["outcome"] for h in result["heterogeneity"] if not h["pooled"]}
        self.assertEqual(pooled_outcomes, {"postoperative nausea and vomiting (PONV)", "postoperative pain score"})
        self.assertEqual(narrative_outcomes, {"adverse events"})

        with open(synth_out_dir / "effect_sizes.json") as f:
            effect_sizes_normalized = _normalize_svg_paths(json.load(f), str(self.topic_dir))
        effect_sizes_bytes = json.dumps(effect_sizes_normalized, indent=2).encode()
        self.assertEqual(
            hashlib.sha256(effect_sizes_bytes).hexdigest(), self._expected_hash("synthesis/effect_sizes.json"),
            "synthesis/effect_sizes.json does not match the frozen golden snapshot",
        )
        for name in ("heterogeneity.json", "rob_table.json", "grade_table.json"):
            with open(synth_out_dir / name, "rb") as f:
                actual_bytes = f.read()
            self.assertEqual(
                hashlib.sha256(actual_bytes).hexdigest(), self._expected_hash(f"synthesis/{name}"),
                f"synthesis/{name} does not match the frozen golden snapshot",
            )

        # SVGs are exercised (produced, non-empty) but never hashed against
        # a frozen byte-for-byte target -- matplotlib's SVG output is not
        # guaranteed stable across matplotlib versions/fonts.
        ponv_svg = next(e for e in result["effect_sizes"] if e["outcome"] == "postoperative nausea and vomiting (PONV)")["forest_plot_svg"]
        pain_svg = next(e for e in result["effect_sizes"] if e["outcome"] == "postoperative pain score")["forest_plot_svg"]
        self.assertTrue(os.path.getsize(ponv_svg) > 0)
        self.assertTrue(os.path.getsize(pain_svg) > 0)
        self.assertIsNotNone(result["rob_traffic_light_svg"])
        self.assertTrue(os.path.getsize(result["rob_traffic_light_svg"]) > 0)
        # k<10 for both pooled outcomes -- no funnel plot for either. The
        # narrative-fallback "adverse events" entry has no funnel_plot_svg
        # key at all (it never reached pooling), so only check pooled entries.
        for e in result["effect_sizes"]:
            if e["pooled"]:
                self.assertIsNone(e["funnel_plot_svg"])

        # ---- The Paule-Mandel/HKSJ/prediction-interval machinery (PR10) is
        # actually exercised here, not just unit-tested in isolation ----
        ponv_pooled = next(e for e in result["effect_sizes"] if e["outcome"] == "postoperative nausea and vomiting (PONV)")["pooled_effect"]
        self.assertEqual(ponv_pooled["k"], 3)
        self.assertIsNotNone(ponv_pooled["pi_low"])  # k=3 >= PI_MIN_K
        self.assertIsNotNone(ponv_pooled["ci_caution"])  # k=3 < HKSJ_CAUTION_MAX_K=5
        pain_pooled = next(e for e in result["effect_sizes"] if e["outcome"] == "postoperative pain score")["pooled_effect"]
        self.assertEqual(pain_pooled["k"], 2)
        self.assertIsNone(pain_pooled["pi_low"])  # k=2 < PI_MIN_K=3

        # ---- Extraction provenance (PR11) survived into effect_sizes.json ----
        ponv_studies = next(e for e in result["effect_sizes"] if e["outcome"] == "postoperative nausea and vomiting (PONV)")["studies"]
        c2001 = next(s for s in ponv_studies if s["study_id"] == "crossref:C2001")
        self.assertEqual(c2001["source"]["locator"], "Table 2")
        self.assertEqual(c2001["reports"][0]["doi"], "10.1111/aaa")
        self.assertEqual(c2001["by"], "claude (single extractor pass)")
        w1003 = next(s for s in ponv_studies if s["study_id"] == "openalex:W1003")
        self.assertEqual(w1003["verified_by"], "Dr. Reviewer")

    def _expected_hash(self, rel_path):
        return self._manifest[rel_path]


if __name__ == "__main__":
    unittest.main()
