#!/usr/bin/env python3
"""protocol.json.versions[] -- a living-review "version" (docs/ROADMAP.md
M5) is a snapshot of this topic's canonical record set taken at a specific
point in time, closing out a search/screening pass so a later living
rerun can report exactly what changed since (tools/status.py's
since_last_version()). Follows the same convention protocol.json's
known_items[] and amendments[] already use -- read/written ad hoc, no
dedicated JSON Schema file, since neither of those has one either.

Nothing computes a delta from mere counts alone: counts can't say *which*
records are new if some were also reclassified as duplicates in between,
so each version snapshot stores the full canonical record_id set, not
just a count.

Usage:
    python3 tools/versioning.py --topic <slug> record
    python3 tools/versioning.py --topic <slug> latest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.ledger import latest_decisions, load_ledger  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


class VersioningError(ValueError):
    """protocol.json is missing -- a version cannot be recorded before a
    protocol exists."""


def _protocol_path(topic_dir) -> Path:
    return Path(topic_dir) / "protocol.json"


def _load_protocol(topic_dir) -> dict:
    path = _protocol_path(topic_dir)
    if not path.exists():
        raise VersioningError(f"{path} does not exist -- cannot record a version before a protocol exists")
    return json.loads(path.read_text())


def _canonical_record_ids(topic_dir) -> list[str]:
    records_path = Path(topic_dir) / "records.jsonl"
    if not records_path.exists():
        return []
    ids = []
    with open(records_path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if not rec.get("duplicate_of"):
                ids.append(rec["record_id"])
    return sorted(ids)


def latest_version(topic_dir) -> dict | None:
    """The most recently recorded version entry, or None if this topic has
    never had one recorded yet (its first pass -- not living mode yet)."""
    protocol = _load_protocol(topic_dir)
    versions = protocol.get("versions") or []
    return versions[-1] if versions else None


def record_version(topic_dir, topic: str) -> dict:
    """Appends a new version snapshot to protocol.json.versions[]: the
    current canonical record set plus an included count read from
    tools/ledger.py's own latest decisions (never a second, parallel
    decision-counting mechanism -- the same reasoning tools/status.py and
    tools/flow_counts.py already document relative to each other).

    Idempotent no-op if nothing changed since the latest recorded version
    (same canonical record_ids, same included count) -- otherwise a stray
    repeated `/prisma-search --living` run would append an identical-content
    version entry and tools/status.py's since_last_version() would report a
    phantom zero-record delta as if a real rerun had happened."""
    protocol = _load_protocol(topic_dir)
    record_ids = _canonical_record_ids(topic_dir)

    entries = load_ledger(topic_dir)
    latest = latest_decisions(entries)
    included = sum(1 for (rid, stage), e in latest.items() if stage == "full_text" and e["decision"] == "include")

    versions = list(protocol.get("versions") or [])
    if versions and versions[-1]["record_ids"] == record_ids and versions[-1]["n_included"] == included:
        return {**versions[-1], "unchanged": True}

    entry = {
        "version": len(versions) + 1,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "record_ids": record_ids,
        "n_records": len(record_ids),
        "n_included": included,
    }
    versions.append(entry)
    protocol["versions"] = versions
    _protocol_path(topic_dir).write_text(json.dumps(protocol, indent=2) + "\n")
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("action", choices=["record", "latest"])
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        result = record_version(topic_dir, args.topic) if args.action == "record" else latest_version(topic_dir)
    except VersioningError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
