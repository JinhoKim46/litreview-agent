"""Fixture-based tests for connectors.semanticscholar -- no live network calls.

Mocks connectors.semanticscholar.http_get_with_backoff directly (rather than
mocking `requests`) since that's the seam the connector actually calls through.
"""
import argparse
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors import semanticscholar as s2  # noqa: E402
from connectors._shared import validate_output_shape  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    def json(self):
        return self._json_body


def _search_args(**overrides):
    ns = argparse.Namespace(
        query="machine learning", query_file=None, source_key=None,
        limit=25, page=0, cursor=None, since=None, until=None,
        format="json", out=None,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


class TestSemanticScholarSearch(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(FIXTURE_DIR, "semanticscholar_search_response.json")) as f:
            self.fixture = json.load(f)

    def test_search_shape_and_fields(self):
        with patch.object(s2, "http_get_with_backoff", return_value=FakeResponse(200, self.fixture)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                s2.cmd_search(_search_args())
        output = json.loads(buf.getvalue())
        validate_output_shape(output)  # raises on any contract violation
        self.assertEqual(output["meta"]["source"], "semanticscholar")
        self.assertEqual(output["meta"]["retrieved"], 2)
        self.assertEqual(output["meta"]["total_available"], 2)
        self.assertFalse(output["meta"]["truncated"])
        first = output["results"][0]
        self.assertEqual(first["doi"], "10.18653/v1/N18-3011")
        self.assertEqual(first["authors"], ["Waleed Ammar", "Dirk Groeneveld"])
        second = output["results"][1]
        self.assertIsNone(second["doi"])  # no DOI in externalIds -> null, never omitted
        self.assertIsNone(second["abstract"])

    def test_truncated_true_when_more_available_than_retrieved(self):
        fixture = dict(self.fixture, total=500)
        with patch.object(s2, "http_get_with_backoff", return_value=FakeResponse(200, fixture)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                s2.cmd_search(_search_args(limit=2))
        output = json.loads(buf.getvalue())
        self.assertEqual(output["meta"]["total_available"], 500)
        self.assertTrue(output["meta"]["truncated"])

    def test_rate_limited_after_retries_maps_to_error_code(self):
        with patch.object(s2, "http_get_with_backoff", return_value=FakeResponse(429, text="slow down")):
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                s2.cmd_search(_search_args())
        self.assertEqual(ctx.exception.code, 1)
        payload = json.loads(err.getvalue())
        self.assertEqual(payload["code"], "RATE_LIMITED")
        self.assertIn("error", payload)

    def test_missing_query_is_invalid_query_error(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            s2.cmd_search(_search_args(query=None, query_file=None))
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(json.loads(err.getvalue())["code"], "INVALID_QUERY")


class TestSemanticScholarDetail(unittest.TestCase):
    def test_detail_found(self):
        paper = {
            "paperId": "abc123",
            "title": "A Paper",
            "abstract": "abstract text",
            "year": 2021,
            "venue": "Venue",
            "authors": [{"authorId": "1", "name": "A Author"}],
            "externalIds": {"DOI": "10.1/x"},
            "url": "https://example.org/abc123",
        }
        with patch.object(s2, "http_get_with_backoff", return_value=FakeResponse(200, paper)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                s2.cmd_detail(argparse.Namespace(id="abc123", format="json", out=None))
        output = json.loads(buf.getvalue())
        validate_output_shape(output)
        self.assertEqual(output["meta"]["retrieved"], 1)
        self.assertEqual(output["results"][0]["id"], "abc123")

    def test_detail_not_found_returns_empty_results_not_error(self):
        with patch.object(s2, "http_get_with_backoff", return_value=FakeResponse(404)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                s2.cmd_detail(argparse.Namespace(id="doesnotexist", format="json", out=None))
        output = json.loads(buf.getvalue())
        validate_output_shape(output)
        self.assertEqual(output["results"], [])
        self.assertEqual(output["meta"]["retrieved"], 0)

    def test_bare_doi_gets_prefixed(self):
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return FakeResponse(404)

        with patch.object(s2, "http_get_with_backoff", side_effect=fake_get):
            buf = io.StringIO()
            with redirect_stdout(buf):
                s2.cmd_detail(argparse.Namespace(id="10.1234/xyz", format="json", out=None))
        self.assertTrue(captured["url"].endswith("/paper/DOI:10.1234/xyz"))


if __name__ == "__main__":
    unittest.main()
