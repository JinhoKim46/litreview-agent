---
framework_version: 1.0.0
---

# Agent Guidelines: litreview-agent

This workspace runs a systematic review and meta-analysis pipeline that follows the PRISMA 2020 reporting guideline: search connectors, deduplication, screening, extraction, statistical synthesis, and manuscript generation. See [docs/ROADMAP.md](docs/ROADMAP.md) for where this is headed beyond that one method.

## Thin-Pointer Design (Single Source of Truth)

To prevent duplication and drift across different AI agent runtimes (Claude Code, Codex, Antigravity, Gemini CLI, etc.), this workspace uses a unified thin-pointer design. All agent runtimes should load the canonical specifications and reviewer profile from the files and directories below — never copy their content elsewhere, since a second copy drifts from the first the moment either changes.

1. **Reviewer profile and persona:**
   - The reviewer's field of research, prior work, target journals, and citation style are defined in `CLAUDE.local.md` (gitignored; template at [CLAUDE.local.md.example](CLAUDE.local.md.example)), pulled into [CLAUDE.md](CLAUDE.md) via an `@CLAUDE.local.md` import.
2. **Canonical workflow specifications:**
   - The step-by-step instructions and triggers for every pipeline stage (init, search, screen, extract, synthesize, report, status, add-source, reset) are defined under [.claude/commands/](.claude/commands/) and [.claude/skills/](.claude/skills/). Treat these as the single source of truth — do not duplicate their rules elsewhere.
3. **Search connector pointers:**
   - Search-connector CLIs live under [.agents/skills/](.agents/skills/) in the portable Agent Skills format (one `SKILL.md` per source: OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv). Codex and Antigravity discover these automatically. Each `SKILL.md` is a thin pointer that documents invoking `python3 -m connectors.<source> search ...` — the actual HTTP/retry/parsing logic lives once, in [connectors/](connectors/), never duplicated per runtime.
