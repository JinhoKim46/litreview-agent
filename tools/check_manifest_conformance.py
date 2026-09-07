#!/usr/bin/env python3
"""Manifest/code conformance guard: catches a pack or method manifest that
declares a capability the executable pipeline never actually reads.

references/docs/panel_discussion/merge-01.md item #2 (panel-discussion round
1, generalized in round 3): at least 7 independent instances were found of a
pack/manifest declaring an appraisal instrument, confidence framework, or
reporting-standard reference that no code path ever consults -- a capability
"asserted but undelivered." This check walks every pack's declared
`appraisal_instruments_by_design`/`confidence_framework` values and every
method manifest's `standards[].ref` entries, plus (the symmetric direction)
every routing-table field name, and fails the build if a declared value has
no real consumer anywhere in the implementing skill/command files.

This is a grep-based heuristic, not a real call graph: it confirms a
declared value's literal string appears somewhere in a plausible consuming
file, not that the reference is reached correctly (e.g. conditionally on the
right `method.id`). That is a known, disclosed limitation -- see
merge-01.md item #6 for an instance this check's own heuristic cannot fully
verify (whether a checklist reference is loaded *conditionally* on the
right method, not just present somewhere in the repo).

Known existing instances are pre-populated in KNOWN_UNCONSULTED_BASELINE so
this check is green today; each entry must carry a merge-01.md item number
as its tracking reference, and prints a loud (non-fatal) warning on every
run so the debt stays visible in CI logs. A *new*, un-baselined instance
fails the build (exit 1) -- the same discipline tools/security_guards.py
already uses for its own allowlists.

Run from anywhere: python3 tools/check_manifest_conformance.py
Stdlib only (plus jsonschema, already a requirement via tools/method.py).
Exit 0 on success (including baseline-only warnings), 1 with a failure list
otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.method import METHODS_DIR, NON_MANIFEST_FILES, NON_PACK_FILES, PACKS_DIR  # noqa: E402

# Files a declared value must appear in at least one of, to count as
# "consulted." Grep-based -- see module docstring's disclosed limitation.
APPRAISAL_CONSUMER_FILES = list((ROOT / ".claude" / "skills" / "quality-appraisal").glob("*.md"))
# Scoped to directories that could plausibly implement something -- never
# "**/*.md" from repo root, which would also walk results/ (per-review
# state, tens of MB of screening sheets across many topics) on every run.
STANDARDS_CONSUMER_GLOBS = [
    "*.md",
    ".claude/**/*.md",
    "docs/**/*.md",
    "tools/*.py",
]
ROUTING_FIELD_CONSUMER_FILE = ROOT / "methods" / "_routing.json"

# Each baseline entry's value is a mandatory tracking reference into
# references/docs/panel_discussion/merge-01.md -- never a bare True. A PR
# that adds a NEW declared-but-unconsulted instance must either wire it up
# or add an entry here in the same diff, exactly like
# tools/security_guards.py's ALLOWED_PERMISSIONS.
KNOWN_UNCONSULTED_BASELINE: dict[tuple, str] = {
    ("packs/clinical_interventions.json", "appraisal_instruments_by_design.rct", "rob2"):
        "merge-01.md item #3 -- RoB2 declared for RCTs, quality-appraisal skill implements RoB1 only",
    ("packs/clinical_interventions.json", "appraisal_instruments_by_design.cohort", "robins-i"):
        "merge-01.md item #3 -- ROBINS-I declared for cohort studies, NOS substituted instead",
    ("packs/clinical_interventions.json", "appraisal_instruments_by_design.qualitative", "casp"):
        "merge-01.md item #3 -- CASP declared for qualitative studies, never wired (falls to \"unsupported\")",
    ("packs/generic.json", "appraisal_instruments_by_design.cohort", "robins-i"):
        "merge-01.md item #3 -- ROBINS-I declared for cohort studies, NOS substituted instead",
    ("packs/generic.json", "appraisal_instruments_by_design.qualitative", "casp"):
        "merge-01.md item #3 -- CASP declared for qualitative studies, never wired (falls to \"unsupported\")",
    ("methods/scoping_review.json", "standards[].ref", "prisma-scr-2018-checklist.md"):
        "merge-01.md item #6 -- PRISMA-ScR checklist exists and is declared, never loaded by /litreview-report",
    ("_routing_field", "venue_default"):
        "merge-01.md item #5 -- venue_default read by R4a/R4b/R6d, set by zero shipped packs",
}


def _iter_packs() -> list[tuple[Path, dict]]:
    packs = []
    if not PACKS_DIR.exists():
        return packs
    for path in sorted(PACKS_DIR.glob("*.json")):
        if path.name in NON_PACK_FILES:
            continue
        packs.append((path, json.loads(path.read_text())))
    return packs


def _iter_manifests() -> list[tuple[Path, dict]]:
    manifests = []
    if not METHODS_DIR.exists():
        return manifests
    for path in sorted(METHODS_DIR.glob("*.json")):
        if path.name in NON_MANIFEST_FILES:
            continue
        manifests.append((path, json.loads(path.read_text())))
    return manifests


def _grep_any(files: list[Path], needle: str) -> bool:
    for path in files:
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


# The repo-root /references/ directory (self-referential panel-discussion
# prose, e.g. this check's own merge-01.md quoting a filename it flags) and
# /tests/ (fixtures quoting a filename under test) would each otherwise make
# the check blind to a violation it exists to catch -- excluded from the
# consumer scan entirely. Deliberately root-relative, not a substring match:
# .claude/skills/*/references/ subdirectories are real, shipped skill
# reference material and must stay in scope. .claude/worktrees/ is pruned
# too -- ephemeral branch checkouts, not this tree's own implementing files.
THIS_FILE = Path(__file__).resolve()
_EXCLUDED_TOP_LEVEL = {"references", "tests"}


def _consumer_files(root: Path, patterns: list[str]) -> list[Path]:
    """Resolve STANDARDS_CONSUMER_GLOBS/APPRAISAL_CONSUMER_FILES-style
    patterns to a concrete file list once, so repeated needle checks (one
    per declared value) don't each re-walk the tree from scratch."""
    files = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file() or path.resolve() == THIS_FILE:
                continue
            rel_parts = path.relative_to(root).parts
            if rel_parts[0] in _EXCLUDED_TOP_LEVEL:
                continue
            if ".claude" in rel_parts and "worktrees" in rel_parts:
                continue
            files.append(path)
    return files


def _grep_any(files: list[Path], needle: str) -> bool:
    for path in files:
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


def check_appraisal_instruments() -> list[tuple]:
    """Every non-null appraisal_instruments_by_design value must appear
    somewhere in the quality-appraisal skill's own files."""
    violations = []
    for path, pack in _iter_packs():
        rel = path.relative_to(ROOT).as_posix()
        for design, instrument in pack.get("appraisal_instruments_by_design", {}).items():
            if instrument is None:
                continue  # an honest "no instrument for this design" -- not a gap
            key = (rel, f"appraisal_instruments_by_design.{design}", instrument)
            if not _grep_any(APPRAISAL_CONSUMER_FILES, instrument):
                violations.append(key)
    return violations


def check_confidence_frameworks() -> list[tuple]:
    """Every non-'none' confidence_framework value must appear somewhere
    under .claude/skills/quality-appraisal/."""
    violations = []
    for path, pack in _iter_packs():
        rel = path.relative_to(ROOT).as_posix()
        framework = pack.get("confidence_framework", "none")
        if framework == "none":
            continue  # an honest opt-out
        key = (rel, "confidence_framework", framework)
        if not _grep_any(APPRAISAL_CONSUMER_FILES, framework):
            violations.append(key)
    return violations


def check_standards_refs() -> list[tuple]:
    """Every methods/*.json standards[].ref filename must be mentioned by
    at least one other file in the repo (a command, skill, or tool)."""
    consumer_files = _consumer_files(ROOT, STANDARDS_CONSUMER_GLOBS)
    violations = []
    for path, manifest in _iter_manifests():
        rel = path.relative_to(ROOT).as_posix()
        for entry in manifest.get("standards", []):
            ref_filename = Path(entry["ref"]).name
            key = (rel, "standards[].ref", ref_filename)
            if not _grep_any(consumer_files, ref_filename):
                violations.append(key)
    return violations


def check_routing_fields_set_by_packs() -> list[tuple]:
    """Symmetric direction: a field methods/_routing.json's rows read
    (e.g. venue_default) that zero packs ever set is itself a conformance
    failure -- a routing branch nothing can reach."""
    routing_table = json.loads(ROUTING_FIELD_CONSUMER_FILE.read_text())
    read_fields: set[str] = set()

    def _walk(cond):
        if "all" in cond:
            for c in cond["all"]:
                _walk(c)
        elif "any" in cond:
            for c in cond["any"]:
                _walk(c)
        else:
            for field in cond:
                read_fields.add(field)

    for row in routing_table["rows"]:
        _walk(row["when"])

    # goal/question_focus/evidence_type/expects_pooling/reviewers/time_budget
    # etc. are elicited directly by /litreview-init, never pack-declared --
    # only fields a *pack* could plausibly set are in scope for this check.
    pack_settable_candidates = {"venue_default"}
    packs = _iter_packs()
    violations = []
    for field in read_fields & pack_settable_candidates:
        if not any(field in pack for _, pack in packs):
            violations.append(("_routing_field", field))
    return violations


def main() -> int:
    all_violations = (
        check_appraisal_instruments()
        + check_confidence_frameworks()
        + check_standards_refs()
        + check_routing_fields_set_by_packs()
    )

    failures = []
    warnings = []
    for key in all_violations:
        baseline_ref = KNOWN_UNCONSULTED_BASELINE.get(key)
        if baseline_ref is None:
            failures.append(key)
        elif not baseline_ref.startswith("merge-"):
            failures.append(key)  # a baseline entry must point at a real merge-doc anchor
        else:
            warnings.append((key, baseline_ref))

    for key, ref in warnings:
        print(f"note: declared-but-unconsulted (baselined): {key!r} -- {ref}")

    # A baseline entry that no longer reproduces should be pruned -- same
    # stale-allowlist idiom as tools/security_guards.py.
    reproduced = set(all_violations)
    for key, ref in KNOWN_UNCONSULTED_BASELINE.items():
        if key not in reproduced:
            print(f"note: baseline entry no longer reproduces, remove from KNOWN_UNCONSULTED_BASELINE: {key!r} ({ref})")

    if failures:
        print(f"check_manifest_conformance: {len(failures)} new/un-baselined failure(s)")
        for key in failures:
            print(f"  - {key!r}")
        return 1

    print(f"check_manifest_conformance: OK ({len(warnings)} known baselined instance(s), 0 new failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
