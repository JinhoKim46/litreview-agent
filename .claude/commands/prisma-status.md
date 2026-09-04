---
allowed-tools: Read, Glob, Bash(python3:*)
---

# /prisma-status - Report Pipeline Progress and the Next Command to Run

You are answering one question: **for a given review, exactly what has this pipeline
already done, and what should the reviewer run next?** This is the resumability
mechanism the whole framework depends on — every state file under `results/<TOPIC>/` is
append-only or fully re-derivable (architecture plan §2) specifically so that closing a
laptop mid-screening for weeks and running `/prisma-status <TOPIC>` reconstructs exactly
where things stand, with no number ever hand-typed or recalled from memory.

`$ARGUMENTS` is the topic name (or an already-slugged folder name). With no argument,
list every review under `results/` with a one-line status each.

**Never open `records.jsonl` or `screening_decisions.jsonl` with the `Read` tool** — the
same context-flatness discipline `screening-assistant` and `/prisma-report` enforce
applies here: a review with 5,000 records must cost the same context as one with 50. All
counts in this command come from the single `python3` subprocess in Step 3, whose stdout
is a compact report, never the raw ledgers. `protocol.json`, `search_plan.json`, and
`extraction_table.json`/`synthesis/*.json` are small and structured enough that the
script reads them directly, but they are still read *inside* the subprocess, never with
the `Read` tool, so this command has exactly one place that touches disk.

Follow the steps below **in order**. Do not skip a step.

---

## Step 0: Parse `$ARGUMENTS` and Determine Mode

1. Trim leading/trailing whitespace from `$ARGUMENTS`.
2. **Empty after trimming → list-all mode.** Skip Step 2 (topic resolution) entirely and
   go straight to Step 1, then Step 3's list-all invocation.
3. **Non-empty → single-topic mode.** Hold the trimmed string as `<TOPIC_HINT>` for Step 2.

---

## Step 1: Discover Existing Reviews

Run `Glob` for `results/*/` to list every existing review directory. Do this
unconditionally, in both modes — list-all mode needs the full set, and single-topic mode
needs it to resolve `<TOPIC_HINT>` against real directories rather than guessing a slug
that was never actually created.

- **Zero directories found:**
  - List-all mode: reply `No reviews found under results/. Run /prisma-init "<topic>" to
    start one.` and stop — there is nothing further to compute.
  - Single-topic mode: reply `No reviews found under results/. Run /prisma-init
    "<TOPIC_HINT>" to start this one.` and stop.
- **One or more directories found:** continue. List-all mode skips straight to Step 3;
  single-topic mode continues to Step 2.

---

## Step 2: Resolve `<TOPIC>` (single-topic mode only)

`<TOPIC_HINT>` may be free text (`"AI in Korean Elder Care"`), an already-slugged folder
name (`ai-in-korean-elder-care`), or something close but not exact. Resolve it against the
directories from Step 1 in this order, stopping at the first that yields a match:

1. **Exact match** — `<TOPIC_HINT>` equals a directory name exactly.
2. **Slug match** — derive a slug from `<TOPIC_HINT>` using the exact rule
   `/prisma-init` Step 0 uses (lowercase, trim whitespace, replace every run of
   characters that are not `[a-z0-9]` with a single hyphen, strip leading/trailing
   hyphens, cap at 60 characters) and match that slug against the directory names.
3. **Fuzzy match** — case-insensitive, with spaces/hyphens/underscores collapsed to
   nothing on both sides (`"korean elder care"` ~ `korean-elder-care`), match
   `<TOPIC_HINT>` against every directory name.

Then:

- **Zero matches:** stop. Reply `No review matching "<TOPIC_HINT>" found under results/.
  Existing topics: <list>. Run /prisma-init "<TOPIC_HINT>" to start a new one.`
- **Exactly one match:** use it as `<TOPIC>`. If it came from the slug or fuzzy path
  (not an exact match), say which folder you resolved to (e.g. `"Using
  results/korean-elder-care/ for 'Korean Elder Care'"`) so the reviewer can redirect you
  if it's wrong.
- **More than one match:** stop. List the matching topics and ask which one is meant —
  never guess among several active reviews.

---

## Step 3: Run the Status Computation

Run the report script via `Bash`. **List-all mode** passes no extra argument; **single-topic
mode** passes the resolved `<TOPIC>` directory name (not a full path, not the original
free-text hint) as the sole argument. Both modes run the exact same script — the branch is
inside `main()`.

```bash
python3 - <TOPIC> <<'PY'
import json, glob, os, sys
from pathlib import Path

RESULTS = Path("results")


def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def as_list(x, list_key="studies"):
    """extraction_table.json has been written under two different top-level shapes
    in this repo's history (a bare JSON array, and {"studies": [...]}) -- accept
    either rather than assuming one. The synthesis/*.json files are always bare
    lists (one entry per outcome group), which this also handles correctly."""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        if isinstance(x.get(list_key), list):
            return x[list_key]
        return list(x.values())
    return []


def study_id(study):
    return study.get("record_id") or study.get("study_id") or study.get("author_year") or "UNKNOWN_STUDY"


def latest_raw_meta(topic):
    """Most recent dated raw/<source>-<YYYYMMDD>.json per source -- lexicographic
    filename sort means the last write per source wins, same rule /prisma-report
    Step 3/Step 8 use."""
    latest = {}
    for p in sorted(glob.glob(str(topic / "raw" / "*.json"))):
        source = os.path.basename(p).rsplit("-", 1)[0]
        latest[source] = p
    per_source = {}
    for s, p in latest.items():
        data = load_json(Path(p))
        meta = (data or {}).get("meta") if isinstance(data, dict) else None
        if not meta:
            continue
        per_source[s] = {
            "retrieved": meta.get("retrieved", 0),
            "total_available": meta.get("total_available"),
            "truncated": bool(meta.get("truncated", False)),
        }
    return per_source


def compute(topic_dir):
    protocol = load_json(topic_dir / "protocol.json")
    search_plan = load_json(topic_dir / "search_plan.json")

    per_source = latest_raw_meta(topic_dir)
    truncated_sources = sorted(s for s, v in per_source.items() if v["truncated"])
    identified_total = sum(v["retrieved"] for v in per_source.values())

    records = load_jsonl(topic_dir / "records.jsonl")
    duplicates_removed = sum(1 for r in records if r.get("duplicate_of"))
    canonical = [r for r in records if not r.get("duplicate_of")]
    canonical_ids = {r["record_id"] for r in canonical}
    records_screened = len(canonical)

    decisions = load_jsonl(topic_dir / "screening_decisions.jsonl")
    latest = {}
    for d in decisions:  # append-only file -> last line in file order wins
        latest[(d["record_id"], d["stage"])] = d

    ta = {rid: d for (rid, stage), d in latest.items() if stage == "title_abstract"}
    orphaned_ta = sorted(rid for rid in ta if rid not in canonical_ids)
    excluded_ta = sum(1 for d in ta.values() if d["decision"] == "exclude")
    ft_candidates = {rid for rid, d in ta.items() if d["decision"] == "include"}
    sought_for_retrieval = len(ft_candidates)
    undecided_ta = len(canonical_ids - set(ta.keys()))

    ft = {rid: d for (rid, stage), d in latest.items() if stage == "full_text"}
    orphaned_ft = sorted(rid for rid in ft if rid not in ft_candidates)
    assessed_for_eligibility = len(ft)
    pending_full_text = len(ft_candidates - set(ft.keys()))
    excluded_ft = [d for d in ft.values() if d["decision"] == "exclude"]
    included_final = sum(1 for d in ft.values() if d["decision"] == "include")
    missing_reason = sorted(d["record_id"] for d in excluded_ft if not (d.get("reason") or "").strip())

    extraction = as_list(load_json(topic_dir / "extraction_table.json"))
    extracted_count = len(extraction)
    extracted_ids = {study_id(s) for s in extraction}
    unextracted_included = sorted(rid for rid in ft if ft[rid]["decision"] == "include" and rid not in extracted_ids)

    heterogeneity = as_list(load_json(topic_dir / "synthesis" / "heterogeneity.json"))
    pooled_outcomes = [o for o in heterogeneity if o.get("pooled") is True]
    narrative_outcomes = [o for o in heterogeneity if o.get("pooled") is False]
    synth_present = (topic_dir / "synthesis" / "heterogeneity.json").exists()

    manuscript_path = topic_dir / "manuscript" / "manuscript.md"
    manuscript_exists = manuscript_path.exists()
    manuscript_words = len(manuscript_path.read_text().split()) if manuscript_exists else 0
    manuscript_mtime = manuscript_path.stat().st_mtime if manuscript_exists else 0
    extraction_path = topic_dir / "extraction_table.json"
    extraction_mtime = extraction_path.stat().st_mtime if extraction_path.exists() else 0
    synth_dir = topic_dir / "synthesis"
    synth_mtime = max((f.stat().st_mtime for f in synth_dir.glob("*.json")), default=0) if synth_dir.exists() else 0

    # ---- current stage + single next-command recommendation ----
    if protocol is None:
        stage, next_cmd = "not_started", f'/prisma-init "{topic_dir.name}"'
        why = "no protocol.json yet"
    elif not search_plan or not per_source:
        stage, next_cmd = "protocol_defined", "/prisma-search"
        why = "protocol is defined but no search has been run yet"
    elif not records:
        stage, next_cmd = "search_incomplete", "/prisma-search"
        why = "raw search results exist but records.jsonl was never written"
    elif undecided_ta > 0:
        stage, next_cmd = "screening_title_abstract", "/prisma-screen export --stage title_abstract"
        why = f"{undecided_ta} record(s) still undecided at title/abstract"
    elif pending_full_text > 0:
        stage, next_cmd = "screening_full_text", "/prisma-screen export --stage full_text"
        why = f"{pending_full_text} record(s) passed title/abstract but have no full-text decision yet"
    elif included_final == 0:
        stage, next_cmd = "screening_complete_zero_included", None
        why = "screening is complete but zero studies were included -- revisit protocol.json's eligibility criteria"
    elif extracted_count < included_final:
        stage, next_cmd = "extraction_incomplete", "/prisma-extract"
        why = f"{extracted_count}/{included_final} included studies extracted"
    elif not synth_present:
        stage, next_cmd = "extraction_complete", "/prisma-synthesize"
        why = "extraction is complete, synthesis has not run yet"
    elif not manuscript_exists:
        stage, next_cmd = "synthesis_complete", "/prisma-report"
        why = f"{len(pooled_outcomes)} outcome(s) pooled, {len(narrative_outcomes)} narrative-fallback -- manuscript not yet drafted"
    elif max(extraction_mtime, synth_mtime) > manuscript_mtime:
        stage, next_cmd = "manuscript_drafted", "/prisma-report"
        why = "extraction_table.json or a synthesis/ file is newer than manuscript.md -- the manuscript may be stale"
    else:
        stage, next_cmd = "manuscript_drafted", None
        why = "manuscript is drafted and up to date -- review it, or re-run /prisma-report after any further pipeline change"

    return dict(
        topic=topic_dir.name, protocol=protocol, per_source=per_source,
        truncated_sources=truncated_sources, identified_total=identified_total,
        duplicates_removed=duplicates_removed, records_screened=records_screened,
        excluded_title_abstract=excluded_ta, sought_for_retrieval=sought_for_retrieval,
        undecided_title_abstract=undecided_ta, assessed_for_eligibility=assessed_for_eligibility,
        pending_full_text=pending_full_text, excluded_full_text_total=len(excluded_ft),
        included_final=included_final, full_text_excludes_missing_reason=missing_reason,
        orphaned_title_abstract=orphaned_ta, orphaned_full_text=orphaned_ft,
        extracted_count=extracted_count, unextracted_included=unextracted_included,
        pooled_outcomes=len(pooled_outcomes), narrative_outcomes=len(narrative_outcomes),
        synth_present=synth_present, manuscript_exists=manuscript_exists,
        manuscript_words=manuscript_words, stage=stage, next_cmd=next_cmd, why=why,
    )


def print_full(s):
    print(f"# PRISMA review status: {s['topic']}")
    print()
    p = s["protocol"]
    if p:
        print(f"Title: {p.get('title', '(untitled)')}")
        print(f"Framework: {p.get('framework', '?')}  |  Review type: {p.get('review_type', '?')}")
        scope = p.get("scope", {}) or {}
        region = f" ({scope.get('region')})" if scope.get("region") else ""
        print(f"Scope: {scope.get('mode', '?')}{region}  |  coverage gaps noted: {len(scope.get('coverage_gaps', []) or [])}")
    else:
        print("(no protocol.json yet)")
    print()
    print("## Pipeline counts")
    print(f"  Records identified (latest run per source): {s['identified_total']}")
    for src, meta in sorted(s["per_source"].items()):
        flag = "  [TRUNCATED]" if meta["truncated"] else ""
        print(f"    - {src}: retrieved={meta['retrieved']} total_available={meta['total_available']}{flag}")
    print(f"  Records deduplicated (unique, screenable): {s['records_screened']}  "
          f"(duplicates removed: {s['duplicates_removed']})")
    print(f"  Screened - title/abstract: include={s['sought_for_retrieval']} "
          f"exclude={s['excluded_title_abstract']} undecided={s['undecided_title_abstract']}")
    print(f"  Screened - full-text: include={s['included_final']} "
          f"exclude={s['excluded_full_text_total']} pending={s['pending_full_text']} "
          f"(assessed so far: {s['assessed_for_eligibility']})")
    print(f"  Included (final): {s['included_final']}")
    print(f"  Extracted: {s['extracted_count']}/{s['included_final']}")
    if s["synth_present"]:
        print(f"  Synthesized: {s['pooled_outcomes']} outcome(s) pooled, "
              f"{s['narrative_outcomes']} narrative-fallback")
    else:
        print("  Synthesized: not yet run")
    ms = f"drafted ({s['manuscript_words']} words)" if s["manuscript_exists"] else "not drafted"
    print(f"  Manuscript: {ms}")
    print()

    warnings = []
    if s["full_text_excludes_missing_reason"]:
        warnings.append(
            ("Data integrity: full-text excludes missing a required reason (PRISMA Item 16b)",
             s["full_text_excludes_missing_reason"],
             "Fix by appending a corrected line to screening_decisions.jsonl (never edit history) "
             "before running /prisma-extract."))
    if s["orphaned_title_abstract"] or s["orphaned_full_text"]:
        warnings.append(
            ("Data integrity: screening decisions reference a record_id no longer canonical in records.jsonl",
             sorted(set(s["orphaned_title_abstract"]) | set(s["orphaned_full_text"])),
             "These records were likely reclassified as duplicates after being screened, or removed by "
             "a hand-edit. They are still counted in the include/exclude tallies above -- this script "
             "deliberately mirrors /prisma-report's own flow-diagram aggregation, which does not filter "
             "them either -- so the two commands never disagree. Confirm the reclassification was "
             "intentional; a record that turned out to be a duplicate after screening may need its "
             "decision reconsidered against whichever record it is now a duplicate of."))
    if s["unextracted_included"]:
        warnings.append(
            ("Extraction gap: full-text includes with no extraction_table.json entry",
             s["unextracted_included"],
             "Run /prisma-extract to pick these up."))
    if s["truncated_sources"]:
        warnings.append(
            ("Search coverage: source(s) truncated by a --limit cap",
             s["truncated_sources"],
             "retrieved < total_available for these -- consider re-running rerun_search.sh uncapped "
             "before treating identified_total as final."))

    for title, ids, fix in warnings:
        print(f"## WARNING: {title}")
        for rid in ids[:20]:
            print(f"    - {rid}")
        if len(ids) > 20:
            print(f"    ... and {len(ids) - 20} more")
        print(f"  {fix}")
        print()

    print(f"## Current stage: {s['stage']}")
    if s["next_cmd"]:
        print(f"## Next command: {s['next_cmd']}")
    print(f"  ({s['why']})")


def print_condensed(s):
    tag = f" -> next: {s['next_cmd']}" if s["next_cmd"] else " -> nothing pending"
    print(f"{s['topic']}: stage={s['stage']}  identified={s['identified_total']} "
          f"dedup={s['records_screened']} included={s['included_final']} "
          f"extracted={s['extracted_count']} synth_pooled={s['pooled_outcomes']}{tag}")


def main():
    args = sys.argv[1:]
    if not RESULTS.exists():
        print("No reviews found -- results/ does not exist yet. Run /prisma-init \"<topic>\" to start one.")
        return
    topics = sorted(d for d in RESULTS.iterdir() if d.is_dir())
    if not topics:
        print("No reviews found under results/. Run /prisma-init \"<topic>\" to start one.")
        return
    if not args:
        print(f"{len(topics)} review(s) under results/:\n")
        for d in topics:
            print_condensed(compute(d))
        return
    topic_dir = RESULTS / args[0]
    if not topic_dir.is_dir():
        print(f"No review at results/{args[0]}/.")
        return
    print_full(compute(topic_dir))


main()
PY
```

For single-topic mode, replace the literal `<TOPIC>` right after `python3 - ` with the
resolved directory name from Step 2 (shell-quote it if it contains characters that need
quoting, though a slug produced by Step 2's rule never does). For list-all mode, delete
`<TOPIC>` entirely so the heredoc runs as `python3 - <<'PY'` with no arguments — that is
what selects the list-all branch inside `main()`.

Do not edit the script's logic per run. It is deterministic and reads only what already
exists on disk; if a count looks wrong, the fix is in the upstream command that wrote the
file, never in this script.

---

## Step 4: Present the Report

Relay the script's stdout to the reviewer essentially verbatim — reformat lightly for
readability (e.g. as Markdown headings/lists matching what it already prints) but **never
recompute, round, or "correct" a number it printed**. Specifically:

1. **List-all mode**: present the condensed one-liner per topic as a short table or list.
   If the reviewer's message named a topic loosely that didn't parse as an argument
   (unusual, since Step 0 already routed a non-empty `$ARGUMENTS` to single-topic mode),
   don't second-guess it here — list-all mode's job is the full inventory.
2. **Single-topic mode**: present the full report. Put **"Current stage"** and **"Next
   command"** at the top of your reply, not buried at the end — that is the one line a
   returning reviewer most needs, even before the counts. Then show the pipeline counts,
   then any `WARNING:` blocks the script printed.
3. If any `WARNING:` block appeared, call it out explicitly and do not treat the "Next
   command" recommendation as sufficient on its own — a missing full-text-exclude reason
   or an extraction gap needs to be resolved before the recommended next command will
   actually run cleanly for `/prisma-extract`/`/prisma-report`, even though the
   state-machine logic already accounts for most of these in choosing what to recommend.
4. If `stage` is `screening_complete_zero_included`, do not suggest any pipeline command —
   say plainly that zero studies were included and ask whether the reviewer wants to
   revisit `protocol.json`'s eligibility criteria (a re-run of `review-protocol`'s
   elicitation, invoked via `/prisma-init` on the same topic) rather than proceeding.
5. Never suggest `/prisma-add-source` or `/prisma-reset` as "the next command" — both are
   always available but neither is part of the sequential pipeline this state machine
   tracks; mention them only if the reviewer's own message suggests they're relevant
   (e.g. they mention wanting to add an institutional database, or wanting to redo a
   stage from scratch).

---

## Notes

- This command **never writes anything**. It is safe to run at any point, any number of
  times, including mid-screening, mid-extraction, or after a `/prisma-reset`.
- The Identification/Screening/Included counts here use the **same aggregation algorithm**
  `/prisma-report` Step 8 uses to compute the PRISMA flow-diagram numbers (latest raw file
  per source, `duplicate_of` truthiness for dedup, latest-line-per-`(record_id, stage)`
  for screening decisions). This is deliberate: a reviewer should never see one count from
  `/prisma-status` and a different one in the eventual manuscript's flow diagram. If the
  two ever disagree, that is a bug in whichever command computed the number differently —
  not a discrepancy to paper over in either command's output.
- `extraction_table.json` has been written under more than one top-level shape at
  different points in this repo's history (a bare JSON array vs. `{"studies": [...]}`,
  with either `record_id` or `study_id` as the per-study identifier). The script's
  `as_list()`/`study_id()` helpers accept either so `/prisma-status` keeps working
  regardless of which shape `/prisma-extract` currently produces — but this inconsistency
  is worth flagging back to whoever maintains `/prisma-extract` and
  `synthesis/run_synthesis.py`, since **those two files still need to agree with each
  other** on one canonical shape; `/prisma-status` papering over it is not a substitute
  for fixing it there.
- The "manuscript may be stale" check (mtimes of `extraction_table.json`/`synthesis/*.json`
  vs. `manuscript/manuscript.md`) is a heuristic, not a content diff — a reviewer who
  re-ran `/prisma-extract` with `--redo` on a single study whose numbers didn't actually
  change will still see this flagged. That is the correct conservative default: silently
  trusting a stale manuscript is worse than an occasional unnecessary "consider
  re-running `/prisma-report`" nudge.
- Orphaned screening decisions (a decision recorded for a `record_id` that is no longer
  canonical in `records.jsonl`) are surfaced here by design — `screening-assistant`'s own
  documentation explicitly defers this check to `/prisma-status` rather than handling it
  at import time, since import has no way to know a record will later be reclassified as
  a duplicate.
