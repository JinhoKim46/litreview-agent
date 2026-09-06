#!/usr/bin/env python3
"""Compute a review's conduct-floor label and report-build blockers.

docs/PLAN.md M2 / references/docs/design/multi-method-consensus.md §2.4
("downgrade honestly" rule): the label a report is allowed to print is
*computed from recorded conduct*, never typed by a user or a prompt, using
the same code at routing (predictive), /prisma-status, and /prisma-report
(definitive). Each requires[] check in a method manifest's label_rules
resolves to True, False, or "not_recorded" -- never silently defaulted to
one or the other:

  * True/False mean the framework CAN determine whether this review's
    recorded conduct meets the check, and did.
  * "not_recorded" means the mechanism to record the underlying fact does
    not exist yet for this review (e.g. no connector declares
    `index_family`, or /prisma-init's routing interview hasn't been wired
    up yet) -- a framework limitation, not the reviewer's fault.

Only the two checks the framework can *always* determine from data that
already exists once a protocol/ledger exists --
`protocol_signed_before_first_protocol_driven_run` and
`second_reviewer_involvement_in_selection` -- gate the label; a
"not_recorded" result for either of those is treated the same as False
(fail closed on the reviewer's own conduct, since the mechanism to record
it has existed all along). Every other check's "not_recorded" becomes a
disclosure instead of a downgrade, per the manifest's own `disclosures[]`.

Incomplete stages (missing full-text exclusion reasons, unfinished
appraisal) never change the label -- they block the report build via
`compute_blockers()` instead, which is a separate, additive to-do list.

Usage:
    python3 tools/label_gate.py --topic <slug>   # print the computed label as JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import ledger  # noqa: E402
from tools.method import resolve as resolve_method  # noqa: E402
from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402

try:
    from synthesis.run_synthesis import _plan_predates_first_run
except ImportError:  # pragma: no cover -- synthesis/ is always present in this repo
    _plan_predates_first_run = None


class LabelGateError(ValueError):
    """A manifest references a check or blocker this module doesn't know how
    to evaluate -- fails loudly rather than silently skipping it."""


# ---------------------------------------------------------------------------
# label_rules.requires[] checks -- each returns True, False, or "not_recorded"
# ---------------------------------------------------------------------------

def _earliest_raw_timestamp(raw_dir: Path, *, exclude_purpose: str | None = None):
    """Earliest `meta.fetched_at` among raw/*.json files, optionally
    excluding a given `meta.purpose` (e.g. "orienting" Q0 runs, which must
    never count as "the first protocol-driven run"). A raw file predating
    the orienting/protocol_driven distinction (docs/PLAN.md M2) has no
    `purpose` field at all -- treated as protocol_driven (the only kind of
    run that existed before this distinction), matching
    synthesis/run_synthesis.py's own no-filter convention. Returns None if
    no qualifying raw file exists."""
    from datetime import datetime, timezone

    earliest = None
    if not raw_dir.exists():
        return None
    for path in sorted(raw_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
            meta = doc.get("meta", {})
        except (OSError, json.JSONDecodeError):
            meta = {}
        if exclude_purpose and meta.get("purpose") == exclude_purpose:
            continue
        ts_raw = meta.get("fetched_at")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
        except (ValueError, AttributeError):
            ts = None
        if ts is None:
            ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if earliest is None or ts < earliest:
            earliest = ts
    return earliest


def check_protocol_signed_before_first_protocol_driven_run(topic_dir, protocol, manifest, value):
    from datetime import datetime

    signed_at = (protocol or {}).get("signed_at")
    if not signed_at:
        return False  # fail closed: no recorded protocol sign date at all
    earliest = _earliest_raw_timestamp(Path(topic_dir) / "raw", exclude_purpose="orienting")
    if earliest is None:
        return True  # no protocol-driven run has happened yet -- can't be "too late"
    signed = datetime.fromisoformat(signed_at.replace("Z", "+00:00"))
    return signed <= earliest


def check_min_index_families(topic_dir, protocol, manifest, value):
    # connectors/registry.py declares no `index_family` field on any source
    # yet (verified: only OPTIONAL_API_KEY_ENV classifies sources today) --
    # a real framework gap, not a per-review conduct failure. Flagged in
    # the PR body; a follow-up PR adds index_family classification and
    # replaces this with a real count against `value` (the manifest's
    # required minimum).
    return "not_recorded"


def check_registry_lookup_recorded(topic_dir, protocol, manifest, value):
    routing = (protocol or {}).get("method", {}).get("routing")
    if routing is None:
        return "not_recorded"  # /prisma-init's routing interview isn't wired up for this review yet
    q0 = routing.get("q0") or {}
    return bool(q0.get("registry_lookup"))


def check_second_reviewer_involvement_in_selection(topic_dir, protocol, manifest, value):
    ledger_path = Path(topic_dir) / "screening_decisions.jsonl"
    if not ledger_path.exists():
        return "not_recorded"  # screening hasn't started yet -- too early to judge
    entries = ledger.load_ledger(topic_dir)
    decision_bys = {e.get("by") for e in entries if e.get("role", "decision") == "decision" and e.get("by")}
    has_verification_sample = any(e.get("role") == "verification" for e in entries)
    return len(decision_bys) >= 2 or has_verification_sample


def check_pooling_only_under_signed_plan(topic_dir, protocol, manifest, value):
    effect_sizes_path = Path(topic_dir) / "synthesis" / "effect_sizes.json"
    if not effect_sizes_path.exists():
        return True  # vacuous: no synthesis has run yet
    try:
        effect_sizes = json.loads(effect_sizes_path.read_text())
    except (OSError, json.JSONDecodeError):
        return True
    pooled = [e for e in effect_sizes if e.get("pooled")]
    if not pooled:
        return True  # vacuous: nothing was actually pooled
    return all(e.get("model_source") == "protocol" for e in pooled)


CHECK_FUNCTIONS = {
    "protocol_signed_before_first_protocol_driven_run": check_protocol_signed_before_first_protocol_driven_run,
    "min_index_families": check_min_index_families,
    "registry_lookup_recorded": check_registry_lookup_recorded,
    "second_reviewer_involvement_in_selection": check_second_reviewer_involvement_in_selection,
    "pooling_only_under_signed_plan": check_pooling_only_under_signed_plan,
}

# The only checks the framework can always resolve to True/False once a
# protocol/ledger exists at all -- their "not_recorded" is treated as a
# downgrade, same as False, per §2.4's "missing (i) or (iv)" rule. Every
# other check's "not_recorded" is a disclosure, never a downgrade.
HARD_GATE_CHECKS = {
    "protocol_signed_before_first_protocol_driven_run",
    "second_reviewer_involvement_in_selection",
}


def compute_label(topic: str, *, topic_dir=None) -> dict:
    """Evaluate the resolved method manifest's label_rules against `topic`'s
    recorded conduct. Returns {"label", "checks", "missing", "disclosures"}.
    Callable at G-Route (predictive, before most artifacts exist), at
    /prisma-status, and at /prisma-report (definitive) -- same code path
    every time, per §2.4.

    `disclosures` here lists which requires[] *checks* came back
    "not_recorded" (e.g. "min_index_families") -- it is not yet the richer,
    named disclosure vocabulary methods/systematic_review.json's own
    label_rules.disclosures[] enumerates ("reviewer_count",
    "verification_sample", "extraction_verification", "search_dates",
    "search_age", "registration", "criteria_changes", "coverage_gaps",
    "legacy_pooling"): several of those (e.g. "search_age"'s 12-month
    currency rule, "extraction_verification"'s SoF footnote) need data this
    module doesn't read yet and are left for a follow-up PR, per §2.4's
    text for each."""
    topic_dir = Path(topic_dir) if topic_dir is not None else safe_topic_path(topic)
    protocol_path = topic_dir / "protocol.json"
    protocol = json.loads(protocol_path.read_text()) if protocol_path.exists() else None

    resolved = resolve_method(topic)
    manifest = resolved["manifest"]
    label_rules = manifest["label_rules"]

    checks = {}
    for req in label_rules.get("requires", []):
        name = req["check"]
        fn = CHECK_FUNCTIONS.get(name)
        if fn is None:
            raise LabelGateError(f"manifest {manifest['id']!r} requires unknown label check {name!r}")
        checks[name] = fn(topic_dir, protocol, manifest, req.get("value"))

    missing = [
        name for name, result in checks.items()
        if result is False or (result == "not_recorded" and name in HARD_GATE_CHECKS)
    ]
    disclosures = [
        name for name, result in checks.items()
        if result == "not_recorded" and name not in HARD_GATE_CHECKS
    ]

    profile_flags = (protocol or {}).get("method", {}).get("profile_flags", [])
    profile_labels = label_rules.get("profile_labels", {})
    for flag in profile_flags:
        if flag in profile_labels:
            return {"label": profile_labels[flag], "checks": checks, "missing": missing, "disclosures": disclosures}

    if missing:
        otherwise = label_rules.get("otherwise", {})
        return {
            "label": otherwise.get("label", label_rules["label"]),
            "checks": checks,
            "missing": missing if otherwise.get("list_missing") else [],
            "disclosures": disclosures,
        }

    return {"label": label_rules["label"], "checks": checks, "missing": [], "disclosures": disclosures}


# ---------------------------------------------------------------------------
# report_blockers -- incomplete stages block the build; they never change
# the label (§2.4: "incomplete stages are not conduct choices").
# ---------------------------------------------------------------------------

def _blocker_fulltext_exclusion_reasons_complete(topic_dir):
    latest = ledger.latest_decisions(ledger.load_ledger(topic_dir))
    bad = ledger.full_text_reason_required_missing(latest)
    if bad:
        return False, f"{len(bad)} full-text decision(s) missing a required reason (PRISMA Item 16b): " + ", ".join(rid for rid, _ in bad[:10])
    return True, None


def _blocker_appraisal_complete(topic_dir, manifest):
    if manifest.get("appraisal", {}).get("requirement") != "mandatory":
        return True, None
    table_path = Path(topic_dir) / "extraction_table.json"
    if not table_path.exists():
        return False, "extraction_table.json does not exist yet"
    table = json.loads(table_path.read_text())
    studies = table if isinstance(table, list) else table.get("studies", [])
    missing = [s.get("record_id", "<unknown>") for s in studies if not s.get("risk_of_bias")]
    if missing:
        return False, f"{len(missing)} extracted study/studies missing a risk_of_bias judgement: " + ", ".join(missing[:10])
    return True, None


def _blocker_references_verified(topic_dir):
    # No stage of this framework writes a references-verification record
    # yet (verifying a citation against a real source is a WebSearch/
    # WebFetch judgement call, not something this script can perform) --
    # fails closed until prisma-manuscript writes one, rather than fabricate
    # a pass. See CLAUDE.md's Verification Checklist.
    marker_path = Path(topic_dir) / "manuscript" / "references_verified.json"
    if not marker_path.exists():
        return False, "no manuscript/references_verified.json record found -- every manuscript reference must be independently verified before report build (CLAUDE.md Verification Checklist)"
    try:
        record = json.loads(marker_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False, "manuscript/references_verified.json exists but is not valid JSON"
    return bool(record.get("verified")), None if record.get("verified") else "manuscript/references_verified.json exists but does not record verified: true"


BLOCKER_FUNCTIONS = {
    "fulltext_exclusion_reasons_complete": lambda topic_dir, manifest: _blocker_fulltext_exclusion_reasons_complete(topic_dir),
    "appraisal_complete": _blocker_appraisal_complete,
    "references_verified": lambda topic_dir, manifest: _blocker_references_verified(topic_dir),
}


def compute_blockers(topic: str, *, topic_dir=None) -> list[dict]:
    """Evaluate manifest.report_blockers against `topic`. Returns a list of
    {"blocker", "detail"} for every unmet blocker -- empty means the report
    build may proceed. Never affects the label."""
    topic_dir = Path(topic_dir) if topic_dir is not None else safe_topic_path(topic)
    resolved = resolve_method(topic)
    manifest = resolved["manifest"]

    blockers = []
    for name in manifest.get("report_blockers", []):
        fn = BLOCKER_FUNCTIONS.get(name)
        if fn is None:
            raise LabelGateError(f"manifest {manifest['id']!r} declares unknown report_blocker {name!r}")
        ok, detail = fn(topic_dir, manifest)
        if not ok:
            blockers.append({"blocker": name, "detail": detail})
    return blockers


# ---------------------------------------------------------------------------
# Forbidden-form lint (§2.4's last bullet)
# ---------------------------------------------------------------------------

# Maps a manifest's forbidden_forms id to the regex(es) that detect it.
# Every pattern is anchored to the specific claim being forbidden (e.g.
# "comprehensive search", never bare "comprehensive") so ordinary phrases
# like "comprehensive geriatric assessment" or "gap junction" never trip
# the lint -- the calibrated forms this rule explicitly allows ("to our
# knowledge, within the search described in S1, we did not identify ...")
# contain none of these anchored phrases and so pass without special-casing.
FORBIDDEN_FORM_PATTERNS = {
    "exhaustive_search": [r"\bexhaustive\s+search\b", r"\bexhaustively\s+search"],
    "comprehensive_search": [r"\bcomprehensive\s+search\b"],
    "no_prior_work": [r"\bno\s+prior\s+work\b", r"\ball\s+relevant\s+studies\b"],
    "first_to": [r"\bfirst\s+to\b", r"\bwe\s+are\s+the\s+first\b"],
    "novelty": [r"\bnovel(?:ty)?\b", r"\bproves\b", r"\bsaturat\w*\b"],
}


def lint_text(text: str, manifest: dict, *, context: str) -> dict:
    """`context` is "templated_output" (the tool's own recon brief,
    prior-work sentences, gap statements, related_work_draft.md -- hard
    failure) or "manuscript_section" (Abstract/Conclusions of an SR/scoping
    manuscript -- warning only, per §2.4). Returns
    {"hard_failures": [...], "warnings": [...]}, each entry
    {"form", "match"}."""
    if context not in ("templated_output", "manuscript_section"):
        raise LabelGateError(f"lint_text: unknown context {context!r}")

    violations = []
    for form in manifest.get("forbidden_forms", []):
        for pattern in FORBIDDEN_FORM_PATTERNS.get(form, []):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                violations.append({"form": form, "match": m.group(0)})

    if context == "templated_output":
        return {"hard_failures": violations, "warnings": []}
    return {"hard_failures": [], "warnings": violations}


def write_label_json(topic: str, label_result: dict, blockers: list[dict], *, topic_dir=None) -> Path:
    """Writes manuscript/label.json = {label, disclosures[], missing[],
    blockers[]} -- only at report time (§2.3). label/disclosures/missing
    come from compute_label(); blockers from compute_blockers(), kept
    separate so a blocker never contaminates the label computation."""
    topic_dir = Path(topic_dir) if topic_dir is not None else safe_topic_path(topic)
    out_path = topic_dir / "manuscript" / "label.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": label_result["label"],
        "disclosures": label_result["disclosures"],
        "missing": label_result["missing"],
        "blockers": blockers,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--write", action="store_true", help="also write manuscript/label.json")
    args = parser.parse_args(argv)

    try:
        label_result = compute_label(args.topic)
        blockers = compute_blockers(args.topic)
    except (UnsafePathError, LabelGateError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output = {**label_result, "blockers": blockers}
    print(json.dumps(output, indent=2))

    if args.write:
        path = write_label_json(args.topic, label_result, blockers)
        print(f"wrote {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
