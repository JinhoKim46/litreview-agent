"""Fixture-based tests for connectors.openalex — no live network calls.

Patches connectors._shared.requests.get (where http_get_with_backoff actually
issues the request), so these exercise the real mapping/pagination/CLI code
against a captured real-shape OpenAlex /works response.
"""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors import _shared, openalex

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


class WorkToResultTests(unittest.TestCase):
    def test_maps_full_record_including_reconstructed_abstract(self):
        work = _load("openalex_search_response.json")["results"][0]
        r = openalex.work_to_result(work)
        self.assertEqual(r["id"], "https://openalex.org/W2741809807")
        self.assertEqual(r["doi"], "10.7717/peerj.4375")  # https://doi.org/ prefix stripped
        self.assertEqual(r["title"], "Melatonin receptors and sleep regulation: a tissue-level study")
        self.assertEqual(r["venue"], "PeerJ")
        self.assertEqual(r["authors"], ["Heather Piwowar", "Jason Priem"])
        self.assertEqual(r["year"], 2018)
        self.assertEqual(r["source"], "openalex")
        self.assertEqual(r["abstract"], "This study examines melatonin receptors in human tissue samples.")
        self.assertEqual(r["url"], "https://peerj.com/articles/4375.pdf")  # oa_url preferred
        self.assertTrue(r["is_oa"])

    def test_missing_fields_are_null_or_empty_not_a_crash(self):
        work = _load("openalex_search_response.json")["results"][1]
        r = openalex.work_to_result(work)
        self.assertIsNone(r["doi"])
        self.assertIsNone(r["venue"])
        self.assertIsNone(r["abstract"])
        self.assertEqual(r["authors"], [])
        self.assertEqual(r["url"], "https://openalex.org/W3006923456")  # falls back to the work's own id
        self.assertFalse(r["is_oa"])

    def test_url_falls_back_to_landing_page_when_not_oa(self):
        work = _load("openalex_search_response.json")["results"][2]
        r = openalex.work_to_result(work)
        self.assertEqual(r["url"], "https://onlinelibrary.wiley.com/doi/10.1234/insomnia.review")


class CmdSearchTests(unittest.TestCase):
    def test_search_output_matches_fixed_shape_and_reports_true_total(self):
        fixture = _load("openalex_search_response.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)):
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(["search", "--query", "melatonin sleep insomnia", "--limit", "3"])
            with mock.patch("builtins.print") as mock_print:
                openalex.cmd_search(args)
        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)  # raises ValueError if malformed
        self.assertEqual(payload["meta"]["source"], "openalex")
        self.assertEqual(payload["meta"]["retrieved"], 3)
        self.assertEqual(payload["meta"]["total_available"], 15420)
        self.assertTrue(payload["meta"]["truncated"])  # 3 retrieved out of 15420
        self.assertEqual(len(payload["results"]), 3)

    def test_limit_is_a_hard_cap_even_when_a_page_overshoots_per_page(self):
        # The fixture always returns all 3 records regardless of the
        # requested per_page — a naive mock, but it exercises the defensive
        # collected[:limit] cap in the cursor branch (real OpenAlex honors
        # per_page, so this path is a belt-and-suspenders guard, not a
        # live-traffic bug).
        fixture = _load("openalex_search_response.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)):
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(["search", "--query", "melatonin", "--limit", "1"])
            with mock.patch("builtins.print") as mock_print:
                openalex.cmd_search(args)
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["meta"]["retrieved"], 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["meta"]["total_available"], 15420)
        self.assertTrue(payload["meta"]["truncated"])

    def test_bare_keyword_query_goes_to_search_param_not_filter(self):
        fixture = _load("openalex_search_response.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)) as mock_get:
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(["search", "--query", "melatonin sleep", "--limit", "1"])
            with mock.patch("builtins.print"):
                openalex.cmd_search(args)
        sent_params = mock_get.call_args[1]["params"]
        self.assertEqual(sent_params["search"], "melatonin sleep")
        self.assertNotIn("filter", sent_params)

    def test_query_file_and_source_key_resolve_the_stored_native_filter_string(self):
        fixture = _load("openalex_search_response.json")
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(fixture)) as mock_get:
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(
                ["search", "--query-file", plan_path, "--source-key", "openalex", "--limit", "2"]
            )
            with mock.patch("builtins.print") as mock_print:
                openalex.cmd_search(args)
        sent_params = mock_get.call_args[1]["params"]
        self.assertEqual(sent_params["filter"], "title_and_abstract.search:melatonin sleep insomnia")
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["meta"]["query"], "title_and_abstract.search:melatonin sleep insomnia")

    def test_cursor_pagination_follows_meta_next_cursor_across_pages(self):
        # Two pages of 2 + 1, distinct next_cursor tokens, so this actually
        # exercises the cursor-following loop rather than the single-request
        # case a one-page fixture would collapse into.
        fixture = _load("openalex_search_response.json")
        page1 = {"meta": dict(fixture["meta"], next_cursor="CURSOR2"), "results": fixture["results"][:2]}
        page2 = {"meta": dict(fixture["meta"], next_cursor=None), "results": fixture["results"][2:]}
        with mock.patch.object(
            _shared.requests, "get", side_effect=[_fake_response(page1), _fake_response(page2)]
        ) as mock_get:
            parser = _shared.build_arg_parser("openalex")
            # No --page and no --cursor: real runs default into the cursor
            # branch (args.page is 0), starting from OpenAlex's "*" sentinel.
            args = parser.parse_args(["search", "--query", "melatonin", "--limit", "3"])
            with mock.patch("builtins.print") as mock_print:
                openalex.cmd_search(args)
        first_call, second_call = mock_get.call_args_list
        self.assertEqual(first_call[1]["params"]["cursor"], "*")
        self.assertEqual(second_call[1]["params"]["cursor"], "CURSOR2")
        payload = json.loads(mock_print.call_args[0][0])
        self.assertEqual(payload["meta"]["retrieved"], 3)
        self.assertEqual(payload["meta"]["total_available"], 15420)  # set once, from page 1


class ErrorHandlingTests(unittest.TestCase):
    def test_missing_query_is_invalid_query_error_on_stderr_with_exit_1(self):
        # An existing query-file with no matching source-key entry —
        # resolve_query's own documented failure mode (KeyError -> ValueError
        # -> INVALID_QUERY).
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        parser = _shared.build_arg_parser("openalex")
        args = parser.parse_args(["search", "--query-file", plan_path, "--source-key", "nonexistent"])
        with mock.patch.object(_shared.sys, "stderr") as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                openalex.cmd_search(args)
        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "INVALID_QUERY")
        self.assertIn("error", err)

    def test_invalid_query_missing_source_key_together_with_query_file(self):
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        parser = _shared.build_arg_parser("openalex")
        args = parser.parse_args(["search", "--query-file", plan_path])
        with mock.patch.object(_shared.sys, "stderr") as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                openalex.cmd_search(args)
        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "INVALID_QUERY")

    def test_rate_limited_error_on_stderr_with_correct_code(self):
        with mock.patch.object(
            _shared.requests, "get", return_value=_fake_response({}, status_code=429)
        ), mock.patch.object(_shared.time, "sleep"), mock.patch.object(
            _shared.sys, "stderr"
        ) as mock_stderr:
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(["search", "--query", "x", "--limit", "1"])
            with self.assertRaises(SystemExit) as ctx:
                openalex.cmd_search(args)
        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "RATE_LIMITED")


class CmdDetailTests(unittest.TestCase):
    def test_detail_fetches_single_record_by_id(self):
        work = _load("openalex_search_response.json")["results"][0]
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(work)):
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(["detail", "W2741809807"])
            with mock.patch("builtins.print") as mock_print:
                openalex.cmd_detail(args)
        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)
        self.assertEqual(payload["meta"]["retrieved"], 1)
        self.assertEqual(payload["meta"]["total_available"], 1)
        self.assertEqual(payload["results"][0]["doi"], "10.7717/peerj.4375")

    def test_detail_unknown_id_returns_empty_results_not_an_error(self):
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response({}, status_code=404)):
            parser = _shared.build_arg_parser("openalex")
            args = parser.parse_args(["detail", "W0000000000"])
            with mock.patch("builtins.print") as mock_print:
                openalex.cmd_detail(args)
        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["meta"]["retrieved"], 0)
        self.assertEqual(payload["meta"]["total_available"], 0)


if __name__ == "__main__":
    unittest.main()
