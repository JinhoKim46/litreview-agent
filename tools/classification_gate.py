#!/usr/bin/env python3
"""Deterministic freeze gate for a systematic mapping study's
classification_table.json.

docs/PLAN.md M3 exit criterion: "a mapping study's coding is blocked until
its scheme is frozen." Mirrors tools/charting_gate.py's decision shape for
the classification capture mode (methods/systematic_mapping_study.json,
schemas/classification_table.schema.json): a scheme (facets[]) is built by
keywording a sample outside this table entirely (no numeric pilot quota --
`capture.pilot_records` is 0 for this method, unlike charting's 8), then
frozen (G-Freeze), then every study is coded against the frozen facets[].
A candidate row's `codes` keys must match the frozen facets[] names exactly
once frozen -- checked here, not left to a prompt's own judgement.

Calibration (inter-rater or delayed intra-rater re-code) is recorded but
never gates coding -- schemas/classification_table.schema.json's own
description: "disclosed, not gated." record_calibration() just performs the
write once the reviewer/skill has actually run the re-code.

Usage:
    python3 tools/classification_gate.py --topic <slug>
    python3 tools/classification_gate.py --topic <slug> --row-codes-json <path>
    python3 tools/classification_gate.py --topic <slug> freeze --facets-json <path>
    python3 tools/classification_gate.py --topic <slug> verify
    python3 tools/classification_gate.py --topic <slug> record-calibration --calibration-json <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


class ClassificationGateError(ValueError):
    """classification_table.json is malformed, or a freeze/calibration write
    was requested with data that doesn't make sense -- never silently
    patched over."""


def _classification_table_path(topic_dir: Path) -> Path:
    return Path(topic_dir) / "classification_table.json"


def load_classification_table(topic_dir: Path, topic: str) -> dict:
    """Returns the existing classification_table.json, or a fresh, unfrozen,
    empty one if this topic hasn't classified anything yet -- absence of the
    file is the expected starting state, never an error."""
    path = _classification_table_path(topic_dir)
    if not path.exists():
        return {
            "framework_version": "1.0.0",
            "topic": topic,
            "scheme_frozen": False,
            "facets": [],
            "calibration": None,
            "studies": [],
        }
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ClassificationGateError(f"{path}: invalid JSON: {exc}") from exc


def check_gate(table: dict, row_codes: dict | None = None) -> dict:
    """Evaluate whether coding may proceed against `table`'s current state.
    Returns {"ok", "reason", "scheme_frozen", "n_studies",
    "row_facet_mismatch"}.

    Pre-freeze: checking bare state is always ok (keywording a sample
    happens outside this table); attempting to write a coded row is refused
    -- bulk coding is blocked until the scheme is frozen, the M3 exit
    criterion this module exists to enforce.
    Post-freeze: ok unless `row_codes` is given and its keys don't exactly
    match the frozen facets[] names (extra or missing -- either direction is
    a mismatch worth refusing, not silently coercing)."""
    frozen = bool(table.get("scheme_frozen", False))
    result = {
        "scheme_frozen": frozen,
        "n_studies": len(table.get("studies", [])),
        "row_facet_mismatch": None,
        "ok": True,
        "reason": None,
    }

    if not frozen:
        if row_codes is not None:
            result["ok"] = False
            result["reason"] = (
                "the classification scheme has not been frozen yet -- build facets[] by keywording a sample "
                "with the reviewer, agree the final list, then `python3 tools/classification_gate.py --topic "
                "<slug> freeze --facets-json <path>` before coding any study."
            )
        return result

    if row_codes is not None:
        frozen_facets = {f["name"] for f in table.get("facets", [])}
        given_facets = set(row_codes.keys())
        if given_facets != frozen_facets:
            missing = sorted(frozen_facets - given_facets)
            extra = sorted(given_facets - frozen_facets)
            result["row_facet_mismatch"] = {"missing": missing, "extra": extra}
            result["ok"] = False
            detail = []
            if missing:
                detail.append(f"missing: {missing}")
            if extra:
                detail.append(f"unexpected: {extra}")
            result["reason"] = f"this row's codes keys don't match the frozen facets[] ({'; '.join(detail)})"

    return result


def verify_table(table: dict) -> list[str]:
    """Post-hoc check: for a frozen table, every row's `codes` keys must
    equal the frozen facets[] names exactly. Returns the record_ids of
    offending rows (empty if none, or if the table isn't frozen yet). The
    write-time check in check_gate() only catches a mismatch if the writer
    calls it first -- this can be run over a finished table regardless of
    whether that happened, mirroring tools/charting_gate.py's verify_table()."""
    if not table.get("scheme_frozen"):
        return []
    frozen_facets = {f["name"] for f in table.get("facets", [])}
    offending = []
    for row in table.get("studies", []):
        if set(row.get("codes", {}).keys()) != frozen_facets:
            offending.append(row.get("record_id", "<missing record_id>"))
    return offending


def freeze(topic_dir: Path, topic: str, facets: list[dict]) -> dict:
    """Writes scheme_frozen: true and facets[] -- the G-Freeze human gate
    itself is a conversation the command file conducts; this function only
    performs the resulting write, atomically, after that agreement is
    reached. Refuses to re-freeze with a different facets list once frozen
    (a scheme change after freeze is a documented amendment, not a silent
    overwrite -- not yet implemented; raises rather than silently allow
    drift)."""
    table = load_classification_table(topic_dir, topic)
    if table.get("scheme_frozen"):
        if table.get("facets") != facets:
            raise ClassificationGateError(
                "classification_table.json is already frozen with a different facets[] list -- "
                "changing a frozen classification scheme is a documented amendment, not supported by this command yet."
            )
        return table  # already frozen with these exact facets -- idempotent no-op
    if not facets:
        raise ClassificationGateError("cannot freeze with an empty facets[] list")
    table["scheme_frozen"] = True
    table["facets"] = facets
    path = _classification_table_path(topic_dir)
    path.write_text(json.dumps(table, indent=2) + "\n")
    return table


def record_calibration(topic_dir: Path, topic: str, calibration: dict) -> dict:
    """Writes the `calibration` block once a re-code has actually run.
    Never gates coding either direction -- schemas/classification_table
    .schema.json's own description: "disclosed, not gated." Requires the
    scheme to already be frozen (calibration re-codes frozen-scheme
    decisions; there is nothing to re-code against before that)."""
    table = load_classification_table(topic_dir, topic)
    if not table.get("scheme_frozen"):
        raise ClassificationGateError("cannot record calibration before the classification scheme is frozen")
    if calibration.get("mode") not in ("inter_rater", "intra_rater_delayed"):
        raise ClassificationGateError(f"calibration.mode must be 'inter_rater' or 'intra_rater_delayed', got {calibration.get('mode')!r}")
    table["calibration"] = calibration
    path = _classification_table_path(topic_dir)
    path.write_text(json.dumps(table, indent=2) + "\n")
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--row-codes-json", help="path to a JSON file holding a candidate row's `codes` dict, to check against frozen facets[]")
    parser.add_argument("action", nargs="?", default="gate", choices=["gate", "freeze", "verify", "record-calibration"])
    parser.add_argument("--facets-json", help="freeze only: path to a JSON file holding the final facets[] list to freeze")
    parser.add_argument("--calibration-json", help="record-calibration only: path to a JSON file holding the calibration block to record")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.action == "freeze":
        if not args.facets_json:
            print("Error: freeze requires --facets-json", file=sys.stderr)
            return 1
        try:
            facets = json.loads(Path(args.facets_json).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: could not read --facets-json: {exc}", file=sys.stderr)
            return 1
        try:
            table = freeze(topic_dir, args.topic, facets)
        except ClassificationGateError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"scheme_frozen": True, "facets": table["facets"]}, indent=2))
        return 0

    if args.action == "record-calibration":
        if not args.calibration_json:
            print("Error: record-calibration requires --calibration-json", file=sys.stderr)
            return 1
        try:
            calibration = json.loads(Path(args.calibration_json).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: could not read --calibration-json: {exc}", file=sys.stderr)
            return 1
        try:
            table = record_calibration(topic_dir, args.topic, calibration)
        except ClassificationGateError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"calibration": table["calibration"]}, indent=2))
        return 0

    if args.action == "verify":
        try:
            table = load_classification_table(topic_dir, args.topic)
        except ClassificationGateError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        offending = verify_table(table)
        print(json.dumps({"ok": not offending, "offending_record_ids": offending}, indent=2))
        return 0 if not offending else 1

    row_codes = None
    if args.row_codes_json:
        try:
            row_codes = json.loads(Path(args.row_codes_json).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: could not read --row-codes-json: {exc}", file=sys.stderr)
            return 1

    try:
        table = load_classification_table(topic_dir, args.topic)
    except ClassificationGateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = check_gate(table, row_codes=row_codes)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
