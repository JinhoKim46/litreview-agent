#!/usr/bin/env python3
"""Evaluate methods/_routing.json against a set of routing answers.

docs/PLAN.md M2 / references/docs/design/multi-method-consensus.md §2.2: a
versioned decision table decides which method manifest a review should use.
First matching row wins. This module only evaluates the table -- it never
reads the filesystem for facts like "does a completed base review exist"
(`base_exists`) or "is this manifest actually shipped"
(`tools.method.list_manifests()`); callers supply those, which keeps this a
pure, easily-unit-tested function (one test per row, per docs/PLAN.md M2's
exit criterion).

A row that resolves to a method with no shipped methods/<id>.json manifest
yet (checked dynamically, never a hardcoded set -- M3/M4 add manifests
without touching this file) is converted into a refusal instead: "no stub
manifests for later methods, routing refusals instead" (docs/PLAN.md
dissent log). Today that means only "systematic_review" ever resolves;
every other target (reconnaissance, scoping_review, systematic_mapping_study,
...) refuses honestly until its milestone ships the manifest.

Usage:
    python3 tools/route.py --answers-json <path>   # print the routing decision as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.method import list_manifests  # noqa: E402

ROUTING_TABLE_PATH = ROOT / "methods" / "_routing.json"

# Method ids the routing table can resolve to but that have no shipped
# manifest as of M2 -- used only for the refusal pointer text, never to
# gate resolution (that gate is always the live list_manifests() result).
ROADMAP_POINTER = "docs/ROADMAP.md's method taxonomy table"


class RouteError(ValueError):
    """The routing table is malformed, or `decide()` was called with
    answers no row (including no fallback) matches -- never silently
    resolved to some default method."""


def load_routing_table() -> dict:
    if not ROUTING_TABLE_PATH.exists():
        raise RouteError(f"{ROUTING_TABLE_PATH} not found")
    try:
        return json.loads(ROUTING_TABLE_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise RouteError(f"{ROUTING_TABLE_PATH}: invalid JSON: {exc}") from exc


def _get(context: dict, dotted_key: str):
    cur = context
    for part in dotted_key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _match(cond: dict, context: dict) -> bool:
    if "all" in cond:
        return all(_match(c, context) for c in cond["all"])
    if "any" in cond:
        return any(_match(c, context) for c in cond["any"])
    if len(cond) != 1:
        raise RouteError(f"malformed condition (expected one field): {cond!r}")
    (field, spec), = cond.items()
    value = _get(context, field)
    if "eq" in spec:
        return value == spec["eq"]
    if "in" in spec:
        return value in spec["in"]
    if "contains" in spec:
        return isinstance(value, (list, tuple, set)) and spec["contains"] in value
    if "intersects" in spec:
        return isinstance(value, (list, tuple, set)) and bool(set(value) & set(spec["intersects"]))
    raise RouteError(f"unknown condition operator: {spec!r}")


def _base_result() -> dict:
    return {
        "kind": None,
        "method_id": None,
        "synthesis_family": None,
        "profile_flags": [],
        "modes": [],
        "output_profiles": [],
        "reason": None,
        "pointer": None,
        "offer": [],
        "never": [],
        "explain": None,
        "note": None,
        "question": None,
        "matched_row": None,
    }


def _apply_row(row: dict, answers: dict) -> dict:
    then = row["then"]
    result = _base_result()
    result["matched_row"] = row["id"]
    kind = then["kind"]

    if kind == "resolve":
        result["kind"] = "resolve"
        result["method_id"] = then["method_id"]
        result["synthesis_family"] = then.get("synthesis_family")
        result["explain"] = then.get("explain")
        result["note"] = then.get("note")
        goal = answers.get("goal") or []
        for goal_term, profile_name in then.get("output_profiles_from_goal", {}).items():
            if goal_term in goal:
                result["output_profiles"].append(profile_name)

    elif kind == "refuse":
        result["kind"] = "refuse"
        result["reason"] = then["reason"]
        result["pointer"] = then.get("pointer")
        result["offer"] = list(then.get("offer", []))
        result["never"] = list(then.get("never", []))
        result["explain"] = then.get("explain")

    elif kind == "living_or_ask":
        base_exists = bool(answers.get(then["base_exists_key"], False))
        if base_exists:
            base_method_id = answers.get("base_method_id")
            if not base_method_id:
                raise RouteError(
                    "goal includes 'update' and base_exists is True but answers['base_method_id'] is missing"
                )
            result["kind"] = "resolve"
            result["method_id"] = base_method_id
            result["modes"] = ["living"]
        else:
            result["kind"] = "ask"
            result["question"] = then["ask"]

    else:
        raise RouteError(f"unknown row 'then.kind': {kind!r}")

    return result


def _gate_against_shipped(result: dict, shipped_method_ids: set[str]) -> dict:
    """Convert a 'resolve' whose method has no shipped manifest into a
    refusal. Never applied to 'living_or_ask' resolutions -- a living base's
    method_id is, by definition, already a completed review's shipped method."""
    if result["kind"] != "resolve" or result["method_id"] in shipped_method_ids:
        return result
    unshipped = _base_result()
    unshipped["matched_row"] = result["matched_row"]
    unshipped["kind"] = "refuse"
    unshipped["reason"] = f"{result['method_id']} has no shipped manifest yet"
    unshipped["pointer"] = ROADMAP_POINTER
    return unshipped


def _apply_profile_offers(table: dict, answers: dict, result: dict) -> dict:
    if result["kind"] != "resolve":
        return result
    for rule in table.get("profile_offers", {}).get("rules", []):
        context = {**answers, "result": result}
        if not _match(rule["when"], context):
            continue
        then = rule["then"]
        if then["kind"] == "override":
            result = dict(result)
            result["method_id"] = then["method_id"]
            result["explain"] = then["explain"]
            result["never"] = ["_overridden_by_" + rule["id"]]
        elif then["kind"] == "offer_profile":
            if then["profile"] not in result["profile_flags"]:
                result["profile_flags"].append(then["profile"])
    return result


def _apply_appraisal_intent_note(table: dict, answers: dict, result: dict) -> dict:
    note_rule = table.get("appraisal_intent_note")
    if not note_rule or result["kind"] != "resolve":
        return result
    context = {**answers, "result": result}
    if _match(note_rule["when"], context):
        result["explain"] = note_rule["then"]["explain_template"].format(method=result["method_id"])
    return result


def decide(answers: dict, *, shipped_method_ids: set[str] | None = None) -> dict:
    """Evaluate the routing table against `answers` and return a result dict:
    {kind: resolve|refuse|ask, method_id, synthesis_family, profile_flags[],
    modes[], output_profiles[], reason, pointer, offer[], never[], explain,
    note, question, matched_row}.

    `shipped_method_ids` defaults to tools.method.list_manifests()'s live
    result -- pass an explicit set only in tests that want to exercise a
    hypothetical future roster without shipping real manifest files."""
    table = load_routing_table()
    if shipped_method_ids is None:
        shipped_method_ids = set(list_manifests())

    for row in table["rows"]:
        if _match(row["when"], answers):
            result = _apply_row(row, answers)
            break
    else:
        raise RouteError(f"no routing row matched answers: {answers!r}")

    result = _gate_against_shipped(result, shipped_method_ids)
    result = _apply_profile_offers(table, answers, result)
    result = _apply_appraisal_intent_note(table, answers, result)
    return result


def resolve_pack(answers: dict, claude_local_pack: str | None = None) -> str:
    """R9: pack resolution. Explicit answers['pack'] wins, then a default
    supplied from CLAUDE.local.md's field-of-research/target-venue (the
    caller's job to derive), then "generic"."""
    return answers.get("pack") or claude_local_pack or "generic"


def record_override(routing_result: dict, chosen_id: str | None, override_reason: str | None) -> dict:
    """R10: user override. Returns the protocol.json.method.routing shape's
    {recommended_id, chosen_id, override_reason} -- the label is still
    computed from recorded conduct regardless of which id is chosen."""
    recommended_id = routing_result.get("method_id")
    return {
        "recommended_id": recommended_id,
        "chosen_id": chosen_id or recommended_id,
        "override_reason": override_reason if (chosen_id and chosen_id != recommended_id) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers-json", required=True, help="path to a JSON file of routing answers")
    args = parser.parse_args(argv)

    try:
        answers = json.loads(Path(args.answers_json).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read --answers-json: {exc}", file=sys.stderr)
        return 1

    try:
        result = decide(answers)
    except RouteError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
