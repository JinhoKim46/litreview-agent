import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors import citation_chase, openalex, _shared

SEED_A = {"id": "https://openalex.org/W1", "title": "Seed A", "display_name": "Seed A",
          "referenced_works": ["https://openalex.org/W10", "https://openalex.org/W11"],
          "primary_location": {}, "open_access": {}, "authorships": [], "publication_year": 2020, "doi": None}
SEED_B = {"id": "https://openalex.org/W2", "title": "Seed B", "display_name": "Seed B",
          "referenced_works": ["https://openalex.org/W11", "https://openalex.org/W12"],
          "primary_location": {}, "open_access": {}, "authorships": [], "publication_year": 2021, "doi": None}


def _work(work_id, title):
    return {"id": f"https://openalex.org/{work_id}", "title": title, "display_name": title,
            "primary_location": {}, "open_access": {}, "authorships": [], "publication_year": 2019, "doi": None}


def _make_args(seed_ids, direction="both", limit=200, fmt="json", out=None):
    return citation_chase.build_arg_parser().parse_args(
        ["chase", "--seed-ids", seed_ids, "--direction", direction, "--limit", str(limit), "--format", fmt]
        + (["--out", out] if out else [])
    )


class ResolveSeedsTests(unittest.TestCase):
    def test_resolves_known_seeds_and_collects_unresolved(self):
        def fake_fetch(raw_id):
            return {"W1": SEED_A, "10.1/a": SEED_B}.get(raw_id)

        with mock.patch.object(openalex, "fetch_work_by_id", side_effect=fake_fetch):
            resolved, unresolved = citation_chase._resolve_seeds(["W1", "10.1/a", "bogus"])

        self.assertEqual(set(resolved.keys()), {"W1", "W2"})
        self.assertEqual(unresolved, ["bogus"])


class ChaseBackwardTests(unittest.TestCase):
    def test_unions_and_dedupes_referenced_works_across_seeds(self):
        resolved = {"W1": SEED_A, "W2": SEED_B}
        fetched = [_work("W10", "Ref 10"), _work("W11", "Ref 11"), _work("W12", "Ref 12")]

        def fake_request(params, headers):
            self.assertIn("openalex_id:", params["filter"])
            ids_requested = params["filter"].split(":", 1)[1].split("|")
            self.assertEqual(set(ids_requested), {"W10", "W11", "W12"})  # deduped union, not 4 raw refs
            return {"results": fetched}

        with mock.patch.object(openalex, "_request", side_effect=fake_request):
            results, total_available = citation_chase.chase_backward(resolved, limit=200, headers={}, mailto=None)

        self.assertEqual(total_available, 3)
        self.assertEqual({r["id"] for r in results}, {"https://openalex.org/W10", "https://openalex.org/W11", "https://openalex.org/W12"})

    def test_limit_caps_before_fetching_not_just_after(self):
        resolved = {"W1": SEED_A, "W2": SEED_B}
        with mock.patch.object(openalex, "_request", return_value={"results": [_work("W10", "Ref 10")]}) as m:
            results, total_available = citation_chase.chase_backward(resolved, limit=1, headers={}, mailto=None)
        requested_ids = m.call_args[0][0]["filter"].split(":", 1)[1].split("|")
        self.assertEqual(len(requested_ids), 1, "limit must cap the batch fetch itself, not just post-filter")
        self.assertEqual(total_available, 3, "total_available reports the true unique-reference count, unaffected by the cap")


class ChaseForwardTests(unittest.TestCase):
    def test_paginates_via_cursor_until_limit_or_exhausted(self):
        resolved = {"W1": SEED_A}
        page1 = {"meta": {"count": 2, "next_cursor": "next-token"}, "results": [_work("W20", "Cite A")]}
        page2 = {"meta": {"count": 2, "next_cursor": None}, "results": [_work("W21", "Cite B")]}
        with mock.patch.object(openalex, "_request", side_effect=[page1, page2]) as m:
            results, total_available = citation_chase.chase_forward(resolved, limit=200, headers={}, mailto=None)
        self.assertEqual(total_available, 2)
        self.assertEqual(len(results), 2)
        self.assertIn("cites:W1", m.call_args_list[0][0][0]["filter"])

    def test_no_resolved_seeds_returns_empty_without_calling_api(self):
        with mock.patch.object(openalex, "_request") as m:
            results, total_available = citation_chase.chase_forward({}, limit=200, headers={}, mailto=None)
        m.assert_not_called()
        self.assertEqual((results, total_available), ([], 0))


class CmdChaseOutputShapeTests(unittest.TestCase):
    def test_full_chase_matches_fixed_output_shape_and_reports_unresolved(self):
        def fake_fetch(raw_id):
            return SEED_A if raw_id == "W1" else None

        backward_page = {"results": [_work("W10", "Ref 10"), _work("W11", "Ref 11")]}
        forward_page = {"meta": {"count": 1, "next_cursor": None}, "results": [_work("W20", "Cite A")]}

        with mock.patch.object(openalex, "fetch_work_by_id", side_effect=fake_fetch), \
             mock.patch.object(openalex, "_request", side_effect=[backward_page, forward_page]), \
             mock.patch("builtins.print") as mock_print:
            citation_chase.main(["chase", "--seed-ids", "W1,bogus", "--direction", "both", "--limit", "200"])

        payload = json.loads(mock_print.call_args[0][0])
        _shared.validate_output_shape(payload)
        self.assertEqual(payload["meta"]["source"], "citation_chase")
        self.assertEqual(payload["meta"]["unresolved_seeds"], ["bogus"])
        self.assertEqual(len(payload["results"]), 3)  # 2 backward + 1 forward, no overlap
        self.assertFalse(payload["meta"]["truncated"])

    def test_missing_seed_ids_is_invalid_query_error_on_stderr_with_exit_1(self):
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as ctx:
                citation_chase.main(["chase", "--seed-ids", "", "--direction", "both"])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
