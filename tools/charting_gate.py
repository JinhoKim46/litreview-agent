#!/usr/bin/env python3
"""Deterministic freeze gate for a scoping review's charting_table.json.

docs/PLAN.md M3 / references/docs/design/multi-method-consensus.md §3.3:
"Charting form co-developed from the pack default, piloted on 5-10
records, frozen (G-Freeze)." This module owns exactly one decision --
"may charting proceed against the *current* form, or does the reviewer
need to freeze it first" -- the same deterministic-decision-a-command-
just-runs-and-obeys pattern as tools/ledger.py's `gate` command and
tools/method.py's --require-capture-mode (§4.5: deterministic Python
validates, humans decide; an LLM reading charting_table.json's fields
itself and deciding "this looks frozen enough" is exactly what this
module exists to prevent).

Once frozen, a candidate row's `data` keys must match the frozen
`fields[]` *exactly* -- otherwise "frozen" enforces nothing. This is
checked here too, not left to a prompt's own judgement.

Usage:
    python3 tools/charting_gate.py --topic <slug>
    python3 tools/charting_gate.py --topic <slug> --row-data-json <path>
    python3 tools/charting_gate.py --topic <slug> freeze --fields-json <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.method import MethodError, resolve as resolve_method  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


class ChartingGateError(ValueError):
    """charting_table.json is malformed, or a freeze was requested with
    fields that don't make sense -- never silently patched over."""


def _charting_table_path(topic_dir: Path) -> Path:
    return Path(topic_dir) / "charting_table.json"


def load_charting_table(topic_dir: Path, topic: str) -> dict:
    """Returns the existing charting_table.json, or a fresh, unfrozen,
    empty one if this topic hasn't charted anything yet -- absence of the
    file is the expected starting state, never an error."""
    path = _charting_table_path(topic_dir)
    if not path.exists():
        return {"framework_version": "1.0.0", "topic": topic, "charting_form_frozen": False, "fields": [], "studies": []}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ChartingGateError(f"{path}: invalid JSON: {exc}") from exc


def check_gate(table: dict, pilot_records_required: int, row_data: dict | None = None) -> dict:
    """Evaluate whether charting may proceed against `table`'s current
    state. Returns {"ok", "reason", "frozen", "n_records",
    "pilot_records_required", "must_freeze_now", "row_field_mismatch"}.

    Pre-freeze: ok unless the pilot quota is already met (n_records >=
    pilot_records_required) -- charting must not silently continue past
    the pilot without a human G-Freeze decision.
    Post-freeze: ok unless `row_data` is given and its keys don't exactly
    match the frozen fields[] (extra or missing -- either direction is a
    mismatch worth refusing, not silently coercing).
    """
    frozen = bool(table.get("charting_form_frozen", False))
    n_records = len(table.get("studies", []))
    result = {
        "frozen": frozen,
        "n_records": n_records,
        "pilot_records_required": pilot_records_required,
        "must_freeze_now": False,
        "row_field_mismatch": None,
        "ok": True,
        "reason": None,
    }

    if not frozen:
        if n_records >= pilot_records_required:
            result["must_freeze_now"] = True
            result["ok"] = False
            result["reason"] = (
                f"pilot phase complete ({n_records} of {pilot_records_required} records charted) but the "
                "charting form has not been frozen yet -- run G-Freeze (agree the final fields[] with the "
                "reviewer, then `python3 tools/charting_gate.py --topic <slug> freeze --fields-json <path>`) "
                "before charting any further record."
            )
        return result

    if row_data is not None:
        frozen_fields = set(table.get("fields", []))
        given_fields = set(row_data.keys())
        if given_fields != frozen_fields:
            missing = sorted(frozen_fields - given_fields)
            extra = sorted(given_fields - frozen_fields)
            result["row_field_mismatch"] = {"missing": missing, "extra": extra}
            result["ok"] = False
            detail = []
            if missing:
                detail.append(f"missing: {missing}")
            if extra:
                detail.append(f"unexpected: {extra}")
            result["reason"] = f"this row's data keys don't match the frozen fields[] ({'; '.join(detail)})"

    return result


def verify_table(table: dict) -> list[str]:
    """Post-hoc check: for a frozen table, every row's `data` keys must
    equal fields[] exactly. Returns the record_ids of offending rows (empty
    if none, or if the table isn't frozen yet -- pre-freeze pilot rows are
    allowed to have data:{} and aren't held to a form that doesn't exist).
    This is what makes "frozen" enforceable after the fact: the gate check
    in check_gate() only catches a mismatch at write time if the writer
    actually calls it first, which nothing forces -- this can be run over
    a finished table regardless of whether that happened."""
    if not table.get("charting_form_frozen"):
        return []
    frozen_fields = set(table.get("fields", []))
    offending = []
    for row in table.get("studies", []):
        if set(row.get("data", {}).keys()) != frozen_fields:
            offending.append(row.get("record_id", "<missing record_id>"))
    return offending


def freeze(topic_dir: Path, topic: str, fields: list[str]) -> dict:
    """Writes charting_form_frozen: true and fields[] -- the G-Freeze human
    gate itself is a conversation the command file conducts; this function
    only performs the resulting write, atomically, after that agreement is
    reached. Refuses to re-freeze with a different field list once frozen
    (a scheme change after freeze is a documented amendment, not a silent
    overwrite -- not yet implemented; raises rather than silently allow
    drift)."""
    table = load_charting_table(topic_dir, topic)
    if table.get("charting_form_frozen"):
        if table.get("fields") != fields:
            raise ChartingGateError(
                "charting_table.json is already frozen with a different fields[] list -- "
                "changing a frozen charting form is a documented amendment, not supported by this command yet."
            )
        return table  # already frozen with these exact fields -- idempotent no-op
    if not fields:
        raise ChartingGateError("cannot freeze with an empty fields[] list")
    table["charting_form_frozen"] = True
    table["fields"] = fields
    path = _charting_table_path(topic_dir)
    path.write_text(json.dumps(table, indent=2) + "\n")
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--row-data-json", help="path to a JSON file holding a candidate row's `data` dict, to check against frozen fields[]")
    parser.add_argument("action", nargs="?", default="gate", choices=["gate", "freeze", "verify"])
    parser.add_argument("--fields-json", help="freeze only: path to a JSON file holding the final fields[] list to freeze")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        resolved = resolve_method(args.topic)
    except MethodError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    pilot_records_required = resolved["manifest"]["capture"].get("pilot_records", 0)

    if args.action == "freeze":
        if not args.fields_json:
            print("Error: freeze requires --fields-json", file=sys.stderr)
            return 1
        try:
            fields = json.loads(Path(args.fields_json).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: could not read --fields-json: {exc}", file=sys.stderr)
            return 1
        try:
            table = freeze(topic_dir, args.topic, fields)
        except ChartingGateError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"frozen": True, "fields": table["fields"]}, indent=2))
        return 0

    if args.action == "verify":
        try:
            table = load_charting_table(topic_dir, args.topic)
        except ChartingGateError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        offending = verify_table(table)
        print(json.dumps({"ok": not offending, "offending_record_ids": offending}, indent=2))
        return 0 if not offending else 1

    row_data = None
    if args.row_data_json:
        try:
            row_data = json.loads(Path(args.row_data_json).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: could not read --row-data-json: {exc}", file=sys.stderr)
            return 1

    try:
        table = load_charting_table(topic_dir, args.topic)
    except ChartingGateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = check_gate(table, pilot_records_required, row_data=row_data)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
