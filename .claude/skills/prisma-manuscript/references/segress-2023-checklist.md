---
framework_version: 1.0.0
---

# SEGRESS 2023 Checklist Reference

This is a condensed paraphrase of the SEGRESS checklist (Kitchenham, Madeyski & Budgen, 2023) -- Software Engineering Guidelines for REporting Secondary Studies. SEGRESS extends the PRISMA 2020 item definitions to cover quantitative systematic reviews, systematic mapping studies, and qualitative reviews in software engineering, in one integrated 27-item structure (Table 9 of the source paper, read in full from the published PDF for this file). Each item below notes whether it is required, optional, or not applicable for a **systematic mapping study** specifically -- this repo's `methods/systematic_mapping_study.json` manifest cites this file (not PRISMA-ScR) as its reporting standard, per Kitchenham et al.'s own conclusion that a systematic mapping study is better served by an extended PRISMA 2020 structure than by adapting PRISMA-ScR, which was designed for scoping reviews' charting process rather than a mapping study's classification/facet process.

Source: Kitchenham B, Madeyski L, Budgen D. SEGRESS: Software Engineering Guidelines for REporting Secondary Studies. *IEEE Transactions on Software Engineering*. 2023;49(3):1273-1298. doi: 10.1109/TSE.2022.3174092. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) -- confirmed directly from the published PDF's own footer.

**License note:** the source is CC BY 4.0, so verbatim reproduction with attribution would be permitted. This file is nonetheless a condensed paraphrase, not a byte-for-byte copy of Table 9's cell text (cells were substantially rewritten/condensed for table brevity here, and the mapping-study-specific applicability framing in the "Applicability (mapping)" column is this file's own synthesis of Table 9's inline per-review-type notes, not copied verbatim) -- carries its own `framework_version` for exactly that reason, unlike this repo's other CC-BY checklist files, which stay byte-for-byte identical to their source and are exempted from version tracking instead (see `tools/check_framework_version.py`'s `EXEMPT_FROM_VERSION`).

**Note on terminology:** SEGRESS replaces "Quality Assessment" with "Risk of Bias" and "Threats to Validity" with "Limitations," aligning software-engineering secondary-study vocabulary with PRISMA 2020's. It also recommends "Analysis of Study Characteristics" in place of "Synthesis of Results" for mapping studies specifically, since a mapping study characterizes a body of work rather than synthesizing primary-study outcomes.

---

## TITLE
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 1 | Required | Identify the report's type (systematic mapping study, in this case) and specify the topic being mapped, so readers can judge relevance at a glance. |

## ABSTRACT
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 2 | Required | Give a structured abstract: background (emphasizing why the mapping matters), objectives, methods, results, optional limitations, conclusion. |

## INTRODUCTION
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 3 | Required | State the rationale for the study -- why this area needs mapping now (an update, a new area, a mature topic with no prior map) and how it serves the larger research/practice problem. |
| 4 | Required | State the research questions and how they connect to that larger problem. |

## METHODS
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 5 | Required | Define eligibility criteria based on the topic/intervention of interest; justify any restriction on the search (date range, language, venue, publication type). A mapping study restricting to high-quality venues must justify that restriction against its research questions. |
| 6 | Required | Describe every information source searched (databases, prior-study reference lists, other), with search end dates. |
| 7 | Required | Present the full search strategy (electronic strings, snowballing, manual search, any methods used to check completeness), including how each contributed to the final search. |
| 8 | Required | State the study-selection process: phases, number of assessors, tools used, and how disagreements were handled. Exclusions should be justified on synthesis-relevant grounds, not just eligibility. |
| 9 | Required | Describe how data were collected from each included report: how many reviewers, whether independently, and which parts of each study were analysed. |
| 10a | Not required | Outcome data items do not apply to mapping studies, which do not analyse primary-study outcomes. |
| 10b | Required | List and define the classification facets/variables the mapping used to categorize studies, and how each relates to a research question. |
| 11 | Optional | A formal risk-of-bias assessment is optional for a mapping study (required for other review types) -- state the rationale either way. |
| 12 | Sometimes required | An effect measure is not usually relevant to a mapping study, except when a research question specifically concerns which outcome metrics the primary studies used. |
| 13 | Required (as "Analysis of Study Characteristics") | Describe the methods used to analyse and present study characteristics -- for a mapping study this means the tables, graphs, and maps built from the classification, not a synthesis of primary-study outcomes. |
| 13a-13c | Required | Describe how studies were judged eligible for each analysis and the methods used to prepare/tabulate/visually display characteristics (e.g. bubble plots, facet-count tables). |
| 13d-13f | Not required | Effect-synthesis methods, sensitivity analysis, and heterogeneity investigation (13d-13f) do not apply -- a mapping study does not pool or synthesize outcome effects. |
| 14 | Not required | Reporting-bias assessment (e.g. publication bias) is not required for a mapping study. |
| 15 | Not required (but see docs/PLAN.md's own conduct-floor rules) | A GRADE-style certainty assessment does not apply to a mapping study's descriptive output. |

## RESULTS
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 16a | Required | Report the search-and-selection flow from records identified to studies included, ideally as a flow diagram; report agreement statistics if collected. |
| 16b | Optional | Citing near-miss studies that failed eligibility is optional for a mapping study (required for other review types). |
| 17 | Required | Present each included study's characteristics and citation. |
| 18 | Optional | Present risk-of-bias data if item 11's assessment was done; report agreement statistics if collected. |
| 19 | Not usually required | Per-study effect estimates/summary statistics do not apply. |
| 20 | Required (as study-characteristics analysis) | Report the classification-based analyses of study characteristics -- the maps, bubble plots, and facet/frequency tables the mapping study exists to produce. |
| 20a | Required | For each map/table produced, briefly summarize the characteristics of the contributing studies and discuss the maps and tables built to address each research question. |
| 20b-20d | Not required | Statistical-synthesis results, sensitivity analysis, and heterogeneity investigation do not apply. |
| 21 | Not required | Publication-bias assessment results do not apply. |
| 22 | Not required | Certainty-of-evidence assessment does not apply. |

## DISCUSSION
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 23a | Required | Interpret the results in the context of other evidence/related maps. |
| 23b | Not required | Discussing limitations of the (nonexistent) primary-study-outcome evidence does not apply to a mapping study. |
| 23c | Required | Discuss limitations of the review process itself -- but only issues not already covered in Methods, and only if they weren't anticipated by the specified protocol. |
| 23d | Required (future research only) | For a mapping study, implications are limited to future-research directions -- practice/policy implications are out of scope for a descriptive map. |

## OTHER INFORMATION
| Item | Applicability (mapping) | Checklist |
|---|---|-----------|
| 24a | Optional | State registration details, or that the study was not registered. |
| 24b | Required | State where the protocol can be accessed, or that none was prepared. |
| 24c | Optional | Describe amendments to the registered/protocol information (required for quantitative/qualitative reviews; optional for mapping studies). |
| 25 | Required | Describe financial/non-financial support and the funder's role. |
| 26 | Required | Declare competing interests of the review authors. |
| 27 | Optional (recommended) | State which of the following are publicly available and where: data-collection forms, extracted/classification data, analytic code, other materials. |

**A note on iterative reporting (SEGRESS items 17-22):** when a mapping study reports its analyses per research question or per study subgroup rather than once for the whole set, it's acceptable to repeat items 17-22 per subgroup -- but state that this iterative structure is being used, since even then some information (e.g. full study characteristics) may need reporting once, up front, rather than fragmented across every subgroup.
