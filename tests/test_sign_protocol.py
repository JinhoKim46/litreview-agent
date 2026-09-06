"""Unit tests for tools/sign_protocol.py (real gap fix: nothing in the
shipped pipeline wrote protocol.json's top-level signed_at before this,
so label_gate.py's check_protocol_signed_before_first_protocol_driven_run
always failed closed for every real review -- only test fixtures
fabricated the field directly)."""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import label_gate, path_policy, sign_protocol


def _complete_protocol(**overrides):
    protocol = {
        "title": "Example review",
        "objective": "Assess X.",
        "framework": "PICO",
        "framework_fields": {"population": "adults", "intervention": "X", "comparator": "Y", "outcome": "Z"},
        "eligibility": {
            "population": {"criterion": "adults", "gate": "hard"},
            "study_design": {"included": ["RCT"], "gate": "hard"},
            "publication_type": {"included": ["peer-reviewed journal article"], "gate": "hard"},
            "date_range": {"from": "2015-01-01", "to": None, "gate": "hard"},
            "language": {"included": ["English"], "gate": "hard", "translation_used": False},
        },
        "scope": {"mode": "global", "region": None, "translation_used": False, "translation_languages": [], "coverage_gaps": []},
    }
    protocol.update(overrides)
    return protocol


class CheckCompletenessTests(unittest.TestCase):
    def test_complete_protocol_has_no_missing_fields(self):
        self.assertEqual(sign_protocol.check_completeness(_complete_protocol()), [])

    def test_null_date_range_to_and_null_region_are_not_gaps(self):
        # litreview-init.md Step 5's own documented exception list.
        protocol = _complete_protocol()
        protocol["eligibility"]["date_range"]["to"] = None
        protocol["scope"]["region"] = None
        self.assertEqual(sign_protocol.check_completeness(protocol), [])

    def test_missing_title_is_flagged(self):
        protocol = _complete_protocol(title="")
        self.assertIn("title", sign_protocol.check_completeness(protocol))

    def test_empty_framework_fields_value_is_flagged(self):
        protocol = _complete_protocol()
        protocol["framework_fields"]["outcome"] = ""
        self.assertIn("framework_fields.outcome", sign_protocol.check_completeness(protocol))

    def test_missing_eligibility_criterion_is_flagged(self):
        protocol = _complete_protocol()
        protocol["eligibility"]["population"]["criterion"] = ""
        self.assertIn("eligibility.population.criterion", sign_protocol.check_completeness(protocol))

    def test_empty_study_design_included_is_flagged(self):
        protocol = _complete_protocol()
        protocol["eligibility"]["study_design"]["included"] = []
        self.assertIn("eligibility.study_design.included", sign_protocol.check_completeness(protocol))

    def test_missing_scope_mode_is_flagged(self):
        protocol = _complete_protocol()
        protocol["scope"]["mode"] = ""
        self.assertIn("scope.mode", sign_protocol.check_completeness(protocol))


class SignTests(unittest.TestCase):
    SLUG = "sign-protocol-test-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def _write(self, protocol):
        (self.topic_dir / "protocol.json").write_text(json.dumps(protocol))

    def test_sign_missing_protocol_raises(self):
        with self.assertRaises(sign_protocol.SignProtocolError):
            sign_protocol.sign(self.topic_dir, "reviewer-a")

    def test_sign_incomplete_protocol_raises_and_lists_missing_fields(self):
        self._write(_complete_protocol(title=""))
        with self.assertRaises(sign_protocol.SignProtocolError) as ctx:
            sign_protocol.sign(self.topic_dir, "reviewer-a")
        self.assertIn("title", str(ctx.exception))

    def test_sign_complete_protocol_writes_signed_at_and_signed_by(self):
        self._write(_complete_protocol())
        signed = sign_protocol.sign(self.topic_dir, "reviewer-a")
        self.assertIsNotNone(signed["signed_at"])
        self.assertEqual(signed["signed_by"], "reviewer-a")
        on_disk = json.loads((self.topic_dir / "protocol.json").read_text())
        self.assertEqual(on_disk["signed_at"], signed["signed_at"])

    def test_sign_is_idempotent_and_never_redates(self):
        self._write(_complete_protocol())
        first = sign_protocol.sign(self.topic_dir, "reviewer-a")
        second = sign_protocol.sign(self.topic_dir, "reviewer-b")
        self.assertEqual(second["signed_at"], first["signed_at"])
        self.assertEqual(second["signed_by"], "reviewer-a")  # not overwritten to reviewer-b

    def test_already_signed_but_incomplete_protocol_still_raises(self):
        # A hand-written or otherwise bogus signed_at must not bypass the
        # completeness gate -- that's the exact bypass this script exists
        # to prevent, coming back in through a different door.
        protocol = _complete_protocol(title="")
        protocol["signed_at"] = "2020-01-01T00:00:00Z"
        protocol["signed_by"] = "someone"
        self._write(protocol)
        with self.assertRaises(sign_protocol.SignProtocolError) as ctx:
            sign_protocol.sign(self.topic_dir, "reviewer-a")
        self.assertIn("title", str(ctx.exception))

    def test_cli_smoke(self):
        self._write(_complete_protocol())
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sign_protocol.main(["--topic", self.SLUG, "--signed-by", "reviewer-a"])
        self.assertEqual(rc, 0)
        self.assertIn("signed_at", buf.getvalue())

    def test_cli_refuses_for_invalid_slug(self):
        rc = sign_protocol.main(["--topic", "../etc/passwd", "--signed-by", "x"])
        self.assertEqual(rc, 1)


class SignThenComputeLabelIntegrationTests(unittest.TestCase):
    """The test advisor named: does compute_label() see a real
    protocol_signed_before_first_protocol_driven_run pass when the
    protocol was actually written and signed through this module, rather
    than by a fixture that fabricates signed_at directly?"""

    SLUG = "sign-protocol-label-gate-integration-topic"

    def setUp(self):
        self.topic_dir = path_policy.RESULTS_ROOT / self.SLUG
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_two_reviewer_fixture_signed_via_sign_protocol_computes_systematic_review(self):
        protocol = _complete_protocol(method={"id": "systematic_review"})
        (self.topic_dir / "protocol.json").write_text(json.dumps(protocol))
        sign_protocol.sign(self.topic_dir, "reviewer-a")

        with open(self.topic_dir / "screening_decisions.jsonl", "w") as f:
            f.write(json.dumps({"record_id": "r1", "stage": "title_abstract", "decision": "include", "by": "reviewer-a", "role": "decision"}) + "\n")
            f.write(json.dumps({"record_id": "r2", "stage": "title_abstract", "decision": "exclude", "by": "reviewer-b", "role": "decision"}) + "\n")

        result = label_gate.compute_label(self.SLUG)
        self.assertEqual(result["label"], "systematic review")
        self.assertNotIn("protocol_signed_before_first_protocol_driven_run", result["missing"])


if __name__ == "__main__":
    unittest.main()
