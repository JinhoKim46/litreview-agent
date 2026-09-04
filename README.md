# prisma-review

*A PRISMA 2020-conformant systematic review and meta-analysis pipeline that
actually runs, built on [Claude Code](https://claude.com/claude-code).*

> Note: This is an independent open-source project and is not affiliated
> with, endorsed by, or sponsored by Anthropic. Anthropic and Claude Code
> are referenced only to describe the toolchain this workflow uses.

Most "AI systematic review" tools are reporting assistants: you search,
screen, and extract data elsewhere (Rayyan, RevMan, Excel), then interview a
model into narrating what you already did. This repo instead runs the whole
pipeline — real database search, real deduplication, a real screening
workflow, real data extraction, and real statistical meta-analysis (pooled
effect sizes, heterogeneity, forest/funnel plots, GRADE certainty) — with
the human judgment calls PRISMA itself requires (screening decisions,
section approval) left to the reviewer, and everything else automated and
auditable.

## Pipeline

```
scope --> field/topic --> keywords --> search --> dedup --> screen --> extract --> synthesize --> report
  |            |              |           |          |          |          |            |             |
PICO/     eligibility    LLM-assisted   6 free    DOI/PMID/  export/   study char-  pool effect   manuscript.md
PICo/     criteria,      synonym +      connector title-hash  import    acteristics, sizes, RoB2,  + flow diagram
SPIDER    global vs.     MeSH/related   CLIs run  key with    sheets    effect data, GRADE, plots  + checklist
record    national       term expansion the same  audit       (never    RoB2 fields  (auto narrative              audit
                          per source     query     trail                              fallback when
                                                                                       not poolable)
```

Every arrow above is a `results/<TOPIC>/` file, not a conversation the
reviewer has to re-have: `protocol.json` -> `search_plan.json` +
`rerun_search.sh` -> `records.jsonl` -> `screening_decisions.jsonl` ->
`extraction_table.json` -> `synthesis/*.json` + plots -> `manuscript/`.
Nothing downstream is ever re-elicited from memory — the report drafts
straight from what the pipeline actually recorded.

## Quickstart

```bash
claude
# Then inside Claude Code:
/prisma-init "your review topic"      # scope, PICO, eligibility criteria, keyword expansion
/prisma-search                        # run connectors against enabled sources, dedupe
/prisma-screen export                 # write a title/abstract screening sheet to disk
# ... edit results/<TOPIC>/screening/title_abstract_sheet.csv (or .md) by hand ...
/prisma-screen import                 # append your decisions to the ledger
/prisma-extract                       # build the extraction table (characteristics, effect data, RoB2)
/prisma-synthesize                    # pool poolable outcomes, plot, assess heterogeneity/GRADE
/prisma-report                        # draft the manuscript, flow diagram, and checklist audit
```

`/prisma-status "your review topic"` works at any point and reconstructs
exactly where a review stands, since every stage's state is either
append-only or fully re-derivable — close your laptop mid-screening for
weeks and pick back up with nothing lost.

## Free, multi-disciplinary sources

Six connectors ship out of the box, chosen to cover most disciplines with no
paid access required:

| Source | Coverage |
|---|---|
| **OpenAlex** | Broad multi-disciplinary index, generous free API |
| **Crossref** | DOI registry metadata, near-universal publisher coverage |
| **Semantic Scholar** | CS/multi-disciplinary, citation graph |
| **PubMed** | Biomedical/life sciences, MeSH-indexed |
| **Europe PMC** | Biomedical + preprints + patents, broader than PubMed |
| **arXiv** | STEM preprints (flagged as not-yet-peer-reviewed in extraction) |

Need an institutional source (Scopus, Web of Science)? Run
`/prisma-add-source` — it scaffolds a new connector against the same fixed
`{meta, results}` JSON contract the six above already use, with credentials
read only from an environment variable, never a flag or a tracked file.

## Fork this and adapt

**This repo is a universal template.** The connectors, PRISMA methodology,
screening workflow, and synthesis math are topic-agnostic and
reviewer-agnostic — fork it, run `/prisma-init "your topic"`, and everything
your specific review produces lands under `results/<your-topic>/`, which is
gitignored by default. Upstream improvements to the pipeline (new
connectors, dedup fixes, better pooling logic) stay mergeable back into your
fork precisely because your review's own data was never committed to it in
the first place. See [CONTRIBUTING.md](CONTRIBUTING.md) for what's
universal-pipeline vs. instance-specific, and [AGENTS.md](AGENTS.md) if
you're driving this from a non-Claude agent runtime.

## Repo structure

```
prisma-review/
├── CLAUDE.md               # persona, reviewer profile, workflow pointer
├── AGENTS.md               # thin pointer for non-Claude runtimes
├── .claude/
│   ├── commands/           # the 9 slash commands
│   └── skills/             # PRISMA methodology, eligibility gates, synthesis stats
├── .agents/skills/         # cross-runtime connector pointers (Codex/Antigravity discoverable)
├── connectors/             # one Python package: 6 source connectors + shared HTTP/retry/contract code
├── synthesis/              # pooling, heterogeneity, forest/funnel plots
├── results/<TOPIC>/        # per-review state (gitignored except structure + schema docs)
├── tools/                  # CI/maintainer scripts (lint, contract checks)
├── tests/                  # fixture-based, no live network
└── requirements.txt        # requests, statsmodels, matplotlib
```

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.10+ (`pip install -r requirements.txt`)
- Optional: [Pandoc](https://pandoc.org/) for `--export docx|pdf` on the
  manuscript; the pipeline is Markdown-first and works fully without it.

## License

MIT for all framework code and prompts, with an explicit carve-out for two
CC BY 4.0 reference documents and one file adapted from another MIT project
with attribution preserved — see [LICENSE](LICENSE) for the exact terms.
