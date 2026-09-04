#!/usr/bin/env python3
"""Lint the repo's skill and command files.

Run from anywhere: python3 tools/lint_skills.py

Checks:
- Every SKILL.md under .claude/skills/*/ and .agents/skills/*/ has YAML
  frontmatter that parses, with non-empty `name` and `description` keys.
- Every .claude/commands/*.md file exists (the glob finding zero is itself a
  failure — it means the glob root moved) and is non-empty.

Adapted from references/ai-job-search/tools/lint_skills.py: dropped the
`allowed-tools: Bash(bun run <path>)` file-existence check, which was
TypeScript/Bun-portal-specific (this repo's connectors are one importable
Python package, invoked as `python3 -m connectors.<source>`, not per-file
paths to check for existence) and the "# /<name> title" check on command
files, since this repo's commands open with an `allowed-tools` YAML
frontmatter block before the title (ai-job-search's don't).

Exit code 0 on success, 1 with a failure list otherwise.
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("lint_skills.py requires PyYAML: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def check_skill(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"{rel(path)}: missing YAML frontmatter (file must start with ---)")
        return
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"{rel(path)}: unterminated YAML frontmatter")
        return
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        errors.append(f"{rel(path)}: frontmatter is not valid YAML: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(f"{rel(path)}: frontmatter did not parse to a mapping")
        return
    for key in ("name", "description"):
        value = data.get(key)
        if not value or not str(value).strip():
            errors.append(f"{rel(path)}: frontmatter missing required key '{key}'")


def check_command(path: Path) -> None:
    if path.stat().st_size == 0:
        errors.append(f"{rel(path)}: command file is empty")
        return
    if not path.read_text(encoding="utf-8").strip():
        errors.append(f"{rel(path)}: command file is whitespace-only")


def check_settings() -> None:
    path = ROOT / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f".claude/settings.json: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(".claude/settings.json: expected top-level JSON value to be an object")
        return
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append(".claude/settings.json: expected permissions to be an object")
        return
    if not isinstance(permissions.get("allow"), list):
        errors.append(".claude/settings.json: expected permissions.allow to be a list")


def main() -> int:
    skills = sorted(ROOT.glob(".claude/skills/*/SKILL.md")) + sorted(ROOT.glob(".agents/skills/*/SKILL.md"))
    commands = sorted((ROOT / ".claude" / "commands").glob("*.md"))
    if not skills:
        errors.append("no SKILL.md files found - glob roots are wrong or the tree moved")
    if not commands:
        errors.append("no command files found under .claude/commands/")

    for skill in skills:
        check_skill(skill)
    for command in commands:
        check_command(command)
    check_settings()

    if errors:
        print(f"lint_skills: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"lint_skills: OK ({len(skills)} skills, {len(commands)} commands, settings.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
