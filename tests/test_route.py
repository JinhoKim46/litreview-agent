"""Unit tests for tools/route.py (docs/PLAN.md M2): one test per
methods/_routing.json row, per the milestone's stated exit criterion."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import route

# Every non-SR method target is refused in M2 because only systematic_review
# has a shipped manifest -- tests that want to see a *resolution* to those
# targets pass an explicit shipped_method_ids set, exercising the table's
# logic independent of which manifests happen to exist today.
ALL_TARGETS = {
    "systematic_review", "reconnaissance", "scoping_review",
    "systematic_mapping_study",
}


class RowResolutionTests(unittest.TestCase):
    """Each row's logic in isolation, with every target treated as shipped."""

    def decide(self, answers, base_exists=None):
        return route.decide(answers, shipped_method_ids=ALL_TARGETS)

    def test_r0_update_external(self):
        result = self.decide({"goal": [], "q0": {"human_judgement": "update_external"}})
        self.assertEqual(result["matched_row"], "R0")
        self.assertEqual(result["kind"], "resolve")
        self.assertEqual(result["method_id"], "systematic_review")

    def test_r1_update_with_base(self):
        result = route.decide(
            {"goal": ["update"], "base_exists": True, "base_method_id": "scoping_review"},
            shipped_method_ids=ALL_TARGETS,
        )
        self.assertEqual(result["matched_row"], "R1")
        self.assertEqual(result["kind"], "resolve")
        self.assertEqual(result["method_id"], "scoping_review")
        self.assertEqual(result["modes"], ["living"])

    def test_r1_update_without_base_asks(self):
        result = route.decide({"goal": ["update"], "base_exists": False}, shipped_method_ids=ALL_TARGETS)
        self.assertEqual(result["matched_row"], "R1")
        self.assertEqual(result["kind"], "ask")
        self.assertIn("which completed review", result["question"])

    def test_r2_overview_refuses_to_umbrella(self):
        result = self.decide({"goal": ["overview"]})
        self.assertEqual(result["matched_row"], "R2")
        self.assertEqual(result["kind"], "refuse")
        self.assertIn("scoping_review", result["offer"])

    def test_r2_existing_reviews_evidence_type_also_refuses(self):
        result = self.decide({"goal": [], "evidence_type": "existing_reviews"})
        self.assertEqual(result["matched_row"], "R2")

    def test_r3_orient_goal_resolves_reconnaissance(self):
        result = self.decide({"goal": ["orient"]})
        self.assertEqual(result["matched_row"], "R3")
        self.assertEqual(result["method_id"], "reconnaissance")

    def test_r3_forming_question_focus_resolves_reconnaissance(self):
        result = self.decide({"goal": [], "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R3")

    def test_r3_output_profiles_from_goal(self):
        result = self.decide({"goal": ["prior_work", "background"]})
        self.assertEqual(set(result["output_profiles"]), {"prior_work_check", "background_section"})

    def test_r4a_map_algorithm_cs_se_resolves_mapping_study(self):
        result = self.decide({"goal": ["map"], "evidence_type": "algorithm", "venue_default": "cs_se"})
        self.assertEqual(result["matched_row"], "R4a")
        self.assertEqual(result["method_id"], "systematic_mapping_study")

    def test_r4b_map_algorithm_other_venue_resolves_scoping(self):
        result = self.decide({"goal": ["map"], "evidence_type": "algorithm", "venue_default": "clinical"})
        self.assertEqual(result["matched_row"], "R4b")
        self.assertEqual(result["method_id"], "scoping_review")

    def test_r4c_map_matrix_dimensions_refuses_to_egm(self):
        result = self.decide({"goal": ["map"], "matrix_dimensions_requested": True})
        self.assertEqual(result["matched_row"], "R4c")
        self.assertEqual(result["kind"], "refuse")

    def test_r4d_map_default_resolves_scoping(self):
        result = self.decide({"goal": ["map"], "evidence_type": "trials"})
        self.assertEqual(result["matched_row"], "R4d")
        self.assertEqual(result["method_id"], "scoping_review")

    def test_r5_answer_forming_resolves_scoping_not_reconnaissance(self):
        # merge-01.md item #1: R3's "... or question_focus == forming" clause
        # used to be unconditional on goal, shadowing this row. Fixed by
        # narrowing R3 to exclude goal ∋ {map, answer} -- see _routing.json's
        # R3 "when" and R5's "_resolved_flagged" note.
        result = self.decide({"goal": ["answer"], "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R5")
        self.assertEqual(result["method_id"], "scoping_review")
        self.assertIn("map first", result["explain"])

    def test_r4a_map_forming_still_resolves_via_algorithm_venue_logic(self):
        # merge-01.md item #1: a "map" goal with question_focus="forming"
        # must still reach R4a-R4d's algorithm/venue logic, not be shadowed
        # by R3's forming clause.
        result = self.decide({"goal": ["map"], "evidence_type": "algorithm", "venue_default": "cs_se", "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R4a")
        self.assertEqual(result["method_id"], "systematic_mapping_study")

    def test_r6a_qualitative_forming_still_hard_refuses(self):
        # merge-01.md item #1, the most consequential instance: a qualitative
        # question that is also "forming" must still hit R6a's hard REFUSE
        # (never systematic_review), not fall through to R3 or R5. This
        # required narrowing R5's own condition too (see R5's
        # "_resolved_flagged" note) -- R3 alone was not a sufficient fix,
        # since R5 would otherwise have shadowed R6a next.
        result = self.decide({"goal": ["answer"], "evidence_type": "qualitative", "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R6a")
        self.assertEqual(result["kind"], "refuse")
        self.assertIn("systematic_review", result["never"])

    def test_r3_no_longer_shadows_more_specific_rows(self):
        # Regression guard for the merge-01 fix to methods/_routing.json's
        # R3/R4/R5/R6a ordering (merge-01.md item #1). Do not let a future
        # table edit reintroduce goal-independent forming-clause precedence.
        for answers, expected_row in [
            ({"goal": ["answer"], "question_focus": "forming"}, "R5"),
            ({"goal": ["map"], "evidence_type": "algorithm", "venue_default": "cs_se", "question_focus": "forming"}, "R4a"),
            ({"goal": ["answer"], "evidence_type": "qualitative", "question_focus": "forming"}, "R6a"),
        ]:
            with self.subTest(answers=answers):
                self.assertEqual(self.decide(answers)["matched_row"], expected_row)

    def test_r5_evidence_type_unset_still_passes_through(self):
        # R5's evidence_type exclusion (added alongside the R3 fix) must not
        # break the case where a reviewer hasn't decided evidence_type yet --
        # "map first" is still the right guidance for goal=answer+forming
        # with no evidence_type recorded.
        result = self.decide({"goal": ["answer"], "question_focus": "forming", "evidence_type": None})
        self.assertEqual(result["matched_row"], "R5")

    def test_r5_trials_forming_still_resolves_scoping(self):
        # R5's evidence_type exclusion only excludes the refusal-only types
        # (qualitative/mixed/test_accuracy_or_model); trials/observational
        # must still resolve via R5, not get swept into the exclusion.
        result = self.decide({"goal": ["answer"], "question_focus": "forming", "evidence_type": "trials"})
        self.assertEqual(result["matched_row"], "R5")

    def test_r6a_answer_qualitative_refuses_never_sr(self):
        result = self.decide({"goal": ["answer"], "evidence_type": "qualitative"})
        self.assertEqual(result["matched_row"], "R6a")
        self.assertEqual(result["kind"], "refuse")
        self.assertIn("systematic_review", result["never"])

    def test_r6b_answer_mixed_refuses(self):
        result = self.decide({"goal": ["answer"], "evidence_type": "mixed"})
        self.assertEqual(result["matched_row"], "R6b")
        self.assertEqual(result["kind"], "refuse")

    def test_r6c_answer_test_accuracy_refuses(self):
        result = self.decide({"goal": ["answer"], "evidence_type": "test_accuracy_or_model"})
        self.assertEqual(result["matched_row"], "R6c")
        self.assertEqual(result["kind"], "refuse")

    def test_r6d_answer_algorithm_cs_se_resolves_mapping_study(self):
        result = self.decide({"goal": ["answer"], "evidence_type": "algorithm", "venue_default": "cs_se"})
        self.assertEqual(result["matched_row"], "R6d")
        self.assertEqual(result["method_id"], "systematic_mapping_study")

    def test_r6d2_answer_algorithm_other_venue_resolves_scoping(self):
        result = self.decide({"goal": ["answer"], "evidence_type": "algorithm", "venue_default": "clinical"})
        self.assertEqual(result["matched_row"], "R6d2")
        self.assertEqual(result["method_id"], "scoping_review")

    def test_r6e_answer_trials_pooling_resolves_sr_pairwise_iv(self):
        result = self.decide(
            {"goal": ["answer"], "evidence_type": "trials", "expects_pooling": "yes", "reviewers": 2, "time_budget": "6+ months"}
        )
        self.assertEqual(result["matched_row"], "R6e")
        self.assertEqual(result["method_id"], "systematic_review")
        self.assertEqual(result["synthesis_family"], "pairwise_iv")

    def test_r6f_answer_observational_no_pooling_resolves_sr_structured_narrative(self):
        result = self.decide(
            {"goal": ["answer"], "evidence_type": "observational", "expects_pooling": "no", "reviewers": 2, "time_budget": "6+ months"}
        )
        self.assertEqual(result["matched_row"], "R6f")
        self.assertEqual(result["synthesis_family"], "structured_narrative")


class ProfileOfferAndOverrideTests(unittest.TestCase):
    def test_r7_afternoon_and_answer_overrides_to_reconnaissance(self):
        result = route.decide(
            {
                "goal": ["answer"], "evidence_type": "trials", "expects_pooling": "no",
                "reviewers": 2, "time_budget": "afternoon",
            },
            shipped_method_ids=ALL_TARGETS,
        )
        self.assertEqual(result["method_id"], "reconnaissance")
        self.assertIn("here is the path", result["explain"])

    def test_r7_single_reviewer_offers_profile(self):
        result = route.decide(
            {
                "goal": ["answer"], "evidence_type": "trials", "expects_pooling": "no",
                "reviewers": 1, "time_budget": "6+ months",
            },
            shipped_method_ids=ALL_TARGETS,
        )
        self.assertIn("single_reviewer", result["profile_flags"])

    def test_r7_rapid_offered_for_short_time_budget(self):
        result = route.decide(
            {
                "goal": ["answer"], "evidence_type": "trials", "expects_pooling": "no",
                "reviewers": 2, "time_budget": "week",
            },
            shipped_method_ids=ALL_TARGETS,
        )
        self.assertIn("rapid", result["profile_flags"])

    def test_r8_appraisal_intent_annotates_non_sr_result(self):
        result = route.decide(
            {"goal": ["orient"], "appraisal_intent": "yes"},
            shipped_method_ids=ALL_TARGETS,
        )
        self.assertEqual(result["method_id"], "reconnaissance")
        self.assertIn("reconnaissance", result["explain"])

    def test_record_override_sets_reason_only_when_changed(self):
        recommended = route.decide({"goal": ["map"]}, shipped_method_ids=ALL_TARGETS)
        same = route.record_override(recommended, chosen_id=recommended["method_id"], override_reason="unused")
        self.assertIsNone(same["override_reason"])
        changed = route.record_override(recommended, chosen_id="reconnaissance", override_reason="want a quick look first")
        self.assertEqual(changed["chosen_id"], "reconnaissance")
        self.assertEqual(changed["override_reason"], "want a quick look first")

    def test_resolve_pack_prefers_explicit_answer_then_default_then_generic(self):
        self.assertEqual(route.resolve_pack({"pack": "cs_se"}, claude_local_pack="medical_imaging"), "cs_se")
        self.assertEqual(route.resolve_pack({}, claude_local_pack="medical_imaging"), "medical_imaging")
        self.assertEqual(route.resolve_pack({}, claude_local_pack=None), "generic")


class ShippedManifestGateTests(unittest.TestCase):
    """M4's real, non-hypothetical behaviour: systematic_review,
    scoping_review, systematic_mapping_study, and reconnaissance are all
    shipped now -- routing resolves to every one of them for real, not just
    the mocked ALL_TARGETS set RowResolutionTests exercises."""

    def test_default_gate_uses_real_list_manifests(self):
        result = route.decide({"goal": ["answer"], "evidence_type": "trials", "expects_pooling": "no",
                                "reviewers": 2, "time_budget": "6+ months"})
        self.assertEqual(result["kind"], "resolve")
        self.assertEqual(result["method_id"], "systematic_review")

    def test_now_shipped_scoping_and_mapping_manifests_actually_resolve(self):
        # docs/PLAN.md M3: once these manifests exist, routing must resolve
        # to them for real -- this is the parity fix the reviewer asked for.
        scoping = route.decide({"goal": ["map"], "evidence_type": "trials"})  # R4d -> scoping_review
        self.assertEqual(scoping["kind"], "resolve")
        self.assertEqual(scoping["method_id"], "scoping_review")

        mapping = route.decide({"goal": ["map"], "evidence_type": "algorithm", "venue_default": "cs_se"})  # R4a
        self.assertEqual(mapping["kind"], "resolve")
        self.assertEqual(mapping["method_id"], "systematic_mapping_study")

    def test_now_shipped_reconnaissance_manifest_actually_resolves(self):
        # docs/ROADMAP.md M4: once methods/reconnaissance.json exists,
        # routing must resolve to it for real -- the same parity fix PR A
        # (M3) made for scoping_review/systematic_mapping_study.
        result = route.decide({"goal": ["orient"]})  # R3 -> reconnaissance
        self.assertEqual(result["kind"], "resolve")
        self.assertEqual(result["method_id"], "reconnaissance")

    def test_unshipped_target_still_refuses_with_pointer(self):
        # Isolates the refusal mechanism itself from which manifests happen
        # to be shipped today, using an explicit empty roster -- same
        # assertion the pre-M4 test made for a real gap, kept alive on
        # purpose now that every method_id the routing table names is shipped.
        result = route.decide({"goal": ["orient"]}, shipped_method_ids=set())
        self.assertEqual(result["kind"], "refuse")
        self.assertIn("reconnaissance", result["reason"])
        self.assertEqual(result["pointer"], route.ROADMAP_POINTER)

    def test_refusal_now_offers_the_now_shipped_scoping_review(self):
        # R2's row offers "scoping_review" -- now a real, shipped manifest,
        # so the offer legitimately survives the shipped-manifest filter.
        result = route.decide({"goal": ["overview"]})  # R2 -> REFUSE, offer=["scoping_review"]
        self.assertEqual(result["kind"], "refuse")
        self.assertEqual(result["offer"], ["scoping_review"])

    def test_refusal_still_filters_an_offer_that_is_not_shipped(self):
        # Isolates the filtering mechanism itself from which manifests
        # happen to be shipped today, using an explicit smaller roster --
        # same assertion the pre-M3 test made, kept alive on purpose.
        result = route.decide({"goal": ["overview"]}, shipped_method_ids=set())
        self.assertEqual(result["kind"], "refuse")
        self.assertEqual(result["offer"], [])

    def test_refusal_keeps_a_shipped_offer(self):
        result = route.decide({"goal": ["overview"]}, shipped_method_ids={"scoping_review"})
        self.assertEqual(result["offer"], ["scoping_review"])


class NoMatchTests(unittest.TestCase):
    def test_no_matching_row_raises_route_error(self):
        with self.assertRaises(route.RouteError):
            route.decide({"goal": []}, shipped_method_ids=ALL_TARGETS)


class PackSourceCoverageTests(unittest.TestCase):
    # docs/PLAN.md M3 / §2.4 line 4: the "because" card's coverage
    # statement, now that packs/{generic,clinical_interventions,cs_se}.json
    # actually ship.
    def test_generic_pack_coverage_marks_registry_unreachable(self):
        coverage = route.pack_source_coverage("generic")
        by_role = {c["role"]: c for c in coverage}
        self.assertFalse(by_role["registry"]["reachable"])
        self.assertIsNone(by_role["registry"]["reachable_via"])

    def test_generic_pack_coverage_marks_openalex_reachable(self):
        coverage = route.pack_source_coverage("generic")
        openalex = next(c for c in coverage if c["reachable_via"] == "openalex")
        self.assertTrue(openalex["reachable"])

    def test_cs_se_pack_coverage_marks_ieee_and_acm_unreachable(self):
        coverage = route.pack_source_coverage("cs_se")
        unreachable_sources = {c["source"] for c in coverage if not c["reachable"]}
        self.assertIn("IEEE Xplore", unreachable_sources)
        self.assertIn("ACM Digital Library", unreachable_sources)

    def test_unshipped_pack_id_returns_none(self):
        self.assertIsNone(route.pack_source_coverage("some_future_pack_not_yet_shipped"))


class MainCliPackFieldsTests(unittest.TestCase):
    def _run_main(self, answers, extra_args=None):
        import contextlib
        import io
        import json as _json
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            _json.dump(answers, f)
            path = f.name
        try:
            buf = io.StringIO()
            argv = ["--answers-json", path] + (extra_args or [])
            with contextlib.redirect_stdout(buf):
                rc = route.main(argv)
            return rc, _json.loads(buf.getvalue()) if rc == 0 else buf.getvalue()
        finally:
            os.unlink(path)

    def test_cli_output_includes_resolved_pack_and_coverage(self):
        rc, printed = self._run_main({"goal": ["map"], "evidence_type": "algorithm"})
        self.assertEqual(rc, 0)
        self.assertEqual(printed["pack"], "generic")
        self.assertIsInstance(printed["pack_source_coverage"], list)
        self.assertTrue(len(printed["pack_source_coverage"]) >= 1)

    def test_cli_claude_local_pack_flag_selects_pack(self):
        rc, printed = self._run_main(
            {"goal": ["map"], "evidence_type": "algorithm"},
            extra_args=["--claude-local-pack", "cs_se"],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(printed["pack"], "cs_se")

    def test_cli_explicit_answers_pack_wins_over_claude_local_pack(self):
        rc, printed = self._run_main(
            {"goal": ["map"], "evidence_type": "algorithm", "pack": "clinical_interventions"},
            extra_args=["--claude-local-pack", "cs_se"],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(printed["pack"], "clinical_interventions")


if __name__ == "__main__":
    unittest.main()
