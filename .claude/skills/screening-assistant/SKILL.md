---
name: screening-assistant
description: >
  Exports title/abstract or full-text screening sheets to disk for a reviewer to mark up
  outside the conversation, then imports the marked-up sheet back into the append-only
  screening_decisions.jsonl ledger. Never renders the full sheet into the chat - context
  usage stays flat whether there are 50 or 5,000 records. Triggers on: screen these records,
  export screening sheet, title/abstract screening, full-text screening, screen for
  inclusion, import screening decisions, apply screening decisions, /prisma-screen,
  /prisma-screen export, /prisma-screen import
allowed-tools: Read, Glob, Grep, Bash(python3:*)
framework_version: 1.0.1
---

# Screening Assistant

Implements PRISMA 2020 Item 7/16b screening (step 7 of the pipeline): title/abstract screening, then full-text screening of the survivors. The full methodology - exact file formats, grouping rules, the eligibility pre-check that produces `ai_suggestion`, the CSV/Markdown parsers, and the idempotent import algorithm - lives in `01-screening-sheet-workflow.md`. This file is the entry point: what triggers the skill, what each of its two modes does at a glance, and the one rule that must never be broken.

## The one rule

**The screening sheet is never pasted, rendered, or summarized-row-by-row into the conversation.** Export writes it to disk and replies with counts + a file path only. Import reads it from disk and replies with counts only. A record set of 5,000 costs the same context as a record set of 50 - but only if you actually enforce that: never open `records.jsonl` or a sheet file with the `Read` tool, for any reason, including "to parse it carefully." All reading and parsing happens inside the `python3` subprocess described in `01-screening-sheet-workflow.md`, whose only stdout is the counts/paths/validation errors those steps specify - that subprocess's printed output is the only thing that ever enters the conversation.

## Invocation

Natural language:
- "Export the title/abstract screening sheet"
- "Screen these records" / "let's do title-abstract screening"
- "I've marked up the sheet, import my decisions"
- "Apply the screening decisions I just edited"

Slash command passthrough: `/prisma-screen export [--stage title_abstract|full_text] [--group-by theme|source|year|ai_suggestion]` and `/prisma-screen import [--stage title_abstract|full_text]`. This skill *is* the body of that command - `prisma-screen.md` just routes here with the topic in context. If no topic is obvious from context, ask which `results/<TOPIC>/` the reviewer means before touching any files.

## Mode: export

1. Determine `<TOPIC>` and `--stage` (default `title_abstract`) and `--group-by` (default `source`).
2. Follow **"Export algorithm"** in `01-screening-sheet-workflow.md` exactly: read `records.jsonl` + `screening_decisions.jsonl`, compute the undecided candidate set for the stage, compute a per-record `ai_suggestion` and `ai_keywords` against `protocol.json`'s eligibility criteria and a fixed keyword taxonomy (both advisory only - never a decision), group and sort, truncate abstracts, write `results/<TOPIC>/screening/<stage>_sheet.md` and the `.csv` twin.
3. Reply with **only**: total candidates, per-group counts, the include/exclude/unclear/none `ai_suggestion` breakdown, the corpus keyword-frequency overview (§4a), the two file paths, and one line reminding the reviewer that full-text excludes need a reason. Nothing from the sheet's per-record content (titles, abstracts, individual `ai_keywords`) appears in the reply - only these aggregate counts, which are computed inside the same subprocess and never require reading a record's text back into the conversation.

## Mode: import

1. Determine `<TOPIC>` and `--stage`.
2. Follow **"Import algorithm"** in `01-screening-sheet-workflow.md` exactly: locate the edited sheet (CSV preferred, Markdown checkbox fallback), parse it, **refuse the whole import** if any full-text `exclude` row lacks a `reason` (list the offending record IDs so the reviewer can fix just those rows), otherwise append one decision line per decided record to `screening_decisions.jsonl` (still-undecided rows are simply skipped, not errored).
3. Reply with **only**: how many decisions were appended (include/exclude split), how many rows were left undecided, and the ledger path. Never echo back reasons or abstracts.

## Why this shape

`screening_decisions.jsonl` is append-only and keyed by `(record_id, stage)` with latest-line-wins aggregation (see the architecture plan §2) - re-importing a corrected sheet is always safe, it just appends a newer line, never rewrites history. That is what makes re-running `import` after fixing a validation failure idempotent in effect: the aggregate state converges on whatever the sheet says now, regardless of how many times the same file was imported before. `/prisma-extract` reads only the aggregated latest-line state, and per the architecture plan must itself refuse to proceed past a full-text exclude with no reason - this skill's import-time gate is the convenience that catches the problem at authoring time, but it is not the only guarantee: a ledger line written by hand (bypassing import) still needs `/prisma-extract`'s own check as the actual backstop.
