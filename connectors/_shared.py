"""Shared helpers for every connectors/<source>.py module.

Written once so the six source connectors (openalex, crossref, semanticscholar,
pubmed, europepmc, arxiv) don't each reimplement HTTP retry/backoff, a
User-Agent, output-shape validation, error reporting, and CLI parsing.

Every connector follows: `python3 -m connectors.<source> <search|detail> [flags]`
and must produce the fixed `{"meta": {...}, "results": [...]}` shape documented
in the architecture plan (§3) -- see validate_output_shape below for the exact
required keys.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

from tools.path_policy import UnsafePathError, resolve_under_results

# ponytail: single placeholder contact -- a real deployment sets this via
# PRISMA_CONTACT_EMAIL so the User-Agent honestly names a reachable maintainer,
# per API "polite pool" etiquette (OpenAlex/Crossref/NCBI all ask for one).
DEFAULT_CONTACT_EMAIL = "your-email@example.com"
TOOL_NAME = "prisma-review-connectors/0.1"

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def build_user_agent(contact_email=None):
    import os

    email = contact_email or os.environ.get("PRISMA_CONTACT_EMAIL") or DEFAULT_CONTACT_EMAIL
    return f"{TOOL_NAME} (mailto:{email})"


def _backoff_delay(attempt, resp=None):
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return (2 ** attempt) + random.uniform(0, 1)


def http_get_with_backoff(url, params=None, headers=None, timeout=30, max_retries=5):
    """GET with exponential backoff + jitter on 429/5xx.

    Returns the `requests.Response` from the final attempt -- including a
    still-429/5xx one once retries are exhausted, so the caller (which knows
    the connector contract's error codes) decides how to map that status,
    rather than this helper guessing RATE_LIMITED vs UPSTREAM_ERROR for every
    source. A network-level failure (no response at all) is retried the same
    way and re-raised as `requests.RequestException` if every attempt fails.
    """
    hdrs = dict(headers or {})
    hdrs.setdefault("User-Agent", build_user_agent())
    resp = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(_backoff_delay(attempt))
            continue
        if resp.status_code not in RETRYABLE_STATUS or attempt == max_retries - 1:
            return resp
        time.sleep(_backoff_delay(attempt, resp))
    return resp


def write_error(message, code):
    """Write the contract's error shape to stderr. Caller still does sys.exit(1)."""
    sys.stderr.write(json.dumps({"error": message, "code": code}) + "\n")


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


REQUIRED_META_KEYS = {"source", "query", "retrieved", "total_available", "truncated", "fetched_at"}
REQUIRED_RESULT_KEYS = {"id", "title", "authors", "year", "venue", "doi", "abstract", "url", "source"}


def validate_output_shape(output):
    """Raise ValueError if `output` doesn't match the fixed connector JSON shape.

    Used both defensively at runtime (write_output calls this before printing)
    and by tools/check_connector_contract.py in CI -- must not be an `assert`,
    which `python -O` would compile away.
    """
    if not isinstance(output, dict) or set(output.keys()) != {"meta", "results"}:
        raise ValueError(
            f"top-level keys must be exactly {{meta, results}}, got "
            f"{(output if not isinstance(output, dict) else set(output.keys()))!r}"
        )
    meta = output["meta"]
    if not isinstance(meta, dict) or not REQUIRED_META_KEYS.issubset(meta.keys()):
        missing = REQUIRED_META_KEYS - (meta.keys() if isinstance(meta, dict) else set())
        raise ValueError(f"meta missing keys: {missing}")
    if not isinstance(output["results"], list):
        raise ValueError("results must be a list")
    for i, r in enumerate(output["results"]):
        if not isinstance(r, dict) or not REQUIRED_RESULT_KEYS.issubset(r.keys()):
            missing = REQUIRED_RESULT_KEYS - (r.keys() if isinstance(r, dict) else set())
            raise ValueError(f"results[{i}] missing keys: {missing}")
    return True


def build_arg_parser(source_name):
    """Shared argparse scaffold for `python3 -m connectors.<source> <search|detail> [flags]`."""
    parser = argparse.ArgumentParser(prog=f"connectors.{source_name}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    q = search.add_mutually_exclusive_group(required=True)
    q.add_argument("--query", help="raw query string in this source's native syntax")
    q.add_argument("--query-file", help="path to search_plan.json; read with --source-key")
    search.add_argument("--source-key", help="key into sources.<name>.query_string of --query-file's JSON")
    search.add_argument("--limit", type=int, default=25, help="max results to retrieve")
    search.add_argument("--page", type=int, default=0, help="0-based page number (page * limit = offset)")
    search.add_argument("--cursor", default=None, help="opaque pagination token, for sources that use one")
    search.add_argument("--since", default=None, help="ISO date/year lower bound, when the source supports it")
    search.add_argument("--until", default=None, help="ISO date/year upper bound, when the source supports it")
    search.add_argument("--format", choices=["json", "table", "plain"], default="json")
    search.add_argument("--out", default=None, help="write the JSON response here instead of stdout")

    detail = sub.add_parser("detail")
    detail.add_argument("id", help="source-native id, or a prefixed external id (e.g. DOI:10.x/y)")
    detail.add_argument("--format", choices=["json", "table", "plain"], default="json")
    detail.add_argument("--out", default=None, help="write the JSON response here instead of stdout")

    return parser


def resolve_query(args):
    """Resolve --query or --query-file+--source-key into a query string.

    Raises ValueError (caller maps to the INVALID_QUERY error code) on any
    problem -- missing --source-key, unreadable file, missing key in the plan.
    """
    if getattr(args, "query", None):
        return args.query
    if getattr(args, "query_file", None):
        if not args.source_key:
            raise ValueError("--source-key is required together with --query-file")
        with open(args.query_file) as f:
            plan = json.load(f)
        try:
            return plan["sources"][args.source_key]["query_string"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"--query-file missing sources.{args.source_key}.query_string") from exc
    raise ValueError("either --query or --query-file (+--source-key) is required")


def write_output(output, fmt, out_path):
    """Validate and write connector output: JSON always to --out, else per --format to stdout.

    `--out` is pre-approved-permission-reachable (see PRODUCT_READINESS_AUDIT.md
    P0-1), so it must never be trusted as a bare filesystem path: resolve it
    and require it stay inside `results/` before opening anything for write.
    Written atomically (temp sibling file + os.replace) so a crash mid-write
    can never leave a partially-written file at the canonical path.
    """
    validate_output_shape(output)
    if out_path:
        try:
            safe_path = resolve_under_results(out_path)
        except UnsafePathError as exc:
            write_error(str(exc), "UNSAFE_PATH")
            sys.exit(1)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = safe_path.with_name(safe_path.name + f".tmp{os.getpid()}")
        with open(tmp_path, "w") as f:
            json.dump(output, f, indent=2)
        os.replace(tmp_path, safe_path)
        return
    if fmt == "plain":
        text = "\n".join(f"{r['title']} ({r['year']}) - {r['url']}" for r in output["results"])
    elif fmt == "table":
        rows = [(r["id"], (r["title"] or "")[:60], str(r["year"])) for r in output["results"]]
        widths = [max((len(row[i]) for row in rows), default=0) for i in range(3)]
        text = "\n".join("  ".join(cell.ljust(w) for cell, w in zip(row, widths)) for row in rows)
    else:
        text = json.dumps(output, indent=2)
    print(text)
