#!/usr/bin/env python3
"""CI check: every connectors/<source>.py produces the fixed {meta, results} shape.

For each of the six source connectors, this imports the real module, mocks the
HTTP layer *exactly the way that connector's own tests/test_connector_<source>.py
does* (same patch target, same fixture file), drives it through its real
`main()` CLI entry point with `--out` pointed at a temp file, and asserts the
parsed output matches connectors._shared.validate_output_shape's fixed shape.
No live network calls.

The six connectors deliberately don't share one mocking recipe -- three patch
`connectors._shared.requests.get` (the seam `http_get_with_backoff` calls
through), two patch `http_get_with_backoff` directly on the connector module
(where it's imported by name), and pubmed's real API is two sequential calls
(esearch then efetch) so it needs a `side_effect` list, not a single
`return_value`. Encoding each connector's real recipe here (rather than
forcing one generic shape) is what makes this an actual contract check against
already-verified integration points, not a second copy of assumptions that
could drift from the connectors' real tests.

Exit code 0 on success, 1 with a per-connector, per-field failure list
otherwise.
"""

import json
import os
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from connectors import _shared  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def _load_json(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def _load_bytes(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


def _json_response(body, status_code=200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.headers = {}
    return resp


def _xml_response(xml_bytes, status_code=200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.content = xml_bytes
    resp.text = xml_bytes.decode("utf-8", errors="replace")
    resp.headers = {}
    return resp


def _run_cli(module, argv):
    """Invoke module.main() with argv (via sys.argv) and --out to a temp file,
    then return the parsed JSON payload it wrote there.

    Uses each connector's real `main()` -> write_output/--out path (rather
    than calling an internal search function directly) so this exercises the
    exact CLI surface `/prisma-search` shells out to, not just the mapping
    logic underneath it. All six connectors accept `main()` with no arguments
    and fall back to `sys.argv[1:]` via argparse, so patching sys.argv is the
    one invocation shape that works uniformly across all of them despite
    their differing `main()` signatures (`main(argv=None)` vs `main()`).
    """
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        full_argv = ["check_connector_contract", *argv, "--out", path]
        with mock.patch.object(sys, "argv", full_argv):
            module.main()
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    finally:
        os.unlink(path)


def _check_openalex():
    from connectors import openalex

    resp = _json_response(_load_json("openalex_search_response.json"))
    with mock.patch.object(_shared.requests, "get", return_value=resp):
        return _run_cli(openalex, ["search", "--query", "cancer immunotherapy", "--limit", "3"])


def _check_crossref():
    from connectors import crossref

    resp = _json_response(_load_json("crossref_search.json"))
    with mock.patch.object(_shared.requests, "get", return_value=resp):
        return _run_cli(crossref, ["search", "--query", "cancer immunotherapy", "--limit", "3"])


def _check_semanticscholar():
    from connectors import semanticscholar as s2

    resp = _json_response(_load_json("semanticscholar_search_response.json"))
    with mock.patch.object(s2, "http_get_with_backoff", return_value=resp):
        return _run_cli(s2, ["search", "--query", "machine learning", "--limit", "3"])


def _check_pubmed():
    from connectors import pubmed

    esearch = _xml_response(_load_bytes("pubmed_esearch.xml"))
    efetch = _xml_response(_load_bytes("pubmed_efetch.xml"))
    with mock.patch.object(_shared.requests, "get", side_effect=[esearch, efetch]):
        return _run_cli(pubmed, ["search", "--query", "melatonin sleep", "--limit", "2"])


def _check_europepmc():
    from connectors import europepmc

    resp = _json_response(_load_json("europepmc_search.json"))
    with mock.patch.object(europepmc, "http_get_with_backoff", return_value=resp):
        return _run_cli(europepmc, ["search", "--query", "cancer", "--limit", "3"])


def _check_arxiv():
    from connectors import arxiv

    resp = _xml_response(_load_bytes("arxiv_search.xml"))
    with mock.patch.object(_shared, "http_get_with_backoff", return_value=resp), mock.patch.object(
        arxiv, "_respect_courtesy_rate", lambda: None
    ):
        return _run_cli(arxiv, ["search", "--query", "all:transformer", "--limit", "3"])


def _check_citation_chase():
    from connectors import citation_chase, openalex

    seed_work = {
        "id": "https://openalex.org/W1", "title": "Seed", "display_name": "Seed",
        "referenced_works": ["https://openalex.org/W10"], "primary_location": {},
        "open_access": {}, "authorships": [], "publication_year": 2020, "doi": None,
    }
    backward_page = {"results": [{
        "id": "https://openalex.org/W10", "title": "Ref 10", "display_name": "Ref 10",
        "primary_location": {}, "open_access": {}, "authorships": [], "publication_year": 2019, "doi": None,
    }]}
    forward_page = {"meta": {"count": 0, "next_cursor": None}, "results": []}

    # citation_chase reuses connectors.openalex's own HTTP/parsing helpers
    # rather than calling requests/http_get_with_backoff directly (see its
    # module docstring), so the mock seam here is those two openalex
    # functions, not _shared.requests.get like the keyword-search connectors.
    with mock.patch.object(openalex, "fetch_work_by_id", return_value=seed_work), mock.patch.object(
        openalex, "_request", side_effect=[backward_page, forward_page]
    ):
        return _run_cli(citation_chase, ["chase", "--seed-ids", "W1", "--direction", "both", "--limit", "10"])


CHECKS = {
    "openalex": _check_openalex,
    "crossref": _check_crossref,
    "semanticscholar": _check_semanticscholar,
    "pubmed": _check_pubmed,
    "europepmc": _check_europepmc,
    "citation_chase": _check_citation_chase,
    "arxiv": _check_arxiv,
}


def main() -> int:
    failures: list[str] = []
    for name, check in CHECKS.items():
        try:
            payload = check()
        except SystemExit as exc:
            failures.append(
                f"{name}: connector exited via sys.exit({exc.code}) instead of writing output "
                "-- check the fixture/mock wiring for this source in this script"
            )
            continue
        except Exception as exc:  # noqa: BLE001 - want the connector name attached to any failure
            failures.append(f"{name}: raised {exc.__class__.__name__}: {exc}")
            continue

        try:
            _shared.validate_output_shape(payload)
        except ValueError as exc:
            failures.append(f"{name}: {exc}")
            continue

        if payload["meta"].get("source") != name:
            failures.append(
                f"{name}: meta.source == {payload['meta'].get('source')!r}, expected {name!r}"
            )
        if not payload["results"]:
            failures.append(f"{name}: results list is empty -- fixture likely wired wrong")

    if failures:
        print(f"check_connector_contract: {len(failures)} failure(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"check_connector_contract: OK ({len(CHECKS)} connectors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
