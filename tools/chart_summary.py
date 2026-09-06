#!/usr/bin/env python3
"""Descriptive-synthesis engine (docs/PLAN.md M3 §3.1 S7) for a scoping
review's charted studies or a systematic mapping study's classified studies
-- the `synthesis_family: "descriptive"` counterpart to
synthesis/run_synthesis.py's pairwise_iv pooling pipeline. Never pools
anything (methods/scoping_review.json and methods/systematic_mapping_study
.json both set `synthesis.families_allowed: ["descriptive"]`, forbidding
pooling by design) -- this only tabulates category frequencies per
field/facet and, for a classification table, pairwise cross-tabulations
rendered as Petersen et al. 2015-style bubble plots (synthesis/plots.py's
bubble_plot(), one SVG per cross-tab, written alongside
descriptive_summary.json).

Refuses cleanly rather than fabricate a summary over incomplete or
corrupted data: the source table must be frozen (a charting form or
classification scheme still being piloted/keyworded has no fixed set of
categories to tabulate yet), and every row must still match the frozen
fields/facets (tools/charting_gate.verify_table() /
tools/classification_gate.verify_table() -- the same post-hoc drift check
those modules use to gate the report build).

Usage:
    python3 tools/chart_summary.py --topic <slug>
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.method import MethodError, resolve as resolve_method  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


class ChartSummaryError(ValueError):
    """The source table isn't ready for descriptive synthesis yet (not
    frozen, or drifted from its frozen fields/facets), or this topic's
    method doesn't use the descriptive synthesis family at all -- never
    silently tabulated anyway."""


def _stringify(value) -> str:
    """JSON object keys must be strings; None becomes an explicit
    "not reported" bucket rather than a crash or a silently dropped count --
    a study that didn't get a value for a field is still a fact worth
    counting, not evidence to discard."""
    if value is None:
        return "not reported"
    return str(value)


def _slugify(name: str) -> str:
    """Facet name -> filesystem-safe token for a bubble-plot SVG filename
    (e.g. "research type" -> "research_type"). Not a general-purpose slug --
    only handles what a facet name (a short, human-chosen field name) can
    contain; anything else collapses to "_". Two facet names differing only
    in punctuation (e.g. "data source" and "data-source") collapse to the
    same slug and would overwrite each other's SVG -- no shipped manifest
    has such a pair, and worth a real fix only if one ever does."""
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower())


def _values_for(raw) -> list[str]:
    """A field/facet value may be a scalar or a list (a multi-valued
    facet) -- normalize to a list of strings either way so frequency
    counting treats both shapes identically."""
    if isinstance(raw, list):
        return [_stringify(v) for v in raw] or ["not reported"]
    return [_stringify(raw)]


def compute_frequencies(studies: list[dict], key_field: str, names: list[str]) -> dict[str, dict[str, int]]:
    """{name: {value: count}} across `studies`, reading each study's
    `key_field` dict (charting's "data" or classification's "codes"). A
    multi-valued value contributes one count per element, not one count for
    the whole list -- matching how a bubble plot / frequency table over a
    multi-valued facet is normally read."""
    frequencies = {name: {} for name in names}
    for study in studies:
        record = study.get(key_field, {})
        for name in names:
            for value in _values_for(record.get(name)):
                frequencies[name][value] = frequencies[name].get(value, 0) + 1
    return frequencies


def compute_cross_tabs(studies: list[dict], key_field: str, names: list[str]) -> list[dict]:
    """Pairwise cross-tabulation between every two distinct facets in
    `names` -- the data a bubble plot renders (bubble size = count per
    (value_a, value_b) cell). Returns a list of {"facet_a", "facet_b",
    "counts"} in the order `names` is given (each unordered pair once)."""
    cross_tabs = []
    for facet_a, facet_b in itertools.combinations(names, 2):
        counts: dict[str, int] = {}
        for study in studies:
            record = study.get(key_field, {})
            values_a = _values_for(record.get(facet_a))
            values_b = _values_for(record.get(facet_b))
            for va, vb in itertools.product(values_a, values_b):
                key = f"{va}|{vb}"
                counts[key] = counts.get(key, 0) + 1
        cross_tabs.append({"facet_a": facet_a, "facet_b": facet_b, "counts": counts})
    return cross_tabs


def run(topic: str, *, topic_dir=None) -> dict:
    """Resolves this topic's capture mode, loads its charting or
    classification table, and returns {"framework_version", "topic",
    "capture_mode", "n_studies", "category_frequencies", "cross_tabs"}.
    Also writes results/<topic>/synthesis/descriptive_summary.json."""
    topic_dir = Path(topic_dir) if topic_dir is not None else safe_topic_path(topic)

    resolved = resolve_method(topic)
    capture_mode = resolved["manifest"]["capture"]["mode"]

    if capture_mode == "charting":
        from tools.charting_gate import load_charting_table, verify_table

        table = load_charting_table(topic_dir, topic)
        frozen = bool(table.get("charting_form_frozen"))
        names = table.get("fields", [])
        key_field = "data"
        not_frozen_reason = (
            "the charting form has not been frozen yet -- pilot and freeze it "
            "(.claude/skills/evidence-mapping/SKILL.md) before running descriptive synthesis."
        )
    elif capture_mode == "classification":
        from tools.classification_gate import load_classification_table, verify_table

        table = load_classification_table(topic_dir, topic)
        frozen = bool(table.get("scheme_frozen"))
        names = [f["name"] for f in table.get("facets", [])]
        key_field = "codes"
        not_frozen_reason = (
            "the classification scheme has not been frozen yet -- keyword a sample and freeze it "
            "(.claude/skills/study-classification/SKILL.md) before running descriptive synthesis."
        )
    else:
        raise ChartSummaryError(
            f"capture_mode {capture_mode!r} does not use descriptive synthesis -- this topic's method "
            "resolves to a different capture stage (see tools/method.py)."
        )

    if not frozen:
        raise ChartSummaryError(not_frozen_reason)

    offending = verify_table(table)
    if offending:
        raise ChartSummaryError(
            f"{len(offending)} row(s) no longer match the frozen fields/facets, so descriptive synthesis "
            f"would tabulate corrupted data: {', '.join(offending[:10])}. Fix or re-code these rows first."
        )

    studies = table.get("studies", [])
    category_frequencies = compute_frequencies(studies, key_field, names)
    cross_tabs = compute_cross_tabs(studies, key_field, names) if capture_mode == "classification" else []

    out_dir = topic_dir / "synthesis"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Petersen et al. 2015's bubble plots: one per cross-tab, classification
    # (systematic mapping study) only -- a scoping review's cross_tabs is
    # always [] (charting has no cross-tab data at all, see compute_cross_tabs'
    # own docstring), so this loop is simply a no-op there.
    for cross_tab in cross_tabs:
        if not cross_tab["counts"]:
            cross_tab["bubble_plot_svg"] = None
            continue
        from synthesis.plots import bubble_plot

        svg_path = out_dir / f"bubble_{_slugify(cross_tab['facet_a'])}_x_{_slugify(cross_tab['facet_b'])}.svg"
        bubble_plot(cross_tab, str(svg_path))
        cross_tab["bubble_plot_svg"] = str(svg_path)

    result = {
        "framework_version": "1.0.0",
        "topic": topic,
        "capture_mode": capture_mode,
        "n_studies": len(studies),
        "category_frequencies": category_frequencies,
        "cross_tabs": cross_tabs,
    }

    (out_dir / "descriptive_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        result = run(args.topic, topic_dir=topic_dir)
    except (MethodError, ChartSummaryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    n_facets = len(result["category_frequencies"])
    print(
        f"capture_mode={result['capture_mode']}. {result['n_studies']} studies tabulated across {n_facets} "
        f"field(s)/facet(s), {len(result['cross_tabs'])} cross-tab(s). Wrote "
        f"{topic_dir}/synthesis/descriptive_summary.json"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
