#!/usr/bin/env python3
"""The screening-decisions ledger: hash-chained append, the PRISMA Item 16b
gate (every full-text exclude/not_retrieved needs a reason), and the
candidate-set join against `records.jsonl` / `extraction_table.json`.

Ported, behavior-preserving, from the inline Python heredocs
`.claude/commands/litreview-extract.md` Steps 1 and 2 used to embed directly
in the prompt (Phase 0 correctness fix, docs/PLAN.md defect #3) -- plus the
hash-chained append this framework's own append-only ledger never actually
verified before (docs/PLAN.md decision 4 / "adopted from open-source
peers": AngelChen-HC/systematic-review-skill, Apache-2.0).

`screening_decisions.jsonl` line shape (additive fields marked *new*):

    {"record_id": "...", "stage": "title_abstract"|"full_text",
     "decision": "include"|"exclude"|"not_retrieved", "reason": str|null,
     "ai_suggestion": "include"|"exclude"|"unclear"|null,
     "decided_at": "<ISO-8601 UTC>",
     "by": str|null,                    # *new* -- who/what recorded this line
     "role": "decision"|"verification", # *new* -- default "decision"
     "eligibility_version": int|null,   # *new* -- protocol.json eligibility version in effect
     "prev_hash": str|null,             # *new* -- previous line's entry_hash, or null for the first hashed line
     "entry_hash": str}                 # *new* -- sha256(prev_hash + canonical JSON of everything above)

A ledger written before this hash-chaining existed has lines with none of
the last two fields ("legacy, unhashed"); verify() tolerates exactly one
such contiguous prefix at the start of the file and reports its length,
rather than treating it as tampering.

Usage:
    python3 tools/ledger.py --topic <slug> gate
    python3 tools/ledger.py --topic <slug> candidates
    python3 tools/ledger.py --topic <slug> verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402

# Full-text decisions that must carry a reason -- "exclude" per PRISMA Item
# 16b, and "not_retrieved" for the same disclosure reason (why a sought
# report could not be obtained is exactly as reportable as why it was
# excluded).
REASON_REQUIRED_DECISIONS = {"exclude", "not_retrieved"}
HASH_FIELDS = ("prev_hash", "entry_hash")


def _ledger_path(topic_dir):
    return Path(topic_dir) / "screening_decisions.jsonl"


def load_ledger(topic_dir):
    path = _ledger_path(topic_dir)
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def compute_entry_hash(prev_hash, entry_without_hash_fields):
    """sha256(prev_hash + canonical JSON of the entry). Canonical = sorted
    keys, compact separators, so the same logical entry always hashes the
    same way regardless of key insertion order."""
    canonical = json.dumps(entry_without_hash_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload = (prev_hash or "") + canonical
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_decisions(topic_dir, rows):
    """Append `rows` (each at least record_id/stage/decision/reason/
    ai_suggestion/decided_at) to screening_decisions.jsonl, chaining each
    new line's prev_hash to the previous line's entry_hash (None for the
    very first line ever written, hashed or not -- a fresh ledger's first
    line always has prev_hash: null). Returns the list of full entries
    written, in order. Never rewrites an existing line."""
    path = _ledger_path(topic_dir)
    existing = load_ledger(topic_dir)
    prev_hash = existing[-1]["entry_hash"] if existing and "entry_hash" in existing[-1] else None

    written = []
    with open(path, "a") as f:
        for row in rows:
            entry = dict(row)
            entry.setdefault("by", None)
            entry.setdefault("role", "decision")
            entry.setdefault("eligibility_version", None)
            entry_hash = compute_entry_hash(prev_hash, entry)
            full_entry = dict(entry)
            full_entry["prev_hash"] = prev_hash
            full_entry["entry_hash"] = entry_hash
            f.write(json.dumps(full_entry, ensure_ascii=False) + "\n")
            prev_hash = entry_hash
            written.append(full_entry)
    return written


def latest_decisions(entries, role="decision"):
    """Reduce to the latest entry per (record_id, stage), restricted to
    `role` (default "decision" -- a "verification" second-rater line never
    overrides the recorded decision the pipeline acts on). File order is
    the aggregation key, never decided_at (see screening-assistant §1)."""
    latest = {}
    for e in entries:
        if e.get("role", "decision") != role:
            continue
        latest[(e["record_id"], e["stage"])] = e
    return latest


def full_text_reason_required_missing(latest):
    """(record_id, entry) pairs whose full-text decision needs a reason
    (PRISMA Item 16b) but doesn't have one."""
    return [
        (rid, e) for (rid, stage), e in latest.items()
        if stage == "full_text" and e["decision"] in REASON_REQUIRED_DECISIONS
        and not (e.get("reason") and e["reason"].strip())
    ]


def candidate_set(records, latest, extracted_record_ids):
    """Port of litreview-extract.md Step 2: full-text includes not yet
    extracted. `records`: dict of record_id -> record (canonical only,
    duplicate_of is None). `latest`: from latest_decisions(). Returns a
    list of {record_id, status, title, year, url, doi} in ledger order."""
    full_text_includes = [
        rid for (rid, stage), e in latest.items()
        if stage == "full_text" and e["decision"] == "include"
    ]
    rows = []
    for rid in full_text_includes:
        r = records.get(rid, {})
        status = "extracted" if rid in extracted_record_ids else "PENDING"
        rows.append({
            "record_id": rid, "status": status,
            "title": r.get("title", "(record missing from records.jsonl)"),
            "year": r.get("year"), "url": r.get("url"), "doi": r.get("doi"),
        })
    return rows


def verify_chain(entries):
    """Walk the hash chain. Tolerates exactly one contiguous unhashed
    prefix at the start (a ledger written before hashing existed); once a
    hashed entry appears, every entry after it must chain correctly.
    Returns {"ok": True, "legacy_unhashed_prefix": n, "entries_checked": n}
    or {"ok": False, "error": str, "index": i} on the first broken/tampered
    link or an unhashed entry appearing after hashing had already begun."""
    legacy_unhashed_prefix = 0
    prev_hash = None
    hashing_started = False
    checked = 0
    for i, e in enumerate(entries):
        if "entry_hash" not in e:
            if hashing_started:
                return {"ok": False, "index": i,
                        "error": f"entry at index {i} (record_id={e.get('record_id')!r}) is missing entry_hash "
                                 "after hashing had already begun for this ledger"}
            legacy_unhashed_prefix += 1
            continue
        hashing_started = True
        if e.get("prev_hash") != prev_hash:
            return {"ok": False, "index": i,
                    "error": f"broken chain at index {i} (record_id={e.get('record_id')!r}): "
                             f"prev_hash {e.get('prev_hash')!r} does not match the prior entry's entry_hash {prev_hash!r}"}
        entry_sans_hash = {k: v for k, v in e.items() if k not in HASH_FIELDS}
        recomputed = compute_entry_hash(prev_hash, entry_sans_hash)
        if recomputed != e["entry_hash"]:
            return {"ok": False, "index": i,
                    "error": f"tampered entry at index {i} (record_id={e.get('record_id')!r}): "
                             "recomputed entry_hash does not match the stored one"}
        prev_hash = e["entry_hash"]
        checked += 1
    return {"ok": True, "legacy_unhashed_prefix": legacy_unhashed_prefix, "entries_checked": checked}


def _load_records(topic_dir):
    path = Path(topic_dir) / "records.jsonl"
    if not path.exists():
        return {}
    with open(path) as f:
        return {r["record_id"]: r for r in (json.loads(l) for l in f if l.strip()) if r.get("duplicate_of") is None}


def _load_extracted_ids(topic_dir):
    path = Path(topic_dir) / "extraction_table.json"
    if not path.exists():
        return set()
    with open(path) as f:
        table = json.load(f)
    return {s["record_id"] for s in table.get("studies", [])}


def cmd_gate(topic_dir):
    latest = latest_decisions(load_ledger(topic_dir))
    bad = full_text_reason_required_missing(latest)
    if bad:
        print("REFUSED")
        for rid, e in bad:
            print(f"{rid}\t(no reason recorded for {e['decision']!r})")
        return 1
    n_includes = sum(1 for (_, stage), e in latest.items() if stage == "full_text" and e["decision"] == "include")
    print(f"OK {n_includes}")
    return 0


def cmd_candidates(topic_dir):
    latest = latest_decisions(load_ledger(topic_dir))
    records = _load_records(topic_dir)
    extracted_ids = _load_extracted_ids(topic_dir)
    for row in candidate_set(records, latest, extracted_ids):
        print(f"{row['record_id']}\t{row['status']}\t{row['title']}\t{row['year']}\t{row['url']}\t{row['doi']}")
    return 0


def cmd_verify(topic_dir):
    result = verify_chain(load_ledger(topic_dir))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="review slug; derives results/<topic>/ itself")
    parser.add_argument("command", choices=["gate", "candidates", "verify"])
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return {"gate": cmd_gate, "candidates": cmd_candidates, "verify": cmd_verify}[args.command](topic_dir)


if __name__ == "__main__":
    sys.exit(main())
