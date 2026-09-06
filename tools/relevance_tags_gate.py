#!/usr/bin/env python3
"""Deterministic tool for a reconnaissance topic's relevance_tags_table.json
(docs/ROADMAP.md M4; methods/reconnaissance.json's capture.mode:
"relevance_tags").

Unlike tools/charting_gate.py / tools/classification_gate.py, there is no
co-developed field/facet form to pilot and freeze here (methods/
reconnaissance.json's capture.freeze_gate is false, capture.pilot_records
is 0) -- a reconnaissance brief tags each candidate with free-text
relevance facets instead, so this module has no "gate" in the freeze sense.
It does two things instead: refuses a duplicate record_id before a row is
written (the one structural mistake worth catching deterministically
rather than trusting a prompt to notice), and computes the
corpus-description table (facet-tag frequency counts) a landscape brief
reports -- a mechanical tally, not something to hand-count in prose.

Usage:
    python3 tools/relevance_tags_gate.py --topic <slug>
    python3 tools/relevance_tags_gate.py --topic <slug> --check-record-id <record_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


class RelevanceTagsGateError(ValueError):
    """relevance_tags_table.json is malformed."""


def _table_path(topic_dir: Path) -> Path:
    return Path(topic_dir) / "relevance_tags_table.json"


def load_relevance_tags_table(topic_dir: Path, topic: str) -> dict:
    """Returns the existing relevance_tags_table.json, or a fresh, empty
    one if this topic hasn't tagged anything yet -- absence of the file is
    the expected starting state, never an error."""
    path = _table_path(topic_dir)
    if not path.exists():
        return {"framework_version": "1.0.0", "topic": topic, "studies": []}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RelevanceTagsGateError(f"{path}: invalid JSON: {exc}") from exc


def already_tagged(table: dict, record_id: str) -> bool:
    """Whether `record_id` already has a row in `table` -- the one
    write-time check this capture mode has, since there is no frozen
    field/facet list for a row's shape to drift from."""
    return any(row.get("record_id") == record_id for row in table.get("studies", []))


def corpus_description(table: dict) -> dict[str, int]:
    """{facet_tag: count} across every row's facet_tags[] -- the
    corpus-description table a landscape brief reports, computed
    deterministically from the table rather than hand-tallied while
    drafting."""
    counts: dict[str, int] = {}
    for row in table.get("studies", []):
        for tag in row.get("facet_tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--check-record-id", help="refuse (exit 1) if this record_id is already tagged, instead of printing the corpus-description table")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        table = load_relevance_tags_table(topic_dir, args.topic)
    except RelevanceTagsGateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.check_record_id:
        dup = already_tagged(table, args.check_record_id)
        print(json.dumps({"record_id": args.check_record_id, "already_tagged": dup}, indent=2))
        return 1 if dup else 0

    print(json.dumps({
        "n_tagged": len(table.get("studies", [])),
        "corpus_description": corpus_description(table),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
