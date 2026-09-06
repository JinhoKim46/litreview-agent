---
name: review-protocol
description: "Elicit and record a systematic review's protocol: the research-question framework (PICO/PICo/SPIDER/other), eligibility criteria, and scope. Use whenever the user starts a new systematic review or meta-analysis, runs /prisma-init, mentions 'PICO', 'PICo', 'SPIDER', 'research question framework', 'eligibility criteria', 'inclusion criteria', 'exclusion criteria', 'protocol', 'PROSPERO', or asks 'is this study eligible' / 'should I include this paper' / 'does this study pass screening'. Also trigger mid-review whenever a screening or extraction step needs an eligibility ruling on a specific study, or when scope needs to change (e.g. adding a language, narrowing a population) partway through a review. Covers framework selection and elicitation questions plus the hard-gate-before-scoring eligibility check; it does not cover keyword expansion (see keyword-expansion) or manuscript drafting (see prisma-manuscript)."
framework_version: 1.6.0
---

# Review Protocol

This skill turns a systematic-review idea into a written, machine-readable protocol: a research-question framework record and a set of hard eligibility gates. It is the first thing `/prisma-init` runs, and the thing `/prisma-screen` and `/prisma-extract` call back into whenever a specific study needs an eligibility ruling.

Read the reference files as needed:
- `01-question-frameworks.md` — PICO/PICo/SPIDER (and related) elicitation prompts, and how to pick the right one for the review type.
- `02-eligibility-criteria.md` — the hard-gate-before-scoring pattern: population, study design, publication type, date range, and language-of-publication gates, run before any study is scored or screened on relevance.

## Before you begin

Check whether `results/<TOPIC>/protocol.json` already exists. If it does, read it and treat this as an *update* to an existing protocol (confirm what's changing) rather than a fresh elicitation — never silently overwrite recorded eligibility criteria without telling the user what changed and why, since screening decisions already made under the old criteria may need re-review.

## Phase 1: Two-path interview

Offer the user two paths up front, exactly as `slr-prisma`'s Phase 1 does — this review may already have a protocol document sitting somewhere else.

### Path A: Upload existing documents

Ask whether the user has a research proposal, a PROSPERO registration, a protocol paper, a draft manuscript, or notes from a previous review attempt. If they share one:

1. Read it with the appropriate tool for its format (PDF, DOCX, plain text).
2. Extract what it says about: research question/framework, population/exposure/comparator/outcome details, study designs eligible, publication types eligible, date range, language(s), and any other stated inclusion/exclusion criteria.
3. Present a summary of what was extracted and ask the user to confirm, correct, or fill gaps — never assume an extracted field is right without the user seeing it stated back.
4. If multiple documents are provided, cross-reference them and flag contradictions explicitly (e.g. "the proposal says 2015–2024, the draft manuscript says 2018–2024 — which is current?") rather than picking one silently.

### Path B: Conversational interview

If no documents are provided, or after extracting what's available, gather the rest conversationally. Work through it in 2–3 grouped rounds, not a single wall of questions:

1. **Big picture first**: working title, the review's objective in one or two sentences, review type (intervention effectiveness, diagnostic accuracy, qualitative, prognosis, scoping-turned-systematic, etc.) — this determines which framework applies (see `01-question-frameworks.md`). Also ask the reviewer to classify the review's **subject domain**, via `AskUserQuestion`, since this decides `keyword-expansion`'s MeSH-vs-free-text default (`01-expansion-methodology.md` §2) and a wrong guess here is exactly the kind of mix-up a reviewer has to catch and correct later:
   - `clinical_medicine` — patient-facing/clinical/hospital medicine: diagnosis, treatment, epidemiology of disease in human or animal patients.
   - `biomedical_technical` — a biomedical-*adjacent* technical/engineering field (imaging reconstruction, biosensor design, bioinformatics tooling, etc.) where a controlled biomedical vocabulary exists but isn't the primary way this literature is indexed or found.
   - `non_biomedical` — no biomedical controlled vocabulary applies at all.

   Pre-check a default option from a quick heuristic (e.g. the reviewer's own field-of-research line in `CLAUDE.local.md`) but always show the question — never infer this silently, since "biomedical-sounding" and "clinical medicine" are not the same thing (an MRI-reconstruction review is biomedical-adjacent engineering, not clinical medicine, even though both mention imaging/patients).
2. **Framework-specific elicitation**: run the prompts from `01-question-frameworks.md` for the chosen framework.
3. **Eligibility gates**: run the elicitation in `02-eligibility-criteria.md` — population match, study design, publication type, date range, and language-of-publication. Get explicit values for each; do not leave a gate undefined and call the protocol complete.
4. **Scope**: global or national/regional (`mode: global|national`); if national, which region and whether keyword translation will be used. Flag known coverage gaps up front if the reviewer already knows a chosen source has weak coverage for the target region/language (e.g. "PubMed has weak Korean-language coverage") — this seeds `protocol.json.scope.coverage_gaps` rather than being discovered as a surprise later.
5. **Quantitative synthesis plan** (only if the reviewer expects to pool any outcome statistically): ask whether they anticipate several included studies reporting the same measurement for the same comparison, such that pooling would make sense. If yes:
   - Ask which pooling model is primary — **fixed-effect** (studies assumed to estimate one true effect; use when studies are clinically/methodologically similar) or **random-effects** (studies assumed to estimate related but different true effects; use when meaningful between-study variation is expected) — and a one-sentence justification. Never derive this choice from data that doesn't exist yet, and never suggest it will be decided later from the pooled studies' own heterogeneity statistics — that is exactly the correctness defect this elicitation step exists to prevent (`synthesis/heterogeneity.py`'s module docstring). Offer, but don't require, an initial guess of the minimum number of studies (`k_min`, default 2) they want before trusting a pooled estimate.
   - Record the answer immediately as `results/<TOPIC>/synthesis_plan.json` (schema: `schemas/synthesis_plan.schema.json`), **before any search runs** — `signed_at` must be the actual current timestamp, since `/prisma-synthesize` compares it against the review's first search run to confirm the model really was prespecified rather than added after study selection (PRISMA 2020 item 13a-c and item 24c).
   - If the reviewer isn't sure yet, don't write the file — `/prisma-synthesize` will refuse to run without either this file or an explicit one-off `--model` override, and re-running `/prisma-init` later to add it is always available.

Use bounded-choice tooling (e.g. `AskUserQuestion`) where the options are a fixed list (framework choice, study-design gate values); use open questions for things like the actual research question text and free-text population description.

Once you have enough to write a complete protocol, **confirm the plan with the user before persisting it** — read the assembled `protocol.json` fields back in plain language and get an explicit go-ahead.

## Phase 2: Persist the protocol

Write (or update) `results/<TOPIC>/protocol.json` with at minimum:

```json
{
  "title": "...",
  "objective": "...",
  "field_domain": "clinical_medicine",
  "framework": "PICO",
  "framework_fields": { "population": "...", "intervention": "...", "comparator": "...", "outcome": "..." },
  "review_type": "intervention_effectiveness",
  "registration": { "status": "unregistered", "id": null },
  "eligibility": {
    "population": { "criterion": "...", "gate": "hard" },
    "study_design": { "included": ["RCT", "quasi-experimental"], "gate": "hard" },
    "publication_type": { "included": ["peer-reviewed journal article"], "excluded": ["preprint-only", "conference abstract"], "gate": "hard" },
    "date_range": { "from": "2015-01-01", "to": null, "gate": "hard" },
    "language": { "included": ["English"], "gate": "hard", "translation_used": false }
  },
  "scope": {
    "mode": "global",
    "region": null,
    "translation_used": false,
    "translation_languages": [],
    "coverage_gaps": []
  },
  "method": {
    "id": "systematic_review", "version": "1.0.0", "synthesis_family": null,
    "profile_flags": [], "modes": [], "pack": null, "output_profiles": [],
    "routing": { "table_version": "1.0.0", "answers": {}, "q0": null, "recommended_id": "systematic_review", "chosen_id": "systematic_review", "override_reason": null, "fallback_reason": null }
  }
}
```

`method` is never elicited by this skill — it's decided by `/prisma-init`'s own Step 0.5 routing interview (`tools/route.py`) before this skill ever runs, and the caller passes the whole block along for this skill to write verbatim (see `schemas/protocol_method.schema.json`). If a caller invokes this skill directly without a routing result (rare — every documented path goes through `/prisma-init`), omit the `method` key entirely rather than inventing one; `tools/method.py` treats its absence as `"systematic_review"`, `recorded: false` (docs/PLAN.md M1's migration path), not an error.

`field_domain` is one of `clinical_medicine` | `biomedical_technical` | `non_biomedical`, from the Phase 1 elicitation above — `keyword-expansion` reads it to decide the MeSH axis's default.

This file is read verbatim by `/prisma-search` (to build `search_plan.json`), `/prisma-screen` (to run the eligibility gate on each candidate record — see `02-eligibility-criteria.md`), and `/prisma-report` (Methods §2.2/§2.3). Never re-elicit these values from memory later in the pipeline — always read them from this file.

### G-Protocol: sign the protocol

Once `protocol.json` is written (or updated) with every field above populated, stamp the sign-off — this is the human gate that fixes the moment the plan predated the first search, which `tools/label_gate.py`'s systematic-review conduct floor and `synthesis/run_synthesis.py`'s `model_source` (`"protocol"` vs. `"post_hoc"`) both depend on:

```bash
python3 tools/sign_protocol.py --topic <TOPIC> --signed-by "<reviewer name from CLAUDE.local.md, or 'reviewer' if unknown>"
```

(Pre-allowlisted — `Bash(python3 tools/sign_protocol.py:*)`.) This independently re-verifies the protocol is actually complete (title, objective, framework fields, every eligibility gate's required value, scope mode) before writing `signed_at`/`signed_by` — do not skip this call because you've already confirmed the fields conversationally; the script is the deterministic gate, not a formality. If it refuses (a field is missing or empty), go back and fill that field rather than signing an incomplete protocol. It is idempotent and never re-dates an already-signed protocol, so it's safe to call again on a resumed/updated review — a genuine post-hoc plan change stays disclosed via `amendments[]` (see "Handling scope changes" below), never by silently moving `signed_at` forward.

If Phase 1 step 5 elicited a quantitative synthesis plan, write it as its own file, `results/<TOPIC>/synthesis_plan.json` (never a `protocol.json` sub-object — `synthesis/run_synthesis.py` reads it directly by that path):

```json
{
  "model": "random",
  "synthesis_family": "pairwise_iv",
  "tau2_estimator": "dl",
  "ci_method": "normal",
  "k_min": 2,
  "signed_at": "2026-09-06T10:12:00Z",
  "justification": "Included trials are expected to vary in dose, population, and follow-up duration; a random-effects model better reflects that heterogeneity."
}
```

`tau2_estimator` accepts `"dl"` (DerSimonian-Laird, one-step -- the default) or `"pm"` (Paule-Mandel, iterative); `ci_method` accepts `"normal"` (fixed-scale, the default) or `"hksj"` (modified Hartung-Knapp-Sidik-Jonkman, an estimated-scale CI -- `synthesis/pooling.py` flags a caution, never a refusal, when fewer than 5 studies contribute). Both only affect outcomes pooled under `model: "random"`. Ask which the reviewer prefers only if they raise it; `"dl"`/`"normal"` is a reasonable default for most reviews and need not be elicited as its own question. Neither value is retroactively changeable without re-running `/prisma-synthesize` — the schema (`schemas/synthesis_plan.schema.json`) is the source of truth for the accepted enum values.

`synthesis_family` (docs/ROADMAP.md) accepts `"pairwise_iv"` (today's inverse-variance pairwise pooling -- the default, and the only family with a working engine) or `"structured_narrative"` (never pools any outcome, regardless of `k`). `"swim"` is a recognized enum value with no engine yet -- `/prisma-synthesize` refuses cleanly rather than fabricate untested vote-counting statistics if it's selected. Omit this field entirely unless the reviewer specifically wants narrative-only synthesis; a plan predating this field behaves identically to `"pairwise_iv"`.

## Running the eligibility gate mid-review

When `/prisma-screen` or `/prisma-extract` (or the user directly) asks whether a specific study is eligible, follow `02-eligibility-criteria.md` exactly: run every gate in order, report a **FAIL** with the quoted source text the moment one is hit, and never silently drop a study that fails — the failure and its quote go into `screening_decisions.jsonl` with a `reason`, per PRISMA Item 16b. A study that passes every gate proceeds to relevance screening/scoring; a study that fails any gate does not.

## Handling scope changes

If eligibility criteria change partway through a review (a narrower population, an added language), do not overwrite history:

1. Update `protocol.json` with the new criteria and bump nothing silently — tell the user which studies already screened under the old criteria may need re-screening.
2. Never delete or edit past lines in `screening_decisions.jsonl`; a corrected decision is a **new** line, latest line wins on aggregation.
3. Note the change and its date in `protocol.json` (e.g. an `amendments: [{date, change, reason}]` array) so `/prisma-report`'s Methods §2.1 can disclose the protocol deviation, per PRISMA Item 24c.
