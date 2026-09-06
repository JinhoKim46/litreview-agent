---
framework_version: 1.0.0
---

# Petersen et al. 2015 Systematic Mapping Study Guidelines Reference

This is a paraphrase of the conduct guidelines for systematic mapping studies in software engineering set out by Petersen, Vakkalanka, and Kuzniarz (2015) -- an update to their earlier 2008 guidelines, informed by a review of how mapping studies were actually being conducted in practice. A systematic mapping study *classifies and structures a research area* (what has been studied, by whom, using what methods, on what topics) rather than *synthesizing the outcomes of primary studies*, which is what distinguishes it from a systematic review. Use this as the authoritative process reference when planning or auditing `methods/systematic_mapping_study.json`'s search/screening/classification stages; see `segress-2023-checklist.md` for the corresponding *reporting* standard.

Source: Petersen K, Vakkalanka S, Kuzniarz L. Guidelines for conducting systematic mapping studies in software engineering: An update. *Information and Software Technology*. 2015;64:1-18. doi: 10.1016/j.infsof.2015.03.007.

**License note:** *Information and Software Technology* (Elsevier) is a subscription journal; no CC BY or other open-reuse license was found for this article, and no openly accessible full-text copy could be located to quote from directly. The summary below is an original paraphrase built from the paper's well-documented, independently-corroborated process description (its own abstract and structure, and multiple secondary academic sources describing its guideline content), not a copy of its text -- treat any specific step's exact wording here as this repo's own summary, not a quotation.

---

## The mapping-study process (as this paper structures it)

1. **Define the research questions.** A mapping study's research questions are typically about the *landscape* of a topic (what kinds of studies exist, which venues, which methods, how the field has trended over time) rather than about a specific comparative effect. Petersen et al. recommend classifying candidate research questions using the research-type taxonomy from Wieringa, Maiden, Mead & Rolland (2006) -- six categories: **validation research** (a technique is investigated in a lab/experimental setting, not yet used in practice), **evaluation research** (a technique already used in practice is evaluated for its actual properties/effects), **solution proposal** (a technique is proposed, with only a small example or argument for its plausibility), **philosophical papers** (a new conceptual framework or way of looking at things, not empirically validated), **opinion papers** (the author's opinion on whether something is good/bad, without a rigorous research methodology), and **experience papers** (the author's personal experience explaining how something was done in practice). Classifying primary studies by this taxonomy is itself one of the mapping study's standard facets.

2. **Conduct the search.** The search process for a mapping study is largely the same as for a systematic review (databases, snowballing, manual search of key venues) -- Petersen et al. note less emphasis is typically placed on exhaustive completeness than in a systematic review, since a mapping study's goal is to characterize a field's shape, not to guarantee every last study is accounted for before drawing a conclusion about a specific effect.

3. **Screen for inclusion/exclusion.** Title/abstract screening against explicit criteria, as in a systematic review -- but per `references/docs/design/multi-method-consensus.md` §3.2, a mapping study's screening may rely on title/abstract alone more often than a systematic review's, since the classification facets to come often don't require full-text depth to assign.

4. **Build the classification scheme by keywording.** This is the paper's most distinctive contribution: a two-phase "keywording of abstracts" method for building a classification scheme *from the actual candidate set*, rather than imposing one a priori. In the first phase, the main researcher reads each candidate study's abstract and keywords (title and introduction/methodology/conclusion too, when the abstract alone isn't informative enough) to identify keywords and concepts describing the problem investigated and the paper's contribution. In the second phase, those keywords/concepts are combined and clustered into a small set of categories per facet (e.g. "research type," "contribution type," "application domain"), producing the classification scheme the mapping study will code every included study against.

5. **Classify (code) every included study against the frozen scheme.** Once the scheme from step 4 is fixed, every included study is coded against every facet. Petersen et al.'s guidance on rigor here (echoed in this repo's own `label_gate.py`/manifest design) is to disclose a calibration check -- inter-rater agreement when two or more coders are involved, or a delayed intra-rater re-code of a sample when only one coder is available -- rather than silently presenting the classification as unambiguous.

6. **Report the map.** The mapping study's core deliverable is the systematic map itself: frequency/count tables per facet, cross-tabulations between facets (e.g. research type x application domain), and bubble plots (a scatter plot where bubble size encodes how many studies fall into a given facet-combination cell) showing the field's overall shape and gaps -- not a narrative synthesis of what the studies concluded.

## What this repo's manifest borrows from this paper

`methods/systematic_mapping_study.json`'s `capture.mode: "classification"` (see `schemas/classification_table.schema.json`) is this paper's keywording-then-coding process: the schema's `scheme_frozen` flag models step 4's scheme-freeze gate (bulk coding is blocked until the scheme is frozen, per this milestone's exit criterion), and its `calibration` block models step 5's disclosed agreement check.
