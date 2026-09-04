"""Fixture-based unit test for connectors/europepmc.py -- no live network calls."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from connectors import _shared, europepmc
from connectors._shared import validate_output_shape

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "europepmc_search.json")
FIXTURES_DIR = os.path.dirname(FIXTURE_PATH)


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class EuropePmcConnectorTest(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()

    def test_search_matches_fixed_output_shape(self):
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(self.fixture)) as mock_get:
            payload = europepmc.run_search("malaria", limit=20, cursor=None, since=None, until=None)

        mock_get.assert_called_once()
        self.assertTrue(validate_output_shape(payload))  # raises ValueError if invalid
        self.assertEqual(payload["meta"]["source"], "europepmc")
        self.assertEqual(payload["meta"]["retrieved"], 2)
        self.assertEqual(payload["meta"]["total_available"], 2)
        self.assertFalse(payload["meta"]["truncated"])

    def test_med_record_fields_mapped_correctly(self):
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(self.fixture)):
            payload = europepmc.run_search("malaria", limit=20, cursor=None, since=None, until=None)

        med = payload["results"][0]
        self.assertEqual(med["id"], "MED:25883531")
        self.assertEqual(med["doi"], "10.1016/j.example.2015.01.001")
        self.assertEqual(med["year"], 2015)
        self.assertEqual(med["venue"], "Journal of Example Medicine")
        self.assertEqual(med["authors"], ["Smith J", "Doe A", "Lee K"])
        self.assertEqual(med["source"], "europepmc")
        # HTML tags stripped from abstractText, entities unescaped.
        self.assertNotIn("<", med["abstract"])
        self.assertIn("Malaria burden remains high", med["abstract"])
        self.assertEqual(med["url"], "https://doi.org/10.1016/j.example.2015.01.001")

    def test_preprint_record_falls_back_to_authorstring_and_generated_url(self):
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(self.fixture)):
            payload = europepmc.run_search("malaria", limit=20, cursor=None, since=None, until=None)

        ppr = payload["results"][1]
        self.assertEqual(ppr["id"], "PPR:PPR123456")
        self.assertIsNone(ppr["doi"])
        self.assertEqual(ppr["authors"], ["Nguyen T", "Park S."])
        # No fullTextUrlList in the fixture record -> derived europepmc.org URL.
        self.assertEqual(ppr["url"], "https://europepmc.org/article/PPR/PPR123456")

    def test_truncated_flag_set_when_hitcount_exceeds_retrieved(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["hitCount"] = 50000
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(fixture)):
            payload = europepmc.run_search("malaria", limit=2, cursor=None, since=None, until=None)

        self.assertEqual(payload["meta"]["total_available"], 50000)
        self.assertTrue(payload["meta"]["truncated"])

    def test_date_range_is_folded_into_query_string_not_params(self):
        query = europepmc._apply_date_range("malaria", "2023-01-01", "2024-01-01")
        self.assertEqual(query, "(malaria) AND FIRST_PDATE:[2023-01-01 TO 2024-01-01]")
        open_ended = europepmc._apply_date_range("malaria", "2023-01-01", None)
        self.assertEqual(open_ended, "(malaria) AND FIRST_PDATE:[2023-01-01 TO *]")

    def test_detail_scopes_search_by_composite_id(self):
        single = {
            "hitCount": 1,
            "resultList": {"result": [self.fixture["resultList"]["result"][0]]},
        }
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(single)) as mock_get:
            payload = europepmc.run_detail("MED:25883531")

        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["query"], "EXT_ID:25883531 AND SRC:MED")
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["id"], "MED:25883531")

    def test_detail_bare_id_defaults_to_med_source(self):
        empty = {"hitCount": 0, "resultList": {"result": []}}
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(empty)) as mock_get:
            payload = europepmc.run_detail("25883531")

        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["query"], "EXT_ID:25883531 AND SRC:MED")
        self.assertEqual(payload["results"], [])

    def test_empty_query_is_invalid(self):
        with self.assertRaises(europepmc.EuropePmcError) as ctx:
            europepmc.run_search("   ", limit=10, cursor=None, since=None, until=None)
        self.assertEqual(ctx.exception.code, "INVALID_QUERY")

    def test_rate_limited_status_maps_to_rate_limited_code(self):
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse({}, status_code=429)):
            with self.assertRaises(europepmc.EuropePmcError) as ctx:
                europepmc.run_search("malaria", limit=10, cursor=None, since=None, until=None)
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

    def test_cli_search_produces_contract_shaped_stdout(self):
        """Full CLI path (main -> write_output -> print), no network."""
        with patch.object(europepmc, "http_get_with_backoff", return_value=FakeResponse(self.fixture)):
            with patch("builtins.print") as mock_print:
                europepmc.main(["search", "--query", "malaria", "--limit", "20"])
        payload = json.loads(mock_print.call_args[0][0])
        self.assertTrue(validate_output_shape(payload))
        self.assertEqual(payload["meta"]["source"], "europepmc")
        self.assertEqual(payload["results"][0]["id"], "MED:25883531")

    def test_cli_missing_query_writes_standard_error_shape_and_exits_1(self):
        """--query-file with a --source-key absent from the plan -> resolve_query's
        ValueError -> INVALID_QUERY, surfaced via main()'s own write_error + exit(1)
        (not argparse's exit(2) for a wholly absent --query, which is a shared-scaffold
        concern common to every connector, not this one)."""
        plan_path = os.path.join(FIXTURES_DIR, "sample_search_plan.json")
        with patch.object(_shared.sys, "stderr") as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                europepmc.main(["search", "--query-file", plan_path, "--source-key", "nonexistent"])
        self.assertEqual(ctx.exception.code, 1)
        written = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        err = json.loads(written)
        self.assertEqual(err["code"], "INVALID_QUERY")
        self.assertIn("error", err)


if __name__ == "__main__":
    unittest.main()
