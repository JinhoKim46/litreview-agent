"""Fixture-based unit test for connectors/arxiv.py -- no live network calls.

Reuses the existing fixtures/arxiv_search.xml and fixtures/arxiv_error.xml
(the real arXiv API returns Atom XML, not JSON, so those -- not a
same-named .json file -- are the realistic saved response shape for this
connector; see connectors/arxiv.py's module docstring for the confirmed
API shape).

Patches connectors._shared.http_get_with_backoff (arxiv.py calls it as
`_shared.http_get_with_backoff`, so patching the attribute on the _shared
module is what actually intercepts it) so these exercise the real
mapping/pagination/CLI code against captured real-shape Atom responses.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors import _shared, arxiv

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_bytes(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


class FakeResponse:
    def __init__(self, content_bytes, status_code=200):
        self.content = content_bytes
        self.status_code = status_code
        self.text = content_bytes.decode("utf-8", errors="replace")
        self.headers = {}


def _search_args(**overrides):
    """Build an argparse Namespace via the real shared scaffold."""
    query = overrides.pop("query", "all:transformer")
    parser = _shared.build_arg_parser("arxiv")
    argv = ["search", "--query", query]
    for flag, val in overrides.items():
        argv += [f"--{flag.replace('_', '-')}", str(val)]
    return parser.parse_args(argv)


class ArxivConnectorTest(unittest.TestCase):
    def setUp(self):
        # Neutralize the real 3s courtesy-delay throttle so tests run fast
        # and don't race a shared tempfile across test runs.
        patcher = mock.patch.object(arxiv, "_respect_courtesy_rate", lambda: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fixture_bytes = _load_bytes("arxiv_search.xml")
        self.error_bytes = _load_bytes("arxiv_error.xml")

    def test_search_matches_fixed_output_shape(self):
        with mock.patch.object(
            _shared, "http_get_with_backoff", return_value=FakeResponse(self.fixture_bytes)
        ) as mock_get:
            payload = arxiv.search(_search_args(limit=2))

        mock_get.assert_called_once()
        self.assertTrue(_shared.validate_output_shape(payload))
        self.assertEqual(payload["meta"]["source"], "arxiv")
        self.assertEqual(payload["meta"]["retrieved"], 2)
        self.assertEqual(payload["meta"]["total_available"], 57312)
        self.assertTrue(payload["meta"]["truncated"])  # 2 retrieved out of 57312

    def test_record_fields_mapped_correctly(self):
        with mock.patch.object(
            _shared, "http_get_with_backoff", return_value=FakeResponse(self.fixture_bytes)
        ):
            payload = arxiv.search(_search_args(limit=2))

        first = payload["results"][0]
        self.assertEqual(first["id"], "1706.03762v7")
        self.assertEqual(first["title"], "Attention Is All You Need")
        self.assertEqual(first["authors"], ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"])
        self.assertEqual(first["year"], 2017)
        self.assertEqual(first["venue"], "arXiv preprint")  # preprints-only rule
        self.assertIsNone(first["doi"])
        self.assertEqual(first["url"], "http://arxiv.org/abs/1706.03762v7")
        self.assertEqual(first["source"], "arxiv")

        second = payload["results"][1]
        self.assertEqual(second["doi"], "10.48550/arXiv.2010.11929")

    def test_error_feed_maps_to_invalid_query(self):
        """arXiv reports a bad query as a 200 Atom feed, not an HTTP error."""
        with mock.patch.object(
            _shared, "http_get_with_backoff", return_value=FakeResponse(self.error_bytes)
        ):
            with self.assertRaises(arxiv.ArxivError) as ctx:
                arxiv.search(_search_args(query="au:[AND]"))
        self.assertEqual(ctx.exception.code, "INVALID_QUERY")

    def test_rate_limited_status_maps_to_rate_limited_code(self):
        with mock.patch.object(
            _shared, "http_get_with_backoff", return_value=FakeResponse(b"", status_code=429)
        ):
            with self.assertRaises(arxiv.ArxivError) as ctx:
                arxiv.search(_search_args())
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

    def test_cli_search_produces_contract_shaped_stdout(self):
        argv_backup = sys.argv
        sys.argv = ["connectors.arxiv", "search", "--query", "all:transformer", "--limit", "2"]
        try:
            with mock.patch.object(
                _shared, "http_get_with_backoff", return_value=FakeResponse(self.fixture_bytes)
            ):
                with mock.patch("builtins.print") as mock_print:
                    arxiv.main()
        finally:
            sys.argv = argv_backup

        payload = json.loads(mock_print.call_args[0][0])
        self.assertTrue(_shared.validate_output_shape(payload))
        self.assertEqual(payload["meta"]["source"], "arxiv")
        self.assertEqual(payload["results"][0]["id"], "1706.03762v7")

    def test_cli_missing_query_writes_standard_error_shape_and_exits_1(self):
        """--query-file with a --source-key absent from the plan -> resolve_query's
        ValueError -> search() wraps it as ArxivError(INVALID_QUERY) -> main()'s
        write_error + exit(1)."""
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        argv_backup = sys.argv
        sys.argv = ["connectors.arxiv", "search", "--query-file", plan_path, "--source-key", "nonexistent"]
        try:
            with mock.patch.object(_shared.sys, "stderr") as mock_stderr:
                with self.assertRaises(SystemExit) as ctx:
                    arxiv.main()
        finally:
            sys.argv = argv_backup

        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "INVALID_QUERY")
        self.assertIn("error", err)


if __name__ == "__main__":
    unittest.main()
