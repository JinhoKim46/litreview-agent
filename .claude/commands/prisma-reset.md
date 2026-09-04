# /prisma-reset - Reset Review State for a Topic

You are resetting part or all of one review's pipeline state under `results/<TOPIC>/` back to a blank slate, so the reviewer can re-run a stage (or the whole pipeline) for that topic.

**This command is destructive.** Nothing is deleted until the user explicitly confirms. Follow these steps exactly in order. Never skip Step 1 (show what will be deleted) or Step 2 (require confirmation), even if `$ARGUMENTS` looks unambiguous.

---

## Step 0: Determine the Topic and the Scope

`$ARGUMENTS` may contain a topic slug, a scope keyword, both, or neither.

### 0.1 Find existing topics

Run `Glob` for `results/*/` to list every existing `results/<TOPIC>/` directory. This repo can hold more than one review at a time, so the topic is never assumed from "there's only one review" — confirm it from what's actually on disk.

### 0.2 Resolve the topic

- If `$ARGUMENTS` contains a token that exactly matches one of the directory names found in 0.1, that is `<TOPIC>`.
- Else, if `$ARGUMENTS` contains a non-scope token that matches **none** of the directory names found in 0.1, do not guess or fall back to "the only one" — report:
  > No review named `<token>` found. Existing topics: `<topic-a>`, `<topic-b>`, ...
and **stop**.
- Else, if no non-scope token was given at all and exactly one `results/<TOPIC>/` directory exists on disk, use it — there is nothing to disambiguate, so do not ask.
- Else, if zero `results/*/` directories exist, tell the user:
  > There is no `results/` data for any topic yet — nothing to reset. Run `/prisma-init "your topic"` to start a review.
and **stop**. Do not continue to Step 1.
- Else (multiple topics exist and none was named), list the topic directories found and ask:
  > **Which review should I reset?** Found: `<topic-a>`, `<topic-b>`, ...
Wait for the user's response before continuing.

### 0.3 Resolve the scope

Check the remaining tokens in `$ARGUMENTS` for a scope keyword:

- `protocol` — deletes only `results/<TOPIC>/protocol.json` and `results/<TOPIC>/search_plan.json`.
- `results` — deletes everything under `results/<TOPIC>/` **except** the `manuscript/` subfolder.
- `all` — deletes the entire `results/<TOPIC>/` folder, including `manuscript/`.

If no recognized scope keyword is present, ask:

> **What would you like to reset for `<TOPIC>`?**
>
> - **`protocol`** — Clears the PICO/PICo/SPIDER record and the per-source search strings (`protocol.json`, `search_plan.json`). Use this to redo scoping or eligibility criteria before searching again. Everything already collected (raw results, records, screening decisions, extraction, synthesis, manuscript) is left in place, but will no longer match the new protocol until you re-run the later stages.
>
> - **`results`** — Clears everything under `results/<TOPIC>/` **except the manuscript**: the protocol (PICO/PICo/SPIDER record, eligibility criteria), search plan, raw connector output, deduped records, screening decisions, extraction table, and synthesis outputs. Use this to redo the review from scratch while keeping a drafted manuscript around for reference. There is no protocol left afterward — `/prisma-init` is the only way back in. The kept manuscript will describe data that no longer exists until you re-run the full pipeline and `/prisma-report` again.
>
> - **`all`** — Deletes the entire `results/<TOPIC>/` folder, manuscript included. Use this to discard the review completely and start `<TOPIC>` over from `/prisma-init`.
>
> Reply with `protocol`, `results`, or `all`.

Wait for the user's response before continuing.

---

## Step 1: Show Exactly What Will Be Deleted

Before touching anything, use `Glob`/`Bash ls -la` to read the real state of `results/<TOPIC>/` and report it. Never rely on the state schema alone — show what is actually on disk right now.

### If scope is `protocol`:

Report the existence and non-trivial content of:

- `results/<TOPIC>/protocol.json`
- `results/<TOPIC>/search_plan.json`

```
## Protocol reset for <TOPIC> will delete:

- protocol.json — [exists, N bytes / does not exist]
- search_plan.json — [exists, N bytes / does not exist]

The following are NOT touched (pipeline output, not protocol data):
  - raw/, records.jsonl, rerun_search.sh, screening/, screening_decisions.jsonl,
    extraction_table.json, synthesis/, manuscript/

Note: rerun_search.sh (if present) was generated from search_plan.json and will
become stale once search_plan.json is deleted — it will still exist but no longer
match the deleted plan. If you are redoing the search itself (not just the
protocol), reset scope `results` instead.
```

If neither file exists, state "Nothing to delete — protocol.json and search_plan.json do not exist for `<TOPIC>`." and skip Step 2; there is nothing to confirm.

### If scope is `results`:

Use `Glob` (`results/<TOPIC>/*` and one level into known subfolders) to list every top-level entry under `results/<TOPIC>/` other than `manuscript/`. Report each with what it holds:

```
## Results reset for <TOPIC> will delete:

- protocol.json — [exists / does not exist]
- search_plan.json — [exists / does not exist]
- rerun_search.sh — [exists / does not exist]
- raw/ — [N files, e.g. openalex-20260310.json, ... / empty / does not exist]
- records.jsonl — [N lines / does not exist]
- screening/ — [files present / empty / does not exist]
- screening_decisions.jsonl — [N lines / does not exist]
- extraction_table.json — [exists / does not exist]
- synthesis/ — [files present, e.g. effect_sizes.json, forest_plot.svg, ... / empty / does not exist]
- <other entries found> — [any file or folder present under results/<TOPIC>/, other
  than manuscript/, not already listed above — list each by name; this schema can
  drift, so trust what Glob actually found, not just this fixed list]

The following is NOT touched:
  - manuscript/ — [files present, e.g. manuscript.md, flow_diagram.svg / empty / does not exist]

Note: manuscript/ is preserved but will describe data that no longer exists after
this reset. Its numbers (flow diagram counts, references, forest plot) will be
stale until you re-run the pipeline and `/prisma-report` again.
```

If `results/<TOPIC>/` contains nothing but an empty `manuscript/` (or is otherwise already empty outside `manuscript/`), state "Nothing to delete — `results/<TOPIC>/` has no pipeline output outside `manuscript/`." and skip Step 2.

### If scope is `all`:

Use `Glob` (`results/<TOPIC>/**`) to list everything under the topic folder, including `manuscript/`. Report it in full:

```
## Full reset for <TOPIC> will delete:

results/<TOPIC>/ and everything inside it:
  - protocol.json — [exists / does not exist]
  - search_plan.json — [exists / does not exist]
  - rerun_search.sh — [exists / does not exist]
  - raw/ — [N files / empty / does not exist]
  - records.jsonl — [N lines / does not exist]
  - screening/ — [files present / empty / does not exist]
  - screening_decisions.jsonl — [N lines / does not exist]
  - extraction_table.json — [exists / does not exist]
  - synthesis/ — [files present / empty / does not exist]
  - manuscript/ — [files present, e.g. manuscript.md, flow_diagram.svg,
    checklist_audit.md, references.md / empty / does not exist]
  - <other entries found> — [any other file or folder present under
    results/<TOPIC>/ not already listed above — list each by name; this schema can
    drift, so trust what Glob actually found, not just this fixed list]

This removes every trace of the "<TOPIC>" review. Other topics under results/ are
not affected.
```

If `results/<TOPIC>/` does not exist or is completely empty, state "Nothing to delete — `results/<TOPIC>/` is already empty or does not exist." and skip Step 2.

---

## Step 2: Require Explicit Confirmation

Present the confirmation prompt, naming the topic and scope so a misread topic is caught here rather than after deletion:

> **This cannot be undone.** This will permanently delete the `<scope>`-scope data shown above for `<TOPIC>`.
>
> Type **`RESET`** (all caps) to confirm, or anything else to cancel.

Wait for the user's response.

- If the user types exactly `RESET`: proceed to Step 3.
- If the user types anything else: abort and tell them "Reset cancelled. Nothing was changed."

---

## Step 3: Execute the Reset

Use the `<TOPIC>` resolved in Step 0. Never substitute a glob or wildcard for `<TOPIC>` in these commands — only the exact, confirmed directory name.

### Scope `protocol`:

```bash
rm -f "results/<TOPIC>/protocol.json"
rm -f "results/<TOPIC>/search_plan.json"
```

### Scope `results`:

Delete every top-level entry under the topic folder except `manuscript/`:

```bash
find "results/<TOPIC>/" -mindepth 1 -maxdepth 1 ! -name manuscript -exec rm -rf {} +
```

### Scope `all`:

```bash
rm -rf "results/<TOPIC>/"
```

After running the command, verify it did what was intended: re-`Glob` the paths that were supposed to be gone and confirm they no longer exist (and, for `protocol` and `results` scope, that `manuscript/` — if it existed — is still there untouched).

---

## Step 4: Confirm What Was Done and Next Steps

After the reset is complete, report:

```
## Reset complete for <TOPIC> (scope: <scope>)

### Deleted
[List each file/folder that was actually removed]

### Preserved
[List anything intentionally left in place — e.g. manuscript/, other topics]
```

Then tell the user what to do next based on scope:

**If scope was `protocol`:**
> The protocol is cleared for `<TOPIC>`. Run `/prisma-init "<TOPIC>"` to redo scoping, PICO/PICo/SPIDER, and keyword expansion. Everything collected under the old protocol (raw results, records, screening, extraction, synthesis, manuscript) is still on disk but will no longer match the new protocol until you re-run `/prisma-search` onward.

**If scope was `results`:**
> All pipeline output for `<TOPIC>` is cleared except the manuscript, including the protocol — there is no `search_plan.json` left for `/prisma-search` to read. Run `/prisma-init "<TOPIC>"` to redo scoping and keyword expansion, then move through `/prisma-search` onward as usual. Re-run `/prisma-report` once the pipeline finishes to bring the manuscript back in sync.

**If scope was `all`:**
> `<TOPIC>` has been fully removed from `results/`. Run `/prisma-init "<TOPIC>"` to start that review over from scratch, or pick a different topic name if you meant to start something new.
