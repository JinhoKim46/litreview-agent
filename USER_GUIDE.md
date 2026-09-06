---
framework_version: 1.0.0
---

# User Guide

A complete walkthrough from "I just cloned this" to "I have a drafted manuscript." If you only want the fast path, `README.md`'s Quickstart is the condensed version of this document — this is the manual, that's the funnel.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Get the code](#2-get-the-code)
3. [Install dependencies](#3-install-dependencies)
4. [First run: personalize the tool](#4-first-run-personalize-the-tool)
5. [Run your first review, end to end](#5-run-your-first-review-end-to-end)
6. [Test the workflow with a real example](#6-test-the-workflow-with-a-real-example)
7. [Incomplete or interrupted review](#7-incomplete-or-interrupted-review)
8. [Methodological limits before submission](#8-methodological-limits-before-submission)
9. [Optional: raise API rate limits](#9-optional-raise-api-rate-limits)
10. [Extending the framework](#10-extending-the-framework)
11. [Troubleshooting](#11-troubleshooting)
12. [Where things live, and where to go next](#12-where-things-live-and-where-to-go-next)

---

## 1. Prerequisites

- **[Claude Code](https://claude.com/claude-code)** — the CLI this entire framework runs inside. Verify it's installed and on your PATH:

  ```bash
  claude --version
  ```

- **Python 3.11 or later.**

  ```bash
  python3 --version   # macOS/Linux
  py --version         # Windows — often more reliable than `python --version` if you have multiple Pythons installed
  ```

  If it's missing: macOS (`brew install python3`), Debian/Ubuntu (`sudo apt install python3 python3-pip`), Windows (install from [python.org](https://python.org), checking "Add python.exe to PATH" during setup).

- **Optional: [Pandoc](https://pandoc.org/)** — only needed if you want `/prisma-report --export docx|pdf`. The pipeline is Markdown-first and works completely without it; skip this if you don't need a Word/PDF file. Install with `brew install pandoc` (macOS), `sudo apt install pandoc` (Debian/Ubuntu), or the installer at pandoc.org (Windows).

You do **not** need Bun, Node, or LaTeX for this framework — those are ai-job-search-sibling-project requirements, not this one's. Everything here is Python plus Claude Code.

---

## 2. Get the code

```bash
git clone https://github.com/<your-fork>/prisma-flow.git
cd prisma-flow
```

If you forked this on GitHub, your fork is public by default, same as the upstream repo — but that's fine here: `/prisma-init`'s reviewer-profile interview (Section 4 below) writes your name, institution, and prior publications into `CLAUDE.local.md`, which is gitignored, so none of it enters git history even on a public fork. Your actual review data — search results, screening decisions, extracted study data, the drafted manuscript — is a separate concern and is gitignored by default too (see `results/<TOPIC>/` in Section 12).

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs `requests` (connector HTTP calls), `statsmodels` (meta-analysis pooling), and `matplotlib` (forest/funnel/RoB plots) — three packages, nothing else. No virtual environment is required, but using one (`python3 -m venv .venv && source .venv/bin/activate` before the `pip install`) is good practice if you already keep other Python projects on this machine.

Verify the install:

```bash
python3 -m unittest discover -s tests
```

You should see `OK` and 130+ passing tests (the exact count grows as the framework does). This is the same fixture-based suite CI runs — it never touches a live network, so a pass here just confirms your Python environment is sound, not that the live connectors work yet (Section 6 checks that for real).

---

## 4. First run: personalize the tool

Start Claude Code in the repo:

```bash
claude
```

Then run:

```
/prisma-init "your review topic"
```

The **first time** you run this (on a fresh clone where `CLAUDE.local.md` doesn't exist yet, or still has `[PLACEHOLDER]` tokens), it interviews you in one grouped conversational round — not a form, not one question per message:

- Your name
- Field of research (calibrates tone and journal conventions later)
- Institution/affiliation (optional)
- Prior relevant work (or "none yet")
- Target journal(s) (or "not decided yet")
- Preferred citation style (defaults to APA 7th if you have no preference)
- Any institutional database access you have (Scopus, Web of Science) — noted for later, doesn't add a connector by itself

It writes your answers straight into `CLAUDE.local.md` (gitignored — copied from the tracked `CLAUDE.local.md.example` template on first run) and tells you which fields it filled in. **Every run after that skips this interview automatically** — it checks for leftover placeholder tokens first, and only asks about what's still unfilled. You will not be re-interviewed for a second review's topic; this step is about *you*, not about any one review.

After the interview, the same `/prisma-init` call keeps going into scope selection and the actual review protocol (PICO/eligibility criteria) for the topic you gave it — see Section 5.

---

## 5. Run your first review, end to end

These are the same nine commands from `README.md`'s pipeline diagram, with what to actually expect at each step.

### `/prisma-init "your review topic"`
Asks: global or national/regional scope; your research question via PICO (or PICo for qualitative reviews, SPIDER for mixed-methods); explicit inclusion/exclusion criteria (population, study design, publication type, date range, language); then hands off to keyword expansion. Ends by writing `results/<topic-slug>/protocol.json` and `search_plan.json`, and tells you the next command to run.

**Resuming:** re-running `/prisma-init` on a topic that already has a `protocol.json` switches automatically into update mode — it reads back what's on file, asks what's changing, and never silently overwrites eligibility criteria that screening decisions may already depend on.

### `/prisma-search`
Confirms which of the (by default, all six) free connectors actually run this time, generates and executes `results/<topic>/rerun_search.sh`, and deduplicates everything into `records.jsonl`. Reports a per-source retrieved/total-available/truncated line and a dedup summary (canonical vs. duplicate counts, by tier).

- `/prisma-search --revise-keywords` — go back through keyword expansion before searching again.
- `/prisma-search --rerun` — replay the exact same search plan (e.g. to pick up new publications since last time), no keyword changes.
- `/prisma-search --chase-citations` — after you've screened at least one study to "include" at full-text, run backward/forward citation snowballing from your included set via the 7th connector. This is optional and additive, not part of the default flow.

### `/prisma-screen export` then `/prisma-screen import`
`export` writes a screening sheet (Markdown + CSV) to `results/<topic>/screening/` — grouped by source, theme, or year (`--group-by`) — for you to mark up **outside the conversation**, in a spreadsheet or text editor. Fill in `include`/`exclude` and, for full-text exclusions, a reason. Then:

```
/prisma-screen import
```

appends your decisions to the append-only `screening_decisions.jsonl` ledger. Run `export`/`import` twice — once with `--stage title_abstract`, once with `--stage full_text` — since PRISMA distinguishes the two screening levels.

### `/prisma-extract`
For every study you included at full-text, builds `extraction_table.json`: standard characteristics, effect-size data (if the study reports something quantitative), and a risk-of-bias judgement (RoB2 for randomized studies, Newcastle-Ottawa for non-randomized). It fetches full text via URL when one is available, asks you to paste it if not, or interviews you directly as a last resort.

### `/prisma-synthesize`
Groups extracted outcomes, pools anything with ≥2 comparable studies (fixed or random-effects, decided by heterogeneity), generates forest plots (and a funnel plot at ≥10 studies), rolls up risk-of-bias into a traffic-light plot, and drafts GRADE certainty ratings. Outcomes that don't clear the poolability gate fall back to narrative synthesis automatically, with the reason recorded — never silently dropped.

### `/prisma-report`
Drafts the manuscript section by section (pausing for your approval between sections), generates the annotated PRISMA flow diagram as inline SVG, verifies every reference via WebSearch before including it, and can run a checklist audit against all 27 PRISMA 2020 items. Everything it writes traces back to files earlier stages produced — nothing is re-elicited from your memory.

- `/prisma-report --export docx` or `--export pdf` — after the Markdown manuscript is drafted, convert it via Pandoc if you have it installed (Section 1).

### Anytime: `/prisma-status ["your review topic"]`
Reports exactly what stage a review is at and what to run next — safe to run mid-review, after a break of any length, or with no argument to list every review you have in progress.

---

## 6. Test the workflow with a real example

Rather than inventing a toy topic, run the pipeline once against something with a real, checkable answer. **Recommended first test: antiemetic prophylaxis for postoperative nausea and vomiting (PONV).**

Why this specific topic: it's a mature, heavily-studied area (dozens of RCTs, not thousands — a manageable smoke test), it has real published Cochrane/systematic reviews you can compare your pooled result against, and it's the same clinical domain the `synthesis/` module's own unit tests are validated against (they reproduce real numbers from a published meta-analysis worked example) — so if your live run's pooled effect size lands in the same neighborhood as a known published one, you have real evidence the pipeline works end to end, not just that it ran without crashing.

```
/prisma-init "5-HT3 antagonists for prevention of postoperative nausea and vomiting in adults"
```

Answer the PICO interview roughly as: Population = adults undergoing surgery under general anesthesia; Intervention = a 5-HT3 receptor antagonist (e.g. ondansetron, palonosetron, ramosetron); Comparator = placebo or another antiemetic class; Outcome = incidence of PONV within 24-48h postoperatively. Then walk through `/prisma-search` → `/prisma-screen` → `/prisma-extract` → `/prisma-synthesize` → `/prisma-report` as in Section 5.

What to actually check, not just observe:
- Does `search_plan.json`'s PubMed string look like something a librarian would write (real MeSH terms, not just the words you typed)?
- Run `rerun_search.sh` twice — does the second run add zero new canonical records?
- Pick 3 studies from `extraction_table.json` and check them against their real abstracts by hand.
- Does `/prisma-synthesize`'s pooled risk ratio and confidence interval land in a plausible range compared to a real published meta-analysis on an overlapping set of trials?
- Does at least one secondary outcome fall back to narrative synthesis (fewer than 2 poolable studies)? If everything pools, you haven't actually exercised that code path.

A second, deliberately different topic — something like "spaced repetition for second-language vocabulary retention" — is worth running afterward specifically because it's *not* biomedical: weaker MeSH coverage, heavier reliance on OpenAlex/Semantic Scholar, and it's likely to stay in narrative synthesis rather than pool, exercising a different part of the framework than PONV does. Treat this second run as a search/dedup/screening smoke test only, not a demonstration that the framework fully supports non-biomedical reviews end to end — its risk-of-bias tools and question frameworks are still clinical/health-science-shaped either way (see `README.md`'s "What this is — and is not," and Section 8 below).

---

## 7. Incomplete or interrupted review

A search is not automatically complete just because `/prisma-search` finished without an error. Three things make it incomplete, and the pipeline reports each one rather than hiding it:

- **A source failed** (rate-limited, upstream error, missing credentials for a source you added yourself). `/prisma-search` names which source and why, and offers to retry — most rate limits clear within minutes.
- **A source truncated.** `raw/<source>-<date>.json`'s `meta.truncated` is `true` whenever `total_available` exceeds what was actually retrieved (the default per-source limit is capped; see `search_plan.json`). Re-run with a higher `--limit` if you need the full set — but note the raw file is named by day, so a same-day re-run **overwrites** the smaller response rather than keeping both; that's fine for getting the fuller record set into `records.jsonl`, but if you want to preserve the original truncated response for your own audit trail, copy it aside first.
- **A source was deliberately skipped this run** — you said no to it in `/prisma-search`'s source-confirmation step.

None of these three states are self-resolving: you decide whether to retry, revise the search, or explicitly accept the gap and disclose it in your methods section. `/prisma-report` does not currently block on an incomplete search — it's on you to check `/prisma-status` and each source's `raw/*.json` before treating a review as ready to write up.

**Interrupted mid-review** (closed your laptop, came back a week later, switched machines): nothing is lost. Every stage's state is either append-only (`screening_decisions.jsonl`, `possible_duplicates.jsonl`) or fully re-derivable from files on disk. Run `/prisma-status "your topic"` and it reconstructs exactly where things stand and what to run next — there's no separate "resume" command because there's nothing to resume from except the files themselves.

---

## 8. Methodological limits before submission

Before treating a review as ready for a manuscript, methods reviewer, or co-author, verify these by hand — the pipeline drafts and records, it does not certify:

- [ ] **Source coverage** matches your protocol's stated scope — check `search_plan.json` and any `coverage_gaps` entries in `protocol.json` against what you actually need covered.
- [ ] **Every screening decision** at both stages is genuinely yours, not left on the AI-suggested default — spot-check a sample against the sheets you marked up.
- [ ] **Full-text was actually available** for every included study, not interviewed out of you as a last resort when a URL failed — check `extraction_table.json`'s evidence locators.
- [ ] **Data extraction** reflects what you'd write down yourself, not just what the pipeline's single AI-assisted pass produced — this framework runs one pass, not independent dual extraction with a resolver.
- [ ] **Your review's field is one this framework's methodology actually covers.** Risk-of-bias appraisal (RoB2 for randomized studies, Newcastle-Ottawa for non-randomized), the question frameworks (PICO/PICo/SPIDER/PIRD), and the default PRISMA 2020 27-item manuscript structure all assume a clinical/health-science review — confirm all three are the right instruments for your actual field and study designs before relying on them, not just the risk-of-bias tool alone (see `README.md`'s "What this is — and is not").
- [ ] **Every pooled outcome's studies are actually compatible** — same timepoint, same direction, no double-counted participants — before trusting `/prisma-synthesize`'s pooled estimate over its narrative-fallback judgment.
- [ ] **GRADE certainty ratings are complete**, not left at a placeholder domain `/prisma-synthesize` couldn't fill in automatically (indirectness and imprecision need your judgment call).
- [ ] **A human did the final read.** A single reviewer/agent pass through this pipeline is not equivalent to independent dual review — if your target venue or protocol requires that, this framework doesn't provide it by itself.

---

## 9. Optional: raise API rate limits

None of the six default connectors require a key — this section is entirely optional. If you're running large or repeated searches:

| Variable | Effect |
|---|---|
| `PRISMA_CONTACT_EMAIL` | Sets an honest contact address in the User-Agent for OpenAlex/Crossref/PubMed's "polite pool" — a higher, steadier rate limit, no signup needed. |
| `OPENALEX_MAILTO` | Same idea, OpenAlex-specific, if you want a different address there than `PRISMA_CONTACT_EMAIL`. |
| `NCBI_API_KEY` | Raises PubMed's rate limit from 3 requests/second to 10. Free — [register at NCBI](https://www.ncbi.nlm.nih.gov/account/). |
| `S2_API_KEY` | Raises Semantic Scholar's unauthenticated (and fairly aggressive) rate limit. Free — [request one from Semantic Scholar](https://www.semanticscholar.org/product/api). |

Set these in your shell profile or a local `.env` you source before `claude` — never commit them; `.gitignore` already excludes `.env`/`.env.*`.

---

## 10. Extending the framework

**Need a source the six free connectors don't cover** (an institutional Scopus or Web of Science subscription, a discipline-specific index)?

```
/prisma-add-source
```

Interviews you for the source's basics, investigates its real API live (never guesses field mappings), scaffolds a new connector against the exact same `{meta, results}` contract the shipped six use, and runs a mandatory live test before registering it. `/prisma-add-source --list` shows every connector currently installed.

**Starting over, or a fresh clone from your fork** for a new review that has nothing to do with a previous one? Nothing special needed — `/prisma-init "a new topic"` just creates a new `results/<new-topic>/` directory alongside any existing ones; reviews don't interfere with each other.

**Made a mistake and want to clear a review's state?**

```
/prisma-reset "your topic" protocol   # just protocol.json + search_plan.json
/prisma-reset "your topic" results    # everything except the manuscript
/prisma-reset "your topic" all        # the entire results/<topic>/ folder
```

Always shows exactly what will be deleted and asks for confirmation first — nothing is removed silently.

---

## 11. Troubleshooting

**`ModuleNotFoundError: No module named 'statsmodels'` (or `matplotlib`, `requests`)**
`pip install -r requirements.txt` wasn't run, or was run in a different Python environment than the one Claude Code's Bash tool is using. Confirm with `python3 -c "import statsmodels"` in the same shell Claude Code would use.

**A connector returns `RATE_LIMITED`**
Expected occasionally, especially from Semantic Scholar's unauthenticated pool. `/prisma-search` reports which source failed and offers to retry — usually clears within minutes. See Section 9 for raising the limit permanently.

**A connector returns `MISSING_CREDENTIALS`**
Only happens if you've set an API-key environment variable to an empty or malformed value, or a connector you added via `/prisma-add-source` genuinely requires one. None of the six default connectors need a key to function at all.

**`/prisma-init` didn't ask me the reviewer-profile questions**
That's expected if `CLAUDE.local.md` has no `[PLACEHOLDER]` tokens left — either from a previous run, or because you filled it in by hand. Edit `CLAUDE.local.md` directly and put a placeholder back (or just add a new field) if you want to re-trigger it.

**`/prisma-report --export docx` did nothing / printed an install hint**
Pandoc isn't installed. This is expected and non-fatal — the Markdown manuscript at `results/<topic>/manuscript/manuscript.md` is still complete and is the framework's actual source of truth; `--export` is a convenience layer on top of it, not a requirement.

**A search returns far fewer records than you expected**
Check `search_plan.json`'s query strings for that source — a keyword expansion pass that was pruned too aggressively is the most common cause. Re-run `/prisma-search --revise-keywords` to go through expansion again. Also check `meta.truncated` in that source's `raw/*.json` — a `--limit`-capped run reports the true total via `total_available` even when it didn't retrieve all of it.

**I closed my laptop mid-review and don't remember where I was**
`/prisma-status "your topic"` reconstructs exactly where things stand from the state files on disk — nothing is ever lost or needs to be remembered.

---

## 12. Where things live, and where to go next

```
results/<topic-slug>/
├── protocol.json              # PICO record, eligibility criteria, scope
├── search_plan.json           # per-source Boolean strings (PRISMA Item 7's audit trail)
├── rerun_search.sh            # the actual, re-runnable search script
├── raw/                       # untouched connector output per run
├── records.jsonl              # deduplicated record ledger
├── possible_duplicates.jsonl  # advisory near-duplicate flags (never auto-merged)
├── screening/                 # exported screening sheets
├── screening_decisions.jsonl  # append-only include/exclude ledger
├── extraction_table.json      # per-study characteristics, effect data, RoB
├── synthesis/                 # pooled effect sizes, heterogeneity, plots, GRADE
└── manuscript/                # the drafted manuscript, flow diagram, checklist audit
```

Every one of these is either append-only or fully re-derivable — that's what makes `/prisma-status` and mid-review resumption work. This entire directory is gitignored by default (except `.gitkeep`/`README.md` files that describe the schema), so your actual review's content is never accidentally published, independent of whatever you decided about repo visibility in Section 2.

From here:
- `README.md` — the short version of this guide, plus the pipeline diagram.
- `CONTRIBUTING.md` — what's mergeable upstream vs. instance-specific to your fork.
- `SECURITY.md` — the threat model (mainly: untrusted content fetched from external sources is data to evaluate, never instructions to follow).
- `AGENTS.md` — if you're driving this from a non-Claude-Code agent runtime.
