#!/usr/bin/env python3
"""Deterministic builder for a title/abstract or full-text screening sheet.

Replaces the old "adapt inline every run" export algorithm in
`.claude/skills/screening-assistant/01-screening-sheet-workflow.md` for
everything that's mechanical: reading records.jsonl/screening_decisions.jsonl/
possible_duplicates.jsonl, computing the stage-progression candidate set,
grouping, sorting, truncating abstracts, and writing the CSV/MD twin. Every
factual column (title/year/authors/source/doi/url/...) is emitted straight
from records.jsonl, keyed by record_id -- never by row position -- so a
row/column misalignment bug can't be reintroduced by a future improvised
export.

The one thing this script does NOT do is the eligibility-gate judgment behind
`ai_suggestion`/`ai_rationale` -- that's protocol-specific (varies with each
review's PICO/eligibility criteria) and stays a Claude-authored step. Claude
writes that judgment to a small `_suggestions.jsonl` scratch file
(`{"record_id": ..., "ai_suggestion": "include|exclude|unclear", "ai_rationale": "..."}`
per line) and this script merges it in by record_id via --suggestions.

Exit code 0 on success (including the "nothing to export" case), 1 on a real
failure (missing records.jsonl, malformed JSONL/flags).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

STAGE_TITLES = {
    "title_abstract": "Title/Abstract Screening",
    "full_text": "Full-Text Screening",
}

CSV_FIELDS = [
    "record_id", "decision", "reason", "ai_suggestion", "ai_rationale",
    "ai_keywords", "title", "year", "authors", "source", "doi", "url",
    "abstract_truncated", "possible_duplicate",
]

AI_SUGGESTION_GROUP_ORDER = ["include", "exclude", "unclear", "none"]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_records(topic_dir: Path) -> list[dict]:
    records = _read_jsonl(topic_dir / "records.jsonl")
    return [r for r in records if r.get("duplicate_of") is None]


def load_latest_decisions(topic_dir: Path) -> dict[tuple[str, str], dict]:
    latest: dict[tuple[str, str], dict] = {}
    for event in _read_jsonl(topic_dir / "screening_decisions.jsonl"):
        latest[(event["record_id"], event["stage"])] = event  # file order = truth, last wins
    return latest


def load_possible_duplicates(topic_dir: Path) -> dict[str, list[tuple[str, float]]]:
    dup_map: dict[str, list[tuple[str, float]]] = {}
    for entry in _read_jsonl(topic_dir / "possible_duplicates.jsonl"):
        a, b, sim = entry["record_id_a"], entry["record_id_b"], entry["similarity"]
        dup_map.setdefault(a, []).append((b, sim))
        dup_map.setdefault(b, []).append((a, sim))
    for pairs in dup_map.values():
        pairs.sort(key=lambda p: -p[1])
    return dup_map


def load_suggestions(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    return {entry["record_id"]: entry for entry in _read_jsonl(path)}


def select_candidates(records: list[dict], latest: dict[tuple[str, str], dict], stage: str) -> list[dict]:
    if stage == "title_abstract":
        return [r for r in records if (r["record_id"], "title_abstract") not in latest]
    return [
        r for r in records
        if latest.get((r["record_id"], "title_abstract"), {}).get("decision") == "include"
        and (r["record_id"], "full_text") not in latest
    ]


def match_keywords(text: str, taxonomy: list[str]) -> list[str]:
    text_lower = text.lower()
    seen = []
    for term in taxonomy:
        if term and term.lower() in text_lower and term not in seen:
            seen.append(term)
    return seen


def truncate_abstract(abstract: str | None, limit: int = 500) -> str:
    if not abstract:
        return "(no abstract available)"
    if len(abstract) <= limit:
        return abstract
    cut = abstract[:limit].rsplit(" ", 1)[0]
    remaining_chars = len(abstract) - len(cut)
    return f"{cut}… [truncated, {remaining_chars} chars remaining]"


def _year_sort_key(row: dict) -> tuple[bool, int]:
    year = row.get("year")
    if year in (None, ""):
        return (True, 0)
    return (False, -int(year))


def sort_group(rows: list[dict]) -> list[dict]:
    """Sorts already-built row dicts (year is the string CSV column, "" or None-able)."""
    rows = sorted(rows, key=lambda r: (r.get("title") or "").casefold())
    rows = sorted(rows, key=_year_sort_key)
    return rows


def format_possible_duplicate(record_id: str, dup_map: dict[str, list[tuple[str, float]]]) -> str:
    pairs = dup_map.get(record_id, [])
    return "; ".join(f"{other_id} (similarity {sim:.2f})" for other_id, sim in pairs)


def build_row(record: dict, suggestions: dict[str, dict], taxonomy: list[str],
              dup_map: dict[str, list[tuple[str, float]]]) -> dict:
    record_id = record["record_id"]
    suggestion = suggestions.get(record_id)
    ai_suggestion = (suggestion or {}).get("ai_suggestion") or "none"
    ai_rationale = (suggestion or {}).get("ai_rationale") or "no eligibility criteria yet"
    title = record.get("title") or ""
    abstract = record.get("abstract") or ""
    return {
        "record_id": record_id,
        "decision": "",
        "reason": "",
        "ai_suggestion": ai_suggestion,
        "ai_rationale": ai_rationale,
        "ai_keywords": ", ".join(match_keywords(f"{title} {abstract}", taxonomy)),
        "title": title,
        "year": "" if record.get("year") is None else str(record["year"]),
        "authors": "; ".join(record.get("authors") or []),
        "source": record.get("source") or "",
        "doi": record.get("doi") or "",
        "url": record.get("url") or "",
        "abstract_truncated": truncate_abstract(abstract if abstract else None),
        "possible_duplicate": format_possible_duplicate(record_id, dup_map),
    }


def group_candidates(rows: list[dict], group_by: str) -> tuple[list[tuple[str, list[dict]]], str | None]:
    fallback_note = None

    if group_by == "source":
        keys = {r["source"] or "unknown" for r in rows}
        groups = {k: [] for k in keys}
        for r in rows:
            groups[r["source"] or "unknown"].append(r)
        ordered = sorted(groups.items())

    elif group_by == "year":
        keys = {r["year"] or "Year unknown" for r in rows}
        groups = {k: [] for k in keys}
        for r in rows:
            groups[r["year"] or "Year unknown"].append(r)
        ordered = sorted((k, v) for k, v in groups.items() if k != "Year unknown")
        if "Year unknown" in groups:
            ordered.append(("Year unknown", groups["Year unknown"]))

    elif group_by == "theme":
        if not any(r.get("theme") for r in rows):
            fallback_note = "no theme tags found on any candidate - showing a single ungrouped list"
            ordered = [("Ungrouped (no theme tags yet)", rows)]
        else:
            keys = {r.get("theme") or "Ungrouped (no theme tags yet)" for r in rows}
            groups = {k: [] for k in keys}
            for r in rows:
                groups[r.get("theme") or "Ungrouped (no theme tags yet)"].append(r)
            ordered = sorted((k, v) for k, v in groups.items() if k != "Ungrouped (no theme tags yet)")
            if "Ungrouped (no theme tags yet)" in groups:
                ordered.append(("Ungrouped (no theme tags yet)", groups["Ungrouped (no theme tags yet)"]))

    elif group_by == "ai_suggestion":
        groups = {k: [] for k in AI_SUGGESTION_GROUP_ORDER}
        for r in rows:
            groups[r["ai_suggestion"]].append(r)
        ordered = [(k, groups[k]) for k in AI_SUGGESTION_GROUP_ORDER if groups[k]]

    else:
        raise ValueError(f"unknown --group-by value: {group_by!r}")

    return [(name, sort_group(group_rows)) for name, group_rows in ordered], fallback_note


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, topic: str, stage: str, groups: list[tuple[str, list[dict]]],
                    group_by: str, fallback_note: str | None) -> None:
    total = sum(len(g) for _, g in groups)
    lines = [f"# {STAGE_TITLES[stage]} — {topic}", ""]
    if fallback_note:
        lines.append(f"{total} undecided records ({fallback_note}). Fill in exactly one checkbox "
                      "per record; add a REASON line for any full-text exclude.")
    else:
        lines.append(f"{total} undecided records, grouped by {group_by}. Fill in exactly one "
                      "checkbox per record; add a REASON line for any full-text exclude.")
    lines.append("")

    for group_name, group_rows in groups:
        lines.append(f"## Group: {group_name} ({len(group_rows)} records)")
        lines.append("")
        for row in group_rows:
            lines.append(f"#### {row['record_id']} — {row['title']} ({row['year']})")
            lines.append(f"- **Authors:** {row['authors']}")
            lines.append(f"- **Source:** {row['source']} | **DOI:** {row['doi']} | **Year:** {row['year']}")
            lines.append(f"- **Link:** {row['url']}")
            if row["possible_duplicate"]:
                lines.append(f"- **Possible duplicate of:** {row['possible_duplicate']} "
                              "— *only shown when flagged; advisory, does not affect screening*")
            lines.append(f"- **AI suggestion:** {row['ai_suggestion']} — {row['ai_rationale']}")
            if row["ai_keywords"]:
                lines.append(f"- **Keywords:** {row['ai_keywords']}")
            lines.append(f"- **Abstract (truncated to 500 chars):** {row['abstract_truncated']}")
            lines.append("")
            lines.append("- [ ] Include")
            lines.append("- [ ] Exclude")
            lines.append("REASON:")
            lines.append("")
            lines.append("---")
            lines.append("")

    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def print_summary(topic: str, stage: str, groups: list[tuple[str, list[dict]]], group_by: str,
                   fallback_note: str | None, taxonomy: list[str],
                   csv_path: Path, md_path: Path) -> None:
    all_rows = [r for _, g in groups for r in g]
    total = len(all_rows)

    print(f"Exported {total} undecided {stage} records for {topic}", end="")
    if fallback_note:
        print(f" ({fallback_note}):")
    else:
        print(f", grouped by {group_by}:")
    for name, group_rows in groups:
        print(f"  {name}: {len(group_rows)}")
    print()

    counts = {k: 0 for k in AI_SUGGESTION_GROUP_ORDER}
    for r in all_rows:
        counts[r["ai_suggestion"]] += 1
    print("AI suggestion breakdown: " + ", ".join(f"{k} {counts[k]}" for k in AI_SUGGESTION_GROUP_ORDER))
    print()

    if taxonomy:
        term_counts: dict[str, int] = {t: 0 for t in taxonomy}
        for r in all_rows:
            for term in (r["ai_keywords"].split(", ") if r["ai_keywords"] else []):
                term_counts[term] += 1
        top = sorted(term_counts.items(), key=lambda kv: -kv[1])[:10]
        top = [(t, c) for t, c in top if c > 0]
        if top:
            print(f"Corpus keyword overview (top matches across these {total} records):")
            print("  " + ", ".join(f"{t}: {c}" for t, c in top))
            print()

    print("Files:")
    print(f"  {csv_path}  (preferred - edit this one)")
    print(f"  {md_path}")
    print()
    print(f"Edit the decision/reason columns (or checkboxes in the .md), then run "
          f"`/litreview-screen import --stage {stage}`. Full-text excludes will need a reason.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic-dir", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=["title_abstract", "full_text"])
    parser.add_argument("--group-by", default="source", choices=["source", "year", "theme", "ai_suggestion"])
    parser.add_argument("--suggestions", type=Path, default=None)
    parser.add_argument("--taxonomy", default=None, help="comma-separated keyword taxonomy terms")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    topic_dir: Path = args.topic_dir
    if not (topic_dir / "records.jsonl").exists():
        print(f"Error: {topic_dir / 'records.jsonl'} not found", file=sys.stderr)
        return 1

    try:
        records = load_records(topic_dir)
        latest = load_latest_decisions(topic_dir)
        dup_map = load_possible_duplicates(topic_dir)
        suggestions = load_suggestions(args.suggestions)
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"Error: malformed input data - {exc}", file=sys.stderr)
        return 1

    taxonomy = [t.strip() for t in args.taxonomy.split(",")] if args.taxonomy else []
    taxonomy = [t for t in taxonomy if t]

    candidates = select_candidates(records, latest, args.stage)
    if not candidates:
        print(f"0 undecided {args.stage} records for {topic_dir.name} - nothing to export")
        return 0

    rows = [build_row(r, suggestions, taxonomy, dup_map) for r in candidates]
    groups, fallback_note = group_candidates(rows, args.group_by)

    out_dir = args.out_dir or (topic_dir / "screening")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{args.stage}_sheet.csv"
    md_path = out_dir / f"{args.stage}_sheet.md"

    ordered_rows = [r for _, g in groups for r in g]
    write_csv(csv_path, ordered_rows)
    write_markdown(md_path, topic_dir.name, args.stage, groups, args.group_by, fallback_note)
    print_summary(topic_dir.name, args.stage, groups, args.group_by, fallback_note, taxonomy, csv_path, md_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
