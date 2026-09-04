"""Fixture-based tests for connectors.crossref — no live network calls.

Patches connectors._shared.requests.get (where http_get_with_backoff actually
issues the request), so these exercise the real mapping/pagination/CLI code
against captured real-shape Crossref responses.
"""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors import _shared, crossref

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def _fake_response(json_body, status_code=200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = json.dumps(json_body)
    resp.headers = {}
    return resp


class ItemToResultTests(unittest.TestCase):
    def test_maps_standard_journal_article(self):
        item = _load("crossref_search.json")["message"]["items"][0]
        r = crossref.item_to_result(item)
        self.assertEqual(r["id"], "10.1016/0014-5793(86)80287-3")
        self.assertEqual(r["doi"], "10.1016/0014-5793(86)80287-3")
        self.assertEqual(r["title"], "Characterization of central melatonin receptors using 125I-melatonin")
        self.assertEqual(r["venue"], "FEBS Letters")
        self.assertEqual(r["authors"], ["Moshe Laudon", "Nava Zisapel"])
        self.assertEqual(r["year"], 1986)
        self.assertEqual(r["source"], "crossref")
        # JATS tags stripped, entities unescaped, no fabricated content
        self.assertNotIn("<jats:p>", r["abstract"])
        self.assertIn("Kd = 38 nM", r["abstract"])

    def test_missing_abstract_is_null_not_empty_string(self):
        item = _load("crossref_search.json")["message"]["items"][1]
        r = crossref.item_to_result(item)
        self.assertIsNone(r["abstract"])
        self.assertEqual(r["authors"], [])  # empty author list, not a crash
        self.assertIsNone(r["venue"])  # no container-title key at all

    def test_organizational_author_falls_back_to_name(self):
        item = _load("crossref_search.json")["message"]["items"][2]
        r = crossref.item_to_result(item)
        self.assertEqual(r["authors"], ["World Trade Organization"])

    def test_strip_jats_abstract_empty_after_strip_is_none(self):
        self.assertIsNone(crossref.strip_jats_abstract("<jats:p>   </jats:p>"))
        self.assertIsNone(crossref.strip_jats_abstract(None))
        self.assertIsNone(crossref.strip_jats_abstract(""))


class CmdSearchTests(unittest.TestCase):
    def test_search_output_matches_fixed_shape_and_reports_true_total(self):
        fixture = _load("crossref_search.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)):
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["search", "--query", "melatonin sleep", "--limit", "3"])
            with mock.patch("builtins.print") as mock_print:
                crossref.cmd_search(args)
        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)  # raises ValueError if malformed
        self.assertEqual(payload["meta"]["source"], "crossref")
        self.assertEqual(payload["meta"]["retrieved"], 3)
        self.assertEqual(payload["meta"]["total_available"], 98796)
        self.assertTrue(payload["meta"]["truncated"])  # 3 retrieved out of 98796
        self.assertEqual(len(payload["results"]), 3)

    def test_limit_caps_results_without_understating_total(self):
        fixture = _load("crossref_search.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)):
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["search", "--query", "melatonin", "--limit", "1"])
            with mock.patch("builtins.print") as mock_print:
                crossref.cmd_search(args)
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["meta"]["retrieved"], 1)
        self.assertEqual(payload["meta"]["total_available"], 98796)
        self.assertTrue(payload["meta"]["truncated"])

    def test_query_file_and_source_key_resolve_the_stored_query_string(self):
        fixture = _load("crossref_search.json")
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)) as mock_get:
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(
                ["search", "--query-file", plan_path, "--source-key", "crossref", "--limit", "2"]
            )
            with mock.patch("builtins.print") as mock_print:
                crossref.cmd_search(args)
        sent_params = mock_get.call_args[1]["params"]
        self.assertEqual(sent_params["query.bibliographic"], "melatonin sleep insomnia")
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["meta"]["query"], "melatonin sleep insomnia")

    def test_cursor_pagination_follows_next_cursor(self):
        fixture = _load("crossref_search.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)) as mock_get:
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["search", "--query", "melatonin", "--limit", "3", "--cursor", "*"])
            with mock.patch("builtins.print") as mock_print:
                crossref.cmd_search(args)
        sent_params = mock_get.call_args[1]["params"]
        self.assertEqual(sent_params["cursor"], "*")
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["meta"]["retrieved"], 3)


class WriteErrorGoesToStderrTests(unittest.TestCase):
    def test_rate_limited_error_on_stderr_with_correct_code(self):
        with mock.patch.object(
            _shared.requests, "get", return_value=_fake_response({}, status_code=429)
        ), mock.patch.object(_shared.time, "sleep"), mock.patch.object(
            _shared.sys, "stderr"
        ) as mock_stderr:
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["search", "--query", "x", "--limit", "1"])
            with self.assertRaises(SystemExit) as ctx:
                crossref.cmd_search(args)
        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "RATE_LIMITED")

    def test_missing_query_is_invalid_query_error(self):
        # A real query-file with no matching source-key entry —
        # resolve_query's own documented failure mode (KeyError -> ValueError
        # -> INVALID_QUERY).
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        parser = _shared.build_arg_parser("crossref")
        args = parser.parse_args(["search", "--query-file", plan_path, "--source-key", "nonexistent"])
        with mock.patch.object(_shared.sys, "stderr") as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                crossref.cmd_search(args)
        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "INVALID_QUERY")


class CmdDetailTests(unittest.TestCase):
    def test_detail_fetches_single_record_by_doi(self):
        fixture = _load("crossref_detail.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)):
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["detail", "10.1038/nphys1170"])
            with mock.patch("builtins.print") as mock_print:
                crossref.cmd_detail(args)
        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)
        self.assertEqual(payload["meta"]["retrieved"], 1)
        self.assertEqual(payload["meta"]["total_available"], 1)
        self.assertEqual(payload["results"][0]["doi"], "10.1038/nphys1170")

    def test_detail_strips_doi_org_prefix_before_building_path(self):
        fixture = _load("crossref_detail.json")
        with mock.patch.object(
            _shared.requests, "get", return_value=_fake_response(fixture)
        ) as mock_get:
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["detail", "https://doi.org/10.1038/nphys1170"])
            with mock.patch("builtins.print"):
                crossref.cmd_detail(args)
        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "https://api.crossref.org/works/10.1038/nphys1170")

    def test_detail_unknown_doi_returns_empty_results_not_an_error(self):
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response({}, status_code=404)):
            parser = _shared.build_arg_parser("crossref")
            args = parser.parse_args(["detail", "10.9999/does-not-exist"])
            with mock.patch("builtins.print") as mock_print:
                crossref.cmd_detail(args)
        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["meta"]["retrieved"], 0)
        self.assertEqual(payload["meta"]["total_available"], 0)


if __name__ == "__main__":
    unittest.main()
