# Working plan: prisma-flow → multi-method evidence-synthesis workspace

> **Temporary document.** This is the execution plan for Phase 0 (correctness baseline) and
> milestones M1–M5 (multi-method tool). It is tracked in the repo so every PR can point at it.
> **Remove this file and `docs/design/multi-method-consensus.md` when M5 is complete**; by then
> the durable content lives in `methods/`, `packs/`, the skills' reference files, and
> `docs/ROADMAP.md`. Status of each PR is tracked in the table under "Build sequence".
>
> Produced 2026-09-06 with Claude Code. Owner decisions recorded in "Decisions adopted".

## Context

**Ask.** PRISMA is one evidence-review method among many; the tool should first decide which method fits a project, then guide the user through that method's own pipeline. The owner asked for a multi-agent specialist debate converging on one consensus, and for open-source peers to be benchmarked and borrowed from where license-safe.

**How this plan was produced.** (1) Two code-exploration passes verified the repo's defects and constraints. (2) A web survey verified nine proposal-cited projects and found ~20 more (see "Landscape"). (3) A 19-agent panel — seven specialists (evidence-synthesis methodologist, information specialist, biostatistician, CS/engineering methodologist, qualitative/social-science methodologist, software architect, researcher-experience designer) wrote positions, cross-examined each other, a chair synthesized, three skeptics (methodological correctness, engineering feasibility, novice usability) attacked it, the chair revised. The full consensus is `docs/design/multi-method-consensus.md`; this plan is its executable summary.

**Verified Phase 0 defects** (the panel's "confirm the RoB2 string exists" question is answered: yes — 66 occurrences in 14 files, including `tool == "RoB2"` in `synthesis/run_synthesis.py`).

| # | Defect | Evidence |
|---|---|---|
| 1 | RoB tool mislabeled | `.claude/skills/quality-appraisal/01-risk-of-bias.md` implements the 2011 Cochrane six-domain tool but calls it "RoB2"; `synthesis/run_synthesis.py` has `ROB2_DOMAIN_LABELS` and `tool == "RoB2"` checks (~L74-85, 261, 415); the rollup borrows RoB 2's "some concerns" tier |
| 2 | Post-hoc model choice | `synthesis/heterogeneity.py:64-71` `choose_model` (I²>50 or p<0.10) called unconditionally at `run_synthesis.py:362`; `protocol.json` never read; only flag `--topic`; DerSimonian–Laird only (`pooling.py:49`) |
| 3 | State logic in prompts | dedup `prisma-search.md:281-460, 473-550`; ledger gate/candidates `prisma-extract.md:38-110`; flow counts `prisma-report.md:175-244`; status `prisma-status.md:56-335` |
| 4 | Unpinned env | bare `requirements.txt`; CI hardcodes Python 3.12; docs say 3.10+; verified passing on 3.11 with `matplotlib==3.11.1 numpy==2.4.6 PyYAML==6.0.1 requests==2.33.1 scipy==1.17.1 statsmodels==0.15.0` |
| 5 | No end-to-end test | 16 unit modules only |
| 6 | Over-claim | "PRISMA 2020-conformant pipeline" in `README.md:3`, `CLAUDE.md:12`, `AGENTS.md:7`, `.claude/commands/prisma-report.md:3` |

**Repo constraints.** `tools/check_framework_version.py` requires a `framework_version` bump for any edit under the five watched skill dirs (baseline `origin/$GITHUB_BASE_REF`); `tools/security_guards.py` requires every `.claude/settings.json` allow-entry to equal an entry in its hardcoded `ALLOWED_PERMISSIONS` (existing tool entries use `Bash(python3 tools/x.py:*)` — keep that form); `tools/lint_skills.py` checks skill frontmatter and non-empty commands only; tools are `main(argv)->int` + argparse + `tools/path_policy.safe_topic_path`; tests are `unittest`, in-process; doctrine (AGENTS.md, CONTRIBUTING.md) = thin pointers, single source of truth, no speculative infrastructure, fork-per-topic.

## The consensus in one paragraph

A **method is a small flat JSON manifest of policy differences** from today's systematic-review pipeline plus the claims that policy licenses. The nine Markdown commands keep the stage sequence and remain the implementation (one added Step-0 line each). The algebra is **review type × synthesis family × maintenance mode × profile flags**. Prompts propose, deterministic Python validates and records, humans decide. **The label printed in any report is computed from recorded conduct** (`tools/label_gate.py`), never typed by a user or prompt. Three of the owner's original framings were unanimously rejected and the owner accepted the panel's position: meta-analysis is a *synthesis family* inside a systematic review, not a mode; living update is a *maintenance mode* over any completed method, not a method; docs say "evidence-synthesis and landscape methods" rather than "pre-research methods" (the router still understands "meta-analysis" and "living review" as user words).

## Decisions adopted (owner-ratified items marked ★; the rest are chair rulings the owner may override)

1. ★ Meta-analysis → family `pairwise_iv` under systematic review; living update → mode; "evidence-synthesis and landscape methods" wording.
2. ★ **Label policy = project conduct floor.** "Systematic review" requires (i) protocol signed before the first protocol-driven search run, (ii) ≥2 distinct index families, (iii) a recorded PROSPERO/OSF lookup, (iv) some second-reviewer involvement in selection (dual screening or a recorded verification sample), (v) pooling only under a plan whose hash predates the first protocol-driven run. Missing (i) or (iv) → "systematized review" with the missing elements listed, shown at routing time. Unfinished stages block the build, never change the label. Missing extraction verification under `pairwise_iv` = disclosure + mandatory Limitations text, not a downgrade.
3. ★ **Diagnostic-accuracy / prediction-model questions fail closed in v1** (router offers a scoping review); a `dta_narrative` dialect (PRISMA-DTA, TRIPOD-SRMA, QUADAS-2 per-domain, PROBAST+AI, no pooling) ships in v2.
4. ★ **Phase 0 includes the panel's additive items**: connectors echo `connector_version, query, purpose: orienting|protocol_driven, plan_hash` into `raw/*.meta`; `index_family` in `connectors/registry.py`; ledger lines gain `by, role: decision|verification, eligibility_version`; decision enum gains `not_retrieved`; extraction rows gain `reports[], by, verified_by, risk_of_bias.instrument` (beside legacy `tool`); `synthesis_plan.schema.json` with `pooling_unit.identity_fields`; `jsonschema` pinned.
5. RoB: rename to RoB1 (2011 tool); legacy `"RoB2"` accepted on input with a warning and normalized in outputs; correct the borrowed rollup; real RoB 2 only as identifiers + own paraphrase (official text is CC BY-NC-ND).
6. Prespecified pooling: `synthesis_plan.json` signed **at protocol**; `--model` override recorded as `model_source`; both models computed, non-primary under `sensitivity`; `choose_model` deleted; heterogeneity descriptive only; DL default now, Paule–Mandel + modified HKSJ + prediction interval selectable (PR 10); a plan hash newer than the first protocol-driven run routes outputs to `synthesis/post_hoc/` with "specified after study selection" rendering.
7. Python 3.11–3.13, exact pins; docs "3.11+".
8. Entry point stays `/prisma-init`; no `/review` wrapper; project name stays `prisma-flow` until a second method has users.
9. Field packs are **flat data only** (glosses, source expectations, instrument ids, confidence framework, pooling-unit *proposal*); no override of manifest fields; a pack needing code is a fork. `generic`, `clinical_interventions`, `cs_se` in M3; `medical_imaging_prediction` and `image_reconstruction` (no RoB instrument; a reproducibility/leakage checklist explicitly "not a risk-of-bias instrument") in M5.
10. QES (meta-aggregation, thematic synthesis), mixed-methods, NMA, bibliometrics, methodological reviews: **later**, as routing-row refusals with pointers, no stub manifests. Realist/meta-narrative/CIS/meta-ethnography, integrative/critical reviews, IPD-MA, patent landscaping: out of scope (refusal + pointer).
11. Statistics stay in Python; `metafor`/`mada`/Cochrane DTA reference values used as CI fixtures; NMA exported to R.
12. Licensing: PRISMA checklists (CC BY 4.0) vendored as Markdown references with attribution; RoB 2 / ROBINS-I / CASP as ids + paraphrase + links; only Apache-2.0/MIT code vendored; ideas only from non-commercial projects.
13. Default for CS users with unknown venue: scoping review (PRISMA-ScR); systematic mapping study when `CLAUDE.local.md` target venue is SE/CS.
14. Single-reviewer verification default: the Cochrane RRMG-conformant option offered first (joint pilot + ≥20 % of abstracts, then all excludes); a lighter sample is a non-RRMG shortcut with different label text.
15. Registration itself is a disclosure ("registered at … / not registered, reason"); the *lookup* is required for the SR label.

## Method taxonomy (final; per-method standards, appraisal tools and synthesis types are in the consensus §1)

- **core-v1 (manifests):** systematic review (exists), scoping review, systematic mapping study, exploratory literature brief ("reconnaissance"). **core-v1 non-manifest:** SR with meta-analysis (family `pairwise_iv`), SWiM and structured narrative (families), systematized review (computed label), rapid review (profile `shortcuts[]` from the Cochrane RRMG 2024 menu; PRISMA-RR is unpublished and never cited), prior-work check and related-work section (reconnaissance outputs), living update (mode), snowballing (recorded strategy, PRISMA-S item 5).
- **v2:** `dta_narrative` dialect; evidence & gap map (+ matrix; every empty cell corpus-qualified); umbrella review (PRIOR 2022, AMSTAR 2 / ROBIS ids, CCA); meta-analysis of proportions (logit/GLMM); MOOSE / ROBINS-E pack defaults; `structured_survey` family for benchmark tabulation (cross-dataset pooling refused by the core `pooling_unit` predicate); recency-bounded scoping preset; multivocal / grey source layer (AACODS).
- **later:** QES meta-aggregation and thematic/framework synthesis (ENTREQ, CERQual/ConQual), mixed-methods, NMA (PRISMA-NMA, CINeMA), `dta` engine (bivariate/HSROC), dose-response / economics / eco-evo engines, bibliometrics (corpus-description table only until then), methodological reviews.
- **out-of-scope:** realist / meta-narrative / CIS / meta-ethnography, integrative / critical / hermeneutic reviews, IPD-MA, patent landscape / FTO / horizon scanning, COSMIN / HTA.

## Routing (`methods/_routing.json` evaluated by `tools/route.py`; one unit test per row; recorded in `protocol.json.method.routing`)

Free-text aim first, then: **Q1** what you need at the end (orient / prior-work check / background section / map / answer one question / summarise existing reviews / update a review here); **Q0** computed after Q1 — a bounded existing-review scan over enabled connectors written to `raw/` with `purpose: orienting`, plus a recorded human PROSPERO/OSF lookup (required for the SR label); **Q2** can you state the question as "does A vs B affect C in D" (pack-rendered template; yes / roughly / not yet); **Q3** expected evidence type (+ benchmark-vs-clinical disambiguator); **Q4** reviewers and time budget (sets *offers* and the predicted label, never the method); **Q5** appraisal intent; **Q6** (conditional) expects pooling → plan drafted and signed at protocol. Rules R0–R10 (consensus §2.2): a fallback may only go *down* the claims ladder (→ scoping → reconnaissance) or refuse — never sideways into an SR label for qualitative, mixed, review-of-reviews, or (v1) test-accuracy questions. The "because" card (five fixed lines from manifest `microcopy`) explains what / gives / costs / allowed label and why, with "why not the next step up". `label_gate.py` lint: hard failure on the tool's own templated outputs for "comprehensive/exhaustive search", "all relevant studies", "first to", "no prior work", "proves", "novel", "saturat*", unqualified "gap"; warnings only on manuscript Abstract/Conclusions.

## Common stage model (sequence stays in the Markdown commands; manifests only switch stages off or change their rules)

| Stage | Command / skill | Deterministic tool | Human gate |
|---|---|---|---|
| S0 route | `/prisma-init` Step 0.5 | `tools/route.py`, Q0 orienting run, `label_gate.py` (predictive) | G-Route: confirm/override |
| S1 protocol | `review-protocol` | schema validation; `signed_at` vs first protocol-driven raw run; plan hash | G-Protocol: sign protocol (+ plan) |
| S2 search-plan | `keyword-expansion` | grammar parse; plan↔`rerun_search.sh` drift test; PRISMA-S items 1–16 structured | G-Terms: accept terms; supply 3–5 known items with provenance |
| S3 search-run | `/prisma-search`, connectors, `citation_chase.py` | `tools/dedup.py`, `tools/search_preflight.py` (recall by provenance, index-miss vs string-miss, unique contribution, new-records-per-query series) | G-Search: resolve ambiguous pairs; accept/waive validation |
| S4 screen | `screening-assistant` | `tools/ledger.py` (hash chain, `by/role/eligibility_version`), `tools/flow_counts.py` (`not_retrieved` box), kappa from verification lines | G-Screen / G-FullText |
| S5 chart-or-extract | `/prisma-extract` + new `evidence-mapping` skill | schema + provenance validation; `schema_freeze` after 5–10 pilot records; solo calibration re-code | G-Freeze, G-Values |
| S6 appraise | `quality-appraisal` | instrument completeness; domain→overall only for RoB 2 / ROBINS-I; `rob2` fails closed outside clinical packs | G-Appraise |
| S7 synthesize | `synthesis/` | `run_synthesis.py` dispatch on family; refuses `pairwise_iv` without plan hash; `post_hoc/`; `pooling_unit` predicate | G-Synthesis |
| S8 report | `prisma-manuscript` | flow counts from ledger; `label_gate.py` definitive → `manuscript/label.json`; lint; reference verification | G-Claims: approve every templated sentence |
| S9 living (mode) | `--rerun` → export undecided → re-synthesize → report | idempotent dedup = delta; `versions[]`; `--since` counts; methods-changed block on plan-hash change | G-Impact |

Per-method applicability and method-specific rules: consensus §3.2–3.3.

## Architecture (additions only; nothing existing moves)

```
methods/  _schema.json  _routing.json  systematic_review.json  scoping_review.json  systematic_mapping_study.json  reconnaissance.json
packs/    _schema.json  generic.json  clinical_interventions.json  cs_se.json  (M5: medical_imaging_prediction.json  image_reconstruction.json)
schemas/  protocol_method  synthesis_plan  extraction_table (array | {"studies":[]})  charting_table  classification_table  screening_decision  deviations
.claude/skills/*/references/  prisma-2020, prisma-s-2021, swim-2020, prisma-scr-2018, segress-2023, petersen-2015-conduct, prisma-lsr-2024 (Markdown, attributed)
tools/    method.py  route.py  label_gate.py  status.py  chart_summary.py  dedup.py  ledger.py  flow_counts.py  search_preflight.py  preflight.py
synthesis/ run_synthesis.py (family dispatch)  families/{structured_narrative,swim,pairwise_iv}.py  heterogeneity.py (descriptive only)
.claude/skills/  + evidence-mapping/ (M3)  + reconnaissance-brief/ (M4)
results/<TOPIC>/  protocol.json(+method, eligibility_version, versions[])  raw/*.meta(+connector_version, query, purpose, plan_hash)  records.jsonl(+first_seen)
                  screening_decisions.jsonl(+by, role, eligibility_version, hashes)  extraction|charting|classification_table.json  synthesis_plan.json  deviations.jsonl
                  synthesis/  recon/  handoff/  manuscript/(+label.json, checklist_audit.md)
```

Manifest fields (closed enums in `_schema.json`; each `check` backed by one function in `label_gate.py`): `id, label, aliases, version, family, question_frameworks, search{mode, min_index_families, primary_strategies_default, known_item_recall}, screening{recommend_reviewers, criteria_may_evolve}, capture{mode, schema, freeze_gate, pilot_records}, appraisal{requirement, use}, synthesis{families_allowed, plan_required_for, plan_required_at, proposal_defaults}, standards[{ref, when}], label_rules{label, requires[], profile_labels, otherwise, disclosures}, report_blockers, forbidden_forms, profiles, living, microcopy{what, gives, costs, cannot_claim, upgrade_to, stage_names}, exports`. Worked `systematic_review.json` and `scoping_review.json` are in consensus §4.3. Pack fields: `source_expectations[]` (required; renders the coverage statement and Limitations), `controlled_vocab`, `search.primary_strategies_allowed`, `question_template`, `framework_glosses`, `default_capture_fields`, `appraisal_instruments_by_design` (ids), `confidence_framework`, `pooling_unit_identity_proposal`, `preprint_eligibility_default`, `label_rule_additions` (closed enum only). Deterministic-vs-LLM-vs-human split: consensus §4.5. Commands become thin via one Step-0 line: resolve method/pack with `tools/method.py` (absent ⇒ `systematic_review` / `generic`); if the stage does not apply, print the applicable stage from `microcopy.stage_names`. Migration: absence of `protocol.json.method` ⇒ systematic review; `false` vs `not_recorded`; one-time self-report via `/prisma-status`; legacy pooled topics get `synthesis_plan.json{retrospective: true}` + disclosure; all new fields additive; the golden test stays byte-identical except `label.json`.

## Build sequence

### Phase 0 — correctness baseline (one branch and PR per concern, all from `origin/main`)

| PR | Branch | Concern | Status |
|---|---|---|---|
| 0 | `claude/plan-multi-method` | this plan + `docs/design/multi-method-consensus.md` | open |
| 1 | `claude/p0-1-roadmap-docs` | `docs/ROADMAP.md` (roadmap in the consensus framing; owner's original proposal as appendix; landscape), deferral/cross-reference note in `AGENTS.md` and `CONTRIBUTING.md`, PRISMA positioning wording at README:3 / CLAUDE.md:12 / AGENTS.md:7 / prisma-report.md:3 | pending |
| 2 | `claude/p0-2-pinned-env` | exact pins + `jsonschema`; CI matrix 3.11/3.12/3.13 on the test job; docs "3.11+" | pending |
| 3 | `claude/p0-3-rob1-rename` | RoB1 intro + rollup correction in `01-risk-of-bias.md` (version bump); `ROB1_DOMAIN_LABELS`; legacy `"RoB2"` alias + warning; `risk_of_bias.instrument` beside `tool`; version bumps in every touched watched skill file; `tests/test_synthesis_rob_labels.py` | pending (mechanical rename stashed) |
| 4 | `claude/p0-4-prespecified-model` | `synthesis_plan.json` + `schemas/synthesis_plan.schema.json` (model, tau2_estimator, ci_method, k_min, `pooling_unit.identity_fields`, signed_at, hash); `run_synthesis.py` reads it, `--model` override → `model_source`, both models computed, `sensitivity`, plan-hash vs first protocol-driven run → `post_hoc/`; `choose_model` deleted; `prisma-synthesize.md`, `prisma-report.md`, `prisma-init.md` + `review-protocol` elicitation (bump); tests | pending |
| 5 | `claude/p0-5-dedup-module` | `tools/dedup.py` (`--pass exact|fuzzy`, behavior-preserving port of `prisma-search.md:281-460, 473-550`, `first_seen`), command rewired, allowlist in both places, `tests/test_dedup.py` incl. snapshot | pending |
| 6 | `claude/p0-6-ledger-module` | `tools/ledger.py` (append with `prev_hash/entry_hash`, `by/role/eligibility_version`, `not_retrieved`; `gate`, `candidates`, `verify`), `tools/flow_counts.py` (port of `prisma-report.md:175-244`, `not_retrieved` box, `truncated_sources`), `screening-assistant` writes through `ledger.py` (bump); commands rewired; allowlist; tests | pending |
| 7 | `claude/p0-7-search-gates` | `tools/search_preflight.py` (per-source complete/truncated/failed/missing; known-item recall from `protocol.json.known_items[]` with provenance, seeds excluded, index-miss vs string-miss; new-records-per-query series) → `search_status.json`; `tools/preflight.py --stage synthesize|report` aggregating ledger gate, chain verify, search preflight, plan presence; connectors echo `connector_version/query/purpose/plan_hash` into `raw/*.meta`; `index_family` in `registry.py`; commands call preflight; allowlist; tests | pending |
| 8 | `claude/p0-8-status-module` | `tools/status.py` = port of `prisma-status.md:56-335`; command rewired; tests | pending |
| 9 | `claude/p0-9-unsupported-design` | `quality-appraisal` design table: neither RCT nor NOS-eligible → `instrument: "unsupported"`, fail closed (bump); `run_synthesis.py` counts it as not-low-risk; tests | pending |
| 10 | `claude/p0-10-re-estimators` | `tau2_estimator: dl|pm` (statsmodels `method_re="iterated"`), `ci_method: normal|hksj` (modified Knapp–Hartung, k<5 caution), 95 % prediction interval at k≥3; forest-plot PI bar; reference-value tests (BCG dataset values from the literature); DL byte-identical regression | pending |
| 11 | `claude/p0-11-extraction-provenance` | extraction rows: `source{quote, locator, notes}`, `reports[]`, `by`, `verified_by`; pass-through to `effect_sizes.json`; `prisma-extract.md` asks and refuses quotes absent from available full text (bump); tests | pending |
| 12 | `claude/p0-12-golden-pipeline` | `tests/fixtures/golden/<slug>/` frozen inputs (protocol with plan + known_items, raw/ with planted duplicates, ledger with superseded and verification lines, extraction with RoB1×3 incl. one legacy "RoB2" + NOS×1, two poolable outcomes + one below k_min) → dedup → sheet → ledger gate/candidates/flow-counts → preflight → run_synthesis → `expected/` + sha256 manifest (SVGs excluded); writes to a unique slug under repo `results/` (gitignored), cleaned in tearDown | pending |

Phase 0 exit criterion: an external methodologist can audit one golden run without finding a mislabeled method or an unreproducible transition; CI green on the matrix; no command contains executable Python.

### Milestones after Phase 0 (consensus §5 has full scope and exit text)

| M | Scope | Exit criterion |
|---|---|---|
| **M1 One method, made explicit** | `methods/_schema.json`, `methods/systematic_review.json`, `tools/method.py`, `schemas/protocol_method.schema.json`, `run_synthesis.py` family dispatch (`structured_narrative`, `swim`, `pairwise_iv`) + plan-hash gate + `post_hoc/`; retrospective-plan path; Markdown references PRISMA-S, SWiM; `check_framework_version` watches `methods/`, `packs/`, all skills | Golden test byte-identical except `label.json`; legacy fixture resolves to SR with `not_recorded` disclosures; `pairwise_iv` refused without plan hash |
| **M2 Routing + label integrity** | `_routing.json`, `tools/route.py`, `/prisma-init` Step 0.5 (aim, Q1, Q0 orienting run + registry lookup, Q2–Q6), manifest-conditional Steps 1–2, `tools/label_gate.py` (conduct floor, `false`/`not_recorded`, disclosures, blockers, lint), `microcopy`, rapid `shortcuts[]` + `deviations.jsonl`, `role: verification` + kappa, `eligibility_version`, `manual_source` runs, four-valued recall severity | Every routing row tested; single-screener fixture → "systematized review" at routing and report with identical text; verification-sample fixture → "systematic review" + disclosure; qualitative and test-accuracy questions fail closed with pointers; lint fails "no prior work", passes the calibrated sentence |
| **M3 Scoping review + systematic mapping study** (first non-PRISMA methods) | two manifests; PCC + Petersen RQs in `review-protocol`; new `evidence-mapping` skill (charting form pilot→freeze; keywording→scheme freeze→calibration re-code); charting/classification schemas; `tools/chart_summary.py`; references PRISMA-ScR 2018, SEGRESS 2023, Petersen 2015; QGS path; snowballing meta (PRISMA-S item 5); string-miss re-entry into `keyword-expansion`; packs `generic`, `clinical_interventions`, `cs_se` | Second golden fixture runs to a PRISMA-ScR-audited report; `/prisma-synthesize` on it refuses pooling; mapping fixture blocks bulk coding until the scheme is frozen; `not_retrieved` gets its own flow box; coverage gaps render on the card and in Limitations. No public tag between M3 and M4. |
| **M4 Reconnaissance (exploratory literature brief)** | `methods/reconnaissance.json`; `reconnaissance-brief` skill; relevance-tag sheet; `landscape_brief.md` + `related_work_draft.md` + `supplementary_search_log.md`; prior-work-check output (facet tags + quoted claims with provenance); corpus-description table; `handoff/` (seed terms, gold-set candidates `provenance: recon-db`, disclosure); same-topic promotion (`recon/` archive, amendment, fresh run) | Brief fails lint on "no prior work"/"saturation", passes templates; hand-off gold set enters the SR recall gate and prints "non-independent gold set" until an external item is added; recon records never enter the promoted method's `records.jsonl` without a fresh run. v1 tag possible here. |
| **M5 Living mode + first field packs** | `protocol.json.versions[]`, `--since` flow counts, PRISMA-LSR reference + block, methods-changed block on plan-hash change; packs `medical_imaging_prediction` (PROBAST+AI, QUADAS-2 ids, CLAIM 2024 / TRIPOD+AI adherence fields, TRIPOD-SRMA reference) and `image_reconstruction` (no RoB instrument; reproducibility/leakage checklist; `pooling_unit_identity_proposal`: dataset, split_policy, acceleration, mask, coil_setting, metric_definition) | Delta fixture: `--rerun` adds two records, screens only the delta, report carries the PRISMA-LSR block + human impact sentence + methods-changed block when the hash differs; imaging fixture: pooled PSNR across two datasets refused by the core `pooling_unit` predicate. v1 complete. |
| **v2 (by demand)** | `dta_narrative`; EGM + matrix; umbrella review (+ `appraisal/` store, CCA); `proportions` family; MOOSE / ROBINS-E pack defaults; `structured_survey`; recency preset; grey source layer + AACODS; Stevens 2024 interim rapid items; PRESS self-assessment; retraction/preprint fields | each = manifest/pack/reference PR + ≤1 tested module with published-example fixtures |
| **Later** | QES, `dta` engine, mixed-methods, NMA, bibliometrics, methodological review, gap-typology tags (absent cell, thin cell, direction-conflict), claim-evidence graph once a second consumer exists | needs a new data unit, a heavy engine, or a maintainer |

## Landscape: adopted from open-source peers (license-checked)

| Adoption | Source (license) | Lands in |
|---|---|---|
| Known-item (gold-set) recall gate with provenance | AngelChen-HC/systematic-review-skill (Apache-2.0); y9655980-crypto/sr-search-skill (MIT) | PR 7, M2 |
| Hash-chained decision ledger + `verify` | AngelChen-HC (Apache-2.0) | PR 6 |
| Exit-code gates via one preflight | idea from O0000-code/meta-analysis-skill (non-commercial → reimplemented) | PR 7 |
| Paule–Mandel τ², modified HKSJ, prediction interval | idea from meta-analysis-skill; statsmodels already computes HKSJ | PR 10 |
| Quote + locator + notes provenance; `by` / `verified_by` | AngelChen-HC; chunchiehfan/systematic-review | PR 11 |
| Single-authority state, update/merge mode | daltonhaslam/lit-review-agent (MIT) | M5 living mode (`versions[]`) |
| New-records-per-query series (the word "saturation" is forbidden) | O0000-code/paper-search-pro (Apache-2.0) | PR 7, M4 |
| Per-source `query_strategy.json` / `audit.json` status | u9401066/pubmed-search-mcp | PR 7 (`search_status.json`) |
| RoB 2 as signalling-question data model | rob-luke/risk-of-bias (MIT); official text CC BY-NC-ND → ids + paraphrase only | v2 / later |
| Arbitrator-on-disagreement, κ / PABAK | LatteReview (CC BY-NC-ND, idea only); AngelChen | M2 (`role: verification` + kappa) |
| PRISMA-trAIce AI-transparency checklist | Drignacioalcala/systematic-review-skill (MIT) | v2 report section |
| RIS import/export, ASReview and Zotero interop | ASReview (Apache-2.0), 54yyyu/zotero-mcp (MIT) | v2 source layer |
| Anthropic hosted PubMed MCP (no auth) as optional connector | anthropics/life-sciences | v2 |

Reference only: PaperQA2, STORM, gpt-researcher (no PRISMA semantics); PapersFlow / Elicit / Consensus (hosted, paid); meta-mcp (proof of concept). Sci-Hub-enabled servers are never used. In-session catalogs (2026-09-06): no systematic-review skill or plugin exists in the claude.ai skill library or Anthropic plugin catalogs; the Bio Research plugin lacks any prior-art step.

## Dissent log (most consequential; all 25 items in consensus §6)

Reconnaissance ships in M4 not M2 (no public tag between M3 and M4; if M3 slips >6 weeks, ship on M2's lint alone) · no stub manifests for later methods (routing refusals instead) · single-reviewer label = conduct floor, not disclosure-only · packs kept as flat data · rapid label from `shortcuts[]`, never from calendar time · recall gate four-valued per manifest + provenance · no unqualified "gap" anywhere, EGM cells included · "prior-work check", never "novelty" · Q0 computed after Q1 as an `orienting` run · policy-delta manifests, no stage registry or generic walker · living mode via `--rerun` + `versions[]`, no delta store · standards as Markdown references, LLM-audited · test-accuracy fails closed in v1.

## Out of scope / deferred

Real RoB 2 wording (licensing), REML (not in statsmodels; Paule–Mandel instead), JSON Schemas for every state file at once (they arrive with M1–M3 as listed), repo rename, `core/` restructure, generic stage interpreter, delta store, claim-evidence graph before a second consumer exists, the `connectors/citation_chase.py` `remaining or limit` cap bug (separate small PR, unrelated to this plan).

## Verification (every PR)

`python3 -m unittest discover -s tests -v` (count only grows) · `python3 tools/lint_skills.py` · `python3 tools/check_connector_contract.py` · `python3 tools/security_guards.py` · `python3 tools/check_framework_version.py` (with `origin/main` fetched) · `git diff --stat` limited to the PR's concern · CI green on 3.11/3.12/3.13 · PR body carries what/why, tests, migration note, docs touched. Milestone exits are the golden fixtures named above.
