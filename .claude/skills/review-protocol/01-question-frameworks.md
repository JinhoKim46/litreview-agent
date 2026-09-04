---
framework_version: 1.0.0
---

# Question Frameworks

A systematic review's research question needs a structured framework before it can drive a search strategy or eligibility criteria. This file gives elicitation prompts for the frameworks a Claude-Code-run review is likely to need, and when to pick each one.

Ask which review type applies (or infer it from the objective the reviewer states) before running elicitation — the framework follows from the review type, not the other way around.

## Decision: which framework

| Review type | Framework | Why |
|---|---|---|
| Intervention/treatment effectiveness (does X improve outcome Y vs. a comparator?) | **PICO** | Needs an explicit comparator and measurable outcome to support pooling later. |
| Prevalence, prognosis, risk/exposure, or any question without a comparator (what proportion of X has Y? does exposure Z predict outcome W?) | **PICo** or **PEO** | No intervention/comparator to name; forcing PICO here produces an empty Comparator field and a worse search string. |
| Qualitative evidence synthesis (experiences, perceptions, meaning-making) | **SPIDER** | PICO's Intervention/Comparator language doesn't fit lived-experience research; SPIDER's Sample/Phenomenon of Interest/Design/Evaluation/Research type maps to qualitative methods sections directly. |
| Diagnostic test accuracy | **PIRD** (Population, Index test, Reference test, Diagnosis of interest) | Needs an index test and a reference/gold standard, which PICO has no slot for. |
| Mixed-methods or broad scoping-turned-systematic review | **PICO** for the quantitative arm + **SPIDER** for the qualitative arm, recorded separately | Trying to force one framework across both study types produces a criteria table that fits neither. |

When genuinely unsure, ask the reviewer directly: "Is there a comparator/control group in the studies you expect to find, or are you looking at prevalence/experience/diagnosis instead?" — the answer picks the framework.

## PICO (intervention effectiveness)

Elicit each field with its own question, not as a single compound question:

- **Population**: "Who is the population of interest? Be specific about condition, age range, setting, or other defining characteristics (e.g. 'adults aged 18-65 with type 2 diabetes in outpatient settings', not just 'diabetics')."
- **Intervention**: "What is the intervention or exposure being studied? Include specific forms/doses/delivery modes if that granularity matters for your question."
- **Comparator**: "What is it being compared against? Common answers: placebo, usual care, an alternative active intervention, no intervention, waitlist control. If multiple comparators are acceptable, list them all."
- **Outcome**: "What outcome(s) determine whether the intervention worked? Distinguish primary from secondary outcomes if there's more than one — the primary outcome drives the effect-measure choice in `/prisma-extract` and `/prisma-synthesize`."
- Optional: **Timing** ("over what follow-up period?") and **Setting** ("in what care/context setting?") when PICOTS granularity is useful for the search string.

Worked example: "Population: adults with major depressive disorder; Intervention: cognitive behavioral therapy delivered via smartphone app; Comparator: face-to-face CBT or waitlist; Outcome: change in depression symptom severity (PHQ-9 or equivalent) at ≥8 weeks."

## PICo (qualitative/no comparator — prevalence, prognosis, exposure)

- **Population**: same prompt style as PICO.
- **Interest** (the phenomenon, exposure, or condition being studied — not an intervention with a comparator): "What phenomenon, exposure, or condition are you examining? This replaces Intervention/Comparator since there's no controlled comparison here."
- **Context**: "In what context or setting does this occur? (geographic, clinical, cultural, organizational)"

Worked example: "Population: nurses in intensive care units; Interest: experiences of moral distress; Context: hospitals in high-income countries during the COVID-19 pandemic."

## SPIDER (qualitative evidence synthesis)

- **Sample**: "Who or what is being sampled? (Qualitative reviews sample participants, not populations in the epidemiological sense — note the terminology shift.)"
- **Phenomenon of Interest**: "What experience, behavior, or phenomenon are you trying to understand?"
- **Design**: "What study designs are you expecting/willing to include? (interviews, focus groups, ethnography, case studies, mixed-methods with a qualitative component)"
- **Evaluation**: "What outcome or evaluation measure, if any, are you extracting? (Often thematic findings rather than a numeric outcome.)"
- **Research type**: "Qualitative only, or also mixed-methods studies with an extractable qualitative component?"

Worked example: "Sample: informal caregivers of dementia patients; Phenomenon of Interest: experience of caregiver burden; Design: semi-structured interview studies; Evaluation: qualitative themes; Research type: qualitative and mixed-methods."

## PIRD (diagnostic test accuracy)

- **Population**: same style as PICO.
- **Index test**: "What is the test being evaluated?"
- **Reference test**: "What is the reference/gold-standard test it's being compared against?"
- **Diagnosis of interest**: "What condition is being diagnosed?"

## After elicitation

1. Read the assembled framework fields back to the reviewer in plain language and get explicit confirmation before writing them to `protocol.json`.
2. Persist under `protocol.json.framework` (the framework name) and `protocol.json.framework_fields` (the field values) — see `02-eligibility-criteria.md` and the parent `SKILL.md` for how these feed eligibility gates and the search-string build in `keyword-expansion/`.
3. If the reviewer's framework choice and the review type they described don't match (e.g. they ask for PICO but describe a qualitative interview study with no comparator), say so and suggest the better fit rather than silently forcing their stated framework — flag it, don't override it without asking.
