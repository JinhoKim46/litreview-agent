<!--
TEMPORARY DESIGN RECORD — companion to docs/PLAN.md.
Remove this file (and docs/PLAN.md) once Phase 0 and milestones M1–M5 described in
docs/PLAN.md have landed; the durable parts (method manifests, routing table, reference
checklists, ROADMAP) will live in their own files by then.

Provenance: produced 2026-09-06 by a 19-agent specialist panel (seven specialists, a chair,
three adversarial reviewers) convened in Claude Code at the project owner's request, then
ratified by the owner on four decisions (framing; label policy = conduct floor; DTA fails
closed in v1; extended Phase 0). Everything else below is the panel's recommendation, not
yet an approved backlog. Standards named here were re-verified by the adversarial round but
should be re-checked against the primary source before any is cited in a manuscript.
-->

# Consensus Design: prisma-flow as a Multi-Method Evidence-Synthesis Workspace

*Panel chair's synthesis of two panel rounds plus one adversarial round (methodological-correctness, engineering-feasibility, researcher-usability). Verified against the repository layout on 2026-09-06 (`connectors/registry.py`, `synthesis/{pooling,heterogeneity,plots,run_synthesis}.py`, `tools/{build_screening_sheet,export_report,lint_skills,path_policy,security_guards,check_connector_contract,check_framework_version}.py`, `raw/<source>-<date>.json.meta`, nine `.claude/commands/prisma-*.md`, five skills). Standards re-verified by the adversarial round: PRISMA-LSR 2024, STARD-AI 2025, PROBAST+AI 2025, SEGRESS 2023, Cochrane RRMG recommendations 2024 (Garritty) and interim reporting guidance (Stevens et al.), PRISMA-RR still unpublished, QUADAS-AI protocol only, PRISMA-ScR update in Delphi, AMSTAR 2 critical items 2/4/7/9/11/13/15, PRISMA-S item 5 = citation searching and item 9 = limits.*

**The one-sentence design the panel converged on:** a *method* is a small JSON manifest of **policy differences from today's systematic-review pipeline** plus the claims that policy licenses; the nine Markdown commands keep the stage sequence and remain the implementation; **review type × synthesis family × maintenance mode × profile flags** is the algebra; prompts propose, deterministic Python validates and records, humans decide; and the label printed in any report is *computed from recorded conduct*, never typed by a user or a prompt.

Three owner-proposal framings were unanimously rejected and are recorded as such: **meta-analysis is a synthesis family inside a systematic review, not a mode**; **living update is a maintenance mode over any completed method, not a method** (PRISMA-LSR is an add-on for exactly this reason); and **"pre-research methods" undersells systematic reviews and qualitative syntheses, which are research** — the docs say "evidence-synthesis and landscape methods". The router still *understands* "meta-analysis" and "living review"; they resolve to `systematic_review + synthesis_plan` and `base_method + living`.

**What the adversarial round changed (summary).** (1) Stage lists, gate strings, dialect sub-manifests, packs-with-merge-semantics, stub manifests, JSON checklists with a "deterministic" audit, `runs[]`, `search_delta.py`, `updates/`, `claims.json`, `derived_from`, the `/review` pointer and the generic state-machine walker are **cut**; manifests are flat policy files, refusals live in the routing table, standards are Markdown reference files, run history is the `raw/*.meta` the repo already keeps. (2) Every misattributed standard the methods reviewer found is corrected (PRISMA-S item 5 not 9; no "Petersen/SEGRESS" composite; MECIR and Kitchenham 2010 removed as standards; SWiM and GRADE become conditional; RoB 2/PROBAST/QUADAS-2 scoped to the designs they were validated for; QUADAS-2 has no overall algorithm; "exhaustive" leaves the manifest vocabulary). (3) Prespecification of pooling moves to the **protocol**, not "before extraction". (4) The label rule is a **project conduct floor** (MECIR C39 + Grant & Booth), not "AMSTAR-2-critical"; incomplete stages block the build rather than change the label. (5) The routing interview and outputs are rewritten for the persona who has never heard of PRISMA: free-text aim first, Q0 after Q1, a prior-work-check option, pack-rendered question templates, plain-word labels, two recon exports (audit brief + usable related-work draft with a supplementary search log).

---

## 1. Method taxonomy (final)

Tier legend: **core-v1** = wired end-to-end in the first multi-method release (M1–M5; no public tag between M3 and M4); **v2** = next release; **later** and **out-of-scope** = *no manifest exists*; the routing table carries a one-line refusal and a guideline pointer so the router fails closed honestly. Rows marked **(label)**, **(mode)**, **(profile)**, **(family)**, **(preset)**, **(output)** or **(pack)** are recognised by the router and the label gate but are not separate manifests. Contested tiers marked (*) — see §6.

| Method | Aliases | Purpose | When to use | Question framework(s) | Reporting standard | Appraisal tool(s) | Synthesis type | Effort | Tier | Rationale for tier |
|---|---|---|---|---|---|---|---|---|---|---|
| **Systematic review** | SR, SLR (CS: Kitchenham & Charters 2007) | Defensible, bias-appraised answer to a focused question | Focused question; enough primary studies; months and (ideally) ≥2 reviewers | PICO/PICOS, PICo, SPIDER, PEO (PIRD via DTA dialect, v2) | PRISMA 2020 + PRISMA-S 2021 (+ PRISMA-P for protocol); SWiM 2020 **only when the `swim` family is used**. MECIR C39 is cited as the *rationale* for the second-reviewer rule, not listed as a standard the pipeline meets. | By design and pack: RoB 2 (RCTs, clinical packs only), ROBINS-I/-E, NOS, JBI checklists, MMAT; Kitchenham quality checklist (`use: describe`) in `cs_se`. Certainty framework from pack (GRADE in clinical; `none` in `cs_se`). | `structured_narrative` (default), `swim` (directional effect estimates only), `pairwise_iv` (signed plan at protocol) | 6–18 months | **core-v1** (exists) | The shipped pipeline; becomes the first manifest with zero behaviour change. |
| Systematic review with meta-analysis | SR/MA | Pooled estimate, heterogeneity, precision | SR *and* a `synthesis_plan.json` signed **at protocol** *and* poolability predicates met | as SR | PRISMA 2020 items 13a–f, 20–22; MOOSE for observational | as SR + GRADE SoF | `pairwise_iv`: REML/PM τ², HKSJ **with the modified (ad hoc) Knapp–Hartung correction** and a k<5 caution, PI at k≥3 (DL selectable with justification); k-minimum lives only in the signed plan | +1–3 months | **core-v1 (family)** | Not a method: a family unlocked by a plan whose hash predates the first protocol-driven search run. |
| Synthesis without meta-analysis | SWiM, structured narrative synthesis | Structured, prespecified non-pooled synthesis | Whenever pooling is not prespecified or predicates fail | as SR | SWiM 2020 items audited **only** when extraction rows are directional effect estimates; otherwise `structured_narrative` with no SWiM audit | as SR | `swim`: grouping, effect-direction tables, vote-count by direction only; `structured_narrative`: grouped tabulation, no direction counting | as SR | **core-v1 (two families)** | Replaces "narrative fallback"; SWiM misapplied to benchmark tables or CS themes was a mislabel the reviewer caught. |
| Systematized review | single-reviewer SR, student SR — consistent with Grant & Booth 2009 | SR-shaped process missing a conduct-floor element | Assigned automatically, never chosen | as SR | PRISMA 2020 "as far as applicable" + missing-elements list | as SR (optional) | as SR | 2–4 months | **core-v1 (label)** (*) | Computed label when SR conduct fails the **project conduct floor** (§2.4): no protocol before the first protocol-driven run, or no second-reviewer involvement in selection. CS wording: "systematized literature review". |
| Rapid review | REA, rapid evidence assessment | SR question under a deadline with declared shortcuts | Every shortcut nameable | as SR | PRISMA 2020 + Stevens et al. 2024 interim reporting items; conduct per Garritty et al. 2024 (RRMG); **PRISMA-RR unpublished — never cited as a checklist** | as SR | as SR | 2–12 weeks | **core-v1 (profile)**: `shortcuts[]` in M2; RRMG menu verbatim in M2, interim items as reference Markdown in v2 | The label derives from `shortcuts[]` being non-empty, **never from calendar time**; "rapid review (Cochrane RRMG 2024-conformant)" only if the recorded process matches the RRMG options (dual screening of ≥20% of abstracts after a joint pilot; second reviewer over *all* excludes at TA and FT), else "rapid review (non-RRMG shortcuts; see deviations table)". |
| **Scoping review** | scoping study, JBI scoping review, Arksey & O'Malley / Levac | Map extent, range and nature of evidence; clarify concepts; test SR feasibility | Broad/emerging topic; eligibility not yet fixable | PCC (pack-glossed); PICO/SPIDER permitted | PRISMA-ScR 2018 (pinned; update in Delphi) + PRISMA-S; JBI Manual ch. 11 | None by default; `optional_with_justification`, `use: describe` | Descriptive charting, frequency tables, concept map; **pooling forbidden** | 2–9 months | **core-v1** | First non-PRISMA method: highest demand after SR, ~80% stage reuse, exercises the no-appraisal/no-pooling path, correct destination for most misrouted "SR" requests. |
| Systematic mapping study | SMS, systematic map, mapping review (SE) | Classify a technical field by facets | CS/SE and engineering | Petersen-style RQs; Wieringa research types | **Petersen et al. 2015** (conduct: scheme freeze, QGS) and **SEGRESS 2023** (reporting) — two reference files, never one composite | None (optional rigour/relevance) | Classification counts, bubble plots, trend tables | 1–5 months | **core-v1** (fourth flat manifest, family `mapping`) | Same command sequence as scoping; differs in capture (classification), two gates (scheme freeze, calibration re-code), and reference files. Chosen by user, defaulted from target venue in `CLAUDE.local.md`. |
| Recency-bounded scoping review | "state-of-the-art review" (user vocabulary) | Recency-bounded map of the frontier | Fast-moving technical field | PCC with a justified time window | PRISMA-ScR borrowed; **Barry et al. 2022 not cited** (their six-step SotA method is interpretive and is not a scoping review) | None | Chronological/thematic tables + trend | 2–6 months | **v2 (preset** on scoping) | A date-window preset and a trend output; no new machinery. |
| Evidence and gap map | EGM, systematic evidence map (Campbell/CEE) | Where evidence is dense/absent across a fixed 2-D framework | Portfolio decisions; precursor to SRs | PCC + fixed matrix dimensions | Campbell EGM guidance (White et al. 2020); CEE/ROSES; PRISMA-ScR for selection | Optional; AMSTAR 2 on included SRs | Coded corpus + matrix; **every** gap cell carries the corpus qualifier ("no included study in this corpus, searched in [sources] on [date]") — no unqualified gap anywhere | 4–12 months | **v2 (fifth flat manifest + matrix renderer)** | Scoping + frozen framework + matrix; the reviewer's point that an empty cell is bounded by the search too is accepted. |
| **Exploratory literature brief (reconnaissance)** | landscape brief, orientation scan, "literature recon", quick look | What is this field, who are the key papers, what vocabulary is used, is a formal review warranted | Start of a project; before any protocol | Free-text aim + 2–4 facets + seed papers (no eligibility) | **None** — locked label "exploratory literature brief (non-systematic)"; PRISMA-S items recorded internally | None | Ranked seed list, vocabulary harvest, draft taxonomy, new-records-per-query series (the word "saturation" is forbidden), *candidate gaps as templated questions* | Hours–2 days | **core-v1** (M4; no public tag between M3 and M4) (*) | The on-ramp and feeder of every other method's vocabulary and gold-set candidates — safe because its search is recorded, its label is locked, and its templated outputs are linted. |
| Prior-work check | "has anyone done X?", contribution check | Calibrated statement of prior work found within a recorded search | Before any paper | as reconnaissance | None; templated sentence with corpus qualifier | None | Per-paper "closest on: [facet]" tags + one quoted claim with provenance + "we did not identify … in [sources] on [date] with [strings]" | Hours | **core-v1 (output** of reconnaissance; Q1 option g) (*) | The most-requested job, served as a *sentence form*, never a novelty claim. No UI element may contain "novelty". Patents stated out of scope on the card. |
| Narrative background / related-work section | traditional literature review, thesis Chapter 2 | Framed account of a field | Every primary study | as reconnaissance or scoping | SANRA (quality scale only) | None | `related_work_draft.md` (prose citing "search log in Supplementary S1") + generated `supplementary_search_log.md`; audit copy `landscape_brief.md` keeps its banner | Days | **core-v1 (output** of recon/scoping) | Generatable from a recorded corpus. The design no longer claims an "unstrippable" footer; the guarantee is that the log exists and is cited. |
| **Living update** | LSR, living review, review update | Has new evidence changed the conclusions since the last search? | A completed review in `results/<TOPIC>/` | Inherits base | PRISMA-LSR (2024) add-on; Cochrane LSR guidance (Elliott et al. 2017) | Inherits | `/prisma-search --rerun` (idempotent dedup appends only new records) → `/prisma-screen export` (already exports only undecided) → re-synthesise → human `impact_on_conclusions` in `protocol.json.versions[]` | Recurring; days per cycle | **core-v1 (mode)** | Replay + append on primitives the repo already has; no delta files, no new directory. A plan-hash change between versions forces a "methods changed since version N" block. Retraction/preprint sweeps need connector work → v2. |
| Snowballing / citation chasing | backward/forward citation search (Wohlin 2014, 2022) | Closure of relevant work reachable by citations | Unstable terminology; complement or (CS packs) primary strategy | n/a | **PRISMA-S item 5** (citation searching); item 9 is populated from eligibility limits, never from snowballing | Inherits | Inherits | Days per iteration | **core-v1 (recorded search strategy)** | `citation_chase.py` exists; seed set, iteration and stopping rule are written to its `raw/*.meta`. Seeds are excluded from the recall denominator. |
| Umbrella review / overview / tertiary study | review of reviews, meta-review | What existing SRs collectively show; overlap | Several SRs exist | Review-level question | PRIOR 2022; JBI umbrella methodology; **SEGRESS** for SE tertiary studies (Kitchenham 2010 is an example, not a guideline) | AMSTAR 2, ROBIS (ids only) | Tabulation + corrected covered area; re-pooling only after primary-study de-duplication across SRs by `reports[]`, with CCA reported | 3–9 months | **v2** | SR manifest with `unit_of_analysis: review`; the `appraisal/` store arrives with it (first second consumer). |
| Meta-analysis of proportions | prevalence MA, CoCoPop | How common is X | Non-comparative studies | CoCoPop | PRISMA 2020; JBI prevalence chapter | JBI prevalence checklist; Hoy et al. 2012 | `proportions`: logit/GLMM (no Freeman–Tukey default) | 3–6 months | **v2 (family)** | Own transform module with `metafor` fixtures. |
| MA of observational exposure studies | MOOSE-type review | Exposure–outcome association | Trials impossible | PECO/PEO | MOOSE 2000; PRISMA 2020 | ROBINS-E; NOS; GRADE observational start rules | `pairwise_iv` with adjusted estimates | 4–12 months | **v2 (pack defaults)** | Same engine; instrument and GRADE start rules are pack data. |
| Diagnostic accuracy / prediction-model / diagnostic-AI review | DTA SR, CHARMS review, SR of ML classifiers | Which models/tests exist, how well they perform, how biased | Clinical AI classification/segmentation, imaging diagnosis | PIRD; PICO with index model / reference standard | PRISMA-DTA 2018; TRIPOD-SRMA 2023; CLAIM 2024 / TRIPOD+AI 2024 / STARD-AI 2025 as primary-study adherence checklists | QUADAS-2 (per-domain only; **no overall algorithm**), QUADAS-C, PROBAST 2019, PROBAST+AI 2025 (QUADAS-AI protocol only — flagged, not used) | `dta_narrative` first (2×2 tables, no pooling); `dta` (bivariate/HSROC, Deeks' test; **never DL on sens/spec**) later | 6–18 months | **v2 (dialect over SR: `dta_narrative`)**; `dta` engine **later**; **v1 fails closed** on accuracy/prediction-model questions and offers scoping (*) | Routing a DTA question to SR + PRISMA 2020 without PRISMA-DTA is misreporting; the reviewer is right. Pack `medical_imaging_prediction`. |
| Image-reconstruction / benchmark tabulation | leaderboard review, ML methods survey, fastMRI table | Which methods perform best on which benchmarks; are results reproducible | Shared public benchmarks | Pack-rendered PICO ("method A vs baseline B on metric C, dataset D, condition E") | No review-level standard (report says so); SEGRESS; Pineau et al. 2021 reproducibility checklist for extraction | **`appraisal: none`** — reproducibility/leakage checklist explicitly labelled "not a risk-of-bias instrument"; PROBAST/QUADAS-2 do not apply to PSNR/SSIM studies | `structured_survey` (v2: `structured_narrative` stratified by dataset/protocol); **cross-dataset pooling refused by the core `pooling_unit.identity_fields` predicate** | 1–3 months | **v2 (pack `image_reconstruction` + family)**; v1 routes to scoping/mapping | Shared test sets are not independent samples; the tool's job is to refuse the pooled PSNR. |
| Multivocal literature review | MLR, grey-literature review | Practitioner + academic evidence | Practice-heavy SE/ML | as SR/scoping | Garousi et al. 2019; SEGRESS | AACODS | Thematic, source-stratified | 3–9 months | **v2 (source layer)** | A grey-source class + one appraisal id; needs connector work. |
| Methodological / meta-research review | methods review, reporting-quality audit | How a literature uses/reports method M | Meta-science | PCC | PRISMA 2020 borrowed; the audited checklist | The audited checklist | Descriptive adherence counts | 2–9 months | **later** (routing refusal → scoping) | Scoping with a checklist-shaped charting form when someone asks. |
| QES — meta-aggregation (JBI) | JBI qualitative SR | Aggregated findings with graded credibility | Experience/acceptability questions | PICo, SPIDER, SPICE | ENTREQ 2012; JBI Manual | JBI qualitative checklist (`use: describe`); ConQual | Findings (U/C/NS) → categories → synthesised findings | 6–12 months | **later** (routing refusal; **never** SR) (*) | Three new stage kinds, four schemas, an owner; the routing row alone guarantees no qualitative question lands in SR. |
| QES — thematic / framework synthesis | Thomas & Harden 2008; Carroll et al. 2011 | Descriptive→analytical themes | as above | as above | ENTREQ; Cochrane QIMG; BeHEMoTh | CASP / JBI (`use: describe`); GRADE-CERQual | Codebook → themes; framework fill + residual | 4–12 months | **later** (*) | Same findings store; interpretive steps human-only. |
| Mixed-methods systematic review | MMSR | Effect + experience | Complex/implementation questions | PICO + PICo | PRISMA 2020 + ENTREQ; JBI MMSR | MMAT 2018 + strand tools | Convergent/segregated | 9–18 months | **later** (refusal → "two linked topics, SR + scoping") | Composition of SR + QES. |
| Network meta-analysis | NMA | Rank ≥3 interventions | Connected network; transitivity plausible | as SR | PRISMA-NMA 2015 | RoB 2 + CINeMA | Network models | +3–6 months | **later** (export to R `netmeta`) | Transitivity is substantive judgment; engine after pairwise, proportions and DTA are trusted. |
| Dose–response MA; economics meta-regression; eco-evo MA; SYRCLE preclinical; COSMIN | — | Domain engine or instrument variants | Domain owners | varies | as named | as named | engine variants | varies | **later** / COSMIN & HTA **out-of-scope** | Family/pack PRs when an owner appears. |
| Bibliometric / science-mapping analysis | scientometrics | Structure of a literature as an object | Field-structure questions | n/a | BIBLIO 2023 (preliminary) | None | Network/cluster metrics | Weeks | **later** (*) | v1/v2 ship only a "corpus description" table (year/venue/type counts) labelled as such, excluded from evidence claims. |
| Realist synthesis; meta-narrative; critical interpretive synthesis; meta-ethnography | RAMESES; CIS; eMERGe | Theory-driven / interpretive syntheses | Complex programmes | CMO; n/a | RAMESES I/II; eMERGe | Relevance/rigour; CASP | Programme theory; line-of-argument | 9–18 months | **out-of-scope** (routing refusal + pointer) | Iterative theory-led searching contradicts a fixed replayable `search_plan.json`. |
| Integrative / critical / hermeneutic review; concept analysis; meta-summary | Whittemore & Knafl; Walker & Avant | Label-level variants without a validatable process | — | — | none governing conduct | — | — | — | **out-of-scope** (folded into scoping/recon by routing) | No process a gate can check. |
| IPD meta-analysis | IPD-MA | Participant-level pooling | Consortia | as SR | PRISMA-IPD 2015 | RoB 2 + data integrity | One-/two-stage | 1–3 years | **out-of-scope** | Data governance, not literature tooling. |
| Patent landscape / FTO; horizon scanning; maturity assessment; Delphi; guideline EtD | PLR, foresight | IP, foresight, maturity, consensus | — | — | WIPO PLR 2015 | — | — | — | **out-of-scope** | Wrong sources or non-bibliographic processes; a scholarly search can never support a novelty claim. A pack-defined "maturity stage" field may exist per study; **ISO 16290 is not cited** (space-systems TRLs). |

---

## 2. Routing assessment

**Principle:** the LLM asks and explains; a versioned decision table `methods/_routing.json` evaluated by `tools/route.py` decides; answers, table version, recommendation, chosen method and any override are recorded in `protocol.json.method`; the recommendation is one the human confirms (the first human gate). Unsupported targets fail closed against a *routing row* carrying refusal text and a pointer (no stub files). Questions are phrased in the user's language; answer options never use method vocabulary.

**Before the interview.** `/prisma-init` accepts a free-text aim; the topic slug is derived after Q1 and confirmed. `/prisma-init` Steps 1–2 (scope selection, reviewer-profile interview) become manifest-conditional: reconnaissance skips scope selection and defers the profile interview to the first `/prisma-report`; when `CLAUDE.local.md` already carries "field of research" and "target venue", they pre-select the pack, the Q3 default and the mapping/scoping default instead of being asked again.

### 2.1 Ordered steps (five asked, one computed after Q1, one conditional)

| # | Step | Wording shown to the user | Recorded as |
|---|---|---|---|
| Q1 | Asked (multi-select among a/b/g; ordered by newcomer frequency) | **What do you need at the end?** (a) get oriented — key papers, vocabulary, what's been done · (g) check whether something like my idea has already been done · (b) a background/related-work section · (c) a map of what exists and where it is thin · (d) a defensible answer to one specific question · (f) a summary of what existing reviews conclude · (e) update a review that already exists in this workspace | `goal ⊆ {orient, prior_work, background, map, answer, overview, update}` |
| Q0 | **Computed after Q1** on the free-text aim | *(no question)* A **bounded existing-review scan** over enabled connectors: per-connector filter `type:review OR title~(survey|review|overview|systematic|mapping|benchmark)`, written to `raw/` with meta `purpose: orienting`. Block title: "Existing reviews found in [sources] — this does **not** search PROSPERO, Epistemonikos, Cochrane Library or INPLASY." Options in plain words: "one of these already does what I need", "I want to update one of these", "I want to summarise what these reviews say", "none of these — keep going". A recorded human PROSPERO/OSF lookup (date, result) is asked for here and is **required for the SR label**. | `routing.q0 = {raw_files[], human_judgement: use_existing|update_external|overview|proceed, registry_lookup: {date, result, url}}` |
| Q2 | Asked | Template rendered from the pack, with one worked example per option. Generic: **Can you state your question as "does/how well A, compared with B, affect C in D"?** Imaging/CS pack: **"does method A, compared with baseline B, improve metric C on dataset D under condition E?"** Yes · Roughly · Not yet — it's an area, not a question | `question_focus: focused|rough|forming` |
| Q3 | Asked, with one disambiguator | **What kind of papers do you expect to find?** trials/experiments with numbers · observational studies · algorithm/benchmark papers · test-accuracy or prediction-model studies · interviews/qualitative · existing reviews · mixed/don't know. If algorithm *or* test-accuracy: **Are results reported on shared public datasets (fastMRI, BraTS…) or on patients / clinical outcomes?** | `evidence_type`, `benchmark_vs_clinical` (selects pack default and instruments; pack missing ⇒ `generic` + printed note) |
| Q4 | Asked | **How many people can screen independently, and how much time do you have?** just me · 2 or more; an afternoon · a week · 1–3 months · 6+ months | `reviewers: 1|2+`, `time_budget` — sets the *offer* of profile flags and the predicted label shown on the card; never selects the method and never stored as a label |
| Q5 | Asked | **Will you formally rate each paper's risk of bias with a checklist (e.g. RoB 2, PROBAST)? Most related-work sections and surveys do not.** Yes · No · Not sure (treated as No) | `appraisal_intent` |
| Q6 | Conditional (`goal ∋ answer` and `evidence_type ∈ {trials, observational}`) | **Do you expect several studies to report the same measurement for the same comparison, so their numbers could be combined?** Yes · No · Not sure | `expects_pooling` — if yes, the synthesis plan is drafted and signed **at G-Protocol** |

Everything else the current `/prisma-init` asks is asked **after** the recommendation card, and only the fields the chosen manifest requires.

### 2.2 Decision logic (`methods/_routing.json`; one unit test per row)

```
# First matching rule wins. RESULT = (method_id, synthesis_family, profile_flags[], modes[], output_profiles[])
# Rows may terminate in REFUSE{reason, pointer, offer[]} — no manifest exists for refused targets.

R0  q0.human_judgement == update_external   -> systematic_review, update_of = {citation}     # a "review update" (Garner 2016): new protocol,
                                                                                            # PRISMA 2020 items 3/24 disclosure; NOT living mode
R1  goal ∋ update                            -> LIVING(base) if a completed base exists in results/<TOPIC>/ else ASK("which completed review?")
R2  goal ∋ overview or evidence_type == existing reviews
                                             -> REFUSE{umbrella_review (v2), PRIOR 2022; offer: scoping_review "describes reviews, does not appraise them"}
R3  goal ∩ {orient, prior_work, background} ≠ ∅ or question_focus == forming
                                             -> reconnaissance, output_profiles from goal (prior_work_check, background_section)
R4  goal ∋ map:
      evidence_type == algorithm/benchmark   -> systematic_mapping_study if venue_default == cs_se else scoping_review (user may switch)
      matrix dimensions requested            -> REFUSE{egm (v2)} offer scoping_review
      else                                   -> scoping_review
R5  goal ∋ answer and question_focus == forming
                                             -> scoping_review, explain("your question is not yet answerable; map first")
R6  goal ∋ answer:
      evidence_type == qualitative           -> REFUSE{meta_aggregation (later), ENTREQ/JBI; offer scoping_review only — never SR}
      evidence_type == mixed                 -> REFUSE{mixed_methods (later); offer "two linked topics: SR + scoping"}
      evidence_type == test-accuracy/model   -> REFUSE{dta_narrative (v2), PRISMA-DTA 2018 / TRIPOD-SRMA 2023; offer scoping_review}   # v1
      evidence_type == algorithm/benchmark   -> scoping_review or systematic_mapping_study (v1); v2: systematic_review + structured_survey (pooling forbidden)
      evidence_type in {trials, observational}:
          expects_pooling == yes             -> systematic_review, family = pairwise_iv (plan signed at protocol)
          else                               -> systematic_review, family = structured_narrative (swim if rows are directional effects)
R7  profile offers (SR only):
      reviewers == 1                         -> offer single_reviewer (verification sample menu); predicted label shown now (§2.4)
      time_budget <= weeks                   -> offer rapid (RRMG shortcuts menu); the rapid LABEL derives from shortcuts[] non-empty, not from time
      time_budget == afternoon and goal ∋ answer
                                             -> reconnaissance ONLY, explain("you can find what exists today; deciding whether it works takes weeks —
                                                here is the path to that if you want it later")
R8  appraisal_intent == yes and RESULT in {scoping_review, systematic_mapping_study, reconnaissance}
                                             -> keep RESULT; explain("X does not appraise; if you need certainty claims you need an SR, which costs …")
R9  pack resolution: pack from CLAUDE.local.md field / Q3; missing -> generic + printed note
R10 user override                            -> record {recommended_id, chosen_id, override_reason}; label still computed from conduct
```

**Fallback rule (settled):** routing may only fall *down* the claims ladder (→ scoping → reconnaissance) or refuse. It never falls *sideways* into an SR label for a question type the tool cannot synthesise or report correctly (qualitative, mixed, review-of-reviews, diagnostic accuracy in v1). A fallback is recorded as `fallback_reason` and printed verbatim in the manuscript's Methods.

### 2.3 What is recorded

`protocol.json.method` (the single new per-topic *input*):

```json
"method": {
  "id": "systematic_mapping_study", "version": "1.0.0", "synthesis_family": null,
  "profile_flags": [], "modes": [], "pack": "cs_se", "output_profiles": [],
  "routing": {
    "table_version": "1.2.0",
    "answers": {"goal": ["map"], "question_focus": "rough", "evidence_type": "algorithm", "benchmark_vs_clinical": "benchmark",
                "reviewers": 1, "time_budget": "1-3 months", "appraisal_intent": "no"},
    "q0": {"raw_files": ["raw/openalex-20260906.json"], "human_judgement": "proceed", "registry_lookup": null},
    "recommended_id": "systematic_mapping_study", "chosen_id": "systematic_mapping_study",
    "override_reason": null, "fallback_reason": null
  },
  "signed_at": "2026-09-06T10:12:00Z", "signed_by": "reviewer-id"
}
```

No `predicted_label` is stored (it is derived state and would go stale); `tools/label_gate.py` computes it on demand at routing, `/prisma-status` and `/prisma-report`, and writes `manuscript/label.json` = `{label, disclosures[], missing[], blockers[]}` only at report time.

### 2.4 Explaining the recommendation ("because" card, rendered from manifest `microcopy`)

Five lines, fixed template, filled only from recorded answers and the manifest; **every label and gate name on the card carries a one-sentence gloss** (e.g. "*Sign* = type 'confirm'; it timestamps that you wrote the plan before searching, which reviewers will ask about"):

1. **What you told me** — the answers echoed in the user's words.
2. **What I recommend and what it is** — `microcopy.what`.
3. **What you will have at the end** — `microcopy.gives` and the reporting checklist that will be audited.
4. **What it costs** — effort band, whether a second person is needed, the human gates, **the sources this workspace can and cannot reach for your field** (from `pack.source_expectations × connectors/registry.py`, with each connector's "what this indexes / does not" blurb), and current API-key status (rate limits an afternoon user will hit).
5. **What you will be allowed to call this, and why** — the predicted label with its reason ("with one screener and no verification sample this will be reported as a systematized review; adding a second person over a 20% sample of your title/abstract excludes changes that"), and `microcopy.cannot_claim`.

Two collapsed links: *why not the next step up* (`microcopy.upgrade_to`, with cost) and *the guideline this follows*.

**"You asked for X but Y fits better because…"** — when `chosen_id ≠ recommended_id` or R8 fires, one sentence tied to a specific answer, e.g. *"You said you cannot yet fix what A is compared with, so this is a scoping review, not a systematic review; a scoping review maps what has been studied but cannot tell you whether the method works. If you later find ≥5 comparable studies on one sub-question, you can start a systematic review from this corpus — a fresh protocol, but nothing is retyped."*

**"Downgrade honestly" rule — the project conduct floor** (same `label_gate.py` code and manifest `label_rules` at routing, status and report):

- The floor is **not** AMSTAR-2 (a confidence-rating tool for healthcare-intervention SRs, not a taxonomy, and not validated for CS/SE). It is a *project rule*, cited to MECIR C39 (duplicate selection) and Grant & Booth 2009, and the text "AMSTAR-2" never appears in a label. "**systematic review**" requires: (i) `protocol.signed_at` earlier than the first `raw/*.meta` with `purpose: protocol_driven`; (ii) ≥2 distinct **index families** (`connectors/registry.py` declares `index_family`; PubMed ⊂ Europe PMC counts once; the report states "N connectors over M distinct indexes"); (iii) a recorded PROSPERO/OSF lookup (Q0); (iv) **some second-reviewer involvement in selection** (dual screening, or a recorded verification sample declared in `shortcuts[]`); (v) pooling only under a plan whose hash predates the first protocol-driven run.
- Missing (i) or (iv) → "**systematized review**" ("systematized literature review" in `cs_se`), missing elements listed in Methods and Limitations, told at routing from `reviewers == 1`, not at month six.
- **Incomplete stages are not conduct choices**: missing full-text exclusion reasons or unfinished appraisal **block the report build** with a to-do list; they never change the label.
- Single screener **with** a recorded verification sample → label "systematic review", with `disclosures[] += "single-reviewer screening with verification (N%, stage)"`; `label.json` separates `label` from `disclosures[]` so the disclosure lands in Methods, never in a title.
- **Extraction verification**: `extraction_table.json` rows carry `by` and `verified_by`; for `pairwise_iv` outcomes without a recorded outcome-data verification sample, the SoF table carries a footnote and Limitations carries mandatory text (MECIR C50 / AMSTAR 2 item 6) — a disclosure, not a downgrade (§6 #19).
- **Search currency**: if the last protocol-driven run is older than 12 months at report time, Limitations carries mandatory text and `disclosures[] += "search_age"`; no downgrade.
- Scoping/mapping reviews are never downgraded for single screening — **disclosed per PRISMA-ScR item 9; JBI recommends two reviewers** (the earlier rationale "JBI permits it" was wrong).
- Reconnaissance is always "exploratory literature brief (non-systematic)"; no flow diagram; "screening", "eligibility", "saturation" vocabulary is forbidden in its outputs.
- **Forbidden-form lint** (in `label_gate.py`): *hard failure* only on the tool's own templated outputs (recon brief, prior-work sentences, gap statements, `related_work_draft.md`) for the forms "comprehensive/exhaustive search", "all relevant studies", "first to", "no prior work", "proves", "novel", "saturat*", unqualified "gap"; *warnings* (listed in the checklist audit) on Abstract/Conclusions of SR/scoping manuscripts for the short blocklist, so "gap junction" or "comprehensive geriatric assessment" never blocks a build. The calibrated forms "to our knowledge, within the search described in S1, we did not identify …" and the PRISMA item-3 rationale context are allowed.

---

## 3. Common stage model

### 3.1 Shared stages (documented in the nine commands; manifests carry only the policy that switches a stage off or changes its rules)

The stage sequence stays where it lives today — in the Markdown commands and skills, which *are* the implementation. Manifests do **not** list stages or gates; each command's Step 0 reads the manifest's policy fields and, if the policy says this stage does not apply, prints the stage that does. S0–S9 below are the panel's vocabulary for the design, not a registry the code enforces.

| # | Stage | Command / skill (existing unless noted) | Artifact(s) | Deterministic tool | Human gate (and the deliverable handed back) |
|---|---|---|---|---|---|
| S0 | route | `/prisma-init` Step 0.5 (routing questions live as a reference file in `review-protocol`) | `protocol.json.method` | `tools/route.py`; Q0 raw run with `purpose: orienting`; `label_gate.py` predictive | **G-Route**: confirm/override method → "because" card + Q0 list + predicted label |
| S1 | protocol | `review-protocol` | `protocol.json` (framework per manifest and pack glosses, eligibility, `eligibility_version`, `signed_at`, `amendments[]`, `versions[]`), `synthesis_plan.json` **when family is `pairwise_iv`, signed here** | schema validation (`jsonschema`, pinned); `signed_at` vs first protocol-driven raw run; plan hash | **G-Protocol**: sign protocol (and plan) → rendered protocol draft (PRISMA-P-shaped for SR; PCC/charting-form draft for scoping; Petersen RQs for mapping) |
| S2 | search-plan | `keyword-expansion` | `search_plan.json` (per-source strings, PRISMA-S items 1–16 structured; small — no run history) + `rerun_search.sh` | per-source grammar parse; plan↔script drift test; **PRISMA-S item 14 = "not peer reviewed" unless a distinct `by` id signs**; item 5 from citation chasing, item 9 from eligibility limits | **G-Terms**: accept/prune terms; supply 3–5 known papers with `provenance` (recon-db | citation-chase | external-review | expert) → PRISMA-S appendix draft |
| S3 | search-run | `/prisma-search` + connectors + `citation_chase.py` | `raw/<source>-<date>.json` + `.meta` (**the run ledger**: `fetched_at, retrieved, total_available, truncated` + new connector-owned `connector_version, query, purpose: orienting|protocol_driven, plan_hash`; snowballing meta adds seed set, iteration, stopping rule; `manual_source` entries for uploaded exports, flagged non-replayable and printed as such in PRISMA-S items 1/13), `records.jsonl` (`duplicate_of` unchanged; `first_seen` = raw filename), `dedup_report.json` | connectors; `dedup.py`; `search_preflight.py` (known-item recall per gold-item provenance, classified index-miss/string-miss, seeds excluded from denominator; "non-independent gold set" printed when all items came from the same connectors; unique contribution; new-records-per-query series) | **G-Search**: resolve ambiguous duplicate pairs; accept validation or revise strings — a **string-miss re-enters `keyword-expansion` with the missed paper's title/abstract terms as LLM-suggested additions the user accepts or declines**; waiver-with-reason where the manifest allows → validation report, coverage-gap list |
| S4 | screen | `screening-assistant` | `screening/*.md|csv`, `screening_decisions.jsonl` (hash-chained; `by`, `role: decision|verification`, `eligibility_version`; decision enum gains `not_retrieved`) | `ledger.py` (append/verify); `flow_counts.py` (aggregates `role == decision`; `not_retrieved` counted in its own PRISMA box); kappa from `verification` lines paired with the latest `decision` | **G-Screen / G-FullText**: every include/exclude; every full-text exclusion reason → live flow counts, Item 16b list |
| S5 | chart-or-extract | `/prisma-extract` (+ new `evidence-mapping` skill for charting/classification) | `extraction_table.json` (array **or** `{"studies": [...]}`, both accepted; rows gain `by`, `verified_by`, `reports[]` for several reports of one study, `risk_of_bias.instrument` id next to legacy `tool`) **or** `charting_table.json` / `classification_table.json` (provenance quote/page/hash; `suggested_by: llm|connector`) | schema validation; provenance presence; `schema_freeze` (charting form after 5–10 pilot records — `packs/generic` ships a default form: year, venue, publication type, data source, method family, main metric, code/weights available, claimed contribution); classification scheme after keywording a sample; solo calibration = delayed intra-rater re-code of ≥10 records with disagreement count disclosed | **G-Freeze** then **G-Values**: freeze form/scheme; confirm every LLM-suggested value (connector-sourced year/venue/type need no confirmation) → table with provenance |
| S6 | appraise | `quality-appraisal` | `risk_of_bias` blocks in extraction rows (the `appraisal/` store arrives with umbrella review, v2) with `instrument`, item, judgement, justification, quote, `judged_by` | instrument list per pack (ids + own paraphrase; no verbatim NC-ND text); completeness; domain→overall algorithms **only** for RoB 2 and ROBINS-I (QUADAS-2 is per-domain; NOS has none); `rob2` fails closed outside clinical packs; `use ∈ {describe, sensitivity, exclude}` — **never weight** | **G-Appraise**: every domain judgement and justification (LLM may only locate passages) → RoB summary figure |
| S7 | synthesize | `synthesis/` | `synthesis/<family>/*.json`, SVGs, `synthesis/post_hoc/` | `run_synthesis.py` dispatches on family; refuses `pairwise_iv` without a plan hash; **any plan hash newer than the one recorded at the first protocol-driven run forces output to `post_hoc/` and the "specified after study selection" rendering (PRISMA 2020 item 24c) — `amendments[]` text goes to item 24c, never to the plan's authority**; `pooling_unit.identity_fields` predicate in core; heterogeneity descriptive only (`choose_model` deleted); certainty-table *assembly* from human fields | **G-Synthesis**: confirm grouping/poolability/interpretation; every certainty-domain judgement with justification → SoF table, forest/funnel or SWiM/structured tables or charting summaries |
| S8 | report | `prisma-manuscript` (standard-agnostic) | `manuscript/`, `flow_diagram.svg`, `checklist_audit.md` (LLM-audited against the manifest's Markdown reference checklists), `label.json` | flow counts from ledger; `label_gate.py` definitive + templated-output lint; `export_report.py`; reference verification | **G-Claims**: approve every templated "we did not identify…" / gap sentence (batched in one sheet); own the manuscript → manuscript + audited checklist + Limitations generated from `coverage_gaps`, shortcuts, deviations, disclosures |
| S9 | living update (mode) | `/prisma-search --rerun` + `/prisma-screen export` + `/prisma-synthesize` + `/prisma-report` | `protocol.json.versions[] = {base_report_date, rerun_date, plan_hash, impact_on_conclusions}`; `--since <raw date>` flow counts for the PRISMA-LSR block | idempotent dedup yields the delta; a `plan_hash` change between versions forces a "methods changed since version N" block | **G-Impact**: write "conclusions unchanged / more precise / direction changed" → PRISMA-LSR block, version history |

`/prisma-status` reads manifest policy flags via `tools/status.py` (Phase 0's extraction of its inline Step 3) and prints **the plain-language stage name, the deliverable, and the command** from `microcopy` — e.g. "Next: summarise your charted table (counts and plots) — run `/prisma-synthesize`".

### 3.2 Per-method stage applicability

R = required, O = optional (declared), — = not applicable (the command refuses and points to the stage that applies), (*) = variant in §3.3. Each "—" or variant corresponds to one manifest policy field, named in parentheses.

| Method | S1 protocol | S2 plan | S3 run | S4 screen | S5 capture | S6 appraise | S7 synthesize | S8 report | S9 living |
|---|---|---|---|---|---|---|---|---|---|
| Systematic review | R (+ plan when `pairwise_iv`) | R | R (recall `fail_closed`) | R (dual recommended; count disclosed) | R extraction | R (`appraisal.requirement: mandatory`; fail-closed on unsupported design/pack) | R (`families_allowed`) | R (PRISMA 2020 + PRISMA-S; SWiM when `swim`) | O |
| Rapid / single-reviewer (profile) | R (+ `shortcuts[]` from RRMG menu) | R | R | R (verification per shortcut) | R | R (may be limited per declaration) | R | R (+ deviations table) | O |
| Scoping review | R (PCC with pack glosses; `criteria_may_evolve: versioned`) | R | R (recall `waivable_with_reason`) | R (single + verification acceptable, disclosed) | R charting (`capture.mode: charting`, freeze after pilot) | O (`optional_with_justification`, `use: describe`) | R descriptive (`families_allowed: [descriptive]`) | R (PRISMA-ScR) | O |
| Systematic mapping study | R (Petersen RQs) | R (snowballing may be primary if pack allows) | R (QGS quasi-sensitivity when `controlled_vocab: none`) | R (TA may suffice) | R classification (scheme freeze; calibration re-code) | O | R (bubble plots, facet counts) | R (SEGRESS report; Petersen conduct) | O |
| EGM (v2) | R (+ frozen 2-D framework) | R | R (recall `fail_closed`) | R | R coding to cells (dual-coded sample) | O (AMSTAR 2 on SRs) | R matrix + corpus-qualified cells | R (Campbell/ROSES) | O |
| Reconnaissance | R-lite (aim, facets, seeds; **no eligibility, no outcome-magnitude field**) | R-lite (`search.mode: orienting`; seeds only) | R (bounded caps; one snowball iteration; new-records series; recall `advisory`) | — (`capture.mode: relevance_tags`: ~30–60 items tagged in one exported sheet, ledgered as `relevance`, never "screening") | R-lite (connector-filled year/venue/type; human `claimed_contribution`) | — (`appraisal.requirement: none`) | — (`families_allowed: []`) | R (fixed templates; no flow diagram; linted) | — |
| Living (mode) | R (update rule in base protocol) | inherits | R rerun | R undecided only | R new rows | R new rows | R cumulative | R (+ PRISMA-LSR block) | is S9 |

### 3.3 Method-specific rules

- **Systematic review:** for `pairwise_iv`, effect measure, model, τ² estimator, CI method (HKSJ + modified KH), PI, k-minimum, subgroups, sensitivity, small-study methods (k≥10 rule), unit-of-analysis rules and `pooling_unit.identity_fields` are drafted by the LLM and **signed at G-Protocol, before the first protocol-driven run**; only outcome-to-row mapping may be finalised pre-extraction. A plan signed after selection is permitted but every analysis under it renders as "specified after study selection". Report→study identity is `reports[]` on the extraction row. Migrated legacy topics get a `synthesis_plan.json` with `retrospective: true`; the label gate prints "legacy: model selected by heterogeneity statistic, not prespecified" as a disclosure.
- **Scoping review:** pilot screening may refine eligibility; each refinement bumps `protocol.json.eligibility_version` (ledger lines carry it; the label gate discloses changes after first screening; SR permits change only via `amendments[]`). Charting form co-developed from the pack default, piloted on 5–10 records, frozen (G-Freeze). Appraisal, if enabled, records a justification. Consultation exercise optional and recorded.
- **Systematic mapping study:** classification scheme built by keywording a sample (pack supplies candidate facets; Wieringa research types), frozen, then coded; calibration re-code (inter-rater when two, delayed intra-rater ≥10 records when one) with agreement/disagreement disclosed. Snowballing primary only where `pack.search.primary_strategies_allowed` includes it; recall gate applies with seeds excluded.
- **Reconnaissance:** stopping rule declared; new-relevant-records-per-query series recorded (never called saturation). `landscape_brief.md` (audit copy: banner, "prior work identified so far", "what this did not search", candidate gaps as templated questions each approved at G-Claims) and `related_work_draft.md` + `supplementary_search_log.md` (usable prose citing S1). Prior-work check: per-paper "closest on: [facet]" tags and one quoted claim with provenance; comparison left to the human. Hand-off files in `handoff/` (`seed_terms.json`, `gold_set_candidates.json` with `provenance: recon-db`, `disclosure.md` glossed as "if you later run a scoping/systematic review, reviewers will ask whether you had seen the literature before writing your protocol; this paragraph answers that honestly"). **Promotion is same-topic**: recon artifacts move to `recon/`, `records.jsonl` is archived, `method` changes via `amendments[]`, the new method's search is rerun from its protocol, `handoff/` is read only from the same topic (CLAUDE.md's cross-topic rule holds).
- **Living mode:** requires a completed base; update rule (cadence, trigger, stopping rule) signed into the base protocol; delta = new lines after `--rerun`; cumulative estimate + PI, no repeated significance claims unless sequential methods were in the base plan; `impact_on_conclusions` is human. Retraction/preprint sweeps arrive with connector support (v2).
- **Rapid profile:** `shortcuts[]` chosen at G-Protocol from the RRMG 2024 menu verbatim; each written to `deviations.jsonl`; label per §2.4.
- **Umbrella (v2):** re-pooling only after primary-study de-duplication across included SRs via `reports[]`, with CCA reported.

---

## 4. Architecture

### 4.1 Guiding rule and the layers

Keep the doctrine literally. **Behaviour and sequence** stay in the Markdown commands and skills. Add one thin **data layer** (flat `methods/*.json`, flat `packs/*.json`, Markdown reference checklists under the owning skill, JSON Schemas for state files) and extend the **deterministic layer** (`tools/`, `synthesis/`) that both the Markdown and CI read. No orchestrator, no generic stage interpreter, no schema composition, no plugin loader beyond "glob a directory of JSON and validate it" — the pattern `connectors/registry.py` already uses. Runtime neutrality is the artifact contract (`results/<TOPIC>/` + `methods/` + `packs/` + `tools/` CLIs).

### 4.2 Directory layout (additions only; nothing existing moves)

```
methods/
  _schema.json                     # JSON Schema 2020-12; closed enums for families, checks, capture modes, appraisal use; ~60 lines
  _routing.json                    # versioned (semver) decision table; refused targets carry {reason, pointer, offer[]}
  systematic_review.json           # today's pipeline as policy fields (M1)
  scoping_review.json              # (M3)
  systematic_mapping_study.json    # (M3)
  reconnaissance.json              # (M4)
  evidence_gap_map.json  umbrella_review.json   # v2, added when implemented — no stubs
packs/
  _schema.json                     # source_expectations REQUIRED; flat data; no schema composition
  generic.json  clinical_interventions.json  cs_se.json          # M3, data only
  medical_imaging_prediction.json  image_reconstruction.json     # M5, data only, status: experimental
schemas/
  protocol_method.schema.json  synthesis_plan.schema.json (Phase 0)  extraction_table.schema.json (array | {"studies": array})
  charting_table.schema.json  classification_table.schema.json  screening_decision.schema.json  deviations.schema.json
.claude/skills/*/references/       # standards as Markdown reference files (existing pattern)
  prisma-manuscript/references/{prisma-2020-checklist, swim-2020-checklist, prisma-scr-2018-checklist, segress-2023-checklist, prisma-lsr-2024-addon}.md
  evidence-mapping/references/petersen-2015-conduct.md      # conduct gates, not a reporting checklist
  keyword-expansion/references/prisma-s-2021-checklist.md
tools/
  method.py          # glob+validate methods/ and packs/; resolve for topic (absent -> systematic_review, pack absent -> generic)
  route.py           # answers -> recommendation; writes protocol.json.method.routing (no predicted_label)
  label_gate.py      # closed check enum; false vs not_recorded; writes manuscript/label.json; lints templated outputs
  status.py          # Phase 0 extraction of /prisma-status Step 3, reading manifest policy flags
  chart_summary.py   # counts, crosstabs, bubble plots (M3); EGM matrix (v2)
  dedup.py  ledger.py  flow_counts.py  search_preflight.py      # Phase 0 (preflight also emits the recon new-records series)
  # invoked as `python3 -m tools.<name>`; ~5 new allowlist entries in .claude/settings.json + security_guards, same PR as each module
synthesis/
  run_synthesis.py   # dispatches on synthesis_family; refuses pairwise_iv without a plan hash; post_hoc/ routing
  families/structured_narrative.py  families/swim.py  families/pairwise_iv.py   # v1
  families/proportions.py (v2)  families/dta.py (later)                        # absent -> "not implemented; export for R"
  heterogeneity.py   # descriptive only; choose_model deleted
.claude/commands/    # nine prisma-*.md unchanged in name; no /review pointer (README documents /prisma-init as the entry point)
.claude/skills/      # existing five + two new: evidence-mapping/ (M3), reconnaissance-brief/ (M4)
results/<TOPIC>/
  protocol.json (+ method, eligibility_version, versions[])  search_plan.json  rerun_search.sh
  raw/*.json + .meta (+ connector_version, query, purpose, plan_hash)  records.jsonl (+ first_seen)
  screening_decisions.jsonl (+ by, role, eligibility_version)  extraction_table.json | charting_table.json | classification_table.json
  synthesis_plan.json  deviations.jsonl  synthesis/  recon/ (after promotion)  handoff/  manuscript/ (+ label.json, checklist_audit.md)
```

### 4.3 The method manifest (policy deltas, not a stage list)

Fields (each fact once): `id`, `label`, `aliases[]`, `version` (semver, watched by `check_framework_version.py`), `family` (`systematic|mapping|exploratory`), `question_frameworks[]`, `search{mode: protocol_driven|orienting, min_index_families, primary_strategies_default[], known_item_recall: fail_closed|waivable_with_reason|advisory}`, `screening{recommend_reviewers, criteria_may_evolve: amendment_only|versioned}`, `capture{mode: extraction|charting|classification|relevance_tags, schema, freeze_gate, pilot_records}`, `appraisal{requirement: mandatory|optional_with_justification|none, use[]}` (instrument ids come from the pack), `synthesis{families_allowed[], plan_required_for[], plan_required_at}`, `standards[]` (paths to Markdown reference files, optional `when`), `label_rules{label, requires[{check, value?}], profile_labels{}, otherwise{}, disclosures[]}`, `report_blockers[]`, `forbidden_forms[]`, `profiles[]`, `living` (bool), `microcopy{what, gives, costs, cannot_claim, upgrade_to, stage_names{}}`, `exports[]`. `check` values are a closed enum in `_schema.json`, each backed by one function in `label_gate.py`. No code, no templating, no wildcards.

**`methods/systematic_review.json` (today's pipeline):**

```json
{
  "id": "systematic_review", "label": "Systematic review", "aliases": ["SR", "SLR", "systematic literature review"],
  "version": "1.0.0", "family": "systematic",
  "question_frameworks": ["PICO", "PICOS", "PICo", "SPIDER", "PEO"],
  "search": {"mode": "protocol_driven", "min_index_families": 2, "primary_strategies_default": ["database"], "known_item_recall": "fail_closed"},
  "screening": {"recommend_reviewers": 2, "criteria_may_evolve": "amendment_only"},
  "capture": {"mode": "extraction", "schema": "schemas/extraction_table.schema.json", "freeze_gate": false},
  "appraisal": {"requirement": "mandatory", "use": ["describe", "sensitivity", "exclude"]},
  "synthesis": {"families_allowed": ["structured_narrative", "swim", "pairwise_iv"], "plan_required_for": ["pairwise_iv"], "plan_required_at": "protocol",
                "proposal_defaults": {"tau2": "REML", "ci": "HKSJ_modified", "prediction_interval_min_k": 3, "small_study_min_k": 10}},
  "standards": [
    {"ref": ".claude/skills/prisma-manuscript/references/prisma-2020-checklist.md"},
    {"ref": ".claude/skills/keyword-expansion/references/prisma-s-2021-checklist.md"},
    {"ref": ".claude/skills/prisma-manuscript/references/swim-2020-checklist.md", "when": {"synthesis_family": "swim"}}
  ],
  "label_rules": {
    "label": "systematic review",
    "requires": [{"check": "protocol_signed_before_first_protocol_driven_run"}, {"check": "min_index_families", "value": 2},
                 {"check": "registry_lookup_recorded"}, {"check": "second_reviewer_involvement_in_selection"}, {"check": "pooling_only_under_signed_plan"}],
    "profile_labels": {"rapid": "rapid review"},
    "otherwise": {"label": "systematized review", "list_missing": true},
    "disclosures": ["reviewer_count", "verification_sample", "extraction_verification", "search_dates", "search_age", "registration", "criteria_changes", "coverage_gaps", "legacy_pooling"]
  },
  "report_blockers": ["fulltext_exclusion_reasons_complete", "appraisal_complete", "references_verified"],
  "forbidden_forms": ["exhaustive_search", "comprehensive_search", "no_prior_work", "first_to", "novelty"],
  "profiles": ["rapid", "single_reviewer"], "living": true,
  "microcopy": {
    "what": "A systematic review answers one focused question from all eligible studies, with each study's risk of bias judged.",
    "gives": "A protocol, a replayable search appendix, a PRISMA flow diagram, an extraction table, risk-of-bias and certainty tables, and a PRISMA 2020 manuscript.",
    "costs": "Typically 6–18 months; two people who can screen independently, or one plus a second person over a recorded verification sample.",
    "cannot_claim": "That the search was exhaustive, or that anything is 'first' or 'novel'.",
    "upgrade_to": null,
    "stage_names": {"extract": "fill the study table", "appraise": "judge each study's risk of bias", "synthesize": "combine or tabulate the results", "report": "draft the manuscript and checklist"}
  },
  "exports": ["md", "docx", "ris", "csv", "svg"]
}
```

**`methods/scoping_review.json`:**

```json
{
  "id": "scoping_review", "label": "Scoping review", "aliases": ["scoping study", "evidence map"],
  "version": "1.0.0", "family": "mapping",
  "question_frameworks": ["PCC", "PICO", "SPIDER"],
  "search": {"mode": "protocol_driven", "min_index_families": 2, "primary_strategies_default": ["database"], "known_item_recall": "waivable_with_reason"},
  "screening": {"recommend_reviewers": 2, "criteria_may_evolve": "versioned"},
  "capture": {"mode": "charting", "schema": "schemas/charting_table.schema.json", "freeze_gate": true, "pilot_records": 5},
  "appraisal": {"requirement": "optional_with_justification", "use": ["describe"]},
  "synthesis": {"families_allowed": ["descriptive"], "plan_required_for": [], "plan_required_at": null},
  "standards": [{"ref": ".claude/skills/prisma-manuscript/references/prisma-scr-2018-checklist.md"},
                {"ref": ".claude/skills/keyword-expansion/references/prisma-s-2021-checklist.md"}],
  "label_rules": {"label": "scoping review",
                  "requires": [{"check": "protocol_signed_before_first_protocol_driven_run"}, {"check": "min_index_families", "value": 2}],
                  "otherwise": {"label": "scoping review (protocol not recorded before search)", "list_missing": true},
                  "disclosures": ["reviewer_count", "appraisal_performed_or_not", "criteria_changes", "search_dates", "coverage_gaps"]},
  "report_blockers": ["fulltext_exclusion_reasons_complete", "charting_form_frozen"],
  "forbidden_forms": ["effect_estimate", "effectiveness_conclusion", "certainty_rating", "exhaustive_search", "novelty", "no_prior_work", "unqualified_gap"],
  "profiles": [], "living": true,
  "microcopy": {
    "what": "A scoping review maps what has been studied, how, and where the literature is thin; it does not judge whether things work.",
    "gives": "A charted table of every included study, frequency tables and plots, a PRISMA-style flow diagram, and a PRISMA-ScR report.",
    "costs": "Typically 2–9 months; one screener is acceptable and is disclosed.",
    "cannot_claim": "Whether a method works, how certain the evidence is, or that the search was exhaustive; gaps are stated as 'no included study reported …' within the search bound.",
    "upgrade_to": "systematic_review",
    "stage_names": {"extract": "chart each study", "synthesize": "summarise your charted table (counts and plots)", "report": "draft the PRISMA-ScR report"}
  }
}
```

`systematic_mapping_study.json` differs only in `question_frameworks: ["petersen_rqs"]`, `capture.mode: classification` (+ `calibration_recode: true`), `standards` (SEGRESS report + Petersen conduct), `label: "systematic mapping study"`, `microcopy`. `reconnaissance.json` sets `search.mode: orienting`, `capture.mode: relevance_tags`, `appraisal.requirement: none`, `synthesis.families_allowed: []`, `label: "exploratory literature brief (non-systematic)"` with no `requires`, and `forbidden_forms += ["screening_vocabulary", "eligibility_vocabulary", "saturation"]`.

### 4.4 Field packs (flat data underneath methods; packs add glosses and expectations, never rules)

`packs/<id>.json` is a flat file with exactly these fields: `source_expectations[]` (**required**: source id, role `bibliographic|registry|grey|preprint|proceedings`, standard that expects it, `reachable_via` connector id or null — renders the coverage statement, fills `protocol.json.scope.coverage_gaps`, generates the Limitations paragraph); `controlled_vocab` (`mesh|emtree|none`); `search.primary_strategies_allowed[]`; `question_template` and `framework_glosses{}` (imaging: Population → "imaging modality / anatomy / dataset"; Concept → "method family"; Context → "acceleration, sampling pattern, evaluation setting", with an example filled form); `default_capture_fields[]`; `appraisal_instruments_by_design{}` (ids only; `rob2` only in clinical packs); `confidence_framework` (`grade|none`); `pooling_unit_identity_proposal[]` (pre-fills the core `synthesis_plan.pooling_unit.identity_fields` as a *proposal* the human signs — e.g. `dataset, split_policy, acceleration, mask, coil_setting, metric_definition`; the refusal to pool across datasets is then a core predicate over the signed plan, not pack code); `preprint_eligibility_default`; `label_rule_additions[]` restricted to the closed `check` enum (clinical: `{"check": "registry_or_grey_source", "value": 1}`, satisfiable via `manual_source` runs). No extraction-fragment schemas, no `allOf`, no override of any manifest field; `method.py` validates and refuses anything else. A pack that needs code is a fork, per doctrine.

### 4.5 Deterministic Python vs LLM-guided vs human-only

| Deterministic Python (tested, CI) | LLM-guided (Markdown specs; every output `suggested_by: llm`, inert until a human import) | Human only |
|---|---|---|
| Manifest/pack/schema validation; method resolution; routing table; predicted and definitive label; templated-output lint; flow counts | Asking the routing questions; rendering the "because" card and glosses from microcopy | Confirming/overriding the method; the Q0 overlap judgement and registry lookup |
| `signed_at` vs first protocol-driven run; plan hash ordering; `eligibility_version` | Eliciting framework fields (with pack glosses), eligibility wording, charting-form fields; drafting the synthesis plan at protocol | Signing protocol, plan, charting form, classification scheme |
| Connector execution, raw archiving with meta, dedup, hit counts, grammar parsing, recall classification with provenance, unique contribution, new-records series, snowballing bookkeeping | Concept extraction; synonym proposals; per-source string drafts; string-miss repair proposals | Accepting terms; supplying the gold set with provenance; waivers |
| Ledger append/verify, flow counts (`not_retrieved` box), kappa from `verification` lines | Screening-sheet drafting aids (never decisions) | Every include/exclude and exclusion reason |
| Schema + provenance validation; connector-sourced field fill | Extraction/charting/classification *proposals* with quote + location | Confirming every LLM value; freeze decisions |
| Instrument completeness; RoB 2 / ROBINS-I domain→overall algorithms; `rob2` fail-closed outside clinical packs | Locating passages per signalling question — **nothing else** | Every appraisal judgement and justification |
| All statistics (REML/PM/DL, HKSJ modified, PI, Q/I²/τ² descriptive, subgroup tests, Egger/Peters k≥10, SWiM sign tests), `pooling_unit` predicate, post-hoc routing, plots; certainty-table *assembly* | Plain-language interpretation with numbers injected from JSON; manuscript prose from state; templated gap/prior-work sentences; checklist audit prose | Poolability confirmation, grouping, every certainty-domain rating, impact-on-conclusions, approval of every templated sentence |
| Replay via `--rerun`; `--since` counts; methods-changed detection by plan hash; AI-use statement from `suggested_by` fields | Impact-on-conclusions *draft* | The impact judgement |

### 4.6 How the Claude commands become thin

- Every `/prisma-*` command keeps its name and steps. Its Step 0 gains **one line**: *"Resolve `method` and `pack` via `python3 -m tools.method` (absent ⇒ `systematic_review`/`generic`); if this command's stage does not apply under the manifest's policy fields, stop and print the stage that does, in plain language from `microcopy.stage_names`."* So `/prisma-synthesize` on a scoping topic renders charting summaries and refuses pooling; on a reconnaissance topic it says "this brief has nothing to combine; run `/prisma-report`"; `/prisma-extract` on scoping invokes the `evidence-mapping` charting sheet.
- `/prisma-init` gains Step 0.5 (Q1, Q0, Q2–Q6) with the questions and card template as a reference file in `review-protocol`; Steps 1–2 become manifest-conditional; the existing elicitation is filtered by `manifest.question_frameworks` and `pack.framework_glosses`.
- No `/review` pointer (a wrapper command is a declined-PR pattern); README names `/prisma-init` as the entry point. Renaming revisited only after a second method has users.
- `/prisma-status`'s inline Python becomes `tools/status.py` (Phase 0), reading policy flags; a generic stage walker is deferred until a method whose stage *order* differs exists.
- `prisma-manuscript` reads `manifest.standards[]` and audits against those Markdown files (LLM judgement, as today); `review-protocol` gains PCC and Petersen RQs as data; `keyword-expansion` gains item-5/item-9 population rules and snowballing logging; `screening-assistant` gains the relevance-tag sheet and classification sheet; `quality-appraisal` gains the `instrument` id and pack-scoped instrument lists.
- `tools/lint_skills.py` gains two checks: every method id in `_routing.json` has a manifest (refused rows excepted); every `standards[].ref` path exists. `check_framework_version.py` switches `WATCHED_SKILLS` to a glob over `.claude/skills/*/` and adds `methods/*.json` and `packs/*.json` in the PR that lands the first new skill. `jsonschema` is added and pinned in Phase 0's pinning PR.

### 4.7 Migration path (zero required migration for existing `results/<TOPIC>/`)

1. `methods/systematic_review.json` describes today's nine commands. The Phase 0 golden end-to-end test passes **byte-identical for all pipeline artifacts except `manuscript/label.json`** (which did not exist) before any second method merges. A second M1 assertion: a legacy fixture without a `method` block resolves to `systematic_review` and the label gate returns `not_recorded` disclosures, not a downgrade.
2. **Absence of `protocol.json.method` means `systematic_review`.** The label gate distinguishes `false` from `not_recorded`; `/prisma-status` offers a one-time self-report (`method.migration = {self_reported: true, reviewers, signed_date}`), rendered as "self-reported, not ledgered" in Methods.
3. Legacy pooled topics: on absence of `synthesis_plan.json`, the runner (or the self-report step) writes one with `retrospective: true` and an `amendments[]` entry; runners accept it; the label gate discloses "pooling not prespecified".
4. `risk_of_bias` stays in extraction rows; `instrument` is added next to legacy `tool`; `is_low_risk`/`build_rob_traffic_light` accept both. The `appraisal/` store arrives only with umbrella review. `extraction_table.json` gains no top-level field; its schema accepts both shapes.
5. `records.jsonl` keeps `duplicate_of` as the only cluster edge; nothing is renamed; all new fields are additive; derived state is never stored as input.

### 4.8 Doctrine compliance

Thin pointers: one Step-0 line per command; two new skills; routing as a reference file. Single source of truth: sequence in the Markdown, policy differences in the manifest, words in `microcopy`, checklists as Markdown references, labels in `label_gate.py`, run history in `raw/*.meta`. No speculative infrastructure: no stubs, no stage registry, no schema composition, no delta store, no generic interpreter; engines arrive with the family that needs them and published-example fixtures. Forks: per-topic customisation and any pack needing code.

---

## 5. Build sequence

**Phase 0 — correctness (unchanged in goal; additive items revised).** RoB citation pinned to Cochrane Handbook v5.1.0 (2011) Ch. 8 for RoB 1 and `instrument` id added beside `tool` with both accepted (the owner must confirm the exact mislabel location before scheduling — the two reviewers disagree on whether a legacy "RoB2" string exists); remove I²/Q model switching (`choose_model` deleted); inline Python → tested `tools/` (`dedup`, `ledger` with hash chain and `by`/`role`/`eligibility_version`, `flow_counts` with `not_retrieved`, `status`, `search_preflight`); pin deps including `jsonschema`, Python 3.11–3.13 CI matrix; golden end-to-end test; search-completeness + known-item recall gates; unsupported-study-design fail-closed; PM/HKSJ-modified/PI options; `synthesis_plan.schema.json` with `pooling_unit.identity_fields`; extraction provenance fields and `reports[]`. **Cheap-now additive items:** connectors echo `connector_version`, `query`, `purpose`, `plan_hash` into `raw/*.meta`; `index_family` in `connectors/registry.py`.

| Milestone | Scope | Exit criterion | Why this order |
|---|---|---|---|
| **M1 — One method, made explicit** | `methods/_schema.json`, `methods/systematic_review.json`, `tools/method.py`, `protocol.json.method` schema, `run_synthesis.py` family dispatch (`structured_narrative`, `swim`, `pairwise_iv`) + plan-hash gate + `post_hoc/` routing; retrospective-plan path; Markdown reference files for PRISMA 2020 (existing), PRISMA-S, SWiM; `check_framework_version` watch extended | Golden test byte-identical excluding `label.json`; legacy fixture resolves to SR with `not_recorded` disclosures; `run_synthesis.py` refuses `pairwise_iv` without a plan hash and routes a newer-hash plan to `post_hoc/` | Zero user-visible change; proves the seam against the real pipeline; every later method is one JSON file plus at most one skill. |
| **M2 — Routing + label integrity** | `methods/_routing.json` + `tools/route.py` + Step 0.5 in `/prisma-init` (free-text aim, Q1, Q0 after Q1 with `purpose: orienting`, Q2–Q6, registry lookup); manifest-conditional Steps 1–2; `label_gate.py` (conduct floor, `false`/`not_recorded`, disclosures, report blockers, templated-output lint); `microcopy` + glosses; `shortcuts[]` from the RRMG menu + `deviations.jsonl`; `role: verification` + kappa; `eligibility_version`; `manual_source` runs; four-valued recall severity with provenance | Every routing row has a passing test; a single-screener fixture reports "systematized review" at routing and at report with identical text and a verification-sample fixture reports "systematic review" with the disclosure; a qualitative question and a test-accuracy question fail closed with pointers; the recon-template lint fails "no prior work" and passes the calibrated sentence | The owner's thesis ("decide the method first") and the integrity rule ("label matches process") are one feature; adding methods before label enforcement multiplies mislabelling. |
| **M3 — Scoping review + systematic mapping study (FIRST non-PRISMA methods)** | `methods/scoping_review.json`, `methods/systematic_mapping_study.json`; PCC + Petersen RQs in `review-protocol`; new `evidence-mapping` skill (default charting form pilot-and-freeze; keywording → scheme freeze → calibration re-code incl. solo intra-rater; sheet export/import); charting/classification schemas; `chart_summary.py`; reference files PRISMA-ScR 2018, SEGRESS 2023, Petersen 2015 conduct; `controlled_vocab: none` QGS path; snowballing meta as a recorded strategy (PRISMA-S item 5); string-miss re-entry into `keyword-expansion`; `packs/{generic, clinical_interventions, cs_se}.json` (flat data) so the coverage statement and question templates render | Second golden test: a scoping fixture runs to a PRISMA-ScR-audited report; `/prisma-synthesize` on it refuses pooling; a mapping fixture blocks bulk coding until the scheme is frozen; a paywalled full text records `not_retrieved` and appears in its own flow box; coverage gaps render on the card and in Limitations | Highest-demand methods after SR, ~80% reuse, exercise every policy field (optional appraisal, forbidden pooling, charting/classification capture, freeze gates, second and third checklists), and are the destination for most misrouted "SR" requests. **No public release is tagged between M3 and M4.** |
| **M4 — Reconnaissance (exploratory literature brief)** | `methods/reconnaissance.json`; `reconnaissance-brief` skill; relevance-tag sheet with connector-filled fields and batched G-Claims approvals; `landscape_brief.md` + `related_work_draft.md` + `supplementary_search_log.md` templates; prior-work-check output (facet tags + quoted claims); corpus-description table; `handoff/`; same-topic promotion (`recon/` archive, amendment); protocol-before-search check ignores `purpose: orienting` | Brief fails the lint on "no prior work"/"saturation" and passes the templated sentences; hand-off gold set enters an SR fixture's recall gate with `provenance: recon-db` and prints "non-independent gold set" until an external item is added; recon records never enter the promoted method's `records.jsonl` without a fresh run | Ships immediately after the lint and the claims boundary exist, inside the same release, so the first multi-method release opens with value before any protocol interview. **→ v1 release may be tagged here.** |
| **M5 — Living mode + first field packs** | `protocol.json.versions[]`; `--since` flow counts; PRISMA-LSR reference file + block; methods-changed block on plan-hash change; `packs/medical_imaging_prediction.json` (PROBAST+AI, QUADAS-2 ids; CLAIM 2024/TRIPOD+AI adherence fields; TRIPOD-SRMA reference) and `packs/image_reconstruction.json` (`appraisal_instruments_by_design: none`; reproducibility/leakage checklist labelled "not a risk-of-bias instrument"; `pooling_unit_identity_proposal` with dataset/split/acceleration/mask/coil/metric) — both data only, experimental | Delta fixture: `--rerun` adds two records, screens only the delta, and the report carries the PRISMA-LSR block with a human impact sentence and a methods-changed block when the plan hash differs; imaging fixture: a pooled PSNR across two datasets is refused by the *core* `pooling_unit` predicate over the signed plan | Living mode monetises the replayable-search differentiator on primitives that already exist; the two imaging packs test the flat pack seam (glosses, instruments, identity proposal) without any merge code. **→ v1 complete.** |
| **v2 (order by demand)** | `dta_narrative` dialect over SR (PRISMA-DTA reference, 2×2 schema, QUADAS-2 per-domain, PROBAST+AI) so R6 test-accuracy stops refusing; EGM manifest + matrix; umbrella review (+ `appraisal/` store, CCA, PRIOR); `proportions` family with `metafor` fixtures; MOOSE/ROBINS-E pack defaults; `structured_survey` family; recency-bounded scoping preset; grey-literature source layer + AACODS; Stevens 2024 interim rapid items as reference Markdown; descriptor resolution + PRESS-checklist self-assessment rendered as plain questions (item 14 stays "not peer reviewed" unless a distinct `by` signs); retraction/preprint fields via Crossref; corpus-description report section | Each arrives as a manifest/pack/reference-file PR plus at most one tested module with published-example fixtures | Every item is data plus one module on a proven seam. |
| **Later** | QES (meta-aggregation first; `findings.jsonl`, code/theme stages, CERQual/ConQual assembly, ENTREQ) when a qualitative maintainer commits; `dta` engine (bivariate/HSROC, Cochrane DTA fixtures); mixed-methods; NMA (export to R meanwhile); bibliometric layer; methodological review; dose–response/economics/eco-evo engines; gap-typology tags for the three computable signals (absent cell, thin cell, direction-conflict flag); claim-evidence graph when a second consumer exists | — | Each needs a new data unit, a heavy engine, or a maintainer the repo does not have. |

---

## 6. Dissent log

| # | Issue | Positions | Chair's ruling and reason | What would reopen it |
|---|---|---|---|---|
| 1 | **Reconnaissance build order** | UX: M2. Others: after the lint and scoping. Adversarial UX: at M3 the persona falls to a fail-closed refusal with a 2–9-month scoping fallback; asked for an interim degraded recon path. | **M4, with an explicit commitment: no public release is tagged between M3 and M4.** The degraded-path proposal (scoping manifest truncated after search-run) is rejected as more machinery than the problem warrants. | M3 slipping >6 weeks; then recon ships on M2's lint alone. |
| 2 | **QES tier; stubs** | Qualitative: v2 with stubs from day one. Engineering: zero stubs — refusals belong in routing rows. | **Later; no stub manifests.** A routing row with refusal text and pointer guarantees no qualitative question routes into SR, at zero maintenance surface. `derived_from` ledger edges dropped until a consumer exists. | A named qualitative maintainer. |
| 3 | **Single-reviewer label** | Methodologist, architect: disclosure only. UX, CS, information specialist, biostatistician: "systematized". Adversarial methods: the rule is not "AMSTAR-2-critical"; incomplete stages must not change the label. | **Project conduct floor** (MECIR C39 + Grant & Booth): no second-reviewer involvement in selection or no protocol before the first protocol-driven run → "systematized review"; unfinished stages block the build instead. "AMSTAR-2" is never printed in a label. | Owner electing disclosure-only (§7); PRISMA-RR publishing a conduct floor. |
| 4 | **Descriptor resolution / offline** | Information specialist: unvalidated MeSH blocks export. Architect, UX: never fail on connectivity. Engineering: defer entirely to v2. | **Deferred to v2** on the `keyword-expansion` skill; v1 relies on the known-item recall gate, which covers the failure that matters. When it lands: run regardless; waiver-with-reason recorded and printed. | v1 recall-gate misses traceable to descriptor errors. |
| 5 | **Field packs in v1** | Architect, engineering: cut packs; put `source_expectations` on the method manifest. CS, biostatistician, UX, information specialist, adversarial methods: field-level facts (GRADE applicability, RoB 2 scope, PCC glosses, source expectations, question templates) are not method-level facts. | **Flat data-only packs kept; all merge semantics cut.** Packs carry glosses, expectations, instrument ids, a confidence framework and a pooling-unit *proposal*; they may not override any manifest field; no extraction-fragment schemas. `generic`, `clinical_interventions`, `cs_se` in M3; two imaging packs (prediction vs reconstruction, per the misinstrumentation finding) in M5. Engineering's "cut entirely" is rejected because three reviewers independently showed method manifests cannot carry the field-specific facts. | Any pack needing code (→ fork). |
| 6 | **Rapid review timing and definition** | CS, biostatistician: M2. Methodologist, UX: v2. Adversarial: the label must derive from shortcuts, not time; 20%-of-excludes is not RRMG. | **Profile in M2**; label from `shortcuts[]` non-empty; RRMG menu verbatim; "RRMG-conformant" only when the recorded process matches; interim reporting items as reference Markdown in v2. | None needed. |
| 7 | **Recall-gate severity** | Biostatistician: strict everywhere. Information specialist: mandatory. Methodologist, qualitative, UX: waivable. Adversarial: recon-sourced gold sets are circular; seeds inflate snowballing recall. | **Four-valued manifest field** as before, **plus** gold-item provenance with per-provenance recall, seeds excluded from the denominator, and a "non-independent gold set" notice. | Scoping reviews built here systematically missing known items. |
| 8 | **Gap language** | Methodologist: "gap" forbidden outside EGM. UX: templated corpus-qualified questions. Adversarial: even EGM cells are search-bounded. | **UX's template everywhere, including EGM cells**; no unqualified gap anywhere; lint enforces the form. | Lint evasion in the wild. |
| 9 | **"Novelty check" naming** | UX: named prior-art output. Qualitative: no UI may say "novelty". | **"Prior-work check"** as a Q1 option and output profile; "novelty" appears only in the blocklist; the PRISMA item-3 rationale context is exempt. | None. |
| 10 | **Bibliometrics** | UX: v2. Others: later. | **Later**; corpus-description table only. | A citation-graph tool with label discipline and demand. |
| 11 | **MA and living as top-level modes (owner)** | Owner: modes. Panel: family and mode. | **Panel position adopted.** | Owner may overrule (§7). |
| 12 | **Gap typology / claim-evidence graph** | Owner: v2. Others: statements now, tags later. | **Unchanged**: statements with provenance now; three computable tags later; graph only with a second consumer. | EGM shipping and a second consumer. |
| 13 | **Where the method record lives** | `review.json` vs `protocol.json.method`. Adversarial: `predicted_label` must not be stored. | **`protocol.json.method`, without `predicted_label`**; `label.json` regenerated at report. | — |
| 14 | **Appraisal split timing** | Methodologist: with Phase 0. Architect: creep. Engineering: two sources of truth during transition. | **No split in v1.** `instrument` id added beside `tool`; `appraisal/` arrives with umbrella review. | Umbrella review shipping. |
| 15 | **Python vs R** | As before. | **Python; `metafor`/`mada`/Cochrane DTA fixtures in CI; NMA exported to R.** | A maintainer volunteering an R runtime. |
| 16 | **Snowballing as primary** | CS: universal. Health specialists: supplementary. Adversarial: wrong PRISMA-S item. | **Pack-constrained; PRISMA-S item 5 (not 9); seeds excluded from recall.** | — |
| 17 | **Health SR label with six free connectors** | Information specialist: allowed with gaps printed. Methodologist: require registry/grey. Adversarial: unsatisfiable without a registry connector. | **Clinical pack adds `registry_or_grey_source ≥ 1`, satisfiable via `manual_source` runs** (uploaded export, date, strings; flagged non-replayable in PRISMA-S items 1/13); `index_family` counting replaces raw connector counting. | An institutional/registry connector shipping. |
| 18 | **Terminology** | Owner: "pre-research methods". Panel: "evidence-synthesis and landscape methods". | **Panel wording in docs**; routing intent unchanged. | Owner preference (§7). |
| 19 | **Extraction verification (new)** | Adversarial methods: `pairwise_iv` without dual/verified extraction should downgrade. Chair: the conduct floor stays narrow (protocol, selection). | **Disclosure + mandatory Limitations text + SoF footnote, not a downgrade.** MECIR C50 is a Cochrane standard the tool never claims to meet; AMSTAR 2 item 6 is non-critical. | Owner choosing the stricter rule (§7). |
| 20 | **Search currency (new)** | Adversarial methods: a label rule. Chair: a disclosure. | **Disclosure (`search_age` >12 months) + mandatory text; no downgrade** — search age is a reporting fact, not a conduct choice. | — |
| 21 | **Q0 as computed vs human step (new)** | Engineering: human-only in v1 (a pre-protocol run breaks the protocol-before-search rule; `orienting` threads through five modules). UX: computed after Q1 is the first value moment. | **Computed after Q1**, recorded as `raw/*.meta` with `purpose: orienting` — one connector-owned meta field, not a cross-module state; the protocol check reads meta. The block is titled as a bounded scan; the human PROSPERO/OSF lookup is recorded and required for the SR label. | Q0 producing false "no prior review" statements in the wild. |
| 22 | **Stage registry vs policy-delta manifests (new)** | Original consensus: closed registry of ten stage kinds in manifests + generic walker. Engineering: the pipeline would be described twice. | **Policy-delta manifests; Markdown keeps the sequence.** Every "—" in §3.2 maps to a policy field. Generic walker deferred. | A method whose stage *order* differs from the nine commands. |
| 23 | **Living mode machinery (new)** | Original: `search_delta.py`, `updates/<date>/`. Engineering: `--rerun` + idempotent dedup + undecided export already yield the delta. Adversarial methods: plan changes between cycles must be reported. | **`versions[]` + `--since` + PRISMA-LSR block + methods-changed block**; no delta store; retraction sweep with connector support in v2. | A living-review user needing something `--rerun` + `versions[]` cannot record. |
| 24 | **Standards as JSON + deterministic audit (new)** | Original: `standards/*.json` + `checklist_audit.py`. Engineering: item adherence is a judgement over prose; JSON conversion collides with the verbatim-reference rule. Adversarial methods: Petersen and SEGRESS must be separate files. | **Markdown reference files under the owning skill, split by source and licence; LLM audits; manifest lists paths.** | — |
| 25 | **Test-accuracy questions in v1 (new)** | Original R7: SR + swim with a note. Adversarial methods: PRISMA 2020 without PRISMA-DTA is misreporting. | **Fail closed in v1, offer scoping; `dta_narrative` dialect in v2.** This affects the owner's field and is flagged in §7. | `dta_narrative` shipping. |

---

## 7. Open questions for the project owner

1. **Accept the panel's rejection of "meta-analysis" and "living update" as top-level modes?** The router still understands the words.
2. **Phase 0 scope:** approve the revised additive items (connector-owned `raw/*.meta` fields; `index_family`; `by`/`role`/`eligibility_version` on ledger lines; `not_retrieved`; `reports[]`, `by`/`verified_by`, `instrument` on extraction rows; `synthesis_plan.schema.json` with `pooling_unit.identity_fields`; `jsonschema` pinned). And **confirm the exact RoB mislabel location** — the two adversarial reviewers disagree on whether a legacy "RoB2" string exists anywhere.
3. **Label policy:** adopt the project conduct floor (no second-reviewer involvement in selection, or no protocol before search → "systematized review") or disclosure-only? Separately, should missing extraction verification under `pairwise_iv` be a disclosure (chair) or a downgrade (adversarial methods; dissent #19)?
4. **Entry point:** confirm `/prisma-init` (documented in README) as the entry point with no `/review` wrapper; confirm `prisma-flow` stays the project name.
5. **Pack posture:** confirm flat, data-only packs with no override capability (dissent #5), `generic`/`clinical_interventions`/`cs_se` in M3, and the split of your field into `medical_imaging_prediction` and `image_reconstruction` (the latter with **no risk-of-bias instrument**, because PROBAST/QUADAS-2 do not cover PSNR/SSIM studies).
6. **Test-accuracy and prediction-model questions fail closed in v1** (dissent #25) until a `dta_narrative` dialect with PRISMA-DTA/TRIPOD-SRMA references ships in v2. Acceptable for your first field, or should `dta_narrative` move into M5?
7. **Verification default for `single_reviewer`:** the RRMG-conformant option (second person over a joint pilot + ≥20% of abstracts, then all excludes) or a lighter non-RRMG sample (e.g. 20% of title/abstract excludes) — the label text differs accordingly.
8. **QES ownership:** is there, or will there be, a qualitative maintainer?
9. **Default for CS users:** "systematic mapping study" (SEGRESS/Petersen) or "scoping review" (PRISMA-ScR) when the target venue is unknown?
10. **Registration:** the design makes a recorded PROSPERO/OSF *lookup* required for the SR label and registration itself a disclosure; should registration (or "not registered, reason") be required too?
11. **Terminology in docs:** "evidence-synthesis and landscape methods" (panel) vs "pre-research methods".
12. **Gap typology ambition:** accept "statements with provenance now, three computable tags later, graph only with a second consumer"?
13. **Licensing posture:** instrument text shipped only as identifiers + own paraphrase + links (RoB 2, ROBINS-I CC BY-NC-ND; CASP CC BY-NC-SA); PRISMA checklists (CC BY 4.0) vendored as Markdown references with attribution; only Apache-2.0/MIT code vendored; ideas only from non-commercial projects.
14. **Runtime neutrality:** confirm that the artifact contract is the neutrality layer and no Python orchestrator or generic stage interpreter will be built.
15. **R in CI:** accept generating `metafor`/`mada` fixture outputs in a CI fixture-generation job (R never required at runtime)?