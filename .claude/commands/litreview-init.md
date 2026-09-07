# /litreview-init - Start or Resume a Systematic Review

You are running the initialization pipeline for a new (or existing) review under this multi-method evidence-synthesis workspace. This command implements pipeline steps 0-4: method routing (which review method this actually is — systematic review, scoping review, or systematic mapping study), scope selection, the reviewer-profile interview, defining the review question (via the `review-protocol` skill), and handing off keyword elicitation (to the `keyword-expansion` skill). It ends with a populated `results/<TOPIC>/` workspace and a written `protocol.json`.

**Follow the steps below in order. Do not skip a step, and do not write `protocol.json` before Steps 0-3 are actually complete** — every field in its schema (Step 5) is sourced from an earlier step, not invented at write time.

---

## Step 0: Parse Arguments and Resolve the Topic Slug

1. Check `$ARGUMENTS`. It may contain a topic name or an already-slugged folder name (e.g. `remote work productivity` or `korea-elder-care-ai`).
2. **Derive the topic slug** (`<TOPIC>`, the exact folder name under `results/`) using this rule: lowercase, trim whitespace, replace every run of characters that are not `[a-z0-9]` with a single hyphen, strip leading and trailing hyphens, cap at 60 characters. Example: `"AI in Korean Elder Care"` → `ai-in-korean-elder-care`.
   - If `$ARGUMENTS` is non-empty, derive `<TOPIC>` from it directly and proceed without blocking on confirmation — just state the folder name you resolved to in your first reply so the reviewer can redirect you if it's wrong (e.g. "I'll use `results/ai-in-korean-elder-care/` for this review — let me know if you'd prefer a different folder name.").
   - If `$ARGUMENTS` is empty, ask the reviewer for a short topic phrase (2-6 words is plenty — it only needs to be enough to name a folder; the full working title and objective are elicited properly in Step 4) before deriving the slug.
3. **Check for an existing review**: attempt to read `results/<TOPIC>/protocol.json`.
   - **If it exists**, this is a resume/update, not a fresh init. Read it in full, summarize its current title, framework, eligibility criteria, and scope back to the reviewer in plain language, and ask whether they want to (a) update this protocol (carry the update into Step 4, which routes to the `review-protocol` skill's own "Before you begin" update path and never silently overwrites recorded eligibility criteria), or (b) start a distinct review under a different topic slug (go back to Step 0.2 with a new slug). Do not re-run Steps 1-3 wholesale for an update — Step 2 (reviewer profile) in particular should only run if `CLAUDE.local.md` still has placeholder tokens; re-confirm scope (Step 1) only if the reviewer says scope is what's changing. Don't write the amendment record yourself — the `review-protocol` skill's update path owns `protocol.json`'s `amendments: [{date, change, reason}]` array (PRISMA Item 24c); your job here is only to route into that path. **Also skip Step 0.5 entirely** — the method is already recorded in `protocol.json.method`; re-running the routing interview on an already-routed review would ask questions whose answer is already settled and risks silently switching methods mid-review.
   - **If it does not exist**, this is a fresh init. Continue to Step 0.5.

---

## Step 0.5: Method Routing (G-Route)

Which method manifest governs this review — `systematic_review`, `scoping_review`, `systematic_mapping_study`, `reconnaissance`, or a clean refusal for a method not shipped yet (living/incremental-update mode, umbrella review, meta-aggregation, mixed-methods review, and diagnostic-test-accuracy narrative are all later milestones or v2) — is decided here, before scope or the protocol interview, using `methods/_routing.json`'s versioned decision table (`tools/route.py`) evaluated against a short set of questions. **This is a deterministic decision the table makes, not a judgment call you make by reading the answers yourself** — run `tools/route.py` and follow its result; do not second-guess it because a different method "feels right."

Ask conversationally, in plain language, never using method vocabulary in the question text itself (the reviewer should never have to know what a "scoping review" is to answer these).

### Q1: What do you need at the end?

Ask this as a plain multi-select list (not the `AskUserQuestion` tool — it has more than four options):

> - **(a)** Get oriented — key papers, vocabulary, what's been done
> - **(g)** Check whether something like my idea has already been done
> - **(b)** A background/related-work section
> - **(c)** A map of what exists and where it is thin
> - **(d)** A defensible answer to one specific question
> - **(f)** A summary of what existing reviews conclude
> - **(e)** Update a review that already exists in this workspace

Record the pick(s) as `goal` — a list drawn from `{"orient", "prior_work", "background", "map", "answer", "overview", "update"}` (a→orient, g→prior_work, b→background, c→map, d→answer, f→overview, e→update). More than one may apply.

**If `"update"` is among the picks**: this means the reviewer wants a living-mode delta rerun of a *different*, already-completed review elsewhere in this workspace (docs/ROADMAP.md M5) — not a fresh protocol under `<TOPIC>` (the slug Step 0 just derived is not used for this path at all; no new `results/<TOPIC>/` is ever created here).

1. `Glob` `results/*/protocol.json` for existing reviews. **None found** — tell the reviewer there is nothing to update yet, and ask whether they'd rather (a) drop `"update"` and continue with whatever other goals they also picked, if any, or (b) treat this as a fresh, independent review (a new protocol) instead. If `"update"` was the only pick and they don't want a fresh review, stop here — do not proceed to Q0 or write anything.
2. **One or more found**: list them (`python3 tools/status.py` with no `--topic`, its own condensed one-liner per review — reuse that output verbatim, never re-derive counts yourself) and ask which one the reviewer means. Never guess among several.
3. Check the chosen review is actually a completed one — living mode updates a review that has already been through a full reporting cycle, not one still mid-pipeline: `python3 tools/status.py --topic <chosen>` and confirm its `stage` is `"manuscript_drafted"` with a manuscript that exists. If it isn't there yet, tell the reviewer plainly (quoting `why` from the status output) and offer the same (a)/(b) fallback as step 1.
4. If it is completed: set `answers = {"goal": [...as recorded above...], "base_exists": true, "base_method_id": <chosen review's protocol.json.method.id>}` and run `tools/route.py`'s `decide()` — `methods/_routing.json`'s R1 row resolves this to `{"kind": "resolve", "method_id": <base_method_id>, "modes": ["living"]}` for real (skip Q0/Q2-Q6 entirely for this path; R1 needs nothing else from them). Render the "because" card exactly as below, but using the **chosen existing review's** own resolved manifest and microcopy, not a new one being routed for `<TOPIC>`.
5. On confirmation (G-Route): **stop this entire command** — do not proceed to Step 1 and do not write a `protocol.json` under `<TOPIC>`. Hand off directly to `/litreview-search --living <chosen review's topic>`, which re-runs the same protocol-bounded search plan (deliberately not narrowed to "since last version" — see that command's Step 0.4 for why) and records a new `protocol.json.versions[]` entry once it completes; `tools/dedup.py`'s record_id idempotency is what makes only the genuinely new records surface for screening.

### Q0: Existing-review check

Ask: "Have you already checked PROSPERO, OSF, or the Cochrane Library for an existing systematic review answering this exact question?" with three answers: *found one and want to build on/formally update it* · *checked, found none* · *haven't checked yet*.

This is a simplified stand-in for the design's full "bounded existing-review scan over enabled connectors with `purpose: orienting`" (not yet implemented — say so if asked, don't pretend a scan ran). Record:

- Found one, wants to update it: `q0.human_judgement = "update_external"`; ask for the citation and fold it into `registry_lookup.result` as free text (e.g. `"found: Smith et al. 2020 systematic review on X — this review updates it"`). This is a *different* thing from Q1's `"update"` goal above — R0 resolves this to `systematic_review` directly (a formal review update per Garner 2016 is fully supported today; it's `"update"`/living-mode over *this workspace's own* prior review that isn't).
- Checked, found none: `q0.human_judgement = "proceed"`, `registry_lookup = {"date": "<today, ISO date>", "result": "none found", "url": null}`.
- Hasn't checked: `q0.human_judgement = "proceed"`, `registry_lookup = null`. This surfaces later as a disclosure (`registry_lookup_recorded` is never a hard-gate check), never a silent downgrade.

### Q2: Question focus

If `CLAUDE.local.md`'s field-of-research/target-venue names a shipped pack (`clinical_interventions`, `cs_se`, `medical_imaging_prediction`, or `image_reconstruction` — check `packs/*.json`'s own `label`, don't guess from the field name alone), render `packs/<id>.json`'s own `question_template` instead of the generic wording below; otherwise (nothing on file, or it names a field with no shipped pack yet) use the generic template plainly rather than pretending a pack informed it: "Can you state your question as 'does/how well A, compared with B, affect C in D'?" — **Yes** · **Roughly** · **Not yet — it's an area, not a question**. Record as `question_focus`: `"focused"` | `"rough"` | `"forming"`.

### Q3: Evidence type

"What kind of papers do you expect to find?" — trials/experiments with numbers · observational studies · algorithm/benchmark papers · test-accuracy or prediction-model studies · interviews/qualitative · existing reviews · mixed/don't know. Record as `evidence_type`: `"trials"` | `"observational"` | `"algorithm"` | `"test_accuracy_or_model"` | `"qualitative"` | `"existing_reviews"` | `"mixed"`.

If `evidence_type` is `"algorithm"` or `"test_accuracy_or_model"`, ask the disambiguator: "Are results reported on shared public datasets (e.g. fastMRI, BraTS) or on patients/clinical outcomes?" — record as `benchmark_vs_clinical`: `"benchmark"` | `"clinical"` (not read by any routing row yet in v1; recorded for the pack layer once it ships).

### Q4: Reviewers and time

"How many people can screen independently, and how much time do you have?" — just me · 2 or more; an afternoon · a week · 1–3 months · 6+ months. Record `reviewers` as the **integer** `1` or `2` (routing rows check `reviewers: {"eq": 1}` — a string `"1"` would silently never match), and `time_budget` as exactly `"afternoon"` or `"week"` for those two answers (routing rows check these two exact strings — `"1_3_months"` / `"6_plus_months"` for the other two, which no row currently reads but should stay consistent for when packs/profiles do).

### Q5: Appraisal intent

"Will you formally rate each paper's risk of bias with a checklist (e.g. RoB 2, PROBAST)? Most related-work sections and surveys do not." — **Yes** · **No** · **Not sure** (treat as No). Record as `appraisal_intent`: `"yes"` | `"no"`.

### Q6: Pooling expectation (conditional)

Only ask if `"answer"` is in `goal` **and** `evidence_type` is `"trials"` or `"observational"`: "Do you expect several studies to report the same measurement for the same comparison, so their numbers could be combined?" — **Yes** · **No** · **Not sure** (treat as No — never assume pooling is wanted). Record as `expects_pooling`: `"yes"` | `"no"` (a **string**, not a boolean — `methods/_routing.json`'s R6e checks `expects_pooling: {"eq": "yes"}`).

### Run the routing table

Write the assembled answers to a JSON file (e.g. `{"goal": [...], "question_focus": "...", "evidence_type": "...", "benchmark_vs_clinical": "...", "reviewers": 1, "time_budget": "...", "appraisal_intent": "...", "expects_pooling": "...", "q0": {"human_judgement": "...", "registry_lookup": {...} | null, "raw_files": []}}` — omit `benchmark_vs_clinical`/`expects_pooling` entirely when Q3/Q6 weren't asked) and run:

```bash
python3 tools/route.py --answers-json <path> --claude-local-pack <id>
```

Omit `--claude-local-pack` entirely when `CLAUDE.local.md`'s field-of-research/target-venue names no shipped pack (`resolve_pack()` then falls through to `"generic"`, per R9). The result now also carries `"pack"` (the resolved pack id — R9: an explicit answer wins, then `--claude-local-pack`, then `"generic"`) and `"pack_source_coverage"` (that pack's `source_expectations[]`, each with a `"reachable"` boolean) — hold both for the card below and for Step 4's handoff.

(Pre-allowlisted — `Bash(python3 tools/route.py:*)`.) The result's `"kind"` is one of:

- **`"resolve"`**: a real, shipped method (`method_id`) was recommended. Continue below to render the card.
- **`"refuse"`**: no method applies (or the recommended one isn't shipped yet). Tell the reviewer the `reason` and `pointer` plainly, and any `offer[]` methods they could pursue instead (already filtered to only ones actually shipped — never suggest a dead end). Ask how they'd like to proceed: adjust an earlier answer and re-run routing, or pick one of the offered methods directly (an explicit override, recorded per R10 below). Do not write `protocol.json.method` for a refusal the reviewer hasn't explicitly overridden.
- **`"ask"`**: only possible via R1 (living mode), which Q1's own interception above already handled — this should not occur in practice; if it does, treat it the same as `"update"` was handled above.

### Render the "because" card and confirm (G-Route)

For a `"resolve"` result, render a five-line card from the resolved manifest's own `microcopy` (`methods/<method_id>.json`) and the routing result — fill this template with real values, never leave a bracketed placeholder in what you show the reviewer:

1. **What you told me** — echo the answers back in the reviewer's own words, not the routing vocabulary (e.g. "you want a defensible answer to one specific question, expect trial data, and can screen with two people").
2. **What I recommend and what it is** — `microcopy.what`.
3. **What you will have at the end** — `microcopy.gives`.
4. **What it costs** — `microcopy.costs`, plus the coverage statement from `pack_source_coverage` (always present now that every pack resolution — including the `"generic"` default — loads a real `packs/*.json` file): name each source with `"reachable": true` as searched, and each with `"reachable": false` by name and its `standard` field (e.g. "a study registry such as PROSPERO or OSF Registries — expected by MECIR C39 / PRISMA 2020 Item 24a — is not reachable by any connector this workspace has installed"). Never omit this clause and never invent a gap not in `pack_source_coverage` — the pack's own data is now the source of truth, not reviewer recall.
5. **What you will be allowed to call this, and why** — the **predicted label**, computed from `reviewers` (Q4) alone, never by calling `tools/label_gate.py` (nothing exists on disk yet to compute a *real* label from — this is a prediction, not a computation):
   - `method_id == "systematic_review"` and `reviewers == 1`: predicted **"systematized review"** — disclose that a second screener, or a documented verification sample over a portion of title/abstract screening, would let it be reported as "systematic review" instead.
   - `method_id == "systematic_review"` and `reviewers == 2`: predicted **"systematic review"** — note this assumes the protocol gets signed (Step 4/Phase 2's `tools/sign_protocol.py` call) before the first search run, which this same command will handle.
   - `method_id` is `"scoping_review"` or `"systematic_mapping_study"`: predicted label is simply the manifest's own `label_rules.label` (`"scoping review"` / `"systematic mapping study"`) — these are never downgraded for single screening (PRISMA-ScR item 9 / JBI), so `reviewers` doesn't change the prediction.
   - `method_id == "reconnaissance"`: predicted label is unconditionally `"exploratory literature brief (non-systematic)"` — its `label_rules.requires[]` is empty, so nothing about `reviewers` or anything else recorded later can change or upgrade it; say so plainly rather than implying a path to a stronger label exists.

   Also state `microcopy.cannot_claim` here, plainly.

If `result["explain"]` is set (R8's appraisal-intent note, or an R7 override), add one more sentence using it verbatim — never paraphrase a routing-table explanation.

If the reviewer's answers led here by a route other than the most direct one (`chosen_id` would differ from `recommended_id` only after an override below — at this point they're still equal), skip this; the "you asked for X but Y fits better" sentence only applies after an override is being explained, not before one exists.

Ask the reviewer to confirm (`recommended_id`) or override with a specific alternative method + a one-sentence reason. Record via `tools/route.py`'s `record_override()` shape: `{"recommended_id": ..., "chosen_id": ..., "override_reason": ...}` (`override_reason` is `null` unless `chosen_id != recommended_id`).

### Hold the result — do not write it yet

Exactly like Step 1's scope answer, **hold** the full routing block in context rather than writing it to disk now: `{"table_version": <methods/_routing.json's own "table_version">, "answers": {...as sent to route.py...}, "q0": {...}, "recommended_id": ..., "chosen_id": ..., "override_reason": ..., "fallback_reason": <result["reason"] if this was a fallback, else null>}`, plus `method_id` (the confirmed `chosen_id`), `synthesis_family` (`result["synthesis_family"]`), `profile_flags` (`result["profile_flags"]`), `modes` (`result["modes"]`), `output_profiles` (`result["output_profiles"]`), and `pack` (`result["pack"]` — the resolved pack id from the `tools/route.py` run above, per R9; never re-resolve or re-guess it here). **`version` is `methods/<chosen_id>.json`'s own `"version"` field, read fresh at this moment** — never hardcode `"1.0.0"` from the schema's worked example; it records which manifest revision actually routed this review, and both `scoping_review.json` and `systematic_mapping_study.json` have already moved past `1.0.0`. It is persisted into `protocol.json.method` in Step 4's handoff to `review-protocol`, per `schemas/protocol_method.schema.json` §2.3 — not written here, so an aborted or restarted run never leaves a half-written `protocol.json`.

---

## Step 1: Scope Selection

Ask the reviewer to choose the review's geographic/linguistic scope using a bounded choice (`AskUserQuestion`):

- **Global (default)** — search all enabled sources with no geographic or language restriction beyond what Step 4's eligibility gates set.
- **National / Regional** — restrict the review to a specific country or region (free text — e.g. `Korea`, `Germany`, `USA`, `Sub-Saharan Africa`). If chosen, ask for the free-text region name.

If **National/Regional** is chosen, ask two follow-ups before moving on:

1. **Known coverage gaps up front**: "Do you already know of any of the six sources (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv) having weak coverage for `<region>` or its language(s)?" This is optional — if the reviewer doesn't know, say so and move on; the `keyword-expansion` skill will also surface gaps mechanically in Step 6. Record any named gaps as free text for now (they get written into `protocol.json.scope.coverage_gaps` in Step 5).
2. **Expected keyword translation**: mention that a national/regional scope makes non-English search terms relevant, and that the actual translation step happens later, in Step 6 (`keyword-expansion`'s own Step 4) — nothing to decide here, just flagging it so it isn't a surprise.

Hold the scope answer (`mode`, `region`, any named `coverage_gaps`) in context — do not write it to disk yet. It is persisted as part of `protocol.json` in Step 5, and the schema's `mode` field only has two valid values: write `"global"` for the default path, and `"national"` for any non-global choice, even when the reviewer described it as "regional" — the actual place name goes in the `region` field, not the `mode` field.

---

## Step 2: Reviewer Profile Interview

1. Check whether the repo root `CLAUDE.local.md` exists.
   - **If it doesn't exist**, create it by copying the tracked template: `cp CLAUDE.local.md.example CLAUDE.local.md`. `CLAUDE.local.md` is gitignored, so this and everything the interview below writes into it never enters git history — safe to fill in even on a public fork.
   - Read `CLAUDE.local.md`.
2. Check it for `[PLACEHOLDER]`-style bracketed tokens (`[YOUR_NAME]`, `[YOUR_FIELD]`, `[YOUR_INSTITUTION]`, `[PRIOR_WORK_1]`, `[TARGET_JOURNAL_1]`, `[CITATION_STYLE]`, etc.).
   - **If none remain** (it was already filled in by a prior run of this command or by hand), skip this interview entirely and say so: "Reviewer profile already on file, skipping the interview." Proceed to Step 3.
   - **If placeholders remain**, continue and ask.
4. Ask conversationally, in one grouped round (not a form, not one question per message):
   - Their name.
   - **Field of research** (e.g. "clinical anesthesiology", "education technology") — this calibrates tone and journal conventions later in `/litreview-report`.
   - Institution / affiliation (optional).
   - **Prior relevant work** — publications, prior reviews, or projects that inform this review's framing and related-work section (one or more; "none yet" is a valid answer).
   - **Target journal(s)** — used to calibrate manuscript tone, length, and reference style in `/litreview-report` (one or more; "not decided yet" is valid).
   - **Preferred citation style** — default to APA 7th edition if the reviewer has no preference; don't block on this.
   - **Institutional database access** (optional) — e.g. Scopus, Web of Science. This doesn't add a connector now; just note it so the reviewer remembers `/litreview-add-source` is available for it later.
5. Use the **Edit** tool to replace the bracketed tokens in `CLAUDE.local.md` with the reviewer's actual answers. Make targeted edits only — do not rewrite the whole file. Preserve the file's structure and its explanatory HTML comments. If the reviewer gave one prior-work item where the template has two placeholder lines (`[PRIOR_WORK_1]`, `[PRIOR_WORK_2]`), remove the unused line rather than leaving a dangling placeholder; the same rule applies to target journals and institutional-access lines — trim to fit what was actually given, add more bullet lines if the reviewer gave more than the template has slots for.
6. State which fields were filled in.

---

## Step 3: Create the Review Workspace

Run this exactly once per topic (skip if resuming an existing review whose directories already exist):

```bash
mkdir -p results/<TOPIC>/raw
mkdir -p results/<TOPIC>/screening
mkdir -p results/<TOPIC>/synthesis
mkdir -p results/<TOPIC>/manuscript
touch results/<TOPIC>/raw/.gitkeep
touch results/<TOPIC>/screening/.gitkeep
touch results/<TOPIC>/synthesis/.gitkeep
touch results/<TOPIC>/manuscript/.gitkeep
```

Substitute the real `<TOPIC>` slug from Step 0. The `.gitkeep` touches matter: `.gitignore` ignores everything under `results/**` except `.gitkeep` and `README.md` files, so an empty subfolder needs one to survive being tracked by anyone who later `git add`s the structure. Do not create `search_plan.json`, `records.jsonl`, `screening_decisions.jsonl`, `extraction_table.json`, or `rerun_search.sh` here — those are written by later pipeline commands (`/litreview-search` writes the first and last of those), not by `/litreview-init`.

---

## Step 4: Define the Review Question

Invoke the **`review-protocol`** skill (Skill tool, `skill: review-protocol`) to run its Phase 1 interview and Phase 2 persistence for `results/<TOPIC>/`. Before invoking it, tell it explicitly:

- The target path is `results/<TOPIC>/protocol.json` (the `<TOPIC>` resolved in Step 0).
- Method routing has **already been decided** in Step 0.5 above (skip this bullet entirely on a resume, where Step 0.5 itself was skipped) — pass along the full `method` block held in context (`id`/`chosen_id`, `version` from the resolved manifest, `synthesis_family`, `profile_flags`, `modes`, `pack`, `output_profiles`, and the `routing` object) so the skill writes it straight into `protocol.json.method`, per `schemas/protocol_method.schema.json`, rather than leaving it unset (which would default the review to `systematic_review`, `recorded: false` — silently wrong for a scoping/mapping review).
- Scope has **already been collected** in Step 1 above — pass along `mode`, `region`, and any named `coverage_gaps` so the skill writes them straight into `protocol.json.scope` rather than re-running its own Phase 1 Step 4 scope elicitation. **Merge in the pack's own auto-derived gaps too**: from Step 0.5's held `pack_source_coverage` (never re-run `tools/route.py` here just to get it again), take every entry with `"reachable": false` and add one `coverage_gaps` entry per source not already named by the reviewer's own Step 1 answer: `{"source": <its "source" field>, "gap": "expected by " + <its "standard" field> + " but not reachable by any connector this workspace has installed", "mitigation": null}`. This is what makes §2.4's card-line-4 statement and the manuscript's Limitations paragraph agree with each other — both trace back to the same `pack_source_coverage` data, one rendered at routing time, the other persisted at protocol time.
- If Step 0 identified this as a resume/update, tell the skill so it takes its "Before you begin" update path (read the existing file, confirm what's changing, never silently overwrite recorded eligibility criteria).

Let the skill run its full interview: framework selection (PICO for intervention-effectiveness reviews, PICo for qualitative reviews, SPIDER for mixed-methods, or another framework where none of those fit), the framework-specific elicitation, and the hard eligibility gates (population, study design, publication type, date range, language-of-publication). Do not shortcut or paraphrase this interview yourself — the skill's own elicitation prompts and confirmation step are the mechanism that keeps `protocol.json` accurate.

---

## Step 5: Verify `protocol.json`

After the `review-protocol` skill finishes, read `results/<TOPIC>/protocol.json` back and confirm it matches this schema with every field actually populated (no leftover `null`/placeholder where a real answer was given in Steps 1 or 4):

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
  "signed_at": "2026-09-06T10:12:00Z",
  "signed_by": "..."
}
```

Some fields are legitimately `null` and are not gaps: `registration.id` when `registration.status` is `"unregistered"`, `eligibility.date_range.to` for an open-ended date range, and `scope.region` for a `"global"` review. Treat only a genuinely unanswered field (an empty `framework_fields` entry, a `criterion`/`included` value the reviewer never actually gave) as a gap. If any such field is missing, do not proceed to Step 6 — go back into the `review-protocol` skill's interview for the missing field specifically, rather than inventing a value or leaving it blank. This file is read verbatim by every later command (`/litreview-search`, `/litreview-screen`, `/litreview-report`) — a gap here becomes a silent gap everywhere downstream.

`signed_at`/`signed_by` should already be present too — `review-protocol`'s own Phase 2 stamps them (`tools/sign_protocol.py`) once every field above is populated, the G-Protocol gate `tools/label_gate.py`'s systematic-review conduct floor depends on. If they're missing, the skill's sign-off call didn't run (or was skipped); go back and run it — do not hand-write these two fields, since the whole point is that `sign_protocol.py` independently re-verified completeness first.

---

## Step 6: Hand Off Keyword Elicitation

Invoke the **`keyword-expansion`** skill (Skill tool, `skill: keyword-expansion`) for `results/<TOPIC>/`. This is a full handoff, not a summary you perform yourself: let the skill read the PICO/PICo/SPIDER seed terms out of the `protocol.json` you just verified, run its own LLM-assisted expansion pass with reviewer confirmation, translate the confirmed terms into each source's native query syntax, apply the Step 1 scope (it will re-read `protocol.json.scope.mode` and, if `"national"`, offer the optional keyword-translation step and record any additional coverage gaps), and persist the result to `results/<TOPIC>/search_plan.json`.

"Enabled" at this stage means **all six shipped sources** (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv) — all six are free at basic-access level (§3), so `/litreview-init` has no reason to exclude any of them. Build a confirmed query string for every one of the six; picking which sources actually *run* in a given search is `/litreview-search`'s job, not this command's — narrowing the set here would leave `search_plan.json` incomplete for PRISMA Item 7's per-database audit trail.

Do not skip this step or defer it to `/litreview-search` "for later" — a review with a protocol but no search plan is not actually ready to search, and `search_plan.json` is what makes PRISMA Item 7 auditable later.

**After the skill returns**, re-read `results/<TOPIC>/protocol.json` once more. If `scope.translation_used` was set to `true` (the skill's Step 4 ran a national-scope translation), also set `eligibility.language.translation_used` to `true` and add the translated language(s) to `eligibility.language.included` if they aren't already there. `scope` is the authoritative record of *whether and into what* translation happened; `eligibility.language` must never silently disagree with it, since `/litreview-report`'s Methods §2.3 and the eligibility gate both read from `eligibility.language` directly.

---

## Step 7: Confirm and Next Steps

Once `protocol.json` and `search_plan.json` both exist and are verified, present a short summary:

> **Review initialized: `results/<TOPIC>/`**
>
> - **Title:** [title from protocol.json] - **Framework:** [framework] — [one-line summary of the framework fields] - **Scope:** [Global | National/Regional: <region>], [N] coverage gap(s) noted - **Eligibility gates set:** population, study design, publication type, date range, language - **Search plan:** confirmed query strings for all six sources (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv) - **Synthesis plan:** [prespecified <fixed|random>-effects model, signed <date> | not set — /litreview-synthesize will need a --model override or a later /litreview-init update if this review ends up pooling anything]
>
> **Next:** run `/litreview-search` to run the connector CLIs against the confirmed search plan and build the deduplicated record ledger.

If the reviewer profile interview (Step 2) was skipped because it was already on file, don't mention it again here — only call out what actually changed in this run.

---

## Notes

- Steps 0-3 establish *where* things go (topic slug, workspace directories, reviewer profile) before Step 4 asks the `review-protocol` skill *what* the review is actually about — doing it in the other order means the skill has nowhere to write its output.
- Scope (Step 1) is collected once, here, and threaded into both `review-protocol` (Step 4) and `keyword-expansion` (Step 6) rather than re-asked by each — a reviewer should never have to answer "global or national?" twice in the same `/litreview-init` run.
- This command is safe to re-run on the same topic: Step 0.3 detects an existing `protocol.json` and routes into the update path instead of silently overwriting eligibility criteria that screening decisions may already depend on.
- Nothing in this command touches `records.jsonl`, `screening_decisions.jsonl`, or any file under `synthesis/`/`manuscript/` — those belong to later commands and stay untouched here even on a resume.
