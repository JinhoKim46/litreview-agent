"""Golden end-to-end pipeline test for a scoping review (docs/PLAN.md M3's
exit criterion, "second golden test"): frozen inputs under
tests/fixtures/golden/youth-digital-literacy-scoping/ (a signed, PCC-framed
protocol for method.id: scoping_review; raw/ connector output for 4 studies
across 2 sources with no planted duplicates -- dedup's exact/fuzzy matching
is already thoroughly exercised by tests/test_golden_pipeline.py's M1
fixture, so this fixture's job is the scoping-specific stages; a
hash-chained screening ledger where one full-text decision is
"not_retrieved" with a reason (a paywalled, unfetchable record); and a
frozen, piloted charting_table.json for the 3 studies that were actually
retrieved) are run through the real deterministic pipeline: dedup ->
ledger gate/verify -> flow_counts (the not_retrieved record in its own
box) -> search_preflight -> preflight (both stages) -> charting_gate's
freeze-drift check -> run_synthesis's real CLI dispatch (descriptive
synthesis via chart_summary.py, pooling never attempted) -> label_gate
(label + report blockers).

Chosen topic ("digital literacy interventions for school-age youth") is
deliberately unrelated to any reviewer's own research field and to any
other topic already used as a demo/fixture in this repository, per this
project's own topic-genericity discipline for validation fixtures.

Every stage's output is compared against a frozen
tests/fixtures/golden/youth-digital-literacy-scoping/expected/ snapshot,
by direct JSON/text comparison (this fixture's cross_tabs is always []
since capture.mode: charting never produces cross-tab data at all --
synthesis/plots.py's bubble_plot() only ever renders for a classification
capture mode, tested separately in tests/test_chart_summary.py and
tests/test_synthesis_plots.py, so there is no SVG for this fixture to
hash).

If a fixture input or a module's output shape legitimately changes,
regenerate expected/ by rerunning the (uncommitted-to-test-discovery)
build script that produced it -- never hand-edit a file under expected/:

    python3 tests/fixtures/golden/youth-digital-literacy-scoping/_build_expected.py

Writes to a throwaway topic directory under the real (gitignored) results/
tree, using the same tools every command actually uses, and removes it in
tearDown -- this is what makes the test "golden": it exercises the exact
code paths a live scoping review's /prisma-search -> /prisma-screen ->
/prisma-extract -> /prisma-synthesize sequence would, not a
reimplementation of them.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthesis import run_synthesis
from tools import charting_gate, dedup, flow_counts, label_gate, ledger, path_policy, preflight, search_preflight

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "golden", "youth-digital-literacy-scoping")
EXPECTED_DIR = os.path.join(FIXTURE_DIR, "expected")
SLUG = "golden-scoping-pipeline-test-run"


def _load_expected(name):
    with open(os.path.join(EXPECTED_DIR, name)) as f:
        return json.load(f)


def _normalize_topic_dir(text, topic_dir_str):
    """run_synthesis.main()'s printed message embeds the absolute topic_dir
    path -- redact it the same way tests/test_golden_pipeline.py normalizes
    SVG paths, so this snapshot compares equal regardless of which absolute
    path this checkout happens to live at (CI included)."""
    return text.replace(topic_dir_str, "<TOPIC_DIR>")


class GoldenScopingPipelineTest(unittest.TestCase):
    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        shutil.copytree(FIXTURE_DIR, self.topic_dir, ignore=shutil.ignore_patterns("expected", "_build_expected.py"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_full_scoping_pipeline_matches_frozen_golden_snapshot(self):
        # ---- Stage 1: dedup -- 4 distinct records, none marked duplicate ----
        rc = dedup.main(["--topic", SLUG, "--pass", "both"])
        self.assertEqual(rc, 0)
        with open(self.topic_dir / "records.jsonl") as f:
            records = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(records), 4)
        self.assertTrue(all(r.get("duplicate_of") is None for r in records))
        with open(os.path.join(EXPECTED_DIR, "records.jsonl")) as f:
            self.assertEqual(f.read(), (self.topic_dir / "records.jsonl").read_text())

        # ---- Stage 2: ledger gate + verify -- the not_retrieved decision
        # carries a reason, so nothing is missing at the PRISMA Item 16b gate ----
        entries = ledger.load_ledger(self.topic_dir)
        latest = ledger.latest_decisions(entries)
        gate_missing = ledger.full_text_reason_required_missing(latest)
        self.assertEqual({"missing_reason": gate_missing}, _load_expected("ledger_gate.json"))
        self.assertEqual(gate_missing, [])
        gate_rc = ledger.main(["--topic", SLUG, "gate"])
        self.assertEqual(gate_rc, 0)

        verify_result = ledger.verify_chain(entries)
        self.assertEqual(verify_result, _load_expected("ledger_verify.json"))
        self.assertTrue(verify_result["ok"])
        verify_rc = ledger.main(["--topic", SLUG, "verify"])
        self.assertEqual(verify_rc, 0)

        # ---- Stage 3: flow counts -- the not_retrieved record gets its own
        # PRISMA box, never silently merged into "excluded" ----
        fc = flow_counts.flow_counts(self.topic_dir)
        self.assertEqual(fc, _load_expected("flow_counts.json"))
        self.assertEqual(fc["reports_not_retrieved"], 1)
        self.assertEqual(fc["included_final"], 3)

        # ---- Stage 4: search-completeness preflight ----
        search_rc = search_preflight.main(["--topic", SLUG])
        self.assertEqual(search_rc, 0)
        with open(self.topic_dir / "search_status.json") as f:
            self.assertEqual(json.load(f), _load_expected("search_status.json"))

        # ---- Stage 5: aggregated preflight, both stages -- "synthesize"
        # must skip synthesis_plan_present for scoping_review (its
        # synthesis.plan_required_for is [], since pooling is forbidden by
        # design) rather than fail forever with no synthesis_plan.json to
        # ever satisfy it (tools/preflight.py's genericity fix) ----
        checks_report = preflight.run_checks(self.topic_dir, "report")
        self.assertEqual(checks_report, _load_expected("preflight_report.json"))
        self.assertTrue(all(c["ok"] for c in checks_report))

        checks_synthesize = preflight.run_checks(self.topic_dir, "synthesize")
        self.assertEqual(checks_synthesize, _load_expected("preflight_synthesize.json"))
        self.assertTrue(all(c["ok"] for c in checks_synthesize))
        self.assertNotIn("synthesis_plan_present", {c["name"] for c in checks_synthesize})

        # ---- Stage 6: charting freeze-gate -- frozen, no drifted rows ----
        table = charting_gate.load_charting_table(self.topic_dir, SLUG)
        self.assertTrue(table["charting_form_frozen"])
        offending = charting_gate.verify_table(table)
        self.assertEqual({"offending_record_ids": offending}, _load_expected("charting_verify.json"))
        self.assertEqual(offending, [])

        # ---- Stage 7: run_synthesis's real CLI dispatch -- descriptive
        # synthesis via chart_summary.py, pooling never attempted (the
        # manifest's synthesis.families_allowed is ["descriptive"] only) ----
        with mock.patch.object(sys, "argv", ["run_synthesis.py", "--topic", SLUG]):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = run_synthesis.main()
        expected_cli = _load_expected("run_synthesis_cli.json")
        actual_stdout_normalized = _normalize_topic_dir(stdout.getvalue(), str(self.topic_dir))
        self.assertEqual(rc, expected_cli["rc"])
        self.assertEqual(actual_stdout_normalized, expected_cli["stdout"])
        self.assertIn('synthesis_family="descriptive", no pooling', stdout.getvalue())
        self.assertIn("3 studies tabulated", stdout.getvalue())
        self.assertIn("0 cross-tab(s)", stdout.getvalue())  # cross-tabs are classification-only

        with open(self.topic_dir / "synthesis" / "descriptive_summary.json") as f:
            summary = json.load(f)
        self.assertEqual(summary, _load_expected("descriptive_summary.json"))
        self.assertEqual(summary["capture_mode"], "charting")
        self.assertEqual(summary["n_studies"], 3)
        self.assertEqual(summary["cross_tabs"], [])
        self.assertEqual(
            summary["category_frequencies"]["outcome_reported"],
            {"digital literacy knowledge/skill assessment": 3},
        )

        # ---- Stage 8: label + report blockers -- the exit criterion's
        # "zero label_gate blockers" for a fully-conducted scoping review ----
        label_result = label_gate.compute_label(SLUG)
        self.assertEqual(label_result, _load_expected("label.json"))
        self.assertEqual(label_result["label"], "scoping review")

        blockers = label_gate.compute_blockers(SLUG)
        self.assertEqual(blockers, _load_expected("blockers.json"))
        self.assertEqual(blockers, [])

        # ---- The M3 exit criterion's coverage-gap clause: protocol.json's
        # scope.coverage_gaps must actually correspond to the resolved
        # pack's own unreachable source_expectations (the PR A wiring in
        # .claude/commands/prisma-init.md Step 4), not merely be present --
        # otherwise this would just assert the fixture reproduces itself.
        # Rendering this data into manuscript prose (Limitations, the
        # "because" card) is an LLM-authored step this deterministic test
        # cannot exercise, the same limitation tests/test_golden_pipeline.py
        # accepts for M1's manuscript. ----
        with open(self.topic_dir / "protocol.json") as f:
            protocol = json.load(f)
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs", "generic.json")) as f:
            generic_pack = json.load(f)
        unreachable_sources = {e["source"] for e in generic_pack["source_expectations"] if e["reachable_via"] is None}
        recorded_gap_sources = {g["source"] for g in protocol["scope"]["coverage_gaps"]}
        self.assertEqual(recorded_gap_sources, unreachable_sources)


if __name__ == "__main__":
    unittest.main()
