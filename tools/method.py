#!/usr/bin/env python3
"""Resolve which method manifest (and field pack) governs a review.

docs/PLAN.md M1: the first piece of the multi-method architecture -- every
review this framework runs is a method-manifest instance (methods/*.json),
even though today only one manifest (methods/systematic_review.json) exists.
A command's Step 0 calls this to find out which policy fields apply; nothing
here decides pipeline stages or sequence -- those stay in the nine
.claude/commands/litreview-*.md files, which are the implementation
(docs/ROADMAP.md's "one sentence design").

Absence of `protocol.json.method` (every review created before this file
existed) resolves to "systematic_review" with `recorded=False` -- not an
error, and not a downgrade; see resolve()'s docstring and
docs/ROADMAP.md's migration note.

Field packs (packs/*.json) add glosses and expectations on top of a method,
never override its rules (docs/ROADMAP.md). `generic`, `clinical_interventions`
and `cs_se` ship from docs/PLAN.md M3 on; a pack id resolving to none of
those (or to a later pack, e.g. M5's imaging packs, before it ships) is the
expected state for that id, not an error -- resolve() treats a missing pack
file as "no pack data", never an error.

Usage:
    python3 tools/method.py --topic <slug>   # print the resolved method/pack as JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.path_policy import UnsafePathError, safe_topic_path  # noqa: E402

METHODS_DIR = ROOT / "methods"
PACKS_DIR = ROOT / "packs"
METHOD_SCHEMA_PATH = METHODS_DIR / "_schema.json"
PACK_SCHEMA_PATH = PACKS_DIR / "_schema.json"
PROTOCOL_METHOD_SCHEMA_PATH = ROOT / "schemas" / "protocol_method.schema.json"

# Not method manifests themselves -- the manifest schema and (from M2 on) the
# routing table. Globbing methods/*.json must skip these by name rather than
# by any content sniff, so a manifest that happens to omit a field the schema
# would also omit is never mistaken for the schema itself.
NON_MANIFEST_FILES = {"_schema.json", "_routing.json"}
NON_PACK_FILES = {"_schema.json"}

DEFAULT_METHOD_ID = "systematic_review"
DEFAULT_PACK_ID = "generic"


class MethodError(ValueError):
    """A methods/*.json or packs/*.json file is missing, malformed, or
    otherwise fails this module's contract -- never silently patched over."""


def list_manifests() -> dict[str, dict]:
    """Glob, parse, and schema-validate every methods/*.json manifest.

    Returns {manifest_id: manifest_dict}. Raises MethodError naming the
    offending file on any parse/schema/id-mismatch failure -- a broken
    manifest must fail loudly, not resolve to some other method silently."""
    if not METHOD_SCHEMA_PATH.exists():
        raise MethodError(f"{METHOD_SCHEMA_PATH} not found -- methods/_schema.json must ship with any manifest")
    schema = json.loads(METHOD_SCHEMA_PATH.read_text())

    manifests: dict[str, dict] = {}
    if not METHODS_DIR.exists():
        return manifests
    for path in sorted(METHODS_DIR.glob("*.json")):
        if path.name in NON_MANIFEST_FILES:
            continue
        try:
            manifest = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise MethodError(f"{path}: invalid JSON: {exc}") from exc
        try:
            jsonschema.validate(manifest, schema)
        except jsonschema.exceptions.ValidationError as exc:
            raise MethodError(f"{path}: fails methods/_schema.json: {exc.message}") from exc
        expected_id = path.stem
        if manifest["id"] != expected_id:
            raise MethodError(f"{path}: manifest id {manifest['id']!r} does not match filename stem {expected_id!r}")
        manifests[manifest["id"]] = manifest
    return manifests


def load_pack(pack_id: str) -> dict | None:
    """Load packs/<pack_id>.json if it exists, validated against
    packs/_schema.json. A missing file (or a missing packs/ directory
    entirely) resolves to None, never an error -- callers before docs/PLAN.md
    M3 (or any topic resolving to a pack id nothing ships yet) rely on this.
    A malformed or schema-invalid pack file that *does* exist still fails
    loudly, the same discipline as list_manifests()."""
    if not re.match(r"^[a-z][a-z0-9_]*$", pack_id):
        raise MethodError(f"invalid pack id {pack_id!r}")
    path = PACKS_DIR / f"{pack_id}.json"
    if not path.exists():
        return None
    try:
        pack = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise MethodError(f"{path}: invalid JSON: {exc}") from exc
    if not PACK_SCHEMA_PATH.exists():
        raise MethodError(f"{PACK_SCHEMA_PATH} not found -- packs/_schema.json must ship with any pack")
    schema = json.loads(PACK_SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(pack, schema)
    except jsonschema.exceptions.ValidationError as exc:
        raise MethodError(f"{path}: fails packs/_schema.json: {exc.message}") from exc
    if pack["id"] != pack_id:
        raise MethodError(f"{path}: pack id {pack['id']!r} does not match filename stem {pack_id!r}")
    known_connectors = set(_installed_connector_ids())
    for expectation in pack["source_expectations"]:
        reachable_via = expectation["reachable_via"]
        if reachable_via is not None and reachable_via not in known_connectors:
            raise MethodError(
                f"{path}: source_expectations entry {expectation['source']!r} names "
                f"reachable_via={reachable_via!r}, which is not an installed connector "
                f"(known: {sorted(known_connectors) or '<none installed>'})"
            )
    return pack


def _installed_connector_ids() -> list[str]:
    """The connector module ids load_pack() checks reachable_via against.
    Imported lazily (not at module load) so a broken connector module can
    never prevent tools/method.py itself from importing."""
    from connectors.registry import list_source_files

    return list_source_files()


def _load_protocol_method_block(protocol: dict | None) -> tuple[str, bool, str | None]:
    """Returns (method_id, recorded, pack_id). `protocol` is protocol.json's
    parsed content, or None if the file does not exist yet (a review that
    has not run /litreview-init's protocol step at all -- resolve() still
    returns the default method so a caller can render "what SR requires"
    before one is signed).

    `pack_id` is R9's recorded pack choice (tools/route.py's
    resolve_pack(), written to protocol.json.method.pack at G-Route) -- None
    when absent, which happens both for a legacy protocol predating M2's
    routing interview and for one where routing explicitly resolved no pack
    at all. resolve() falls back to DEFAULT_PACK_ID in either case; this
    function only reports what was actually recorded, never substitutes a
    default itself."""
    method_block = (protocol or {}).get("method")
    if method_block is None:
        return DEFAULT_METHOD_ID, False, None
    schema = json.loads(PROTOCOL_METHOD_SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(method_block, schema)
    except jsonschema.exceptions.ValidationError as exc:
        raise MethodError(f"protocol.json.method fails schemas/protocol_method.schema.json: {exc.message}") from exc
    return method_block["id"], method_block.get("recorded", True), method_block.get("pack")


def resolve(topic: str, pack_id: str | None = None) -> dict:
    """Resolve the method and pack governing `topic`.

    Reads results/<topic>/protocol.json if it exists; absence of the file,
    or absence of its `method` key, both resolve to
    ("systematic_review", recorded=False) per docs/ROADMAP.md's migration
    path -- never an error, never a different method silently substituted.

    `pack_id` lets a caller override which pack to resolve against. Omitted,
    it defaults to whatever R9 recorded at G-Route
    (protocol.json.method.pack, tools/route.py's resolve_pack()), falling
    back to "generic" only when nothing was recorded (a legacy protocol
    predating M2's routing interview, or no protocol at all) -- never to
    "generic" over a review's own recorded choice. `pack` in the returned
    dict is None whenever the resolved pack id has no packs/<id>.json on
    disk yet; that is expected for any id not shipped, not a failure.

    Returns {"method_id", "recorded", "manifest", "pack_id", "pack"}."""
    topic_dir = safe_topic_path(topic)
    protocol_path = topic_dir / "protocol.json"
    protocol = json.loads(protocol_path.read_text()) if protocol_path.exists() else None

    method_id, recorded, recorded_pack_id = _load_protocol_method_block(protocol)
    manifests = list_manifests()
    if method_id not in manifests:
        raise MethodError(
            f"resolved method id {method_id!r} for topic {topic!r} has no methods/{method_id}.json manifest "
            f"(known methods: {sorted(manifests) or '<none shipped>'})"
        )

    resolved_pack_id = pack_id or recorded_pack_id or DEFAULT_PACK_ID
    return {
        "method_id": method_id,
        "recorded": recorded,
        "manifest": manifests[method_id],
        "pack_id": resolved_pack_id,
        "pack": load_pack(resolved_pack_id),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="review slug under results/")
    parser.add_argument("--pack", help="override the pack id to resolve against (default: generic, or protocol.json.pack.id)")
    parser.add_argument(
        "--require-capture-mode",
        help="the capture.mode a caller's stage expects (e.g. \"extraction\"); exit 1 with a refusal "
             "if the resolved manifest declares a different mode -- docs/PLAN.md M3: a command whose "
             "stage does not apply to this review's method must refuse and point to the stage that "
             "does (references/docs/design/multi-method-consensus.md §3.2's '—' legend), never "
             "silently run its own stage's logic against a manifest that asked for something else.",
    )
    args = parser.parse_args(argv)

    try:
        resolved = resolve(args.topic, pack_id=args.pack)
    except (UnsafePathError, MethodError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    capture = resolved["manifest"]["capture"]
    output = {
        "method_id": resolved["method_id"],
        "recorded": resolved["recorded"],
        "label": resolved["manifest"]["label"],
        "pack_id": resolved["pack_id"],
        "pack_loaded": resolved["pack"] is not None,
        "capture_mode": capture["mode"],
    }

    if args.require_capture_mode and capture["mode"] != args.require_capture_mode:
        output["refused"] = True
        output["reason"] = (
            f"{resolved['method_id']!r}'s capture stage uses mode {capture['mode']!r}, not "
            f"{args.require_capture_mode!r} -- this command's stage does not apply to this review's method."
        )
        print(json.dumps(output, indent=2))
        return 1

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
