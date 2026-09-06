#!/usr/bin/env python3
"""Resolve which method manifest (and field pack) governs a review.

docs/PLAN.md M1: the first piece of the multi-method architecture -- every
review this framework runs is a method-manifest instance (methods/*.json),
even though today only one manifest (methods/systematic_review.json) exists.
A command's Step 0 calls this to find out which policy fields apply; nothing
here decides pipeline stages or sequence -- those stay in the nine
.claude/commands/prisma-*.md files, which are the implementation
(docs/ROADMAP.md's "one sentence design").

Absence of `protocol.json.method` (every review created before this file
existed) resolves to "systematic_review" with `recorded=False` -- not an
error, and not a downgrade; see resolve()'s docstring and
docs/ROADMAP.md's migration note.

Field packs (packs/*.json) add glosses and expectations on top of a method,
never override its rules (docs/ROADMAP.md). No pack ships until
docs/PLAN.md M3, so `packs/` may not exist at all yet -- resolve() treats a
missing pack file as "no pack data", never an error.

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
PROTOCOL_METHOD_SCHEMA_PATH = ROOT / "schemas" / "protocol_method.schema.json"

# Not method manifests themselves -- the manifest schema and (from M2 on) the
# routing table. Globbing methods/*.json must skip these by name rather than
# by any content sniff, so a manifest that happens to omit a field the schema
# would also omit is never mistaken for the schema itself.
NON_MANIFEST_FILES = {"_schema.json", "_routing.json"}

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
    """Load packs/<pack_id>.json if it exists. No pack manifest ships until
    docs/PLAN.md M3 -- a missing file (or a missing packs/ directory
    entirely) is the expected M1 state, not an error. A malformed pack file
    that *does* exist still fails loudly."""
    if not re.match(r"^[a-z][a-z0-9_]*$", pack_id):
        raise MethodError(f"invalid pack id {pack_id!r}")
    path = PACKS_DIR / f"{pack_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise MethodError(f"{path}: invalid JSON: {exc}") from exc


def _load_protocol_method_block(protocol: dict | None) -> tuple[str, bool]:
    """Returns (method_id, recorded). `protocol` is protocol.json's parsed
    content, or None if the file does not exist yet (a review that has not
    run /prisma-init's protocol step at all -- resolve() still returns the
    default method so a caller can render "what SR requires" before one is
    signed)."""
    method_block = (protocol or {}).get("method")
    if method_block is None:
        return DEFAULT_METHOD_ID, False
    schema = json.loads(PROTOCOL_METHOD_SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(method_block, schema)
    except jsonschema.exceptions.ValidationError as exc:
        raise MethodError(f"protocol.json.method fails schemas/protocol_method.schema.json: {exc.message}") from exc
    return method_block["id"], method_block.get("recorded", True)


def resolve(topic: str, pack_id: str | None = None) -> dict:
    """Resolve the method (and, once packs ship, the pack) governing `topic`.

    Reads results/<topic>/protocol.json if it exists; absence of the file,
    or absence of its `method` key, both resolve to
    ("systematic_review", recorded=False) per docs/ROADMAP.md's migration
    path -- never an error, never a different method silently substituted.

    `pack_id` lets a caller override which pack to resolve against; omitted,
    it defaults to "generic". No pack manifest exists until M3 (nothing
    writes a pack choice to protocol.json yet either), so `pack` in the
    returned dict is commonly None -- that is expected, not a failure.

    Returns {"method_id", "recorded", "manifest", "pack_id", "pack"}."""
    topic_dir = safe_topic_path(topic)
    protocol_path = topic_dir / "protocol.json"
    protocol = json.loads(protocol_path.read_text()) if protocol_path.exists() else None

    method_id, recorded = _load_protocol_method_block(protocol)
    manifests = list_manifests()
    if method_id not in manifests:
        raise MethodError(
            f"resolved method id {method_id!r} for topic {topic!r} has no methods/{method_id}.json manifest "
            f"(known methods: {sorted(manifests) or '<none shipped>'})"
        )

    resolved_pack_id = pack_id or DEFAULT_PACK_ID
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
    args = parser.parse_args(argv)

    try:
        resolved = resolve(args.topic, pack_id=args.pack)
    except (UnsafePathError, MethodError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "method_id": resolved["method_id"],
        "recorded": resolved["recorded"],
        "label": resolved["manifest"]["label"],
        "pack_id": resolved["pack_id"],
        "pack_loaded": resolved["pack"] is not None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
