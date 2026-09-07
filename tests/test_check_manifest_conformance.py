"""Unit tests for tools/check_manifest_conformance.py (merge-01.md item #2):
a declared-but-unconsulted pack/manifest value must either be wired up or
carry a merge-01.md-tracked baseline entry, or CI fails."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import check_manifest_conformance as cmc


class ConformanceLogicTests(unittest.TestCase):
    """Exercise main()'s pass/fail/warn logic directly against a synthetic
    violation set, independent of which real pack/manifest gaps exist today
    (those are covered by RealRepoTests below)."""

    def setUp(self):
        self._orig_baseline = dict(cmc.KNOWN_UNCONSULTED_BASELINE)
        self.addCleanup(lambda: cmc.KNOWN_UNCONSULTED_BASELINE.clear() or cmc.KNOWN_UNCONSULTED_BASELINE.update(self._orig_baseline))

    def test_consulted_value_is_not_a_violation(self):
        # "nos" is a real, implemented instrument -- appears in the
        # quality-appraisal skill files, so it must never show up as a
        # violation regardless of which pack declares it.
        violations = cmc.check_appraisal_instruments()
        self.assertNotIn(
            ("packs/generic.json", "appraisal_instruments_by_design.case_control", "nos"),
            violations,
        )

    def test_unbaselined_violation_fails(self):
        cmc.KNOWN_UNCONSULTED_BASELINE.clear()
        rc = cmc.main()
        self.assertEqual(rc, 1)

    def test_baselined_violation_passes_with_warning(self):
        # Real repo state today: every known violation is baselined --
        # main() must exit 0.
        rc = cmc.main()
        self.assertEqual(rc, 0)

    def test_baseline_entry_with_invalid_tracking_ref_fails(self):
        key = next(iter(cmc.KNOWN_UNCONSULTED_BASELINE))
        cmc.KNOWN_UNCONSULTED_BASELINE[key] = "not a real merge-doc anchor"
        rc = cmc.main()
        self.assertEqual(rc, 1)

    def test_stale_baseline_entry_is_flagged_but_does_not_fail(self):
        cmc.KNOWN_UNCONSULTED_BASELINE[("nonexistent", "field", "value")] = "merge-01.md item #999 -- fabricated for this test"
        rc = cmc.main()
        self.assertEqual(rc, 0)  # a stale entry warns, never fails


class RealRepoTests(unittest.TestCase):
    """The real repo state today, per merge-01.md items #3/#5/#6."""

    def test_known_rob2_gap_is_baselined_and_reproduces(self):
        violations = cmc.check_appraisal_instruments()
        self.assertIn(
            ("packs/clinical_interventions.json", "appraisal_instruments_by_design.rct", "rob2"),
            violations,
        )

    def test_venue_default_gap_is_baselined_and_reproduces(self):
        violations = cmc.check_routing_fields_set_by_packs()
        self.assertIn(("_routing_field", "venue_default"), violations)

    def test_prisma_scr_checklist_gap_is_baselined_and_reproduces(self):
        violations = cmc.check_standards_refs()
        self.assertIn(
            ("methods/scoping_review.json", "standards[].ref", "prisma-scr-2018-checklist.md"),
            violations,
        )

    def test_main_exits_zero_against_real_repo_state(self):
        self.assertEqual(cmc.main(), 0)


if __name__ == "__main__":
    unittest.main()
