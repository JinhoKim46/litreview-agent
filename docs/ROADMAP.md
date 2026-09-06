# Roadmap

This pipeline today runs one method end to end: a systematic review, optionally with
meta-analysis, following the PRISMA 2020 reporting guideline. The plan below is the
durable summary of where it's headed next — a workspace that supports several
evidence-synthesis and landscape methods, routes a reviewer to the right one, and
computes the label it prints from what was actually done rather than from what was
typed in. It replaces two temporary planning documents (a working plan and a 19-agent
panel's consensus design) that lived in the repo only long enough to be distilled here;
the full record stays with the project owner outside of git for anyone who picks this
work back up.

## The design in one sentence

A *method* is a small JSON manifest of policy differences from today's
systematic-review pipeline, plus the claims that policy licenses. The nine Markdown
commands keep their stage sequence and remain the implementation — a manifest only
switches a stage off or changes its rules. The algebra is **review type × synthesis
family × maintenance mode × profile flags**. Prompts propose, deterministic Python
validates and records, humans decide. The label printed in any report is *computed
from recorded conduct*, never typed by a reviewer or a prompt.

## Method taxonomy

| Tier | Methods |
|---|---|
| **core-v1** (wired end to end first) | Systematic review (ships today), scoping review, systematic mapping study, exploratory literature brief ("reconnaissance"); SR with meta-analysis, SWiM/structured narrative, systematized review (a computed label, not a chosen one), rapid review, prior-work check, related-work section, living update, snowballing |
| **v2** | Diagnostic-accuracy/prediction-model reviews (`dta_narrative`: PRISMA-DTA, TRIPOD-SRMA, QUADAS-2, PROBAST+AI), evidence & gap maps, umbrella reviews, meta-analysis of proportions, a benchmark-tabulation family, a recency-bounded scoping preset, a grey-literature/multivocal source layer |
| **later** (needs a new data unit, a heavy engine, or a maintainer) | Qualitative evidence synthesis, mixed-methods reviews, network meta-analysis, a dedicated diagnostic-accuracy engine, dose-response/economics/eco-evo engines, bibliometrics, methodological reviews |
| **out of scope** | Realist/meta-narrative/critical-interpretive/meta-ethnography reviews, integrative/critical/hermeneutic reviews, individual-participant-data meta-analysis, patent landscaping/freedom-to-operate/horizon scanning, COSMIN/HTA |

A method the router can't yet serve is a routing-table refusal with a pointer to what
it can offer instead — never a stub manifest that looks supported but isn't.

## Milestones after today's baseline

| Milestone | Scope | Done when |
|---|---|---|
| **M1 — One method, made explicit** | Turn the systematic-review pipeline that ships today into an explicit manifest (`methods/systematic_review.json`) read by a real dispatcher (`tools/method.py`), with `run_synthesis.py` dispatching on synthesis family instead of assuming pairwise meta-analysis | A golden fixture run is byte-identical to today's except for a new `label.json`; a review with no recorded method resolves to "systematic review" with disclosures, not a crash |
| **M2 — Routing + label integrity** | A routing table and `/litreview-init` interview step that gets a reviewer to the right method from a free-text aim; a label gate that computes "systematic review" vs. "systematized review" vs. a disclosed shortfall from recorded conduct, never from what a prompt typed | Every routing row is tested; a single-screener review reports "systematized review" consistently at routing time and in the manuscript; qualitative and diagnostic-accuracy questions fail closed with a pointer, not a bad fit |
| **M3 — Scoping review + systematic mapping study** | The first two non-PRISMA methods: a charting-form workflow with a freeze gate, a keywording/classification workflow for mapping studies, and their own reference standards (PRISMA-ScR, SEGRESS) | A second golden fixture produces a PRISMA-ScR-audited report; pooling is refused on a scoping review's data; a mapping study's coding is blocked until its scheme is frozen |
| **M4 — Reconnaissance (exploratory literature brief)** | A lightweight prior-work-check / related-work-draft output for a reviewer who isn't running a formal review at all, with a clear hand-off path into a real method later | A brief never claims "no prior work" or "saturation"; a promoted review's gold set is flagged as non-independent until an external item is added |
| **M5 — Living-review mode + first field packs** | `--rerun` delta updates over any completed method, plus the first domain packs (medical-imaging prediction models, MRI reconstruction reproducibility) that add glosses and expectations without changing the core rules | A delta run screens only new records and reports what changed; a pooled cross-dataset metric a domain pack shouldn't allow gets refused by the core rules, not by pack-specific code |

`v2` and `later` items (above) get their own milestone once a maintainer picks them up.

## Adopted from open-source peers

Ideas below were verified against the source project and, where the code itself (not
just the idea) is reused, checked for a compatible license.

| Idea | Source | Lands in |
|---|---|---|
| Known-item (gold-set) recall gate with provenance | AngelChen-HC/systematic-review-skill (Apache-2.0); y9655980-crypto/sr-search-skill (MIT) | Shipped (Phase 0) |
| Hash-chained decision ledger + verification | AngelChen-HC/systematic-review-skill (Apache-2.0) | Shipped (Phase 0) |
| Paule–Mandel τ², modified Hartung-Knapp-Sidik-Jonkman CI, prediction interval | idea from O0000-code/meta-analysis-skill (statsmodels already implements the math) | Shipped (Phase 0) |
| Quote + locator + notes provenance on extracted data | AngelChen-HC/systematic-review-skill; chunchiehfan/systematic-review | Shipped (Phase 0) |
| Single-authority state, update/merge mode | daltonhaslam/lit-review-agent (MIT) | M5 living mode |
| New-records-per-query series (deliberately never called "saturation") | O0000-code/paper-search-pro (Apache-2.0) | Shipped (Phase 0); M4 |
| RoB 2 as a signalling-question data model | rob-luke/risk-of-bias (MIT); official Cochrane text is CC BY-NC-ND, so only identifiers and paraphrase are ever vendored | v2 or later |
| Arbitrator-on-disagreement, kappa/PABAK agreement statistics | LatteReview (idea only, CC BY-NC-ND); AngelChen-HC | M2 |
| AI-transparency reporting checklist | Drignacioalcala/systematic-review-skill (MIT) | v2 |
| RIS import/export, reference-manager interop | ASReview (Apache-2.0); 54yyyu/zotero-mcp (MIT) | v2 |

## Appendix: the original ask, and what the design panel changed

The owner's original ask: PRISMA is one evidence-review method among many; the tool
should first decide which method fits a project, then guide the reviewer through that
method's own pipeline, informed by a multi-agent specialist debate converging on one
consensus design and by benchmarking open-source peers for ideas worth borrowing where
license-safe.

Three of the owner's original framings were raised, debated by the panel, and
unanimously revised — the owner reviewed and accepted the panel's position on each:

- **Meta-analysis is a synthesis family inside a systematic review, not a mode of its
  own.** A systematic review either does or doesn't pool its results; that choice
  doesn't need a separate top-level method.
- **A living (regularly updated) review is a maintenance mode layered over any
  completed method, not a method in itself** — PRISMA has its own living-review
  extension (PRISMA-LSR) for exactly this reason, applied on top of whatever method
  produced the review being kept current.
- **"Pre-research methods" undersold what a systematic review or a qualitative
  synthesis actually is.** Both are research in their own right, so the docs describe
  the wider set as "evidence-synthesis and landscape methods" instead. The router still
  understands a reviewer typing "meta-analysis" or "living review" as those words —
  it just resolves them internally to the right combination above.
