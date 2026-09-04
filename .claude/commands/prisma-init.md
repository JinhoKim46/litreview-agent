# /prisma-init - Start or Resume a Systematic Review

You are running the initialization pipeline for a new (or existing) systematic review under this PRISMA-on-Claude-Code framework. This command implements pipeline steps 0-4: scope selection, the reviewer-profile interview, defining the review question (via the `review-protocol` skill), and handing off keyword elicitation (to the `keyword-expansion` skill). It ends with a populated `results/<TOPIC>/` workspace and a written `protocol.json`.

**Follow the steps below in order. Do not skip a step, and do not write `protocol.json` before Steps 0-3 are actually complete** — every field in its schema (Step 5) is sourced from an earlier step, not invented at write time.

---

## Step 0: Parse Arguments and Resolve the Topic Slug

1. Check `$ARGUMENTS`. It may contain a topic name or an already-slugged folder name (e.g. `remote work productivity` or `korea-elder-care-ai`).
2. **Derive the topic slug** (`<TOPIC>`, the exact folder name under `results/`) using this rule: lowercase, trim whitespace, replace every run of characters that are not `[a-z0-9]` with a single hyphen, strip leading and trailing hyphens, cap at 60 characters. Example: `"AI in Korean Elder Care"` → `ai-in-korean-elder-care`.
   - If `$ARGUMENTS` is non-empty, derive `<TOPIC>` from it directly and proceed without blocking on confirmation — just state the folder name you resolved to in your first reply so the reviewer can redirect you if it's wrong (e.g. "I'll use `results/ai-in-korean-elder-care/` for this review — let me know if you'd prefer a different folder name.").
   - If `$ARGUMENTS` is empty, ask the reviewer for a short topic phrase (2-6 words is plenty — it only needs to be enough to name a folder; the full working title and objective are elicited properly in Step 4) before deriving the slug.
3. **Check for an existing review**: attempt to read `results/<TOPIC>/protocol.json`.
   - **If it exists**, this is a resume/update, not a fresh init. Read it in full, summarize its current title, framework, eligibility criteria, and scope back to the reviewer in plain language, and ask whether they want to (a) update this protocol (carry the update into Step 4, which routes to the `review-protocol` skill's own "Before you begin" update path and never silently overwrites recorded eligibility criteria), or (b) start a distinct review under a different topic slug (go back to Step 0.2 with a new slug). Do not re-run Steps 1-3 wholesale for an update — Step 2 (reviewer profile) in particular should only run if `CLAUDE.local.md` still has placeholder tokens; re-confirm scope (Step 1) only if the reviewer says scope is what's changing. Don't write the amendment record yourself — the `review-protocol` skill's update path owns `protocol.json`'s `amendments: [{date, change, reason}]` array (PRISMA Item 24c); your job here is only to route into that path.
   - **If it does not exist**, this is a fresh init. Continue to Step 1.

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
   - **Field of research** (e.g. "clinical anesthesiology", "education technology") — this calibrates tone and journal conventions later in `/prisma-report`.
   - Institution / affiliation (optional).
   - **Prior relevant work** — publications, prior reviews, or projects that inform this review's framing and related-work section (one or more; "none yet" is a valid answer).
   - **Target journal(s)** — used to calibrate manuscript tone, length, and reference style in `/prisma-report` (one or more; "not decided yet" is valid).
   - **Preferred citation style** — default to APA 7th edition if the reviewer has no preference; don't block on this.
   - **Institutional database access** (optional) — e.g. Scopus, Web of Science. This doesn't add a connector now; just note it so the reviewer remembers `/prisma-add-source` is available for it later.
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

Substitute the real `<TOPIC>` slug from Step 0. The `.gitkeep` touches matter: `.gitignore` ignores everything under `results/**` except `.gitkeep` and `README.md` files, so an empty subfolder needs one to survive being tracked by anyone who later `git add`s the structure. Do not create `search_plan.json`, `records.jsonl`, `screening_decisions.jsonl`, `extraction_table.json`, or `rerun_search.sh` here — those are written by later pipeline commands (`/prisma-search` writes the first and last of those), not by `/prisma-init`.

---

## Step 4: Define the Review Question

Invoke the **`review-protocol`** skill (Skill tool, `skill: review-protocol`) to run its Phase 1 interview and Phase 2 persistence for `results/<TOPIC>/`. Before invoking it, tell it explicitly:

- The target path is `results/<TOPIC>/protocol.json` (the `<TOPIC>` resolved in Step 0).
- Scope has **already been collected** in Step 1 above — pass along `mode`, `region`, and any named `coverage_gaps` so the skill writes them straight into `protocol.json.scope` rather than re-running its own Phase 1 Step 4 scope elicitation.
- If Step 0 identified this as a resume/update, tell the skill so it takes its "Before you begin" update path (read the existing file, confirm what's changing, never silently overwrite recorded eligibility criteria).

Let the skill run its full interview: framework selection (PICO for intervention-effectiveness reviews, PICo for qualitative reviews, SPIDER for mixed-methods, or another framework where none of those fit), the framework-specific elicitation, and the hard eligibility gates (population, study design, publication type, date range, language-of-publication). Do not shortcut or paraphrase this interview yourself — the skill's own elicitation prompts and confirmation step are the mechanism that keeps `protocol.json` accurate.

---

## Step 5: Verify `protocol.json`

After the `review-protocol` skill finishes, read `results/<TOPIC>/protocol.json` back and confirm it matches this schema with every field actually populated (no leftover `null`/placeholder where a real answer was given in Steps 1 or 4):

```json
{
  "title": "...",
  "objective": "...",
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
  }
}
```

Some fields are legitimately `null` and are not gaps: `registration.id` when `registration.status` is `"unregistered"`, `eligibility.date_range.to` for an open-ended date range, and `scope.region` for a `"global"` review. Treat only a genuinely unanswered field (an empty `framework_fields` entry, a `criterion`/`included` value the reviewer never actually gave) as a gap. If any such field is missing, do not proceed to Step 6 — go back into the `review-protocol` skill's interview for the missing field specifically, rather than inventing a value or leaving it blank. This file is read verbatim by every later command (`/prisma-search`, `/prisma-screen`, `/prisma-report`) — a gap here becomes a silent gap everywhere downstream.

---

## Step 6: Hand Off Keyword Elicitation

Invoke the **`keyword-expansion`** skill (Skill tool, `skill: keyword-expansion`) for `results/<TOPIC>/`. This is a full handoff, not a summary you perform yourself: let the skill read the PICO/PICo/SPIDER seed terms out of the `protocol.json` you just verified, run its own LLM-assisted expansion pass with reviewer confirmation, translate the confirmed terms into each source's native query syntax, apply the Step 1 scope (it will re-read `protocol.json.scope.mode` and, if `"national"`, offer the optional keyword-translation step and record any additional coverage gaps), and persist the result to `results/<TOPIC>/search_plan.json`.

"Enabled" at this stage means **all six shipped sources** (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv) — all six are free at basic-access level (§3), so `/prisma-init` has no reason to exclude any of them. Build a confirmed query string for every one of the six; picking which sources actually *run* in a given search is `/prisma-search`'s job, not this command's — narrowing the set here would leave `search_plan.json` incomplete for PRISMA Item 7's per-database audit trail.

Do not skip this step or defer it to `/prisma-search` "for later" — a review with a protocol but no search plan is not actually ready to search, and `search_plan.json` is what makes PRISMA Item 7 auditable later.

**After the skill returns**, re-read `results/<TOPIC>/protocol.json` once more. If `scope.translation_used` was set to `true` (the skill's Step 4 ran a national-scope translation), also set `eligibility.language.translation_used` to `true` and add the translated language(s) to `eligibility.language.included` if they aren't already there. `scope` is the authoritative record of *whether and into what* translation happened; `eligibility.language` must never silently disagree with it, since `/prisma-report`'s Methods §2.3 and the eligibility gate both read from `eligibility.language` directly.

---

## Step 7: Confirm and Next Steps

Once `protocol.json` and `search_plan.json` both exist and are verified, present a short summary:

> **Review initialized: `results/<TOPIC>/`**
>
> - **Title:** [title from protocol.json] - **Framework:** [framework] — [one-line summary of the framework fields] - **Scope:** [Global | National/Regional: <region>], [N] coverage gap(s) noted - **Eligibility gates set:** population, study design, publication type, date range, language - **Search plan:** confirmed query strings for all six sources (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv)
>
> **Next:** run `/prisma-search` to run the connector CLIs against the confirmed search plan and build the deduplicated record ledger.

If the reviewer profile interview (Step 2) was skipped because it was already on file, don't mention it again here — only call out what actually changed in this run.

---

## Notes

- Steps 0-3 establish *where* things go (topic slug, workspace directories, reviewer profile) before Step 4 asks the `review-protocol` skill *what* the review is actually about — doing it in the other order means the skill has nowhere to write its output.
- Scope (Step 1) is collected once, here, and threaded into both `review-protocol` (Step 4) and `keyword-expansion` (Step 6) rather than re-asked by each — a reviewer should never have to answer "global or national?" twice in the same `/prisma-init` run.
- This command is safe to re-run on the same topic: Step 0.3 detects an existing `protocol.json` and routes into the update path instead of silently overwriting eligibility criteria that screening decisions may already depend on.
- Nothing in this command touches `records.jsonl`, `screening_decisions.jsonl`, or any file under `synthesis/`/`manuscript/` — those belong to later commands and stay untouched here even on a resume.
