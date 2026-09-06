"""Schema-validity tests for schemas/charting_table.schema.json and
schemas/classification_table.schema.json (docs/PLAN.md M3), written by the
evidence-mapping and study-classification skills respectively. Confirms the
schemas themselves are valid JSON Schema 2020-12, accept a worked example
matching §3.1 S5's shape (same discipline used for
schemas/protocol_method.schema.json in M2), and accept what
tools/charting_gate.freeze() / tools/classification_gate.freeze() /
record_calibration() actually write, not just a hand-built example."""
import json
import os
import shutil
import sys
import unittest

import jsonschema

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import charting_gate, classification_gate, path_policy  # noqa: E402


def _load(name):
    with open(os.path.join(ROOT, "schemas", name)) as f:
        return json.load(f)


class ChartingTableSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = _load("charting_table.schema.json")

    def test_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)

    def test_worked_example_validates(self):
        example = {
            "framework_version": "1.0.0", "topic": "example-topic",
            "charting_form_frozen": True,
            "fields": ["year", "venue", "publication_type", "method_family", "main_metric"],
            "studies": [
                {
                    "record_id": "openalex:W1", "data": {"year": 2024, "venue": "MICCAI", "method_family": "diffusion"},
                    "source": {"quote": "We propose a diffusion-based reconstruction method.", "page": "2", "hash": None},
                    "suggested_by": "llm", "by": "claude (single coder pass)", "verified_by": None,
                },
            ],
        }
        jsonschema.validate(example, self.schema)

    def test_pre_freeze_state_with_no_fields_validates(self):
        example = {"framework_version": "1.0.0", "topic": "example-topic", "charting_form_frozen": False, "studies": []}
        jsonschema.validate(example, self.schema)

    def test_missing_required_field_rejected(self):
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate({"framework_version": "1.0.0", "topic": "x"}, self.schema)

    def test_freeze_output_round_trips_through_the_schema(self):
        # tools/charting_gate.freeze() writes charting_table.json directly --
        # confirm what it actually produces (not just a hand-built example)
        # satisfies the schema it's supposed to conform to.
        slug = "capture-schema-roundtrip-charting"
        topic_dir = path_policy.RESULTS_ROOT / slug
        if topic_dir.exists():
            shutil.rmtree(topic_dir)
        os.makedirs(topic_dir, exist_ok=True)
        try:
            table = charting_gate.freeze(topic_dir, slug, ["year", "venue"])
            jsonschema.validate(table, self.schema)
        finally:
            shutil.rmtree(topic_dir)


class ClassificationTableFreezeRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.schema = _load("classification_table.schema.json")
        self.slug = "capture-schema-roundtrip-classification"
        self.topic_dir = path_policy.RESULTS_ROOT / self.slug
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)

    def tearDown(self):
        if self.topic_dir.exists():
            shutil.rmtree(self.topic_dir)

    def test_freeze_output_round_trips_through_the_schema(self):
        table = classification_gate.freeze(self.topic_dir, self.slug, [{"name": "research_type", "categories": ["validation"]}])
        jsonschema.validate(table, self.schema)

    def test_record_calibration_output_round_trips_through_the_schema(self):
        classification_gate.freeze(self.topic_dir, self.slug, [{"name": "research_type", "categories": ["validation"]}])
        table = classification_gate.record_calibration(
            self.topic_dir, self.slug,
            {"mode": "intra_rater_delayed", "sample_size": 10, "agreement": 0.87, "disagreements": ["r3"]},
        )
        jsonschema.validate(table, self.schema)


class ClassificationTableSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = _load("classification_table.schema.json")

    def test_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)

    def test_worked_example_with_calibration_validates(self):
        example = {
            "framework_version": "1.0.0", "topic": "example-topic", "scheme_frozen": True,
            "facets": [
                {"name": "research_type", "categories": ["evaluation", "validation", "solution proposal", "philosophical", "opinion", "experience"]},
                {"name": "dataset", "categories": ["fastMRI", "BraTS", "other"]},
            ],
            "calibration": {"mode": "intra_rater_delayed", "sample_size": 12, "agreement": 0.83, "disagreements": ["study-7: research_type"]},
            "studies": [
                {
                    "record_id": "openalex:W2", "codes": {"research_type": "evaluation", "dataset": "fastMRI"},
                    "source": {"quote": "We evaluate our method on the fastMRI dataset.", "page": "4", "hash": None},
                    "suggested_by": "llm", "by": "claude (single coder pass)", "verified_by": None,
                },
            ],
        }
        jsonschema.validate(example, self.schema)

    def test_pre_freeze_state_with_no_facets_or_calibration_validates(self):
        example = {"framework_version": "1.0.0", "topic": "example-topic", "scheme_frozen": False, "studies": []}
        jsonschema.validate(example, self.schema)


if __name__ == "__main__":
    unittest.main()
