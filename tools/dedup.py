#!/usr/bin/env python3
"""Deduplicate `raw/*.json` into `records.jsonl` (exact-key pass), and
optionally flag near-duplicate pairs into `possible_duplicates.jsonl`
(fuzzy pass, advisory only).

Ported, behavior-preserving, from the inline Python heredocs
`.claude/commands/prisma-search.md` Steps 7 and 7b used to embed directly
in the prompt and instruct the LLM to "run exactly as written" -- Phase 0
correctness fix (docs/PLAN.md defect #3): state-transition logic belongs in
a tested `tools/` module, not inline in a command file.

Usage:
    python3 tools/dedup.py --topic <slug> [--pass exact|fuzzy|both]

`--pass exact` (default) runs Step 7's dedup only; `--pass fuzzy` runs Step
7b's near-duplicate flagging only (requires `records.jsonl` to already
exist); `--pass both` runs exact then fuzzy in one invocation.

Exit code 0 on success (including "0 raw files found" -- an empty raw/
directory is not an error, just nothing to do yet), 1 on an unsafe path or
a malformed raw file.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402

SIMILARITY_THRESHOLD = 0.90


def normalize_doi(doi):
    if not doi:
        return None
    d = str(doi).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.rstrip("/")
    return d or None


def normalize_pmid(rec):
    # DOI -> PMID -> title|author|year hierarchy, step 2: PMID is only ever
    # recoverable from a "pubmed" record's bare id, or a "europepmc" record
    # whose id is "MED:<pmid>" (Europe PMC's own MEDLINE-source prefix).
    #
    # Bug fixed during the Phase 0 port from .claude/commands/prisma-search.md's
    # inline heredoc (docs/PLAN.md defect #3): the original read rec["id"],
    # but the constructed record dict this is always called on carries only
    # "record_id" ("<source>:<native_id>") -- never a bare "id" key, on a
    # freshly parsed raw result *or* a record read back from records.jsonl.
    # rec.get("id") was therefore always None and this tier could never
    # actually match anything. Recover the native id by stripping the known
    # "<source>:" prefix from record_id instead (source names never contain
    # ":", so this is unambiguous and works uniformly for both cases).
    source = rec.get("source")
    record_id = rec.get("record_id") or ""
    prefix = f"{source}:"
    rid = record_id[len(prefix):] if source and record_id.startswith(prefix) else ""
    if source == "pubmed":
        return rid or None
    if source == "europepmc" and ":" in rid:
        src, _, extid = rid.partition(":")
        if src.upper() == "MED" and extid.isdigit():
            return extid
    return None


def normalize_title(title):
    if not title:
        return ""
    t = re.sub(r"[^\w\s]", " ", title.lower())
    return re.sub(r"\s+", " ", t).strip()


def first_author_surname(authors):
    if not authors:
        return ""
    a = str(authors[0]).strip()
    # MEDLINE style: "Surname IN" (e.g. "Kim JH") -- surname is the first token.
    m = re.match(r"^([A-Za-z\-']+)\s+[A-Z]{1,3}$", a)
    if m:
        return m.group(1).lower()
    if "," in a:
        return a.split(",")[0].strip().lower()
    # "Given ... Surname" style (most other sources) -- surname is the last token.
    parts = a.split()
    return parts[-1].lower() if parts else ""


def tay_key(rec):
    t = normalize_title(rec.get("title"))
    y = rec.get("year")
    if not t or not y:
        return None
    a = first_author_surname(rec.get("authors") or [])
    return f"{t}|{a}|{y}"


def record_keys(rec):
    # DOI -> PMID -> title|author|year: heuristic surname/title normalization
    # catches the large majority of real duplicates, including an arXiv
    # preprint vs. its later published version (arXiv's doi is usually null,
    # so those records fall straight through the doi/pmid tiers to this one;
    # when arXiv *does* carry a doi -- the author later registered the
    # journal DOI -- it is treated as a real doi match like any other, not a
    # special case). Author-order swaps or a retitled published version can
    # still slip past this; screening is the safety net, not this module.
    keys = []
    doi = normalize_doi(rec.get("doi"))
    if doi:
        keys.append(("doi", doi))
    pmid = normalize_pmid(rec)
    if pmid:
        keys.append(("pmid", pmid))
    tay = tay_key(rec)
    if tay:
        keys.append(("title_author_year", tay))
    return keys


def dedupe_raw_files(topic_dir):
    """Exact-key dedup pass: reads every `raw/*.json` under `topic_dir`,
    appends genuinely new records to `records.jsonl` (record_id-based
    idempotency -- a record_id already on disk is never re-appended), and
    returns the same summary stats the original heredoc printed."""
    topic_dir = Path(topic_dir)
    raw_files = sorted(glob.glob(str(topic_dir / "raw" / "*.json")))
    records_path = topic_dir / "records.jsonl"

    existing_ids = set()
    existing_lines = []
    if records_path.exists():
        with open(records_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                existing_lines.append(rec)
                existing_ids.add(rec["record_id"])

    # Seed the key map from records already on disk. Every existing line --
    # canonical or duplicate -- resolves to its own canonical record_id so a
    # new record matching any prior copy's keys still lands on the right
    # canonical.
    key_to_canonical = {}
    for rec in existing_lines:
        canonical_id = rec.get("duplicate_of") or rec["record_id"]
        for _, k in record_keys(rec):
            key_to_canonical.setdefault(k, canonical_id)

    new_lines = []
    stats = {"canonical": 0, "duplicate": 0, "skipped_no_id": 0,
             "by_tier": {"doi": 0, "pmid": 0, "title_author_year": 0}}

    for path in raw_files:
        with open(path) as f:
            payload = json.load(f)
        source = payload.get("meta", {}).get("source")
        for r in payload.get("results", []):
            native_id = r.get("id")
            if not native_id:
                stats["skipped_no_id"] += 1
                continue
            record_id = f"{source}:{native_id}"
            if record_id in existing_ids:
                continue  # already merged by a prior run of this pass
            existing_ids.add(record_id)

            rec = {
                "record_id": record_id,
                "title": r.get("title"),
                "authors": r.get("authors") or [],
                "year": r.get("year"),
                "venue": r.get("venue"),
                "doi": r.get("doi"),
                "abstract": r.get("abstract"),
                "url": r.get("url"),
                "source": source,
                "duplicate_of": None,
            }

            matched_canonical = None
            matched_tier = None
            for tier, k in record_keys(rec):
                if k in key_to_canonical:
                    matched_canonical = key_to_canonical[k]
                    matched_tier = tier
                    break

            if matched_canonical:
                rec["duplicate_of"] = matched_canonical
                stats["duplicate"] += 1
                stats["by_tier"][matched_tier] += 1
            else:
                stats["canonical"] += 1

            # Register every key this record carries -- even a duplicate's
            # own doi/pmid -- against its resolved canonical id. Otherwise a
            # copy that only matched on title|author|year (because the
            # earlier copy it matched had no doi) leaves its own doi
            # unindexed, and a later arrival sharing that doi but with a
            # slightly different title would wrongly start a new canonical
            # instead of joining this study.
            canonical_id = matched_canonical or record_id
            for _, k in record_keys(rec):
                key_to_canonical.setdefault(k, canonical_id)

            new_lines.append(rec)

    if new_lines:
        with open(records_path, "a") as f:
            for rec in new_lines:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_now = len(existing_lines) + len(new_lines)
    total_canonical_now = (sum(1 for r in existing_lines if r.get("duplicate_of") is None)
                            + stats["canonical"])
    return {
        "raw_files_processed": len(raw_files),
        "new_lines_appended": len(new_lines),
        "new_canonical": stats["canonical"],
        "new_duplicates": stats["duplicate"],
        "duplicates_by_tier": stats["by_tier"],
        "skipped_no_native_id": stats["skipped_no_id"],
        "total_records_now": total_now,
        "total_canonical_now": total_canonical_now,
    }


def flag_near_duplicates(topic_dir):
    """Fuzzy near-duplicate pass, advisory only: never rewrites a line in
    `records.jsonl`, never sets `duplicate_of` -- only appends pairs to
    `possible_duplicates.jsonl` for the reviewer to see during
    `/prisma-screen`. Requires `records.jsonl` to already exist (run the
    exact pass first)."""
    topic_dir = Path(topic_dir)
    records_path = topic_dir / "records.jsonl"
    dups_path = topic_dir / "possible_duplicates.jsonl"

    canonical = []
    if records_path.exists():
        with open(records_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("duplicate_of") is None and rec.get("title") and rec.get("year"):
                    canonical.append(rec)

    existing_pairs = set()
    if dups_path.exists():
        with open(dups_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                existing_pairs.add(frozenset((d["record_id_a"], d["record_id_b"])))

    # O(n^2) within each same-year bucket, and only matches records published
    # in the *same* year (a preprint/published-version pair spanning two
    # calendar years relies on the exact pass's title|author|year tier
    # instead, or manual reviewer catch during screening) -- upgrade path if
    # this proves too narrow: bucket by year and year+-1, or swap
    # SequenceMatcher for a proper fuzzy-matching library (rapidfuzz) once
    # near-duplicate volume justifies the new dependency.
    by_year = {}
    for rec in canonical:
        by_year.setdefault(rec["year"], []).append(rec)

    new_pairs = []
    for year, group in by_year.items():
        normed = [(rec, normalize_title(rec["title"])) for rec in group]
        for i in range(len(normed)):
            rec_a, norm_a = normed[i]
            for j in range(i + 1, len(normed)):
                rec_b, norm_b = normed[j]
                if not norm_a or not norm_b:
                    continue
                pair_key = frozenset((rec_a["record_id"], rec_b["record_id"]))
                if pair_key in existing_pairs:
                    continue
                ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
                if ratio >= SIMILARITY_THRESHOLD:
                    new_pairs.append({
                        "record_id_a": rec_a["record_id"],
                        "record_id_b": rec_b["record_id"],
                        "similarity": round(ratio, 2),
                        "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    existing_pairs.add(pair_key)

    if new_pairs:
        with open(dups_path, "a") as f:
            for pair in new_pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    return {"canonical_records_checked": len(canonical), "new_possible_duplicates_flagged": len(new_pairs)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True,
                         help="review slug; derives results/<topic>/{raw,records.jsonl,possible_duplicates.jsonl} "
                              "itself -- never accepts a free-form path")
    parser.add_argument("--pass", dest="pass_", choices=["exact", "fuzzy", "both"], default="exact",
                         help="exact: Step 7's doi/pmid/title-author-year dedup (default). "
                              "fuzzy: Step 7b's near-duplicate flagging (advisory only, requires "
                              "records.jsonl to already exist). both: exact then fuzzy.")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.pass_ in ("exact", "both"):
        stats = dedupe_raw_files(topic_dir)
        print(json.dumps(stats, indent=2))
        if stats["skipped_no_native_id"]:
            print(
                f"Warning: {stats['skipped_no_native_id']} result(s) had no native id and were skipped -- "
                "a connector returning an id-less result is a contract violation worth reporting.",
                file=sys.stderr,
            )

    if args.pass_ in ("fuzzy", "both"):
        if not (Path(topic_dir) / "records.jsonl").exists():
            print("Error: records.jsonl does not exist yet -- run the exact pass first (--pass exact)", file=sys.stderr)
            return 1
        fuzzy_stats = flag_near_duplicates(topic_dir)
        print(json.dumps(fuzzy_stats, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
