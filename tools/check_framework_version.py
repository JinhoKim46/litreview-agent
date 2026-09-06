#!/usr/bin/env python3
"""CI check: methodology files can't change without a `framework_version` bump.

Watches every *.md under every `.claude/skills/<name>/` directory (a glob,
not a hardcoded list -- docs/PLAN.md M1: a new skill is watched automatically,
without a second PR to add it here) for a `framework_version` frontmatter
field (semver-shaped: N.N.N), failing CI if a methodology file changed (per
`git diff <base>..HEAD`) without a version bump. Also watches every
`methods/*.json` and `packs/*.json` manifest's own top-level `"version"`
field the same way (docs/PLAN.md M1's method-manifest architecture) --
`methods/_schema.json` and `methods/_routing.json` are schema/routing
infrastructure, not versioned manifests, so they're excluded by name.

Not running inside a git repo (a fresh export, or a shallow clone with no
base ref) degrades to just checking the field's presence, with a printed
note explaining why the diff check was skipped -- this is a real repo-state
distinction, not a hidden failure mode.

Adapted from references/ai-job-search/tools/check_framework_version.py: that
version watches a single flat skill directory
(.claude/skills/job-application-assistant/*.md) plus AGENTS.md; this repo's
methodology lives in several *skill directories*, each with nested reference
files (e.g. review-protocol/01-question-frameworks.md), so the glob here is
`.claude/skills/<skill>/**/*.md` per watched skill instead of one `*.md` glob.

Exit code 0 on success, 1 with a failure list otherwise.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Manifest globs watched the same way as skill Markdown, but checked for a
# top-level JSON "version" field instead of YAML frontmatter (docs/PLAN.md
# M1). No file needs to exist yet under either glob for this to pass --
# packs/ ships no manifest until M3.
WATCHED_MANIFEST_GLOBS = ["methods/*.json", "packs/*.json"]
MANIFEST_NON_VERSIONED_FILES = {"_schema.json", "_routing.json"}


def watched_skills() -> list[str]:
    skills_dir = ROOT / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(p.name for p in skills_dir.iterdir() if p.is_dir())

# Reference files reused *verbatim* from an externally CC-BY-licensed source
# (architecture plan §9/§10: "prisma-2020-checklist.md and flow-diagram.md
# ... copied verbatim, CC BY 4.0 header preserved"). Stamping our own
# framework_version onto a document whose whole point is to stay byte-for-byte
# identical to Page et al. 2021 would be adding content that isn't in the
# original -- exempt these by name rather than let the recursive **/*.md
# watch force a version field onto them. Every other *.md under a watched
# skill (including its other numbered reference files) is original framework
# methodology and must carry the field.
EXEMPT_FROM_VERSION = {
    ".claude/skills/prisma-manuscript/references/prisma-2020-checklist.md",
    ".claude/skills/prisma-manuscript/references/flow-diagram.md",
    ".claude/skills/keyword-expansion/references/prisma-s-2021-checklist.md",
    ".claude/skills/prisma-manuscript/references/swim-2020-checklist.md",
}


def framework_files() -> list[Path]:
    files: list[Path] = []
    for skill in watched_skills():
        skill_dir = ROOT / ".claude" / "skills" / skill
        for path in sorted(skill_dir.rglob("*.md")):
            if str(path.relative_to(ROOT)).replace(os.sep, "/") not in EXEMPT_FROM_VERSION:
                files.append(path)
    return files


def manifest_files() -> list[Path]:
    files: list[Path] = []
    for pattern in WATCHED_MANIFEST_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.name not in MANIFEST_NON_VERSIONED_FILES:
                files.append(path)
    return files


def parse_manifest_version(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def run_git(args: list[str]) -> tuple[int, str, str]:
    res = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


def inside_git_repo() -> bool:
    rc, out, _ = run_git(["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out.strip() == "true"


def get_base_commit() -> str | None:
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        for candidate in (f"origin/{base_ref}", base_ref):
            rc, _, _ = run_git(["rev-parse", "--verify", candidate])
            if rc == 0:
                return candidate

    if os.environ.get("GITHUB_ACTIONS"):
        rc, _, _ = run_git(["rev-parse", "--verify", "HEAD~1"])
        if rc == 0:
            return "HEAD~1"

    rc, _, _ = run_git(["rev-parse", "--verify", "HEAD"])
    if rc == 0:
        return "HEAD"

    return None


def parse_frontmatter(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    return data


FRONTMATTER_VERSION_LINE_RE = re.compile(r"^framework_version\s*:")
MANIFEST_VERSION_LINE_RE = re.compile(r'^"version"\s*:')


def has_non_trivial_changes(file_path: Path, base_commit: str, version_line_re: re.Pattern = FRONTMATTER_VERSION_LINE_RE) -> bool:
    rel_path = str(file_path.relative_to(ROOT))
    rc, stdout, _ = run_git(["diff", "-U0", base_commit, "--", rel_path])
    if rc != 0:
        return True  # e.g. untracked/new file -- diff failing counts as a change

    meaningful_changes = 0
    version_changed = False
    for line in stdout.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            content = line[1:].strip()
            if not content or content == "---":
                continue
            if version_line_re.match(content):
                version_changed = True
                continue
            meaningful_changes += 1

    if version_changed:
        return False
    return meaningful_changes > 0


def main() -> int:
    errors: list[str] = []
    files = framework_files()
    if not files:
        errors.append(
            "no methodology files found under any watched .claude/skills/<name>/ "
            "directory - glob roots are wrong or the tree moved"
        )

    for path in files:
        rel_path = str(path.relative_to(ROOT))
        fm = parse_frontmatter(path)
        version = fm.get("framework_version")
        if not version:
            errors.append(f"{rel_path}: missing 'framework_version' in frontmatter")
        elif not VERSION_RE.match(version):
            errors.append(
                f"{rel_path}: 'framework_version' is {version!r}, expected semver N.N.N"
            )

    # methods/*.json and packs/*.json manifests (docs/PLAN.md M1) -- an empty
    # result here is expected (no pack ships until M3) and not an error, unlike
    # the skills glob above, which should never legitimately be empty.
    manifests = manifest_files()
    for path in manifests:
        rel_path = str(path.relative_to(ROOT))
        version = parse_manifest_version(path)
        if not version:
            errors.append(f"{rel_path}: missing top-level 'version' field")
        elif not VERSION_RE.match(version):
            errors.append(f"{rel_path}: 'version' is {version!r}, expected semver N.N.N")

    if not inside_git_repo():
        print(
            "check_framework_version: not running inside a git repository "
            "(fresh export or shallow clone with no history) - degrading to a "
            "presence-only check; version-bump-on-change is skipped."
        )
    else:
        base_commit = get_base_commit()
        if base_commit:
            print(f"Comparing HEAD against base commit: {base_commit}")
            for path in files:
                rel_path = str(path.relative_to(ROOT))
                if "framework_version" not in parse_frontmatter(path):
                    continue  # already reported above
                if has_non_trivial_changes(path, base_commit):
                    errors.append(
                        f"{rel_path}: modified without bumping 'framework_version'. "
                        "Please update the version in the frontmatter."
                    )
            for path in manifests:
                rel_path = str(path.relative_to(ROOT))
                if not parse_manifest_version(path):
                    continue  # already reported above
                if has_non_trivial_changes(path, base_commit, version_line_re=MANIFEST_VERSION_LINE_RE):
                    errors.append(f"{rel_path}: modified without bumping its 'version' field.")
        else:
            print(
                "No base commit found (e.g. initial commit or shallow clone "
                "without base branch). Skipping diff checks."
            )

    if errors:
        print(f"check_framework_version: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"check_framework_version: OK ({len(files)} methodology files, {len(manifests)} method/pack manifests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
