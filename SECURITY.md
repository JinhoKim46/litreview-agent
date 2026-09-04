# Security Policy

## Reporting a vulnerability

Once this repo is hosted on GitHub, please report security findings privately via GitHub private vulnerability reporting rather than a public issue. Until then, or if that channel is unavailable, open a public issue that describes the *class* of problem without a working exploit, and note that you have details to share privately with a maintainer.

## Threat model, honestly stated

This is an agentic workflow, but its risk surface is different from a CV-or-personal-data assistant: there is no analogue here to a candidate's salary expectations or employment history. What this pipeline handles instead is **untrusted external content treated as evidence to weigh, not instructions to follow** — abstracts and full text fetched from six external APIs (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv), any one of which could in principle return adversarially crafted text. What the framework does about it:

- **Untrusted-input rules.** `/prisma-screen`, `/prisma-extract`, and `/prisma-report` treat every fetched abstract and full-text passage as data to evaluate, never as instructions to follow. A crafted abstract (e.g. one containing text designed to look like a system instruction) must never steer a screening decision, an extraction value, or a manuscript claim. Screening and eligibility decisions remain the reviewer's, by design — the pipeline drafts a suggestion, the human decides.
- **No auto-fetching of embedded URLs.** No URL found inside fetched abstract or full-text content is ever auto-fetched. The only URLs the pipeline follows are ones the reviewer supplied directly (a source connector's own API endpoint, or a reference the reviewer asked to verify).
- **Reference verification is independent, never self-reported.** Every citation that ends up in the manuscript is checked via an independent WebSearch/WebFetch lookup against a real, separately-located source — never trusted merely because a fetched abstract or full-text document claims a related paper exists. A hallucinated or fabricated reference is a reporting-integrity failure the pipeline is built to catch, not permit.
- **Permission allowlist.** `.claude/settings.json` pre-approves only the specific connector-module invocations and maintainer tool scripts the pipeline needs (see the file itself for the exact list). A future `tools/security_guards.py` CI job is intended to fail any PR that widens this allowlist or weakens the `results/**` gitignore rule without justification. Note the allowlist governs Bash commands — the model's native WebSearch/WebFetch tools sit outside it, which is exactly why the instruction-level rules above exist independently.
- **No personal-data boundary to enforce.** Unlike frameworks that handle a user's CV or salary history, this pipeline's `results/<TOPIC>/` state is bibliographic and methodological (search queries, screening decisions, extracted study data) — sensitive to a reviewer's unpublished work in progress, but not personal data in the CV/salary sense. It is still gitignored by default so an in-progress review isn't accidentally published before the reviewer intends to share it.

Instruction-level defenses raise the bar; they are not a sandbox. If a review's search touches a source you don't fully trust, read what the agent fetched and what it wrote into the manuscript before treating either as final.

## Scope notes

- Connector CLIs make live requests only when a reviewer runs a pipeline command that invokes them; CI is intended to never make live network calls.
- A connector added via `/prisma-add-source` that lives only in a fork is not covered by this policy — review any connector code you copy from another fork before running it, the same way you would review any other third-party script.
