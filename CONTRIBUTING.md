# Contributing

Thanks for considering a contribution! This repo has a deliberate, narrow philosophy, and most declined PRs are well-executed work that simply didn't know about it. Read this first; it will save you effort and tell you where your work will land best.

## The one rule everything follows from

**This repo is a universal template.** Researchers fork it and point it at their own review topic. Upstream stays topic-agnostic, reviewer-agnostic, and Claude Code-native. The corollary: a contribution is judged by fit to this rule first, execution quality second. Well-built but off-policy still gets declined (kindly, with reasons).

See [docs/ROADMAP.md](docs/ROADMAP.md) for the planned direction — a PR that gets ahead of a milestone described there, rather than filling it in as scoped, is more likely to be declined for fit even if well executed.

## What gets merged

- **Connector additions and fixes.** A new source connector that follows the fixed `{meta, results}` JSON contract (see `connectors/_shared.py`), or a fix to an existing one (a stale API parameter, a rate-limit change, incorrect pagination), is squarely in scope.
- **Methodology-file fixes.** Corrections to the PRISMA-item mapping, the eligibility-gate logic, the RoB1/GRADE criteria, or the manuscript drafting conventions — anything that makes the methodology more accurate or more faithful to the PRISMA 2020 statement.
- **Screening and synthesis robustness improvements.** Dedup edge cases (e.g. a preprint/peer-reviewed-version merge that currently fails), a heterogeneity decision-rule bug, a pooling-math correction, a screening sheet import that mishandles a valid CSV shape — all in scope, especially with a failing case demonstrated.

## What gets declined

- **A specific reviewer's `results/<TOPIC>/` data.** The template ships an empty, gitignored `results/` structure. Your actual review's protocol, records, screening decisions, and manuscript belong in your fork, never upstream.
- **A paid-access-only connector that serves one institution.** A connector hardcoded to one university's Scopus/Web of Science proxy has no principled stopping point — it belongs in a fork, exactly the way a market-specific job-portal skill belongs in a fork of a job-search tool. `/litreview-add-source` exists precisely so you can build this for yourself without needing it upstream.
- **Speculative infrastructure.** Complexity must be argued from a problem that exists, not one that might.
- **Alternative-harness ports and duplicate workflow sources.** The Markdown command/skill specs under `.claude/` ARE the implementation; a second copy (another agent CLI, an orchestration layer, a wrapper command) drifts from the first the moment either changes. Claude Code is the reference runtime this repo is verified on; `.agents/skills/` already gives other runtimes a discoverable, non-duplicated pointer to the connector CLIs (see [AGENTS.md](AGENTS.md)).
- **Kitchen-sink PRs.** One concern per PR.

## Before opening a PR

- Start from an issue or a clear problem statement — what's broken, or what's missing, and why it matters to a reviewer using this template.
- For a bug: include a minimal reproduction (the documented CLI invocation, or a real connector fixture) — not a synthetic value fed straight to a function.
- One concern per PR. A connector fix and a doc typo are two PRs.
- No unrelated reformatting riding along with a functional change — it makes the real diff harder to review and revert.
- A methodology change (eligibility-gate wording, RoB1/GRADE criteria, PRISMA-item mapping) must cite the primary source or guideline it's correcting toward — "this reads more clearly" isn't a methodology argument, "the 2019 RoB1 guidance says X" is.

## The CI verification bar

Every PR is expected to pass, and to be checked against, whether it can actually move these from red to green (not just remain green) — this is the exact job list `.github/workflows/ci.yml` runs:

```bash
python3 -m unittest discover -s tests -v
python3 tools/lint_skills.py
python3 tools/check_connector_contract.py
python3 tools/security_guards.py
python3 tools/check_framework_version.py
```

- `python3 -m unittest discover -s tests -v` runs the fixture-based connector, dedup, and synthesis tests — no live network calls, ever, in CI; a connector making a real HTTP request in a test is a bug in that test, not a feature.
- `tools/lint_skills.py` lints skill/command frontmatter and structure.
- `tools/check_connector_contract.py` asserts every connector module still emits the fixed `{meta, results}` shape described in the architecture plan.
- `tools/security_guards.py` fails a PR that widens `.claude/settings.json`'s pre-approved-permission allowlist or weakens the `results/**` gitignore rule without the corresponding update to the guard itself — see `SECURITY.md`.
- `tools/check_framework_version.py` fails a PR that edits a bundled PRISMA methodology file (`.claude/skills/{review-protocol,keyword-expansion,screening-assistant,quality-appraisal,prisma-manuscript}/`) without bumping its declared `framework_version`.

Also worth running if you touched `synthesis/`: its two modules carry their own runnable self-checks —

```bash
python3 synthesis/run_synthesis.py
python3 synthesis/plots.py
```

## Claims get verified

Reviews here are empirical. A bug report is reproduced on the real path before a fix is considered — the documented CLI invocation or a real connector fixture, not a synthetic value fed straight to a function. State the failing case and how to reproduce it; put connector/tool tests under `tests/`.

## Contributor checklists

**Connector PR:** follows the `{meta, results}` contract in `connectors/_shared.py`; `--out` writes go through `write_output`/`tools/path_policy.py`, never a raw `open(path, "w")`; a fixture test exercises the change without a live call.

**Methodology PR:** cites the primary source/guideline; bumps `framework_version` in the edited skill file's frontmatter; states which existing reviews (if any) would need re-screening or re-extraction under the corrected criteria.

**Documentation PR:** links to the owning document instead of restating its rules (README points at USER_GUIDE/CONTRIBUTING/SECURITY/AGENTS rather than duplicating them); doesn't introduce an unqualified claim of full automation or publication-readiness.

**Security-sensitive PR** (permissions, path-writing, credentials, outbound network requests, web fetching, local review-data handling, `.gitignore` rules): call out the specific impact in the PR description and read `SECURITY.md` first — these changes get read more slowly, on purpose.

## Pull request description

```markdown
- Problem and scope:
- Evidence/reproduction:
- Change:
- Tests run:
- Documentation changed:
- Security or methodology impact:
```

## Building for your own review? You don't need a PR for that

1. Fork the repo and run `/litreview-init "your topic"` — everything your review produces lands under `results/<your-topic>/`, gitignored by default.
2. Need a source the six shipped connectors don't cover? Run `/litreview-add-source` — it scaffolds a connector matching the shipped contract, and `/litreview-search` picks it up automatically via `connectors/registry.py`.
3. Institutional-access connector (Scopus, Web of Science)? Same command, same contract, credentials via environment variable only — it stays in your fork.

Instance-specific reviews and institution-specific connectors are genuinely valuable — they just live in forks, where their maintainers can test them and their reviewers can use them without upstream carrying data or access requirements it can't verify.
