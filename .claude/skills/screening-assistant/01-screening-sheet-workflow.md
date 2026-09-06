---
framework_version: 1.2.0
---

# Screening Sheet Workflow

Exact algorithms, file formats, and parsing rules for `/prisma-screen export` and `/prisma-screen import`. `SKILL.md` is the trigger/entry point; this file is what you actually follow step by step. Every snippet below is stdlib-only Python (`json`, `csv`, `sys`, `pathlib`, `datetime`) run via `python3` - no new dependency, nothing that needs `requirements.txt` touched.

All paths below are relative to the repo root and use `<TOPIC>` for the review's slug (the same one `protocol.json` etc. live under in `results/<TOPIC>/`).

---

## 1. Data contracts this workflow depends on

### `results/<TOPIC>/records.jsonl` (input, read-only here)

One JSON object per line, one line per **distinct study** (duplicates are marked, never removed - see architecture plan §2). This workflow reads these fields; it does not write this file:

```json
{"record_id": "openalex:W123456789", "title": "...", "authors": ["Kim S", "Park J"],
 "year": 2022, "venue": "...", "doi": "10.1234/abcd", "abstract": "...",
 "url": "https://...", "source": "openalex", "duplicate_of": null}
```

`record_id` is whatever stable string `/prisma-search`'s dedup step assigned - this workflow never re-derives, renumbers, or reformats it, only round-trips it verbatim. **Contract this workflow requires and `/prisma-search` must honor:** `record_id` contains no whitespace (the Markdown fallback parser in §9.3 splits on it). `duplicate_of` is `null` for a canonical record and the canonical record's `record_id` for a duplicate; duplicates are **excluded from screening entirely** (they were never really two studies). Missing optional fields (`doi`, `venue`) are `null`, not absent keys - treat absence the same as `null`.

### `results/<TOPIC>/screening_decisions.jsonl` (append-only, this workflow's ledger)

One JSON object per **decision event** (not per record - a record can appear multiple times if corrected):

```json
{"record_id": "openalex:W123456789", "stage": "title_abstract", "decision": "include",
 "reason": null, "ai_suggestion": "include", "decided_at": "2026-09-04T14:03:11Z",
 "by": null, "role": "decision", "eligibility_version": null,
 "prev_hash": "3f2a…", "entry_hash": "9c1b…"}
```

- `stage`: `"title_abstract"` or `"full_text"`.
- `decision`: `"include"` or `"exclude"` at either stage; **`"not_retrieved"` is additionally valid at `stage == "full_text"` only** (a report that was sought but genuinely could not be obtained — PRISMA 2020's own "Reports not retrieved" box). Never any other value.
- `reason`: optional in general — `null` when left blank — but **required**, non-empty, human-written text when `stage == "full_text"` and `decision` is `"exclude"` **or** `"not_retrieved"` (PRISMA Item 16b covers both: why it was excluded, or why it couldn't be retrieved, are equally reportable). A reviewer may also write one at title/abstract stage (e.g. to record which gate failed, per `review-protocol/02-eligibility-criteria.md`) — that's welcomed, never required.
- `ai_suggestion`: `"include"`, `"exclude"`, `"unclear"`, or `null` if no suggestion was computed for this record (e.g. no `protocol.json` yet). Recorded for later human/AI agreement analysis - it is never itself a decision.
- `decided_at`: ISO 8601 UTC, generated at import time, never backdated or guessed.
- `by`, `role`, `eligibility_version`, `prev_hash`, `entry_hash`: written by `tools/ledger.py`'s `append_decisions` (§9.5), never hand-authored. `by` names who/what recorded the line (`null` if not tracked yet); `role` is `"decision"` for every line this skill writes today (a future dual-screening `"verification"` role is reserved but not produced here); `eligibility_version` pins the `protocol.json` eligibility version in effect at import time when tracked, else `null`; `prev_hash`/`entry_hash` hash-chain this line to the one before it (`tools/ledger.py verify` walks the chain) - never edit or reorder existing lines, that breaks the chain from that point forward.

**Aggregation rule (used by every reader of this file, including this workflow's own export step):** group lines by `(record_id, stage)`, keep only the **last line in file order** for each key - not the line with the latest `decided_at`. This is an append-only log; file position *is* chronological truth, and it has no resolution limit. `decided_at` is informational metadata for humans/audits, never the aggregation key: an import writes one shared timestamp for every row it appends (§9.5), so two corrections landing in the same import, or two imports within the same second, would tie on `decided_at` - file order never ties. Never average, count, or otherwise combine multiple lines for the same key.

### `results/<TOPIC>/protocol.json` (optional input, for `ai_suggestion` only)

Written by `/prisma-init` via the `review-protocol` skill. This workflow reads `protocol.json.eligibility_criteria` if present (an array of `{"criterion": "...", "gate": "population|design|publication_type|date|language|other"}` objects) purely to generate the advisory `ai_suggestion`. If `protocol.json` doesn't exist yet, or has no `eligibility_criteria`, every `ai_suggestion` is `null` - export still works, it just has nothing to suggest against. **Never block export on a missing protocol.**

### `results/<TOPIC>/possible_duplicates.jsonl` (optional input, informational only)

Written by `/prisma-search`'s fuzzy-dedup pass (title-similarity check within same-year canonical records that didn't already match on doi/pmid/title-author-year - see that command's Step 7b). One JSON object per line:

```json
{"record_id_a": "openalex:W123", "record_id_b": "crossref:10.1234/xyz", "similarity": 0.93, "detected_at": "2026-09-04T12:00:00Z"}
```

If this file exists, load it and build a `record_id -> [(other_id, similarity), ...]` lookup (a record can appear as either `record_id_a` or `record_id_b`). Export then adds one `**Possible duplicate of:** <other_id> (similarity 0.93)` line under any flagged record's `**Link:**` line in both the CSV (`possible_duplicate` column) and Markdown template (§7). **This is advisory only** - never auto-exclude or auto-merge a flagged record; the reviewer decides during screening exactly like any other record. If the file doesn't exist, every record's `possible_duplicate` is empty/absent - export still works.

---

## 2. Stage progression rule

- **`title_abstract` candidates:** every non-duplicate record in `records.jsonl` with no `title_abstract` decision in the aggregated ledger yet.
- **`full_text` candidates:** every non-duplicate record whose aggregated `title_abstract` decision is `include`, **and** that has no `full_text` decision yet. A record excluded at title/abstract never appears in a full-text sheet - it's already done.

If the candidate set is empty, say so plainly (`"0 undecided <stage> records - nothing to export"`) and stop. Don't write empty files.

---

## 3. Export algorithm

**Context-flatness rule:** every step below happens *inside* a `python3` subprocess run via `Bash(python3:*)` - never via the `Read` tool. `Read`ing `records.jsonl` or a sheet file defeats the whole point of this skill the moment a review has thousands of records; the subprocess prints only what §8/§9.6 specify (counts, paths, validation errors), and that printed output is all that ever enters the conversation.

Everything mechanical here - reading `records.jsonl`/`screening_decisions.jsonl`/`possible_duplicates.jsonl`, the stage-progression filter, grouping, sorting, abstract truncation, and writing the CSV/MD twin - is done by the committed `tools/build_screening_sheet.py`, **not** hand-authored inline. A fresh inline re-implementation of row-critical logic every single export run is exactly the kind of unreviewed, untested code that produces row/column misalignment on a bad day; one tested script removes that risk entirely for the parts that are genuinely mechanical.

1. Compute `ai_suggestion`/`ai_rationale` for each undecided candidate per §4 (read `protocol.json.eligibility_criteria` if present; every candidate gets `none`/`no eligibility criteria yet` if it's absent). Write these judgments to a scratch file `results/<TOPIC>/screening/_suggestions.jsonl`, one line per candidate: `{"record_id": "...", "ai_suggestion": "include|exclude|unclear", "ai_rationale": "..."}`. This is the one step that stays a Claude-authored judgment call - it's protocol-specific and can't be a generic committed script.
2. Pick the keyword taxonomy for this review's PICO/PICo/SPIDER concepts per §4a (adapt the term list to the actual review, never reuse a hardcoded imaging-specific list).
3. Run, via `Bash(python3:*)`:
   ```bash
   python3 tools/build_screening_sheet.py \
     --topic-dir results/<TOPIC> \
     --stage <title_abstract|full_text> \
     --group-by <theme|source|year|ai_suggestion> \
     --suggestions results/<TOPIC>/screening/_suggestions.jsonl \
     --taxonomy <comma,separated,terms>
   ```
   Omit `--suggestions` only if `protocol.json` has no eligibility criteria yet (every candidate then renders `ai_suggestion: none` per §4, which is the script's default with no `--suggestions` given). Omit `--taxonomy` only if the review has no keyword taxonomy to check yet.
4. The script writes both files itself:
   - `results/<TOPIC>/screening/<stage>_sheet.md`
   - `results/<TOPIC>/screening/<stage>_sheet.csv`
   and prints the §8 export summary as its stdout.
5. Reply with **only** that printed summary - never the sheet content, and never re-derive or restate it yourself.

---

## 4. AI suggestion (advisory only, never a decision)

For each candidate, if `protocol.json.eligibility_criteria` exists, read the record's title + abstract against each criterion the way `review-protocol/02-eligibility-criteria.md` describes (hard pass/fail gates) and classify:

- **`include`** - nothing in the title/abstract trips a hard-fail gate, and the topic plausibly matches the review's scope.
- **`exclude`** - a gate is clearly tripped from the title/abstract alone (wrong population, wrong study design stated outright, wrong publication type, out-of-range date/language when that's a stated criterion).
- **`unclear`** - the abstract doesn't give enough information to call it either way (the correct answer for most borderline records - PRISMA's title/abstract stage is meant to be inclusive; when genuinely unsure, don't suggest `exclude`).

Write a one-line rationale alongside the label (e.g. `"exclude — animal study, protocol requires human subjects"`). This rationale goes into the sheet for the human to read; only the label (`include`/`exclude`/`unclear`) is what gets persisted to `screening_decisions.jsonl.ai_suggestion` on import. **The suggestion never fills in the DECISION field itself** - it's a column/line the reviewer can glance at and override freely, exactly like the quick fit assessment in job-scraper's Step 3. Write each candidate's label + rationale to `results/<TOPIC>/screening/_suggestions.jsonl` (§3 step 1) for `tools/build_screening_sheet.py` to merge in by `record_id`.

**No `protocol.json` / no `eligibility_criteria`:** render the label as the literal string `none` and the rationale as `no eligibility criteria yet`. §7's templates always show both fields with these literals rather than leaving them blank, so a reviewer or the §9.3 parser never has to distinguish "empty" from "not computed". On import, the label `none` maps back to `ai_suggestion: null` in the ledger (§1) - it is never stored as the string `"none"`. `tools/build_screening_sheet.py` renders this same `none`/`no eligibility criteria yet` default automatically whenever `--suggestions` is omitted, or a specific candidate has no entry in that file.

---

## 4a. Keyword tagging and corpus overview (advisory only, never a decision or a finding)

Two additional pieces of advisory output, both computed the same way as `ai_suggestion` - case-insensitive substring matching against a **fixed keyword taxonomy**, run inside the same export subprocess, never an LLM re-reading each abstract. This is a deliberate choice, not a shortcut taken for lack of a better option: matching every one of a review's candidate abstracts with real semantic judgment would mean reading all of them back into the conversation, which is exactly the context-blowup this skill's "one rule" exists to prevent. A keyword match is honest about being a keyword match - it never claims to report a study's actual finding (a specific result value), only which topics/metrics/methods the title or abstract *mentions*. Never let `ai_keywords` or the corpus overview be read by a reviewer (or by `/prisma-report` later) as a substitute for `/prisma-extract`'s actual data extraction from full text.

Both the per-record match and the corpus overview are computed by `tools/build_screening_sheet.py` from the `--taxonomy` list Claude passes in (§3 step 2/3) - Claude picks the terms, the script does the substring matching and counting.

**Per-record `ai_keywords`:** maintain a small taxonomy of terms relevant to the review's domain (method-family terms and outcome/metric terms - for an imaging/reconstruction review, e.g. `cnn`, `gan`, `u-net`, `transformer`, `diffusion`, `unrolled`, `self-supervised`, `ssim`, `psnr`, `diagnostic accuracy`, `reader study`, `scan time`, `acceleration factor`; adapt the list to the review's actual PICO/PICo/SPIDER concepts rather than hardcoding an imaging-specific list for every topic). For each candidate, `ai_keywords` is the comma-joined list of taxonomy terms found (case-insensitive substring match) in `title + " " + abstract`, in taxonomy order, deduplicated. Empty string if none matched - never fabricate a keyword that isn't a literal substring match.

**Corpus overview (export-time only, printed as part of §8's summary, never written into the sheet itself):** across all candidates being exported this run, count how many records matched each taxonomy term, and report the top terms by frequency (e.g. top 10) as a `term: count` list. This is a frequency count over already-computed `ai_keywords` matches - it costs nothing extra to compute and never requires reading any record's raw text back into the conversation, only the counts. Do not editorialize the counts into a prose "finding" ("this shows GANs are becoming more popular") - report the counts and let the reviewer draw conclusions; a claim like that would need actual publication-year trend analysis and citation, not a hunch from one export's keyword tally.

---

## 5. Grouping and sorting

- **`--group-by source`** (default): one group per `source` value (`openalex`, `pubmed`, ...). Always available since every connector's output shape guarantees `source`.
- **`--group-by year`**: one group per `year` value, records with `year: null` collected into a trailing `"Year unknown"` group.
- **`--group-by theme`**: one group per `theme` field **if the record carries one** (records don't get a `theme` by default - nothing in the pipeline before this stage assigns it; a reviewer or a later `/prisma-extract` pass may tag one manually). If **no** candidate has a `theme` field, don't fabricate groups: emit a single group named `"Ungrouped (no theme tags yet)"` holding everything, and say so in the export summary so the reviewer knows `--group-by theme` had nothing to key on this run rather than silently behaving like `--group-by source`.
- **`--group-by ai_suggestion`**: one group per `ai_suggestion` label computed in §4 (`include`, `exclude`, `unclear`, `none`). Lets a reviewer triage the easy `include`/`exclude` calls first and spend their attention on the `unclear` group. Group order is fixed as `include, exclude, unclear, none` (not alphabetical - alphabetical order would scatter the one group reviewers most want to see last, `unclear`, in the middle) and is never reordered even when a label has zero records that run (just omit the empty group rather than showing a "(0 records)" heading).

Group order (all other modes): alphabetical by group name, except the `theme` fallback group and the `year` unknown group always sort last.

---

## 6. Abstract truncation

Truncate to 500 characters at a word boundary (never mid-word), then append `"… [truncated, N chars remaining]"` where N is `len()` of what was cut. Report characters, not a `str.split()` word count — a space-free CJK abstract (plausible given the Korea-scoped review case in `protocol.json.scope`) would otherwise report "1 words remaining" regardless of how much text was actually cut. A record with no abstract (`null` or empty string) gets `"(no abstract available)"` instead of a truncation marker.

```python
def truncate_abstract(abstract, limit=500):
    if not abstract:
        return "(no abstract available)"
    if len(abstract) <= limit:
        return abstract
    cut = abstract[:limit].rsplit(" ", 1)[0]
    remaining_chars = len(abstract) - len(cut)
    return f"{cut}… [truncated, {remaining_chars} chars remaining]"
```

---

## 7. Sheet formats

### CSV (`<stage>_sheet.csv`) - the preferred edit target

Exact header, in this order (edit columns first so a reviewer in a spreadsheet doesn't have to scroll):

```
record_id,decision,reason,ai_suggestion,ai_rationale,ai_keywords,title,year,authors,source,doi,url,abstract_truncated,possible_duplicate
```

`possible_duplicate` is empty unless `possible_duplicates.jsonl` flagged this record, in which case it holds `"<other_id> (similarity 0.93)"` - read-only/advisory, import never looks at this column.

- `decision` and `reason` start **empty** - the reviewer fills them in. `decision` accepts `include` or `exclude` (case-insensitive; normalized to lowercase on import); at full-text stage, `not_retrieved` is also accepted (a report sought but genuinely unobtainable - not representable via the Markdown checkbox template in §7, CSV only). `reason` is optional except for a full-text `exclude` or `not_retrieved`.
- `ai_suggestion` / `ai_rationale` / `ai_keywords` are pre-filled, read-only in spirit (the reviewer can ignore them; they're not re-derived, checked against, or written to `screening_decisions.jsonl` on import - `ai_keywords` is a sheet-only convenience column, never part of the ledger schema in §1).
- `authors` is `; `-joined so a single CSV field survives round-tripping through a spreadsheet app without being split into extra columns.

Write with the stdlib `csv` module (`csv.DictWriter`, `quoting=csv.QUOTE_MINIMAL`) so commas/quotes inside titles and abstracts are escaped correctly - never hand-join columns with a plain `join(",")`, that breaks the instant an abstract contains a comma. `tools/build_screening_sheet.py` already does this; nothing here needs re-implementing.

### Markdown (`<stage>_sheet.md`) - fallback edit target, and a readable companion

```markdown
# Title/Abstract Screening — <TOPIC>

45 undecided records, grouped by source. Fill in exactly one checkbox per record; add a
REASON line for any full-text exclude.

## Group: openalex (28 records)

#### openalex:W123456789 — Effects of X on Y in adults (2022)
- **Authors:** Kim S; Park J
- **Source:** openalex | **DOI:** 10.1234/abcd | **Year:** 2022
- **Link:** https://doi.org/10.1234/abcd
- **Possible duplicate of:** crossref:10.9999/wxyz (similarity 0.93) — *only shown when flagged; advisory, does not affect screening*
- **AI suggestion:** include — plausible population/design match, no gate tripped
- **Keywords:** cnn, ssim, image quality *(omitted when no taxonomy term matched; a keyword-match tag, not a reported finding)*
- **Abstract (truncated to 500 chars):** Background: ... [truncated, 612 chars remaining]

- [ ] Include
- [ ] Exclude
REASON:

---

#### crossref:10.5678/efgh — A different study (2021)
...
```

One `---` horizontal rule between record blocks, one `## Group: <name> (<n> records)` heading per group. The two checkboxes are always emitted unchecked; the reviewer checks exactly one. `REASON:` is always emitted (even at title/abstract stage, where it's optional) so the format is identical across stages and a reviewer never has to remember which stage needs which line.

---

## 8. Export summary (the only thing that reaches the conversation)

This block is literally `tools/build_screening_sheet.py`'s stdout - relay it verbatim (§3 step 5), don't restate or re-derive it.

```
Exported 45 undecided title_abstract records for <TOPIC>, grouped by source:
  openalex: 28
  crossref: 12
  pubmed: 5

AI suggestion breakdown: include 19, exclude 14, unclear 12, none 0

Corpus keyword overview (top matches across these 45 records):
  deep learning: 31, cnn: 18, ssim: 15, gan: 9, diagnostic accuracy: 7, unrolled: 4

Files:
  results/<TOPIC>/screening/title_abstract_sheet.csv  (preferred - edit this one)
  results/<TOPIC>/screening/title_abstract_sheet.md

Edit the decision/reason columns (or checkboxes in the .md), then run
`/prisma-screen import --stage title_abstract`. Full-text excludes will need a reason.
```

Adjust counts/grouping line/paths to match the actual run; if `--group-by theme` fell back per §5, replace the "grouped by ..." line with a note that no theme tags were found. The "AI suggestion breakdown" line is always shown regardless of `--group-by` value (it's an independent count, not tied to the grouping choice). The "Corpus keyword overview" line is omitted only if `protocol.json` has no eligibility criteria to derive a taxonomy from (matches §4's `none`/no-protocol case) - state that plainly rather than printing an empty list.

---

## 9. Import algorithm

### 9.1 Locate the sheet

Prefer `<stage>_sheet.csv`. Use it if it exists and has at least one non-empty `decision` value. Otherwise fall back to `<stage>_sheet.md`, parsed per §9.3. If neither file exists, refuse with a clear message naming the expected path - don't guess a different stage or topic.

### 9.2 CSV parsing

Same context-flatness rule as export (§3): parse inside the `python3` subprocess, never `Read` the sheet file. The subprocess's only output is the §9.4 validation-error list (if any) and the §9.6 summary counts - never the rows themselves.

```python
import csv, pathlib

rows = list(csv.DictReader((topic_dir / "screening" / f"{stage}_sheet.csv").open(newline="")))
```

For each row: `decision = (row["decision"] or "").strip().lower()`. `ai_suggestion = row["ai_suggestion"] or None`, with the literal `none` (§4) also mapped to `None`. Skip the row entirely (no error, just count it as still-undecided) if `decision` is empty. Valid values are `"include"` or `"exclude"` at either stage, plus `"not_retrieved"` at full-text stage only. If `decision` is anything else, or is `"not_retrieved"` at `title_abstract` stage, that row **fails validation** (§9.4) - list it by `record_id` with the literal bad value, don't silently coerce a typo.

### 9.3 Markdown fallback parsing

Split the file on `^#### ` (one chunk per record block). For each chunk:

1. First line's text before the em dash is unused for parsing (display only); the `record_id` is the token immediately after `#### `.
2. Find both checkbox lines with a regex: `^- \[([ xX])\] (Include|Exclude)$`.
3. Exactly one may be checked (`x`/`X`):
   - Neither checked → still-undecided, skip (no error).
   - Both checked → **validation failure** for this record: "both Include and Exclude checked" - list it, don't guess.
   - Exactly one checked → that word, lowercased, is `decision`.
4. `REASON:` line (may be empty) → `reason` = trimmed text after the colon, or `None` if blank.
5. `ai_suggestion` for the ledger comes from parsing the `**AI suggestion:** <label> —` line in that same block, taking only the leading label word. Map the literal `none` (§4's no-protocol rendering) to `null`; any of `include`/`exclude`/`unclear` is stored as-is.

### 9.4 Validation gate — refuse the whole import, never partial

Before writing **anything**, check every parsed decided row - the same rule `tools/ledger.py`'s `gate` command enforces before `/prisma-extract` runs, checked here too so a bad import is caught at the source rather than only discovered later:

> `stage == "full_text" and decision in ("exclude", "not_retrieved") and not (reason and reason.strip())`

If any row trips this, or any row has an invalid `decision` token (§9.2/§9.3 step 3), the **entire import is refused** - zero lines get appended, even for the rows that were fine. Report exactly which `record_id`s are the problem and why, e.g.:

```
Import refused: 2 rows need fixing before I can import any of this sheet.
  - openalex:W123456789: full-text exclude has no reason (PRISMA Item 16b requires one)
  - crossref:10.5678/efgh: decision is "excldue" - not "include" or "exclude"

Fix these rows in results/<TOPIC>/screening/full_text_sheet.csv and re-run
/prisma-screen import --stage full_text. Nothing was written.
```

Why whole-file refusal rather than best-effort partial import: a half-imported sheet leaves the reviewer unsure which rows landed, and re-editing then re-importing the same file is exactly the corrected-sheet case §1's aggregation rule already handles cleanly - there's no benefit to partial writes and a real risk of a silently-incomplete ledger.

### 9.5 Write decisions

For every row that passed validation and had a non-empty decision, call `tools/ledger.py`'s `append_decisions` - never hand-build the JSON lines. This is what adds `prev_hash`/`entry_hash` (§1) correctly, chained onto whatever is already in the ledger:

```python
import sys
from datetime import datetime, timezone
sys.path.insert(0, ".")  # repo root, so "tools" is importable
from tools.ledger import append_decisions

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
rows = [
    {
        "record_id": row["record_id"],
        "stage": stage,
        "decision": row["decision"],
        "reason": row.get("reason") or None,
        "ai_suggestion": row.get("ai_suggestion"),
        "decided_at": now,
    }
    for row in decided_rows
]
append_decisions(topic_dir, rows)
```

`append_decisions` fills in `by: null`, `role: "decision"`, `eligibility_version: null` when the row doesn't set them (§1) - always **appends**, never reads-modifies-rewrites the ledger. This is what makes re-importing a corrected sheet safe: the old line is still there, but §1's last-line-in-file-order aggregation means every downstream reader sees only the correction. Run `python3 tools/ledger.py --topic <TOPIC> verify` after a bulk import if you want to confirm the chain is intact - not required on every import, but a good check after hand-editing the ledger file directly (which this skill's own workflow never does, but a reviewer might).

### 9.6 Import summary (the only thing that reaches the conversation)

```
Imported 43 decisions for <TOPIC> title_abstract (31 include, 12 exclude).
2 records left undecided (blank decision) - re-export if you want them back on a sheet.

Ledger: results/<TOPIC>/screening_decisions.jsonl
```

Never quote a `reason` or `abstract` back into the reply - counts and the path only.

---

## 10. Edge cases checklist

- **Re-importing an unchanged sheet** appends duplicate-content lines; harmless by design (§1's aggregation just keeps re-confirming the same latest decision). Don't try to detect and skip "no-op" imports - that's complexity the append-only ledger doesn't need.
- **A record disappears from `records.jsonl` between export and import** (shouldn't happen since records are append-only, but if a hand-edit removed one): still import its decision if the sheet has one - the ledger doesn't require the record to currently exist, and `/prisma-status` is where an orphaned decision would surface, not here.
- **Reviewer edits `title`/`abstract`/other read-only columns in the CSV:** ignored on import - only `decision`, `reason`, and the record_id-to-row mapping are read back. Never write corrected metadata into `records.jsonl` from a screening sheet; that's a different file with a different owner.
- **Empty `screening_decisions.jsonl` or missing file on import:** treat as "0 prior decisions", create the file on first append. Same treatment on export's aggregation step.
- **`--stage full_text` requested before any `title_abstract` includes exist:** candidate set is empty (§2); say so and stop, don't fall back to title_abstract.
