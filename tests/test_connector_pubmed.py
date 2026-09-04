"""Fixture-based tests for connectors.pubmed — no live network calls.

Patches connectors._shared.requests.get (where http_get_with_backoff actually
issues the request) with captured real esearch/efetch XML, so these exercise
the real two-step flow and field-mapping code against real-shape responses.
"""

import io
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors import _shared, pubmed

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_xml_bytes(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


def _fake_response(xml_bytes, status_code=200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.content = xml_bytes
    resp.text = xml_bytes.decode("utf-8", errors="replace")
    resp.headers = {}
    return resp


class SearchTests(unittest.TestCase):
    def test_search_output_matches_fixed_shape_and_reports_true_total(self):
        esearch_xml = _load_xml_bytes("pubmed_esearch.xml")
        efetch_xml = _load_xml_bytes("pubmed_efetch.xml")
        with mock.patch.object(
            _shared.requests, "get",
            side_effect=[_fake_response(esearch_xml), _fake_response(efetch_xml)],
        ):
            parser = _shared.build_arg_parser("pubmed")
            args = parser.parse_args(["search", "--query", "melatonin sleep", "--limit", "2"])
            payload = pubmed.search(args)

        _shared.validate_output_shape(payload)  # raises ValueError if malformed
        self.assertEqual(payload["meta"]["source"], "pubmed")
        self.assertEqual(payload["meta"]["retrieved"], 2)
        self.assertEqual(payload["meta"]["total_available"], 7405)  # true Count, not capped by --limit
        self.assertTrue(payload["meta"]["truncated"])
        self.assertEqual(len(payload["results"]), 2)
        first = payload["results"][0]
        self.assertEqual(first["id"], "42687373")
        self.assertEqual(first["source"], "pubmed")
        self.assertEqual(first["url"], "https://pubmed.ncbi.nlm.nih.gov/42687373/")
        self.assertTrue(first["title"].startswith("Nocturnal peak in cardiac baroreflex"))
        self.assertIsInstance(first["authors"], list)
        self.assertGreater(len(first["authors"]), 0)

    def test_zero_hits_short_circuits_without_calling_efetch(self):
        empty_esearch = (
            b"<eSearchResult><Count>0</Count><RetMax>0</RetMax><RetStart>0</RetStart>"
            b"<IdList></IdList></eSearchResult>"
        )
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(empty_esearch)) as mock_get:
            parser = _shared.build_arg_parser("pubmed")
            args = parser.parse_args(["search", "--query", "zzzznomatch", "--limit", "5"])
            payload = pubmed.search(args)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["meta"]["total_available"], 0)
        self.assertFalse(payload["meta"]["truncated"])
        mock_get.assert_called_once()  # esearch only, efetch skipped for an empty id list

    def test_missing_query_is_invalid_query_error(self):
        parser = _shared.build_arg_parser("pubmed")
        with self.assertRaises(SystemExit):
            parser.parse_args(["search", "--limit", "3"])  # argparse itself enforces --query/--query-file

    def test_rate_limited_after_retries_exhausted(self):
        with mock.patch.object(
            _shared.requests, "get", return_value=_fake_response(b"", status_code=429)
        ), mock.patch.object(_shared.time, "sleep"):  # skip real backoff delays
            parser = _shared.build_arg_parser("pubmed")
            args = parser.parse_args(["search", "--query", "x", "--limit", "1"])
            with self.assertRaises(pubmed.UpstreamError) as ctx:
                pubmed.search(args)
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")


class DetailTests(unittest.TestCase):
    def test_detail_by_bare_pmid_fetches_directly(self):
        # The fixture itself carries 2 articles (efetch is a batch endpoint);
        # what matters here is that a bare-numeric id skips esearch entirely
        # and requests exactly that id, not that the mock only returns one.
        efetch_xml = _load_xml_bytes("pubmed_efetch.xml")
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(efetch_xml)) as mock_get:
            parser = _shared.build_arg_parser("pubmed")
            args = parser.parse_args(["detail", "42687373"])
            payload = pubmed.detail(args)
        _shared.validate_output_shape(payload)
        self.assertGreaterEqual(payload["meta"]["retrieved"], 1)
        mock_get.assert_called_once()
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["id"], "42687373")

    def test_detail_by_doi_resolves_pmid_first(self):
        resolve_xml = (
            b"<eSearchResult><Count>1</Count><IdList><Id>42687373</Id></IdList></eSearchResult>"
        )
        efetch_xml = _load_xml_bytes("pubmed_efetch.xml")
        with mock.patch.object(
            _shared.requests, "get",
            side_effect=[_fake_response(resolve_xml), _fake_response(efetch_xml)],
        ):
            parser = _shared.build_arg_parser("pubmed")
            args = parser.parse_args(["detail", "10.1234/example-doi"])
            payload = pubmed.detail(args)
        self.assertEqual(payload["results"][0]["id"], "42687373")

    def test_detail_unknown_id_returns_empty_results_not_an_error(self):
        empty_esearch = b"<eSearchResult><Count>0</Count><IdList></IdList></eSearchResult>"
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(empty_esearch)):
            parser = _shared.build_arg_parser("pubmed")
            args = parser.parse_args(["detail", "10.9999/does-not-exist"])
            payload = pubmed.detail(args)
        _shared.validate_output_shape(payload)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["meta"]["retrieved"], 0)
        self.assertEqual(payload["meta"]["total_available"], 0)


class FieldParsingTests(unittest.TestCase):
    """Synthetic minimal XML for edge cases the two captured fixtures don't hit."""

    def _article(self, inner_xml):
        xml = f"""<PubmedArticle><MedlineCitation><PMID>1</PMID>
            <Article>{inner_xml}</Article></MedlineCitation></PubmedArticle>"""
        return ET.fromstring(xml)

    def test_collective_author_name_used_when_no_individual_name(self):
        el = self._article(
            "<ArticleTitle>T</ArticleTitle><AuthorList>"
            "<Author><CollectiveName>COVERED Team</CollectiveName></Author></AuthorList>"
        )
        record = pubmed._parse_article(el)
        self.assertEqual(record["authors"], ["COVERED Team"])

    def test_doi_falls_back_to_article_id_list_when_no_elocationid(self):
        xml = """<PubmedArticle><MedlineCitation><PMID>1</PMID>
            <Article><ArticleTitle>T</ArticleTitle></Article></MedlineCitation>
            <PubmedData><ArticleIdList>
                <ArticleId IdType="pubmed">1</ArticleId>
                <ArticleId IdType="doi">10.1/fallback</ArticleId>
            </ArticleIdList></PubmedData></PubmedArticle>"""
        record = pubmed._parse_article(ET.fromstring(xml))
        self.assertEqual(record["doi"], "10.1/fallback")

    def test_medline_date_used_when_year_element_absent(self):
        el = self._article(
            "<ArticleTitle>T</ArticleTitle>"
            "<Journal><JournalIssue><PubDate><MedlineDate>1998 Nov-Dec</MedlineDate>"
            "</PubDate></JournalIssue></Journal>"
        )
        record = pubmed._parse_article(el)
        self.assertEqual(record["year"], 1998)

    def test_missing_abstract_is_null_not_empty_string(self):
        el = self._article("<ArticleTitle>T</ArticleTitle>")
        record = pubmed._parse_article(el)
        self.assertIsNone(record["abstract"])

    def test_labeled_abstract_sections_are_joined_with_labels(self):
        el = self._article(
            "<ArticleTitle>T</ArticleTitle><Abstract>"
            '<AbstractText Label="BACKGROUND">B text.</AbstractText>'
            '<AbstractText Label="METHODS">M text.</AbstractText>'
            "</Abstract>"
        )
        record = pubmed._parse_article(el)
        self.assertEqual(record["abstract"], "BACKGROUND: B text. METHODS: M text.")


class CliEndToEndErrorTests(unittest.TestCase):
    """Exercises main() end-to-end: the Connector Contract's stderr JSON error
    shape (not just an internal exception) for a missing/invalid query.

    Uses --query-file with a --source-key absent from the plan -- resolve_query's
    own documented failure mode (KeyError -> ValueError -> INVALID_QUERY) --
    same convention as test_connector_crossref.py / test_connector_europepmc.py.
    A wholly absent --query instead trips argparse's own exit(2) usage error
    before main() ever runs; that's a shared-scaffold concern common to every
    connector (see connectors/_shared.py build_arg_parser), not specific to pubmed.
    """

    def test_missing_query_exits_1_with_standard_stderr_json(self):
        plan_path = os.path.join(FIXTURES, "sample_search_plan.json")
        argv = ["connectors.pubmed", "search", "--query-file", plan_path, "--source-key", "nonexistent"]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv), redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                pubmed.main()
        self.assertEqual(ctx.exception.code, 1)
        payload = json.loads(err.getvalue())
        self.assertEqual(set(payload.keys()), {"error", "code"})
        self.assertEqual(payload["code"], "INVALID_QUERY")

    def test_upstream_invalid_query_exits_1_with_standard_stderr_json(self):
        # NCBI returns 200 + an <ErrorList> (not an HTTP error) for a
        # malformed search term -- _esearch maps that to INVALID_QUERY.
        bad_syntax_xml = (
            b"<eSearchResult><ErrorList><PhraseNotFound>AND[Filter]</PhraseNotFound>"
            b"</ErrorList></eSearchResult>"
        )
        argv = ["connectors.pubmed", "search", "--query", "AND[Filter]", "--limit", "3"]
        err = io.StringIO()
        with mock.patch.object(_shared.requests, "get", return_value=_fake_response(bad_syntax_xml)), \
                mock.patch.object(sys, "argv", argv), redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                pubmed.main()
        self.assertEqual(ctx.exception.code, 1)
        payload = json.loads(err.getvalue())
        self.assertEqual(set(payload.keys()), {"error", "code"})
        self.assertEqual(payload["code"], "INVALID_QUERY")


if __name__ == "__main__":
    unittest.main()
