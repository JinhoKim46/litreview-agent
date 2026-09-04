# /prisma-screen - Export or Import Screening Sheets

You are routing a screening request to the `screening-assistant` skill, which does the actual work. This command's own job is narrow: parse `$ARGUMENTS` correctly, resolve which review (`<TOPIC>`) is in scope, validate everything **before** any file is touched, then hand off. **You never read `records.jsonl`, a `screening_decisions.jsonl` line, or a sheet file yourself with the `Read` tool, at any step below** - that is the one rule the `screening-assistant` skill exists to enforce, and this command must not defeat it by "just peeking" to sanity-check something. Every file access happens inside the skill's `python3` subprocess.

Follow these steps **in order**. Do not skip a step, and do not reorder validation ahead of parsing or parsing ahead of validation.

---

## Step 0: Parse `$ARGUMENTS`

`$ARGUMENTS` must begin with exactly one subcommand: `export` or `import`. Everything after it is flags.

1. Split `$ARGUMENTS` on whitespace. The first token is the subcommand.
   - Not `export` and not `import` (including empty `$ARGUMENTS`) -> **stop** and reply: `"Usage: /prisma-screen export [--stage title_abstract|full_text] [--group-by theme|source|year|ai_suggestion]"` followed by `"       /prisma-screen import [--stage title_abstract|full_text]"`. Do not guess which subcommand was meant.
2. Parse remaining flags for that subcommand only:
   - **`export`** accepts `--stage <value>` (default `title_abstract` if omitted) and `--group-by <value>` (default `source` if omitted).
   - **`import`** accepts `--stage <value>` (default `title_abstract` if omitted) only. If `--group-by` is passed to `import`, **stop** and reply that `--group-by` only applies to `export` - don't silently ignore an argument the user typed on purpose.
3. Validate flag values before anything else runs:
   - `--stage` must be exactly `title_abstract` or `full_text`. Anything else (typos like `fulltext`, `abstract`, case variants) -> **stop**, name the invalid value, list the two valid ones, do not auto-correct a guess.
   - `--group-by` (export only) must be exactly `theme`, `source`, `year`, or `ai_suggestion`. Same stop-and-name rule on anything else.
4. State back, in one line, what you parsed (e.g. `"prisma-screen export --stage title_abstract --group-by source"`) so the user can catch a misparse before any file work starts.

---

## Step 1: Resolve `<TOPIC>`

The pipeline's state lives under `results/<TOPIC>/` and `$ARGUMENTS` never carries the topic explicitly for this command (unlike `/prisma-init`/`/prisma-status`) - it must come from context or be asked for.

1. List the immediate subdirectories of `results/` with the `Glob` tool (`results/*/`) - directory names only, never a file read. There is no slug convention defined anywhere in this repo for turning a free-text topic string into a directory name, so never invent one here.
2. If this conversation already has an active review topic in context (e.g. the user just ran `/prisma-init "Telehealth adherence in older adults"` earlier this session, or named one just now), match that topic string against the directory names from step 1, case-insensitively and ignoring separator characters (spaces/hyphens/underscores). If exactly one directory matches, use it as `<TOPIC>` and skip to step 4.
3. If context gave no topic, or it matched none of the directories, fall back to the listing itself:
   - **Zero subdirectories**: **stop**. Reply that no review exists yet and `/prisma-init "your topic"` must run first.
   - **Exactly one subdirectory**: use it as `<TOPIC>`, but say which one you picked (e.g. `"Using the only review found: results/telehealth-adherence/"`) so a user with a stale mental model of a different topic notices immediately.
   - **More than one subdirectory**: **stop** and ask the user which topic they mean, listing the candidates. Never guess among several active reviews.
4. Confirm `results/<TOPIC>/records.jsonl` exists (`Glob` for that exact path, not a directory listing this time).
   - Missing -> **stop**. Reply that this review has no records yet and `/prisma-search` must run first. Do not create an empty `records.jsonl` and do not proceed to the skill with nothing for it to read.

---

## Step 2: Mode-specific precondition checks

### If subcommand is `export`

1. A missing or empty `screening_decisions.jsonl` and a missing `protocol.json` are both valid, expected states the skill handles on its own (empty decisions = nothing screened yet; no protocol = every `ai_suggestion` comes back `none`). Do not block export on either.
2. **Overwrite guard.** `Glob` for `results/<TOPIC>/screening/<stage>_sheet.csv` (existence only, never a read). If it already exists, a previous export for this exact stage is sitting on disk and may hold marked-up decisions nobody has imported yet - re-exporting now would overwrite it and silently discard that work. **Stop** and tell the user plainly: a `<stage>` sheet already exists at that path, re-running export will regenerate it from scratch and any decisions written into it that were never imported will be lost; ask for explicit confirmation before proceeding. If they confirm (or if `$ARGUMENTS` already carried an explicit `--force` style go-ahead the user stated in plain language this turn), proceed to Step 3. If no sheet exists yet at that path, this is a first export for the stage - proceed to Step 3 with no prompt needed.
3. Proceed to Step 3.

### If subcommand is `import`

1. Confirm the sheet this stage expects exists on disk before invoking the skill: `Glob` for `results/<TOPIC>/screening/<stage>_sheet.csv` and `results/<TOPIC>/screening/<stage>_sheet.md` (existence only, never a read).
   - Neither exists -> **stop**. Reply that no `<stage>` sheet has been exported yet for this topic and `/prisma-screen export --stage <stage>` must run first. Do not fall back to a different stage's sheet.
2. Proceed to Step 3. (The full-text-exclude-needs-a-reason gate, and every other validation rule, is the skill's job during the actual parse in Step 3 - this command does not re-implement or pre-check row-level content, since that would require reading the sheet itself.)

---

## Step 3: Invoke the `screening-assistant` skill

Call the `Skill` tool naming `screening-assistant`, passing the subcommand and every value Steps 0-2 resolved as its `args` - do not hand-roll the export/import logic inline in this command; the full algorithm lives in `.claude/skills/screening-assistant/01-screening-sheet-workflow.md` and loads from that skill invocation, not from anything re-derived here. Build the call literally, e.g.:

```
Skill(skill: "screening-assistant", args: "export --topic <TOPIC> --stage title_abstract --group-by source")
Skill(skill: "screening-assistant", args: "import --topic <TOPIC> --stage full_text")
```

with `<TOPIC>` substituted for the actual resolved directory name and the flags set to whatever Steps 0-2 actually resolved (including applied defaults) - never the literal placeholder text above. This is the same conversation turn continuing under that skill's instructions: it runs the export or import algorithm entirely inside a `python3` subprocess (per `01-screening-sheet-workflow.md` §3/§9.2) and the ONLY thing that may then enter your reply is that subprocess's printed output - the counts/paths/validation-errors specified in §8 (export) or §9.4/§9.6 (import).

---

## Step 4: What the reply contains - and never contains

1. The reply is the skill's counts-and-paths summary, nothing added on top: total candidates/imported decisions, per-group or include/exclude counts, the file path(s), and the one-line next-step reminder (export) or the "full-text excludes need a reason" note (already covered by the summary itself). Do not restate record content, quote a title/abstract/reason "for context," or summarize what you imagine the sheet contains - only the counts and paths §8/§9.6 actually produced belong in the reply.
2. If the import validation gate (§9.4) refused the whole import, the reply is exactly the offending `record_id` list and reasons that step produced, plus a note that nothing was written. Do not attempt to fix the sheet yourself, do not partially retry, and do not imply any decisions were imported - none were.
3. Never follow up this command by opening the sheet or `records.jsonl` "to double check" the summary. If a count looks wrong, say so and suggest re-running export (a fresh regeneration) rather than inspecting the file directly.

---

## Important rules

1. **Context stays flat.** This command must cost the same context whether the review has 50 records or 5,000 - every rule above exists to guarantee that. The only things that ever reach the conversation are: the parsed-arguments confirmation (Step 0.4), the topic-resolution note (Step 1), a precondition-failure message (Step 1.3/Step 2), and the skill's own counts-and-paths summary (Step 4). Nothing else.
2. **Full-text excludes need a reason - this is enforced by the skill, not bypassed here.** Do not add a competing check in this command that might disagree with `01-screening-sheet-workflow.md` §9.4's exact rule; one place owns that gate.
3. **Idempotent by construction.** Re-running `/prisma-screen import --stage <stage>` on the same sheet, or on a corrected version of it, is always safe - it appends new ledger lines and never rewrites history (see `01-screening-sheet-workflow.md` §1's aggregation rule). Never tell the user they need to delete or reset anything before re-importing.
4. **Never invent a `<TOPIC>` or a stage/group-by default not listed above.** If Step 1 or Step 0 can't resolve one unambiguously, stop and ask - guessing produces a sheet for the wrong review, which is worse than pausing to confirm.
5. **Never overwrite an unimported sheet silently.** Step 2's overwrite guard is not optional busywork - a re-export the reviewer didn't mean to trigger is the one way this command can destroy work that was never this command's to destroy.
