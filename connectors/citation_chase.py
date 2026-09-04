"""Citation-chasing connector: backward (references) and forward (citing
works) snowballing from a set of seed studies, via OpenAlex -- a real PRISMA
"other methods" identification source none of the six keyword-search
connectors cover (Haddaway et al.'s `citationchaser` tool is the established
precedent this mirrors, minus its R/Shiny UI).

CLI: python3 -m connectors.citation_chase chase --seed-ids <id1,id2,...>
     --direction backward|forward|both [--limit N] [--format json|table|plain]
     [--out path]

Each seed id is either a bare DOI (e.g. "10.1234/abcd") or a raw OpenAlex
work id (e.g. "W2741809807") -- the same two forms connectors.openalex's
`fetch_work_by_id` already accepts via `_to_path_id`. A seed that fails to
resolve (typo, not indexed by OpenAlex) is skipped with a warning collected
in `meta.unresolved_seeds`, never a hard failure for the whole chase -- one
bad seed out of a reviewer's included-studies list shouldn't block chasing
the rest.

Deliberately reuses connectors.openalex's HTTP/parsing/output helpers
(`fetch_work_by_id`, `work_to_result`, `_request`, `_meta`, `_emit`,
`_user_agent`, `get_mailto`, `BASE_URL`) rather than reimplementing them --
chasing citations through OpenAlex *is* an OpenAlex works-list query
underneath (`filter=cites:<id>` for forward; each seed's own
`referenced_works` field, already present on the work OpenAlex returns, for
backward), so a second copy of that logic here would just drift.

Output uses the same fixed {meta, results} shape as every other connector
(meta.source = "citation_chase") so its raw/*.json output flows through
prisma-search.md's existing Step 7 dedup unchanged. Backward and forward
results are merged into one `results` list per invocation and deduplicated
by id within this connector's own output (cross-run dedup against
records.jsonl is Step 7's job, not this connector's).
"""
import argparse
import sys

from connectors import openalex, _shared

SOURCE_KEY = "citation_chase"
BATCH_SIZE = 50  # OpenAlex's own documented ceiling for a pipe-joined filter clause


def _meta(query, retrieved, total_available, truncated):
    # Deliberately NOT openalex._meta -- that stamps "source": "openalex"
    # (its own module constant), which would misreport every chase result
    # as if it came from the openalex connector itself.
    return {
        "source": SOURCE_KEY,
        "query": query,
        "retrieved": retrieved,
        "total_available": total_available,
        "truncated": truncated,
        "fetched_at": _shared.utc_now_iso(),
    }


def _openalex_id_only(prefixed_or_bare):
    """Reduce an OpenAlex work id (bare "W123..." or a full "https://openalex.org/W123..."
    URL, as `referenced_works` entries come back) to the bare id OpenAlex's
    `filter=openalex_id:...`/`filter=cites:...` clauses expect."""
    return prefixed_or_bare.rsplit("/", 1)[-1]


def _resolve_seeds(seed_ids):
    """Resolve each seed (DOI or OpenAlex id) to its full OpenAlex work dict.

    Returns (resolved: {bare_openalex_id: work_dict}, unresolved: [seed, ...]).
    A seed OpenAlex has no record for is collected in `unresolved`, never
    raised -- the chase proceeds with whatever seeds did resolve.
    """
    resolved = {}
    unresolved = []
    for seed in seed_ids:
        work = openalex.fetch_work_by_id(seed.strip())
        if work is None:
            unresolved.append(seed)
            continue
        resolved[_openalex_id_only(work["id"])] = work
    return resolved, unresolved


def _to_result(work):
    """openalex.work_to_result() stamps "source": "openalex" (its own module
    constant) -- override it here so chased records are correctly attributed
    to the citation-chase identification method, not the underlying API,
    matching this connector's own meta.source."""
    result = openalex.work_to_result(work)
    result["source"] = SOURCE_KEY
    return result


def _batched(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _fetch_by_openalex_ids(ids, headers, mailto):
    """Batch-fetch full work records for a list of bare OpenAlex ids via
    filter=openalex_id:ID1|ID2|...|IDN, chunked to BATCH_SIZE per request."""
    works = []
    for batch in _batched(ids, BATCH_SIZE):
        params = {"filter": f"openalex_id:{'|'.join(batch)}", "per_page": len(batch)}
        if mailto:
            params["mailto"] = mailto
        data = openalex._request(params, headers)
        works.extend(data.get("results") or [])
    return works


def chase_backward(resolved_seeds, limit, headers, mailto):
    """Union of every resolved seed's `referenced_works`, capped at `limit`
    total (not per-seed -- a reviewer with 20 included studies chasing 50
    references each would otherwise trigger 1000 API calls for one command).
    `total_available` is the true unique-reference count before capping,
    since references are fully enumerable from the seed works already fetched
    (no further querying needed to know the real total, unlike forward chase).
    """
    referenced_ids = []
    seen = set()
    for work in resolved_seeds.values():
        for ref in work.get("referenced_works") or []:
            ref_id = _openalex_id_only(ref)
            if ref_id not in seen:
                seen.add(ref_id)
                referenced_ids.append(ref_id)

    total_available = len(referenced_ids)
    capped_ids = referenced_ids[:limit] if limit else referenced_ids
    works = _fetch_by_openalex_ids(capped_ids, headers, mailto)
    return [_to_result(w) for w in works], total_available


def chase_forward(resolved_seeds, limit, headers, mailto):
    """Works citing any resolved seed, via filter=cites:ID1|ID2|...
    Paginated the same way openalex.py's own cmd_search cursor-loops, capped
    at `limit` total across all seeds combined."""
    if not resolved_seeds:
        return [], 0
    seed_ids = list(resolved_seeds.keys())
    base_params = {"filter": f"cites:{'|'.join(seed_ids)}"}
    if mailto:
        base_params["mailto"] = mailto

    collected = []
    total_available = None
    cursor = "*"
    while len(collected) < limit:
        page_size = min(openalex.MAX_PER_PAGE, limit - len(collected))
        params = dict(base_params, per_page=page_size, cursor=cursor)
        data = openalex._request(params, headers)
        if total_available is None:
            total_available = data["meta"]["count"]
        batch = data.get("results") or []
        collected.extend(_to_result(w) for w in batch)
        cursor = data["meta"].get("next_cursor")
        if not cursor or not batch:
            break
    return collected, (total_available or 0)


def cmd_chase(args):
    seed_ids = [s for s in (args.seed_ids or "").split(",") if s.strip()]
    if not seed_ids:
        openalex._fail("--seed-ids is required (comma-separated DOIs or OpenAlex ids)", "INVALID_QUERY")

    mailto = openalex.get_mailto()
    headers = {"User-Agent": openalex._user_agent()}
    resolved, unresolved = _resolve_seeds(seed_ids)

    limit = args.limit if args.limit and args.limit > 0 else 200
    results = []
    total_available = 0
    seen_ids = set()

    if args.direction in ("backward", "both"):
        backward_results, backward_total = chase_backward(resolved, limit, headers, mailto)
        total_available += backward_total
        for r in backward_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                results.append(r)

    if args.direction in ("forward", "both"):
        remaining = max(0, limit - len(results)) if args.direction == "both" else limit
        forward_results, forward_total = chase_forward(resolved, remaining or limit, headers, mailto)
        total_available += forward_total
        for r in forward_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                results.append(r)

    retrieved = len(results)
    truncated = total_available > retrieved
    query_desc = f"{args.direction} chase from {len(resolved)}/{len(seed_ids)} resolved seed(s)"
    meta = _meta(query_desc, retrieved, total_available, truncated)
    meta["unresolved_seeds"] = unresolved
    payload = {"meta": meta, "results": results}
    openalex._emit(payload, args.format, args.out)


def build_arg_parser():
    parser = argparse.ArgumentParser(prog="connectors.citation_chase")
    sub = parser.add_subparsers(dest="command", required=True)

    chase = sub.add_parser("chase")
    chase.add_argument("--seed-ids", required=True, help="comma-separated DOIs and/or OpenAlex work ids")
    chase.add_argument("--direction", choices=["backward", "forward", "both"], default="both")
    chase.add_argument("--limit", type=int, default=200, help="max results per direction (backward+forward each capped at this when --direction both)")
    chase.add_argument("--format", choices=["json", "table", "plain"], default="json")
    chase.add_argument("--out", default=None, help="write the JSON response here instead of stdout")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "chase":
        cmd_chase(args)
    else:
        parser.error(f"unknown command {args.command!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
