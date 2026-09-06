---
allowed-tools: Read, Glob, Bash(python3 tools/status.py:*)
---

# /prisma-status - Report Pipeline Progress and the Next Command to Run

You are answering one question: **for a given review, exactly what has this pipeline already done, and what should the reviewer run next?** This is the resumability mechanism the whole framework depends on — every state file under `results/<TOPIC>/` is append-only or fully re-derivable (architecture plan §2) specifically so that closing a laptop mid-screening for weeks and running `/prisma-status <TOPIC>` reconstructs exactly where things stand, with no number ever hand-typed or recalled from memory.

`$ARGUMENTS` is the topic name (or an already-slugged folder name). With no argument, list every review under `results/` with a one-line status each.

**Never open `records.jsonl` or `screening_decisions.jsonl` with the `Read` tool** — the same context-flatness discipline `screening-assistant` and `/prisma-report` enforce applies here: a review with 5,000 records must cost the same context as one with 50. All counts in this command come from the single `python3 tools/status.py` subprocess in Step 3, whose stdout is a compact report, never the raw ledgers. `protocol.json`, `search_plan.json`, and `extraction_table.json`/`synthesis/*.json` are small and structured enough that the tool reads them directly, but they are still read *inside* the subprocess, never with the `Read` tool, so this command has exactly one place that touches disk.

Follow the steps below **in order**. Do not skip a step.

---

## Step 0: Parse `$ARGUMENTS` and Determine Mode

1. Trim leading/trailing whitespace from `$ARGUMENTS`.
2. **Empty after trimming → list-all mode.** Skip Step 2 (topic resolution) entirely and go straight to Step 1, then Step 3's list-all invocation.
3. **Non-empty → single-topic mode.** Hold the trimmed string as `<TOPIC_HINT>` for Step 2.

---

## Step 1: Discover Existing Reviews

Run `Glob` for `results/*/` to list every existing review directory. Do this unconditionally, in both modes — list-all mode needs the full set, and single-topic mode needs it to resolve `<TOPIC_HINT>` against real directories rather than guessing a slug that was never actually created.

- **Zero directories found:**
  - List-all mode: reply `No reviews found under results/. Run /prisma-init "<topic>" to start one.` and stop — there is nothing further to compute.
  - Single-topic mode: reply `No reviews found under results/. Run /prisma-init "<TOPIC_HINT>" to start this one.` and stop.
- **One or more directories found:** continue. List-all mode skips straight to Step 3; single-topic mode continues to Step 2.

---

## Step 2: Resolve `<TOPIC>` (single-topic mode only)

`<TOPIC_HINT>` may be free text (`"AI in Korean Elder Care"`), an already-slugged folder name (`ai-in-korean-elder-care`), or something close but not exact. Resolve it against the directories from Step 1 in this order, stopping at the first that yields a match:

1. **Exact match** — `<TOPIC_HINT>` equals a directory name exactly.
2. **Slug match** — derive a slug from `<TOPIC_HINT>` using the exact rule `/prisma-init` Step 0 uses (lowercase, trim whitespace, replace every run of characters that are not `[a-z0-9]` with a single hyphen, strip leading/trailing hyphens, cap at 60 characters) and match that slug against the directory names.
3. **Fuzzy match** — case-insensitive, with spaces/hyphens/underscores collapsed to nothing on both sides (`"korean elder care"` ~ `korean-elder-care`), match `<TOPIC_HINT>` against every directory name.

Then:

- **Zero matches:** stop. Reply `No review matching "<TOPIC_HINT>" found under results/. Existing topics: <list>. Run /prisma-init "<TOPIC_HINT>" to start a new one.`
- **Exactly one match:** use it as `<TOPIC>`. If it came from the slug or fuzzy path (not an exact match), say which folder you resolved to (e.g. `"Using results/korean-elder-care/ for 'Korean Elder Care'"`) so the reviewer can redirect you if it's wrong.
- **More than one match:** stop. List the matching topics and ask which one is meant — never guess among several active reviews.

---

## Step 3: Run the Status Computation

Run the deterministic status tool via `Bash`. **List-all mode** passes no `--topic`; **single-topic mode** passes the resolved `<TOPIC>` directory name (not a full path, not the original free-text hint) as `--topic`. Both modes run the exact same script (`tools/status.py`) — the branch is inside its own `main()`.

```bash
python3 tools/status.py --topic <TOPIC>
```

(Pre-allowlisted in `.claude/settings.json` — `Bash(python3 tools/status.py:*)`.) For list-all mode, omit `--topic` entirely: `python3 tools/status.py`.

`tools/status.py` is a behavior-preserving port of what used to be an inline heredoc embedded directly in this prompt (docs/PLAN.md defect #3) — it reuses `tools/ledger.py`'s `load_ledger`/`latest_decisions` for the same title-abstract/full-text aggregation `tools/flow_counts.py` uses for the PRISMA flow diagram, so this command and the eventual manuscript's flow-diagram counts can never silently disagree.

Do not edit the tool's logic per run. It is deterministic and reads only what already exists on disk; if a count looks wrong, the fix is in the upstream command that wrote the file, never in this script.

---

## Step 4: Present the Report

Relay the script's stdout to the reviewer essentially verbatim — reformat lightly for readability (e.g. as Markdown headings/lists matching what it already prints) but **never recompute, round, or "correct" a number it printed**. Specifically:

1. **List-all mode**: present the condensed one-liner per topic as a short table or list. If the reviewer's message named a topic loosely that didn't parse as an argument (unusual, since Step 0 already routed a non-empty `$ARGUMENTS` to single-topic mode), don't second-guess it here — list-all mode's job is the full inventory.
2. **Single-topic mode**: present the full report. Put **"Current stage"** and **"Next command"** at the top of your reply, not buried at the end — that is the one line a returning reviewer most needs, even before the counts. Then show the pipeline counts, then any `WARNING:` blocks the script printed.
3. If any `WARNING:` block appeared, call it out explicitly and do not treat the "Next command" recommendation as sufficient on its own — a missing full-text-exclude reason or an extraction gap needs to be resolved before the recommended next command will actually run cleanly for `/prisma-extract`/`/prisma-report`, even though the state-machine logic already accounts for most of these in choosing what to recommend.
4. If `stage` is `screening_complete_zero_included`, do not suggest any pipeline command — say plainly that zero studies were included and ask whether the reviewer wants to revisit `protocol.json`'s eligibility criteria (a re-run of `review-protocol`'s elicitation, invoked via `/prisma-init` on the same topic) rather than proceeding.
5. Never suggest `/prisma-add-source` or `/prisma-reset` as "the next command" — both are always available but neither is part of the sequential pipeline this state machine tracks; mention them only if the reviewer's own message suggests they're relevant (e.g. they mention wanting to add an institutional database, or wanting to redo a stage from scratch).

---

## Notes

- This command **never writes anything**. It is safe to run at any point, any number of times, including mid-screening, mid-extraction, or after a `/prisma-reset`.
- The Identification/Screening/Included counts here use the **same aggregation algorithm** `/prisma-report` Step 8 uses to compute the PRISMA flow-diagram numbers (latest raw file per source, `duplicate_of` truthiness for dedup, latest-line-per-`(record_id, stage)` for screening decisions). This is deliberate: a reviewer should never see one count from `/prisma-status` and a different one in the eventual manuscript's flow diagram. If the two ever disagree, that is a bug in whichever command computed the number differently — not a discrepancy to paper over in either command's output.
- `extraction_table.json` has been written under more than one top-level shape at different points in this repo's history (a bare JSON array vs. `{"studies": [...]}`, with either `record_id` or `study_id` as the per-study identifier). The script's `as_list()`/`study_id()` helpers accept either so `/prisma-status` keeps working regardless of which shape `/prisma-extract` currently produces — but this inconsistency is worth flagging back to whoever maintains `/prisma-extract` and `synthesis/run_synthesis.py`, since **those two files still need to agree with each other** on one canonical shape; `/prisma-status` papering over it is not a substitute for fixing it there.
- The "manuscript may be stale" check (mtimes of `extraction_table.json`/`synthesis/*.json` vs. `manuscript/manuscript.md`) is a heuristic, not a content diff — a reviewer who re-ran `/prisma-extract` with `--redo` on a single study whose numbers didn't actually change will still see this flagged. That is the correct conservative default: silently trusting a stale manuscript is worse than an occasional unnecessary "consider re-running `/prisma-report`" nudge.
- Orphaned screening decisions (a decision recorded for a `record_id` that is no longer canonical in `records.jsonl`) are surfaced here by design — `screening-assistant`'s own documentation explicitly defers this check to `/prisma-status` rather than handling it at import time, since import has no way to know a record will later be reclassified as a duplicate.
