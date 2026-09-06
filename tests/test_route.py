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

    def test_r5_is_currently_shadowed_by_r3s_unconditional_forming_clause(self):
        # Spec defect, not a test bug: R3 ("... or question_focus == forming")
        # is unconditional on goal and precedes R5 in the documented row
        # order, so it wins first. See _routing.json's R5 "_flagged" note and
        # the PR body -- flagged for a human to disambiguate, not silently
        # patched by reordering rows on a guess about intent.
        result = self.decide({"goal": ["answer"], "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R3")
        self.assertEqual(result["method_id"], "reconnaissance")

    def test_r4_map_sub_cases_also_shadowed_by_r3s_forming_clause(self):
        # Same defect as R5, on a different row: a "map" goal with
        # question_focus="forming" never reaches R4a-R4d's algorithm/venue
        # logic. Documented, not silently patched -- see the _flagged note.
        result = self.decide({"goal": ["map"], "evidence_type": "algorithm", "venue_default": "cs_se", "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R3")
        self.assertEqual(result["method_id"], "reconnaissance")

    def test_r6a_qualitative_refusal_also_shadowed_by_r3s_forming_clause(self):
        # The most consequential instance: a qualitative question that is
        # also "forming" resolves via R3 to reconnaissance instead of
        # hitting R6a's hard REFUSE (never systematic_review). This is a
        # fail-closed path being silently bypassed for a subset of inputs --
        # flagged prominently in the PR body, not patched by guessing at
        # reordering.
        result = self.decide({"goal": ["answer"], "evidence_type": "qualitative", "question_focus": "forming"})
        self.assertEqual(result["matched_row"], "R3")
        self.assertNotEqual(result["method_id"], "systematic_review")

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
    """M3's real, non-hypothetical behaviour: systematic_review,
    scoping_review, and systematic_mapping_study are shipped;
    reconnaissance still refuses honestly (no stub manifests -- routing
    refusals instead, per docs/PLAN.md's dissent log)."""

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

    def test_unshipped_target_refuses_with_pointer(self):
        result = route.decide({"goal": ["orient"]})  # -> reconnaissance, still not shipped
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


if __name__ == "__main__":
    unittest.main()
