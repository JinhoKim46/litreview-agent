---
framework_version: 1.0.0
---

# Eligibility Criteria — run before scoring or synthesis

This is a hard filter, not a scoring dimension. It runs **before** any relevance scoring, screening prioritization, or data extraction — a study can look highly relevant to the topic and still be categorically excluded because it fails one of these gates. Adapted from the job-application-assistant's eligibility-gate pattern (citizenship/language hard-stop before scoring); the gates below replace citizenship/language-of-employment concerns with the five PRISMA-relevant hard gates: **population match, study design, publication type, date range, and language of publication.**

Run every gate in order, for every candidate study, at both title/abstract screening (where abstract detail allows) and full-text screening (where the full gate can finally be confirmed or reversed). A study can pass all five gates at title/abstract on the information available and still fail one at full-text once the full paper is read — that is a normal, expected outcome, not an error.

## The five gates

### 1. Population match

Read the study's stated population/sample **as described in the abstract or methods** and classify against `protocol.json.eligibility.population.criterion`:

| Study's population, as stated | Verdict |
|---|---|
| Matches the protocol's population criterion directly (age range, condition, setting, etc. all consistent) | **PASS** |
| Population is a **strict subset or superset** that plausibly still answers the question (e.g. protocol wants "adults with type 2 diabetes", study reports "adults with type 2 diabetes and comorbid hypertension") | **FLAG** — proceed to the next gate, but note the partial mismatch for the human reviewer to weigh at full-text. |
| Population is **categorically different** from the criterion (wrong age band, wrong condition, wrong species in a study expecting human subjects, wrong clinical setting when setting is a stated criterion) | **FAIL — hard stop.** Do not score, do not extract. Quote the exact population description from the abstract. |
| Population is **not stated clearly enough** to classify | **PROCEED, but mark unverified** — pass to full-text screening for confirmation rather than failing on ambiguity alone. |

### 2. Study design

Classify the study's design against `protocol.json.eligibility.study_design.included`:

| Study design, as stated or inferable from the abstract | Verdict |
|---|---|
| Matches a design listed in `study_design.included` (e.g. protocol wants RCTs and quasi-experimental designs; study is an RCT) | **PASS** |
| Design is **not on the included list but is closely related** (e.g. protocol lists "RCT" only; study is a cluster-randomized trial) | **FLAG** — note the discrepancy, let full-text/human judgment decide whether it counts as the same design family. |
| Design is **explicitly excluded or categorically wrong** (protocol wants controlled trials; study is a case report, narrative review, editorial, or animal study when human trials are required) | **FAIL — hard stop.** Quote the design as stated (e.g. "case series, n=3"). |
| Design **cannot be determined** from the abstract | **PROCEED, but mark unverified** — resolve at full-text. |

### 3. Publication type

Check the record's publication type against `protocol.json.eligibility.publication_type`:

| Publication type | Verdict |
|---|---|
| Peer-reviewed journal article (or whatever `included` lists) | **PASS** |
| On the `excluded` list explicitly (e.g. conference abstract only, dissertation/thesis, preprint with no peer-reviewed version, editorial/letter/commentary, protocol-only publication with no results) | **FAIL — hard stop.** Quote the source type as recorded by the connector (`venue`/`source` fields) or as stated on the record page. |
| Ambiguous — e.g. a preprint that may have a later peer-reviewed version | **FLAG and check for a peer-reviewed twin** before failing outright — this is exactly the arXiv-preprint dedup-merge case described in the state-model documentation (`records.jsonl`'s dedup rule): search for a matching title/author/year record from a peer-reviewed source before treating the preprint as excluded. If no peer-reviewed twin exists and the protocol excludes preprints, **FAIL**. |

### 4. Date range

Compare the study's publication date against `protocol.json.eligibility.date_range` (`from`/`to`):

| Publication date | Verdict |
|---|---|
| Falls within `[from, to]` inclusive (an open-ended `to: null` means "up to the search date") | **PASS** |
| Falls **outside** the range | **FAIL — hard stop.** Quote the publication year/date as recorded. |
| Date is **missing or ambiguous** (e.g. "in press", no year on the record) | **PROCEED, but mark unverified** — resolve at full-text by checking the actual publication date, don't fail on missing metadata alone. |

### 5. Language of publication

Compare the study's language against `protocol.json.eligibility.language.included`:

| Study's language | Verdict |
|---|---|
| On the `included` list | **PASS** |
| **Not** on the `included` list, and `translation_used` is false | **FAIL — hard stop.** Quote the language as recorded by the source (or the language the title/abstract are evidently written in). |
| **Not** on the `included` list, but `translation_used` is true and the reviewer has stated they can assess this language via translation | **PASS**, but note in the extraction record that this study relied on translation (per `protocol.json.scope.translation_languages`), since PRISMA Item 5/Methods should disclose translation use. |
| Language **not stated** on the record | **PROCEED, but mark unverified** — check the actual full text's language before final exclusion; do not assume a missing language field means English. |

## Two rules that are easy to get wrong (carried over from the job-evaluation gate pattern)

1. **Silence is not permission.** A record with no explicit study-design tag, or an abstract that doesn't state the population precisely, is not automatically a PASS — it is "PROCEED, but mark unverified" and gets resolved at full-text, never silently upgraded to a clean pass because the abstract didn't say anything disqualifying.
2. **A near-miss is not a pass.** A study population that is merely *adjacent* to the criterion (e.g. protocol wants "children aged 5-12", study reports "children and adolescents aged 5-17") is a FLAG, not a PASS — the human reviewer decides whether the age-band overlap is close enough, the gate does not decide it for them.

## Reporting a gate failure

**Report every eligibility failure to the user (or write it to `screening_decisions.jsonl`) with the quoted source text**, never as a silent drop:

- At title/abstract screening: the `reason` field is optional for a title/abstract exclude, but still record which gate failed and the quote when available — it saves re-deriving the reason at full-text.
- At full-text screening: the `reason` field is **required** on every exclude decision (PRISMA Item 16b). Write it as `"<gate name>: <quoted source text>"`, e.g. `"study_design: case series, n=3, not a controlled trial"` — specific and countable, never a bare "not relevant".
- A study that fails a gate is not scored on relevance and does not proceed to data extraction. Everything downstream (`/prisma-extract`, `/prisma-synthesize`) only ever sees studies that passed all five gates.
- If a reviewer disagrees with a gate verdict on a specific study, that is exactly the case the gate exists to surface for human judgment — present the quoted evidence and let them override, recording the override and its rationale in `screening_decisions.jsonl` rather than silently changing the gate logic for one study.

## Order of operations

Run gates 1-5 in the order listed above and **stop at the first hard FAIL** — there is no need to evaluate publication type on a study that already failed the population gate, and reporting only the first failure keeps the exclusion reason specific rather than a pile of unrelated objections. If a study passes every gate (or exits with only FLAGs/unverified marks), it proceeds to relevance screening and, if included, to `/prisma-extract`.
