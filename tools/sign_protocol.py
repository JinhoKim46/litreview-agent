#!/usr/bin/env python3
"""Stamp protocol.json's G-Protocol sign-off (docs/PLAN.md M2/M3;
references/docs/design/multi-method-consensus.md §3.1 S1: "G-Protocol: sign
protocol (and plan) -> rendered protocol draft").

This closes a real gap: tools/label_gate.py's
check_protocol_signed_before_first_protocol_driven_run (one of two
HARD_GATE_CHECKS) reads protocol.json's own top-level `signed_at`, but
nothing in the shipped pipeline ever wrote it -- only test fixtures
fabricated the field directly. Every real review this framework has ever
produced was therefore downgraded to "systematized review" regardless of
actual conduct, since the hard-gate check always failed closed on a missing
`signed_at`.

Independently re-verifies the protocol is actually complete before signing
-- the same deterministic-Python-validates-humans-decide discipline as
tools/ledger.py's `gate` command and tools/charting_gate.py's freeze():
the reviewer's own confirmation in conversation is not, by itself, the
gate. Refuses to sign (or re-sign with a different signed_by) once already
signed -- `signed_at` records the moment the plan predated the first
search, and silently overwriting it would let a post-hoc protocol
retroactively claim it was prespecified.

Usage:
    python3 tools/sign_protocol.py --topic <slug> --signed-by <name>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402


class SignProtocolError(ValueError):
    """protocol.json doesn't exist yet, is missing a field required to sign,
    or is already signed and this call would change signed_by/re-date it --
    never silently signed anyway."""


def _protocol_path(topic_dir: Path) -> Path:
    return Path(topic_dir) / "protocol.json"


def check_completeness(protocol: dict) -> list[str]:
    """Returns the dotted paths of every field required before signing that
    is missing or empty (an empty list means ready to sign). Mirrors
    litreview-init.md Step 5's own documented "what's a gap vs. legitimately
    null" list -- registration.id, eligibility.date_range.to and
    scope.region are never checked here, since a null value there is
    correct, not incomplete."""
    missing = []

    def _check_str(value, path):
        if not isinstance(value, str) or not value.strip():
            missing.append(path)

    def _check_nonempty_list(value, path):
        if not isinstance(value, list) or not value:
            missing.append(path)

    _check_str(protocol.get("title"), "title")
    _check_str(protocol.get("objective"), "objective")
    _check_str(protocol.get("framework"), "framework")

    framework_fields = protocol.get("framework_fields")
    if not isinstance(framework_fields, dict) or not framework_fields:
        missing.append("framework_fields")
    else:
        for key, value in framework_fields.items():
            _check_str(value, f"framework_fields.{key}")

    eligibility = protocol.get("eligibility")
    if not isinstance(eligibility, dict):
        missing.append("eligibility")
    else:
        _check_str((eligibility.get("population") or {}).get("criterion"), "eligibility.population.criterion")
        _check_nonempty_list((eligibility.get("study_design") or {}).get("included"), "eligibility.study_design.included")
        _check_nonempty_list((eligibility.get("publication_type") or {}).get("included"), "eligibility.publication_type.included")
        _check_str((eligibility.get("date_range") or {}).get("from"), "eligibility.date_range.from")
        _check_nonempty_list((eligibility.get("language") or {}).get("included"), "eligibility.language.included")

    scope = protocol.get("scope")
    if not isinstance(scope, dict):
        missing.append("scope")
    else:
        _check_str(scope.get("mode"), "scope.mode")

    return missing


def sign(topic_dir: Path, signed_by: str) -> dict:
    """Loads protocol.json, verifies completeness (check_completeness()),
    and stamps signed_at (now, UTC) + signed_by. Idempotent no-op if
    already signed -- returns the protocol unchanged rather than re-dating
    it, since signed_at's whole purpose is to fix the moment the plan
    predated the first search.

    Completeness is checked *before* the already-signed early return, not
    after -- a protocol with a hand-written or otherwise bogus `signed_at`
    but missing required fields must still raise, never be waved through
    as "already validly signed". Skipping this check for an already-signed
    protocol would let exactly the bypass this script exists to prevent
    back in through a different door."""
    path = _protocol_path(topic_dir)
    if not path.exists():
        raise SignProtocolError(f"{path} does not exist yet -- write the protocol (review-protocol Phase 2) before signing it")
    try:
        protocol = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SignProtocolError(f"{path}: invalid JSON: {exc}") from exc

    missing = check_completeness(protocol)
    if missing:
        raise SignProtocolError(
            "cannot sign an incomplete protocol -- missing or empty: " + ", ".join(missing) +
            ". Finish the review-protocol interview for these fields first."
        )

    if protocol.get("signed_at"):
        if protocol.get("signed_by") != signed_by:
            print(
                f"note: already signed at {protocol['signed_at']} by {protocol.get('signed_by')!r} -- "
                f"--signed-by {signed_by!r} ignored (signed_at is never re-dated)",
                file=sys.stderr,
            )
        return protocol  # already signed -- idempotent no-op, never re-dated

    protocol["signed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    protocol["signed_by"] = signed_by
    path.write_text(json.dumps(protocol, indent=2) + "\n")
    return protocol


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--signed-by", required=True, help="reviewer name/id confirming the protocol at G-Protocol")
    args = parser.parse_args(argv)

    try:
        topic_dir = safe_topic_path(args.topic)
    except UnsafePathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        protocol = sign(topic_dir, args.signed_by)
    except SignProtocolError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"signed_at": protocol["signed_at"], "signed_by": protocol["signed_by"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
