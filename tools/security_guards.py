#!/usr/bin/env python3
"""Supply-chain guards for the template's riskiest surfaces.

Run from anywhere: python3 tools/security_guards.py

This repo ships pre-approved Claude Code permissions that every fork user
executes without a prompt. This guard makes a dangerous change LOUD, not
impossible: a PR that intentionally needs a new permission must update
ALLOWED_PERMISSIONS in this file in the same diff, so the widening is explicit
and reviewable rather than buried in a settings.json diff nobody reads closely.

Checks:
1. .claude/settings.json — every permissions.allow entry must be one of the
   exact pinned entries this repo ships: one per connector module
   (`Bash(python3 -m connectors.<source>:*)`), one for the synthesis runner,
   one per tools/*.py maintainer script, `python3 -m unittest discover`, and
   `tools/export_report.py` (the --export docx/pdf path -- a fixed wrapper
   around Pandoc, not a raw `Bash(pandoc:*)` wildcard; see
   PRODUCT_READINESS_AUDIT.md P0-1 and tools/path_policy.py for why a bare
   Pandoc wildcard is unsafe: Lua filters and arbitrary -o/--resource-path
   flags are real code-execution and arbitrary-write surfaces this wrapper
   removes by never accepting them as arguments at all). Catches permission
   widening -- a bare `Bash(*)`, an unpinned `Bash(python3:*)`, a new
   unreviewed entry -- any of which would auto-approve arbitrary commands on
   every fork. The same file's `hooks` key is held to an allowlist too: a
   hook runs automatically when its event fires, with no prompt, so it is
   strictly more dangerous than a pre-approved permission.
2. .gitignore — `results/**` (per-review state) and `.env`/`.env.*` (optional
   NCBI_API_KEY/S2_API_KEY connector credentials) must still be present, and
   no un-allowlisted negation (`!pattern`) may silently re-include them.

Adapted from references/ai-job-search/tools/security_guards.py: dropped that
version's `.agents/**/package.json` npm-lifecycle-script check (this repo's
`.agents/skills/` are thin Python-CLI pointers, not TypeScript/Bun projects
with installable manifests -- there is no `package.json` anywhere in this
repo for a life-cycle-script check to guard).

Stdlib only. Exit 0 on success, 1 with a failure list otherwise.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

# The exact permission entries this repo ships (.claude/settings.json). A PR
# that adds or changes an entry must add it here too -- that is the point:
# the diff shows both.
ALLOWED_PERMISSIONS = {
    "Bash(python3 -m connectors.openalex:*)",
    "Bash(python3 -m connectors.crossref:*)",
    "Bash(python3 -m connectors.semanticscholar:*)",
    "Bash(python3 -m connectors.pubmed:*)",
    "Bash(python3 -m connectors.europepmc:*)",
    "Bash(python3 -m connectors.arxiv:*)",
    "Bash(python3 -m connectors.citation_chase:*)",
    "Bash(python3 -m connectors.registry:*)",
    "Bash(python3 -m synthesis.run_synthesis:*)",
    "Bash(python3 tools/lint_skills.py:*)",
    "Bash(python3 tools/check_connector_contract.py:*)",
    "Bash(python3 tools/check_framework_version.py:*)",
    "Bash(python3 tools/security_guards.py:*)",
    "Bash(python3 -m unittest discover:*)",
    "Bash(python3 tools/export_report.py:*)",
    "Bash(python3 tools/dedup.py:*)",
    "Bash(python3 tools/ledger.py:*)",
    "Bash(python3 tools/flow_counts.py:*)",
    "Bash(python3 tools/status.py:*)",
    "Bash(gh repo view:*)",
}

# Per-review-state and credential ignore rules that must never disappear from
# .gitignore. (architecture plan §10: "results/** ignored except .gitkeep/
# README", ".env* ignored (optional Scopus/WoS keys)".)
REQUIRED_IGNORE_RULES = [
    "results/**",
    ".env",
    ".env.*",
]

# Negation (re-include) rules this repo legitimately ships. .gitignore is
# order-sensitive: a later `!pattern` re-includes a path an earlier rule
# excluded, so a rule can be physically present in REQUIRED_IGNORE_RULES yet
# no longer take effect (e.g. adding `!results/**`). Set membership on the
# required rules cannot see that. Any negation outside this allowlist is a
# failure -- add an intentional one here in the same PR, exactly as with
# ALLOWED_PERMISSIONS, so the widening is explicit and reviewable.
ALLOWED_IGNORE_NEGATIONS = {
    "!results/**/.gitkeep",
    "!results/**/README.md",
}

# Hook commands this repo legitimately ships, as "<Event>:<command>" strings.
# Empty by design -- this repo ships no hooks at all.
#
# A hook is strictly more dangerous than a permissions.allow entry. A
# permission pre-approves something Claude may choose to do; a hook runs
# unconditionally when its event fires, with no prompt and no model decision
# in between. Cloning a repo and opening it is enough. This is the vector the
# Shai-Hulud worm used in its August 2026 wave, planting a SessionStart hook
# in .claude/settings.json that executed on session start:
# https://research.jfrog.com/post/shai-hulud-is-back-august/
ALLOWED_HOOKS: set[str] = set()


def _hook_commands(event: str, entries: object):
    """Yield "<Event>:<command>" for every command a hook event would run.

    Fails closed: any shape this does not recognise yields a marker that
    cannot be in the allowlist, so an unfamiliar hook layout is rejected
    rather than silently skipped.
    """
    unrecognised = f"{event}:<unrecognised hook shape>"
    if not isinstance(entries, list):
        yield unrecognised
        return
    for entry in entries:
        if not isinstance(entry, dict):
            yield unrecognised
            continue
        inner = entry.get("hooks")
        if not isinstance(inner, list):
            yield unrecognised
            continue
        for hook in inner:
            command = hook.get("command") if isinstance(hook, dict) else None
            yield f"{event}:{command}" if isinstance(command, str) else unrecognised


def check_permissions() -> None:
    path = ROOT / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f".claude/settings.json: unreadable or invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(".claude/settings.json: top-level JSON value must be an object")
        return

    # Checked before the permissions shape guards below, so a file that pairs
    # a malformed permissions block with a hook cannot return early and skip
    # this.
    hooks = data.get("hooks", {})
    if hooks:
        if not isinstance(hooks, dict):
            errors.append(".claude/settings.json: hooks must be an object")
        else:
            for event, entries in hooks.items():
                for command in _hook_commands(str(event), entries):
                    if command not in ALLOWED_HOOKS:
                        errors.append(
                            ".claude/settings.json: hook not in the reviewed allowlist: "
                            f"{command!r}. A hook runs automatically when its event fires - "
                            "it is never gated by the permissions prompt, so it executes on "
                            "every fork without the user agreeing to anything. If this hook "
                            "is intentional, add it to ALLOWED_HOOKS in "
                            "tools/security_guards.py in the same PR so the addition is "
                            "explicit and reviewable."
                        )

    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append(".claude/settings.json: permissions must be an object")
        return
    allow = permissions.get("allow", [])
    if not isinstance(allow, list) or not all(isinstance(entry, str) for entry in allow):
        errors.append(".claude/settings.json: permissions.allow must be a list of strings")
        return
    for entry in allow:
        if entry not in ALLOWED_PERMISSIONS:
            errors.append(
                f".claude/settings.json: permission not in the reviewed allowlist: {entry!r}. "
                "Pre-approved permissions run without prompting on every fork. If this entry "
                "is intentional, add it to ALLOWED_PERMISSIONS in tools/security_guards.py in "
                "the same PR so the widening is explicit and reviewable."
            )
    for entry in ALLOWED_PERMISSIONS - set(allow):
        # Not an error: settings may legitimately drop an entry. But an
        # allowlist entry that no longer exists should be pruned.
        print(f"note: allowlisted permission not present in settings.json: {entry!r}")


def check_gitignore() -> None:
    path = ROOT / ".gitignore"
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as exc:
        errors.append(f".gitignore: unreadable: {exc}")
        return
    rules = set(lines)
    for rule in REQUIRED_IGNORE_RULES:
        if rule not in rules:
            errors.append(
                f".gitignore: required rule missing: {rule!r}. This rule keeps fork users "
                "from committing per-review data or connector API-key secrets. If the rule "
                "moved or was renamed intentionally, update REQUIRED_IGNORE_RULES in "
                "tools/security_guards.py in the same PR."
            )
    for line in lines:
        if line.startswith("!") and line not in ALLOWED_IGNORE_NEGATIONS:
            errors.append(
                f".gitignore: negation rule not in the reviewed allowlist: {line!r}. "
                "A negation re-includes a path an earlier rule excluded and can silently "
                "re-expose ignored data (a required ignore rule stays present but stops "
                "taking effect). If this negation is intentional, add it to "
                "ALLOWED_IGNORE_NEGATIONS in tools/security_guards.py in the same PR."
            )


def main() -> int:
    check_permissions()
    check_gitignore()
    if errors:
        print(f"security_guards: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("security_guards: OK (permissions allowlist, hooks allowlist, gitignore rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
