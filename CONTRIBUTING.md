# Contributing

Thanks for considering a contribution! This repo has a deliberate, narrow philosophy, and most declined PRs are well-executed work that simply didn't know about it. Read this first; it will save you effort and tell you where your work will land best.

## The one rule everything follows from

**This repo is a universal template.** Researchers fork it and point it at their own review topic. Upstream stays topic-agnostic, reviewer-agnostic, and Claude Code-native. The corollary: a contribution is judged by fit to this rule first, execution quality second. Well-built but off-policy still gets declined (kindly, with reasons).

## What gets merged

- **Connector additions and fixes.** A new source connector that follows the fixed `{meta, results}` JSON contract (see `connectors/_shared.py`), or a fix to an existing one (a stale API parameter, a rate-limit change, incorrect pagination), is squarely in scope.
- **Methodology-file fixes.** Corrections to the PRISMA-item mapping, the eligibility-gate logic, the RoB2/GRADE criteria, or the manuscript drafting conventions — anything that makes the methodology more accurate or more faithful to the PRISMA 2020 statement.
- **Screening and synthesis robustness improvements.** Dedup edge cases (e.g. a preprint/peer-reviewed-version merge that currently fails), a heterogeneity decision-rule bug, a pooling-math correction, a screening sheet import that mishandles a valid CSV shape — all in scope, especially with a failing case demonstrated.

## What gets declined

- **A specific reviewer's `results/<TOPIC>/` data.** The template ships an empty, gitignored `results/` structure. Your actual review's protocol, records, screening decisions, and manuscript belong in your fork, never upstream.
- **A paid-access-only connector that serves one institution.** A connector hardcoded to one university's Scopus/Web of Science proxy has no principled stopping point — it belongs in a fork, exactly the way a market-specific job-portal skill belongs in a fork of a job-search tool. `/prisma-add-source` exists precisely so you can build this for yourself without needing it upstream.
- **Speculative infrastructure.** Complexity must be argued from a problem that exists, not one that might.
- **Alternative-harness ports and duplicate workflow sources.** The Markdown command/skill specs under `.claude/` ARE the implementation; a second copy (another agent CLI, an orchestration layer, a wrapper command) drifts from the first the moment either changes. Claude Code is the reference runtime this repo is verified on; `.agents/skills/` already gives other runtimes a discoverable, non-duplicated pointer to the connector CLIs (see [AGENTS.md](AGENTS.md)).
- **Kitchen-sink PRs.** One concern per PR.

## The CI verification bar

Every PR is expected to pass, and to be checked against, whether it can actually move these from red to green (not just remain green):

```bash
python -m unittest discover
python3 tools/lint_skills.py
python3 tools/check_connector_contract.py
```

`python -m unittest discover` runs the fixture-based connector, dedup, and pooling tests — no live network calls, ever, in CI. `tools/lint_skills.py` lints skill/command frontmatter and structure. `tools/check_connector_contract.py` asserts every connector module still emits the fixed `{meta, results}` shape described in the architecture plan.

## Claims get verified

Reviews here are empirical. A bug report is reproduced on the real path before a fix is considered — the documented CLI invocation or a real connector fixture, not a synthetic value fed straight to a function. State the failing case and how to reproduce it; put connector/tool tests under `tests/`.

## Building for your own review? You don't need a PR for that

1. Fork the repo and run `/prisma-init "your topic"` — everything your review produces lands under `results/<your-topic>/`, gitignored by default.
2. Need a source the six shipped connectors don't cover? Run `/prisma-add-source` — it scaffolds a connector matching the shipped contract, and `/prisma-search` picks it up automatically via `connectors/registry.py`.
3. Institutional-access connector (Scopus, Web of Science)? Same command, same contract, credentials via environment variable only — it stays in your fork.

Instance-specific reviews and institution-specific connectors are genuinely valuable — they just live in forks, where their maintainers can test them and their reviewers can use them without upstream carrying data or access requirements it can't verify.
