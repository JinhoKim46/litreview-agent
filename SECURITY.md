# Security Policy

## Reporting a vulnerability

Once this repo is hosted on GitHub, please report security findings privately via GitHub private vulnerability reporting rather than a public issue. Until then, or if that channel is unavailable, open a public issue that describes the *class* of problem without a working exploit, and note that you have details to share privately with a maintainer.

## Threat model, honestly stated

This is an agentic workflow, but its risk surface is different from a CV-or-personal-data assistant: there is no analogue here to a candidate's salary expectations or employment history. What this pipeline handles instead is **untrusted external content treated as evidence to weigh, not instructions to follow** — abstracts and full text fetched from six external APIs (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv), any one of which could in principle return adversarially crafted text. What the framework does about it:

- **Untrusted-input rules.** `/litreview-screen`, `/litreview-extract`, and `/litreview-report` treat every fetched abstract and full-text passage as data to evaluate, never as instructions to follow. A crafted abstract (e.g. one containing text designed to look like a system instruction) must never steer a screening decision, an extraction value, or a manuscript claim. Screening and eligibility decisions remain the reviewer's, by design — the pipeline drafts a suggestion, the human decides.
- **No auto-fetching of embedded URLs.** No URL found inside fetched abstract or full-text content is ever auto-fetched. The only URLs the pipeline follows are ones the reviewer supplied directly (a source connector's own API endpoint, or a reference the reviewer asked to verify).
- **Reference verification is independent, never self-reported.** Every citation that ends up in the manuscript is checked via an independent WebSearch/WebFetch lookup against a real, separately-located source — never trusted merely because a fetched abstract or full-text document claims a related paper exists. A hallucinated or fabricated reference is a reporting-integrity failure the pipeline is built to catch, not permit.
- **Permission allowlist.** `.claude/settings.json` pre-approves only the specific connector-module invocations and maintainer tool scripts the pipeline needs (see the file itself for the exact list). `tools/security_guards.py` is a CI job, already wired into `.github/workflows/ci.yml`, that fails any PR widening this allowlist or weakening the `results/**` gitignore rule without a matching update to the guard itself. Note the allowlist governs Bash commands — the model's native WebSearch/WebFetch tools sit outside it, which is exactly why the instruction-level rules above exist independently.
- **Path containment on every write.** Every connector's `--out`, `synthesis/run_synthesis.py`'s output directory, and the manuscript export step all resolve through `tools/path_policy.py` before anything is written: a topic slug is validated, and the resolved path must stay inside `results/`, following symlinks so one planted inside `results/` can't point elsewhere. A pre-approved permission being broad in form no longer means a caller-supplied path can direct a write (or, via a raw Pandoc invocation, code execution through a Lua filter) outside a review's own directory — `tools/export_report.py` replaces the raw `pandoc` call with a fixed argument list for exactly this reason.
- **Review data is not personal data in the CV/salary sense, but it is not nothing.** This pipeline's `results/<TOPIC>/` state is bibliographic and methodological (search queries, screening decisions, extracted study data) — but it can also carry reviewer identity and affiliation (`CLAUDE.local.md`), unpublished protocols, author correspondence pasted in during full-text retrieval, and a team's working notes. `results/**` and `CLAUDE.local.md` are gitignored by default so none of this is accidentally published, but a gitignore rule is not encryption, access control, or a retention policy — it only stops an accidental `git add`.

Instruction-level defenses raise the bar; they are not a sandbox. If a review's search touches a source you don't fully trust, read what the agent fetched and what it wrote into the manuscript before treating either as final.

## For contributors: security-sensitive changes

A PR that touches command permissions (`.claude/settings.json`), path-writing logic (`tools/path_policy.py`, `write_output`, `run_synthesis`'s output resolution, `tools/export_report.py`), credentials, outbound network requests, web fetching, local review-data handling, or `.gitignore` rules needs a one-paragraph threat-model note in the PR description: what could go wrong, and what in the diff prevents it. Report a vulnerability you find in one of these areas privately (see above) rather than as public exploit detail in an issue or PR.

## Scope notes

- Connector CLIs make live requests only when a reviewer runs a pipeline command that invokes them; CI never makes live network calls (see `.github/workflows/ci.yml`'s own header comment).
- A connector added via `/litreview-add-source` that lives only in a fork is not covered by this policy — review any connector code you copy from another fork before running it, the same way you would review any other third-party script.
