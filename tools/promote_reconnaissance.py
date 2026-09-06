#!/usr/bin/env python3
"""Same-topic promotion from a reconnaissance topic to a real
evidence-synthesis method (docs/ROADMAP.md M4).

Promotion is same-topic only, per this repo's existing cross-topic
isolation rule: a reconnaissance topic's own recon-stage artifacts
(`records.jsonl`, `raw/`, `relevance_tags_table.json`) are archived to
`recon/`, never left live where the promoted method's own search would
find them -- "recon records never enter the promoted method's
records.jsonl without a fresh run" (the M4 exit criterion's literal
wording) is enforced here mechanically, by moving the file out of the way,
not left to a prompt to remember.

Writes `handoff/` (`seed_terms.json`, `gold_set_candidates.json` --
each candidate carries `provenance: "recon-db"` --, `disclosure.md`), then
folds any gold-set candidate with a recoverable DOI/PMID into
`protocol.json.known_items[]` (same `provenance: "recon-db"` tag, read by
tools/search_preflight.py's known_item_recall() to compute recall
excluding these seeds and print a "non-independent gold set" notice until
an externally-sourced known item is added). Records the method change via
`protocol.json.amendments[]` (the same `{date, change, reason}` shape
`review-protocol/SKILL.md`'s own update path already uses, PRISMA Item
24c) and clears both `method.signed_at`/`signed_by` and protocol.json's
own top-level `signed_at`/`signed_by` -- tools/sign_protocol.py and
label_gate.py's protocol_signed_before_first_protocol_driven_run check
both read the top-level field, so leaving it in place would make the
promoted method's protocol look already (and wrongly-dated) signed.

Usage:
    python3 tools/promote_reconnaissance.py --topic <slug> --new-method-id <id> --reason "<text>"
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.dedup import normalize_doi, normalize_pmid  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402

DISCLOSURE_TEXT = (
    "# Reconnaissance disclosure\n\n"
    "This review began as a reconnaissance (exploratory literature brief) on this same topic. "
    "If you later run a scoping or systematic review, reviewers will ask whether you had seen the "
    "literature before writing your protocol; this paragraph answers that honestly: yes, a bounded, "
    "orienting search was already run before this protocol was signed, and its candidates are recorded "
    "in `handoff/gold_set_candidates.json` with `provenance: \"recon-db\"`. Any known-item recall check "
    "against those candidates alone would be circular -- they were found by the same search being "
    "evaluated. Recall is reported excluding these seeds until at least one externally-sourced known "
    "item is added; `search_status.json` prints a \"non-independent gold set\" notice until then.\n"
)


class PromotionError(ValueError):
    """The topic isn't a promotable reconnaissance topic, or has already been promoted."""


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _gold_set_candidates(recon_dir: Path) -> list[dict]:
    """Every relevance-tagged row with a non-null `claim`, cross-referenced
    against the archived records.jsonl for a recoverable DOI/PMID -- the
    mechanical transform of what tagging already recorded, not a fresh
    judgement call."""
    tags_table = _load_json(recon_dir / "relevance_tags_table.json") or {"studies": []}
    records = []
    records_path = recon_dir / "records.jsonl"
    if records_path.exists():
        records = [json.loads(l) for l in records_path.read_text().splitlines() if l.strip()]
    records_by_id = {r["record_id"]: r for r in records}

    candidates = []
    for row in tags_table.get("studies", []):
        if not row.get("claim"):
            continue
        record = records_by_id.get(row["record_id"], {})
        doi = normalize_doi(record.get("doi"))
        pmid = normalize_pmid(record)
        if doi:
            id_type, id_value = "doi", doi
        elif pmid:
            id_type, id_value = "pmid", pmid
        else:
            id_type, id_value = None, None
        candidates.append({
            "record_id": row["record_id"],
            "facet_tags": row.get("facet_tags", []),
            "claim": row.get("claim"),
            "id_type": id_type,
            "id": id_value,
            "provenance": "recon-db",
        })
    return candidates


def promote(topic_dir: Path, topic: str, new_method_id: str, reason: str) -> dict:
    topic_dir = Path(topic_dir)
    protocol_path = topic_dir / "protocol.json"
    protocol = _load_json(protocol_path)
    if protocol is None:
        raise PromotionError(f"{protocol_path} does not exist -- nothing to promote")

    current_method_id = (protocol.get("method") or {}).get("id")
    if current_method_id != "reconnaissance":
        raise PromotionError(
            f"this topic's protocol.json.method.id is {current_method_id!r}, not \"reconnaissance\" -- "
            "promotion only applies to a reconnaissance topic"
        )

    recon_dir = topic_dir / "recon"
    if recon_dir.exists():
        raise PromotionError(f"{recon_dir} already exists -- this topic has already been promoted once")

    recon_dir.mkdir(parents=True)
    archived = []
    for name in ("records.jsonl", "raw", "relevance_tags_table.json"):
        src = topic_dir / name
        if src.exists():
            shutil.move(str(src), str(recon_dir / name))
            archived.append(name)

    handoff_dir = topic_dir / "handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)

    search_plan = _load_json(topic_dir / "search_plan.json") or {}
    seed_terms = {
        source: cfg.get("query")
        for source, cfg in (search_plan.get("sources") or {}).items()
        if cfg.get("query")
    }
    (handoff_dir / "seed_terms.json").write_text(json.dumps({"query_strings": seed_terms}, indent=2) + "\n")

    candidates = _gold_set_candidates(recon_dir)
    (handoff_dir / "gold_set_candidates.json").write_text(json.dumps(candidates, indent=2) + "\n")
    (handoff_dir / "disclosure.md").write_text(DISCLOSURE_TEXT)

    known_items = list(protocol.get("known_items") or [])
    existing_ids = {(i.get("id_type"), i.get("id")) for i in known_items}
    added = 0
    for c in candidates:
        if not c["id_type"] or (c["id_type"], c["id"]) in existing_ids:
            continue
        known_items.append({
            "id_type": c["id_type"],
            "id": c["id"],
            "note": f"reconnaissance candidate, closest on: {', '.join(c['facet_tags']) or 'unspecified'}",
            "provenance": "recon-db",
        })
        existing_ids.add((c["id_type"], c["id"]))
        added += 1
    protocol["known_items"] = known_items

    amendments = list(protocol.get("amendments") or [])
    amendments.append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "change": f"promoted from reconnaissance to {new_method_id}",
        "reason": reason,
    })
    protocol["amendments"] = amendments

    method_block = dict(protocol.get("method") or {})
    method_block["id"] = new_method_id
    method_block["signed_at"] = None
    method_block["signed_by"] = None
    protocol["method"] = method_block

    # tools/sign_protocol.py reads protocol.json's own TOP-LEVEL signed_at
    # (not method.signed_at) to decide whether signing is already done, and
    # label_gate.py's protocol_signed_before_first_protocol_driven_run check
    # reads the same top-level field -- a stale value here would make the
    # promoted method's protocol look already (and wrongly-dated) signed,
    # silently blocking it from ever being re-signed for real.
    protocol["signed_at"] = None
    protocol["signed_by"] = None

    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n")

    return {
        "archived": archived,
        "gold_set_candidates": len(candidates),
        "known_items_added": added,
        "new_method_id": new_method_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--new-method-id", required=True, help="the real method this reconnaissance topic is being promoted to")
    parser.add_argument("--reason", required=True, help="one-sentence reason, recorded in protocol.json.amendments[]")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        result = promote(topic_dir, args.topic, args.new_method_id, args.reason)
    except PromotionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
