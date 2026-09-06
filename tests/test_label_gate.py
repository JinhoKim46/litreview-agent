"""Unit tests for tools/label_gate.py (docs/PLAN.md M2). Real results/<slug>/
fixture directories, per tests/test_method.py's established convention."""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import label_gate, path_policy


def _write_json(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(content, f)


def _write_raw(topic_dir, name, fetched_at, purpose=None):
    meta = {"fetched_at": fetched_at}
    if purpose is not None:
        meta["purpose"] = purpose
    _write_json(os.path.join(topic_dir, "raw", name), {"meta": meta, "records": []})


class LabelGateFixtureTests(unittest.TestCase):
    SLUG = "label-gate-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def _write_protocol(self, **overrides):
        content = {"signed_at": "2026-01-01T00:00:00Z", "method": {"id": "systematic_review"}}
        content.update(overrides)
        _write_json(str(self.topic_dir / "protocol.json"), content)

    def _write_ledger(self, entries):
        with open(self.topic_dir / "screening_decisions.jsonl", "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    # -- single-screener fixture: exit criterion "systematized review" -----

    def test_single_screener_fixture_downgrades_to_systematized_review(self):
        self._write_protocol()
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "reviewer-a", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "systematized review")
        self.assertIn("second_reviewer_involvement_in_selection", result["missing"])

    def test_single_screener_label_identical_across_repeated_calls(self):
        # §2.4: same label_gate.py code at routing, status and report --
        # a pure function called twice on unchanged state must agree exactly.
        self._write_protocol()
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "reviewer-a", "role": "decision"},
        ])
        first = label_gate.compute_label(self.SLUG)
        second = label_gate.compute_label(self.SLUG)
        self.assertEqual(first, second)

    # -- verification-sample fixture: exit criterion "systematic review" + disclosure

    def test_verification_sample_fixture_resolves_systematic_review_with_disclosure(self):
        self._write_protocol()
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "reviewer-a", "role": "decision"},
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "reviewer-b", "role": "verification"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "systematic review")
        self.assertEqual(result["missing"], [])
        # min_index_families and registry_lookup_recorded are "not_recorded"
        # (no index_family data yet; no routing block recorded) -- a
        # disclosure, never a downgrade, per §2.4.
        self.assertIn("min_index_families", result["disclosures"])
        self.assertIn("registry_lookup_recorded", result["disclosures"])

    def test_dual_screener_without_verification_role_also_satisfies_second_reviewer_check(self):
        self._write_protocol()
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "reviewer-a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "reviewer-b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "systematic review")

    # -- protocol sign timing ------------------------------------------------

    def test_protocol_signed_after_first_protocol_driven_run_downgrades(self):
        self._write_protocol(signed_at="2026-06-01T00:00:00Z")
        _write_raw(str(self.topic_dir), "openalex-20260101.json", "2026-01-01T00:00:00Z", purpose="protocol_driven")
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "systematized review")
        self.assertIn("protocol_signed_before_first_protocol_driven_run", result["missing"])

    def test_orienting_run_excluded_from_first_protocol_driven_run_timestamp(self):
        # An orienting (Q0) run before the protocol was signed must not count
        # as "the first protocol-driven run" -- it happens by design before
        # G-Protocol.
        self._write_protocol(signed_at="2026-01-15T00:00:00Z")
        _write_raw(str(self.topic_dir), "openalex-20260101-orienting.json", "2026-01-01T00:00:00Z", purpose="orienting")
        _write_raw(str(self.topic_dir), "openalex-20260201-protocol.json", "2026-02-01T00:00:00Z", purpose="protocol_driven")
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertNotIn("protocol_signed_before_first_protocol_driven_run", result["missing"])

    def test_missing_signed_at_fails_closed(self):
        self._write_protocol(signed_at=None)
        del_content = json.loads((self.topic_dir / "protocol.json").read_text())
        del del_content["signed_at"]
        _write_json(str(self.topic_dir / "protocol.json"), del_content)
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertIn("protocol_signed_before_first_protocol_driven_run", result["missing"])

    # -- registry lookup ------------------------------------------------------

    def test_registry_lookup_recorded_true_when_present(self):
        self._write_protocol(method={
            "id": "systematic_review",
            "routing": {"table_version": "1.0.0", "answers": {}, "q0": {"registry_lookup": {"date": "2026-01-01", "result": "none found", "url": None}},
                        "recommended_id": "systematic_review", "chosen_id": "systematic_review"},
        })
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertNotIn("registry_lookup_recorded", result["disclosures"])
        self.assertNotIn("registry_lookup_recorded", result["missing"])

    def test_registry_lookup_false_when_routing_present_but_lookup_missing(self):
        self._write_protocol(method={
            "id": "systematic_review",
            "routing": {"table_version": "1.0.0", "answers": {}, "q0": {"registry_lookup": None},
                        "recommended_id": "systematic_review", "chosen_id": "systematic_review"},
        })
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        # False, not not_recorded -- the mechanism exists for this review
        # (a routing block was recorded) but the lookup itself wasn't done.
        # A definitive False for any requires[] check (not only the two
        # "hard gate" checks) downgrades the label -- "hard gate" only
        # controls how a *not_recorded* result is treated, per §2.4's five
        # requirements all being listed as requires[] uniformly.
        self.assertFalse(result["checks"]["registry_lookup_recorded"])
        self.assertNotIn("registry_lookup_recorded", result["disclosures"])
        self.assertIn("registry_lookup_recorded", result["missing"])
        self.assertEqual(result["label"], "systematized review")

    # -- pooling under a signed plan ------------------------------------------

    def test_pooling_only_under_signed_plan_vacuous_when_no_synthesis_output(self):
        self._write_protocol()
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertTrue(result["checks"]["pooling_only_under_signed_plan"])

    def test_pooling_only_under_signed_plan_false_for_post_hoc_pool(self):
        self._write_protocol()
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
            {"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "b", "role": "decision"},
        ])
        _write_json(str(self.topic_dir / "synthesis" / "effect_sizes.json"), [
            {"outcome": "x", "pooled": True, "model_source": "post_hoc"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertFalse(result["checks"]["pooling_only_under_signed_plan"])
        self.assertIn("pooling_only_under_signed_plan", result["missing"])

    # -- rapid profile label override -----------------------------------------

    def test_rapid_profile_flag_overrides_label_regardless_of_missing_checks(self):
        self._write_protocol(method={"id": "systematic_review", "profile_flags": ["rapid"]})
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "a", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "rapid review")

    def test_scoping_review_never_downgraded_for_single_screening(self):
        # docs/PLAN.md M3 / §2.4: "Scoping/mapping reviews are never
        # downgraded for single screening" -- scoping_review's only
        # requires[] check is min_index_families, which always resolves to
        # "not_recorded" and is never a hard-gate check, so a single
        # screener changes nothing about the label; it surfaces only as a
        # disclosure.
        _write_json(str(self.topic_dir / "protocol.json"), {"signed_at": "2026-01-01T00:00:00Z", "method": {"id": "scoping_review"}})
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "solo-reviewer", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "scoping review")
        self.assertEqual(result["missing"], [])
        self.assertIn("min_index_families", result["disclosures"])

    def test_systematic_mapping_study_never_downgraded_for_single_screening(self):
        _write_json(str(self.topic_dir / "protocol.json"), {"signed_at": "2026-01-01T00:00:00Z", "method": {"id": "systematic_mapping_study"}})
        self._write_ledger([
            {"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "solo-reviewer", "role": "decision"},
        ])
        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "systematic mapping study")
        self.assertEqual(result["missing"], [])


class BlockerTests(unittest.TestCase):
    SLUG = "label-gate-blocker-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(str(self.topic_dir / "protocol.json"), {"signed_at": "2026-01-01T00:00:00Z", "method": {"id": "systematic_review"}})

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_missing_fulltext_reason_blocks(self):
        with open(self.topic_dir / "screening_decisions.jsonl", "w") as f:
            f.write(json.dumps({"record_id": "r1", "stage": "full_text", "decision": "exclude", "reason": None, "by": "a", "role": "decision"}) + "\n")
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertIn("fulltext_exclusion_reasons_complete", names)

    def test_complete_fulltext_reasons_do_not_block(self):
        with open(self.topic_dir / "screening_decisions.jsonl", "w") as f:
            f.write(json.dumps({"record_id": "r1", "stage": "full_text", "decision": "exclude", "reason": "wrong population", "by": "a", "role": "decision"}) + "\n")
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("fulltext_exclusion_reasons_complete", names)

    def test_missing_appraisal_blocks_when_mandatory(self):
        _write_json(str(self.topic_dir / "extraction_table.json"), {"studies": [{"record_id": "r1"}]})
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertIn("appraisal_complete", names)

    def test_present_appraisal_does_not_block(self):
        _write_json(str(self.topic_dir / "extraction_table.json"), {"studies": [{"record_id": "r1", "risk_of_bias": {"tool": "RoB1", "overall_judgement": "low risk"}}]})
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("appraisal_complete", names)

    def test_references_verified_blocks_until_recorded(self):
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertIn("references_verified", names)

    def test_references_verified_marker_clears_blocker(self):
        _write_json(str(self.topic_dir / "manuscript" / "references_verified.json"), {"verified": True})
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("references_verified", names)


class ChartingBlockerTests(unittest.TestCase):
    SLUG = "label-gate-charting-blocker-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(str(self.topic_dir / "protocol.json"), {"signed_at": "2026-01-01T00:00:00Z", "method": {"id": "scoping_review"}})
        _write_json(str(self.topic_dir / "manuscript" / "references_verified.json"), {"verified": True})

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_no_charting_table_does_not_block(self):
        # No studies charted yet -- an absent, unfrozen table is vacuously fine.
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("charting_table_matches_frozen_fields", names)

    def test_frozen_table_with_matching_rows_does_not_block(self):
        _write_json(str(self.topic_dir / "charting_table.json"), {
            "charting_form_frozen": True, "fields": ["year"],
            "studies": [{"record_id": "r1", "data": {"year": 2024}}],
        })
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("charting_table_matches_frozen_fields", names)

    def test_frozen_table_with_drifted_row_blocks(self):
        # A row written without ever calling charting_gate.check_gate first --
        # the write path has no other enforcement, so this is what catches it.
        _write_json(str(self.topic_dir / "charting_table.json"), {
            "charting_form_frozen": True, "fields": ["year"],
            "studies": [{"record_id": "bad1", "data": {"year": 2024, "venue": "extra"}}],
        })
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertIn("charting_table_matches_frozen_fields", names)


class ClassificationBlockerTests(unittest.TestCase):
    SLUG = "label-gate-classification-blocker-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
        _write_json(str(self.topic_dir / "protocol.json"), {"signed_at": "2026-01-01T00:00:00Z", "method": {"id": "systematic_mapping_study"}})
        _write_json(str(self.topic_dir / "manuscript" / "references_verified.json"), {"verified": True})

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_no_classification_table_does_not_block(self):
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("classification_table_matches_frozen_scheme", names)

    def test_frozen_scheme_with_matching_rows_does_not_block(self):
        _write_json(str(self.topic_dir / "classification_table.json"), {
            "scheme_frozen": True, "facets": [{"name": "research_type", "categories": ["validation"]}],
            "studies": [{"record_id": "r1", "codes": {"research_type": "validation"}}],
        })
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertNotIn("classification_table_matches_frozen_scheme", names)

    def test_frozen_scheme_with_drifted_row_blocks(self):
        _write_json(str(self.topic_dir / "classification_table.json"), {
            "scheme_frozen": True, "facets": [{"name": "research_type", "categories": ["validation"]}],
            "studies": [{"record_id": "bad1", "codes": {}}],
        })
        blockers = label_gate.compute_blockers(self.SLUG)
        names = {b["blocker"] for b in blockers}
        self.assertIn("classification_table_matches_frozen_scheme", names)


class ForbiddenFormLintTests(unittest.TestCase):
    def setUp(self):
        from tools.method import list_manifests
        self.manifest = list_manifests()["systematic_review"]

    def test_hard_failure_on_no_prior_work(self):
        result = label_gate.lint_text("We found no prior work on this topic.", self.manifest, context="templated_output")
        self.assertTrue(result["hard_failures"])
        self.assertEqual(result["hard_failures"][0]["form"], "no_prior_work")

    def test_calibrated_sentence_passes(self):
        text = ("To our knowledge, within the search described in S1, we did not identify "
                "any prior systematic review addressing this comparison.")
        result = label_gate.lint_text(text, self.manifest, context="templated_output")
        self.assertEqual(result["hard_failures"], [])

    def test_manuscript_section_context_only_warns_never_hard_fails(self):
        result = label_gate.lint_text("This was a comprehensive search of five databases.", self.manifest, context="manuscript_section")
        self.assertEqual(result["hard_failures"], [])
        self.assertTrue(result["warnings"])

    def test_unrelated_words_never_trip_the_lint(self):
        text = "We assessed the gap junction protein and used a comprehensive geriatric assessment scale."
        result = label_gate.lint_text(text, self.manifest, context="templated_output")
        self.assertEqual(result["hard_failures"], [])

    def test_unknown_context_raises(self):
        with self.assertRaises(label_gate.LabelGateError):
            label_gate.lint_text("text", self.manifest, context="bogus")


class WriteLabelJsonTests(unittest.TestCase):
    SLUG = "label-gate-write-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_write_label_json_shape(self):
        label_result = {"label": "systematic review", "missing": [], "disclosures": ["search_age"]}
        path = label_gate.write_label_json(self.SLUG, label_result, [{"blocker": "appraisal_complete", "detail": "x"}])
        written = json.loads(path.read_text())
        self.assertEqual(written["label"], "systematic review")
        self.assertEqual(written["disclosures"], ["search_age"])
        self.assertEqual(written["blockers"], [{"blocker": "appraisal_complete", "detail": "x"}])


if __name__ == "__main__":
    unittest.main()
