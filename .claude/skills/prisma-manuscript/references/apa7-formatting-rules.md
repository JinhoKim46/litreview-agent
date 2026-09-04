---
framework_version: 1.0.1
---

# APA 7th Edition Formatting Rules

MIT-licensed reference distilled from publicly available APA 7th Edition guidance (American Psychological Association, 2020, *Publication Manual of the American Psychological Association* (7th ed.), and APA's public Style and Grammar Guidelines at apastyle.apa.org). This file is a standalone summary written for this framework — it is not a reproduction of the Publication Manual's text — and exists so `prisma-manuscript/SKILL.md` has no dependency on an external referencing skill. When in doubt about an edge case not covered here, verify against APA's official style guidelines via WebSearch/WebFetch rather than guessing.

---

## 1. In-text citations

- **Parenthetical:** (Author, Year) or (Author & Author, Year) or (Author et al., Year).
- **Narrative:** Author (Year) reported that... / According to Author and Author (Year)...
- **1–2 authors:** cite all names every time. `&` inside parentheses, "and" in narrative prose.
- **3 or more authors:** first author's surname + "et al." from the very first citation onward (e.g. Chen et al., 2021).
- **Multiple works, same parenthetical citation:** order alphabetically by first author's surname, separated by semicolons: (Adams, 2019; Chen et al., 2021; Roberts & Lee, 2020).
- **Same author, same year, multiple works:** disambiguate with lowercase suffixes on the year, assigned by title alphabetical order: (Adams, 2019a, 2019b).
- **Direct quotations:** include a page or paragraph number — (Adams, 2019, p. 12) or, for sources without page numbers, (Adams, 2019, para. 4). Quotations of 40+ words are set as a block quotation (indented 0.5 in, no quotation marks, double-spaced, citation after the final period).
- **Group/organisation as author:** spell out in full on first citation, with the abbreviation introduced if it will be reused: (World Health Organization [WHO], 2023), then (WHO, 2023) thereafter.
- **No identifiable author:** use the title (shortened, in quotation marks for an article/chapter or italicised for a report/book) in place of the author: ("Title of Article," 2022).
- **No date:** use "n.d." in place of the year: (Adams, n.d.).
- **Secondary citation (source you have not read yourself):** cite the original as reported in the source you actually read: (Smith, 1990, as cited in Adams, 2019). Prefer locating and citing the primary source directly whenever possible — verify it exists before citing it directly.

## 2. Reference list

- Heading: "References", centered, bold, not italicised.
- Alphabetical order by first author's surname; for multiple works by the same author, order by year (earliest first); for same author and year, add lowercase suffixes (2019a, 2019b) matching the in-text citations.
- **Hanging indent:** first line flush left, every subsequent line of that entry indented 0.5 in (1.27 cm).
- **Author names:** surname, initials — "Smith, J. A." — for all listed authors. Use "&" before the final author in a multi-author list.
- **Author cap:** list up to 20 authors in full. For 21 or more, list the first 19, insert an ellipsis (...), then the final author's name (no "&" before the final name in this case).
- **Double-spaced**, no extra blank line between entries (spacing comes from the hanging indent + double spacing, not manual line breaks).
- **Sentence case** for article titles, chapter titles, and book titles: capitalise only the first word of the title, the first word after a colon/em dash, and proper nouns. **Title case** for journal/periodical names: capitalise all major words.
- **Italics:** journal names, volume numbers, and book/report titles are italicised. Article titles, chapter titles, and issue numbers are not italicised.
- **DOIs:** format as `https://doi.org/10.xxxx/xxxx` (the full resolvable URL form, not the bare "doi:" prefix). No full stop after a DOI or URL, since a trailing period could be mistaken for part of the link.
- **URLs without a DOI:** use the direct URL in the same position a DOI would occupy. Do not add "Retrieved from" before a URL unless the source is expected to change over time (e.g. a wiki, a dashboard), in which case add "Retrieved Month Day, Year, from" before the URL.

## 3. Reference examples by source type

**Journal article (DOI available):**
```
Author, A. A., & Author, B. B. (Year). Title of article in sentence case.
    Title of Journal in Title Case, Volume(Issue), pages.
    https://doi.org/10.xxxx/xxxx
```

**Journal article (no DOI, from a database or open-access page):**
```
Author, A. A. (Year). Title of article in sentence case. Title of Journal
    in Title Case, Volume(Issue), pages. https://journal-homepage-url
```

**Book:**
```
Author, A. A. (Year). Title of book in sentence case (edition if not
    first). Publisher.
```

**Edited book chapter:**
```
Author, A. A. (Year). Title of chapter in sentence case. In E. Editor & F.
    Editor (Eds.), Title of book in sentence case (pages). Publisher.
```

**Report (e.g. from an agency or organisation):**
```
Organization Name. (Year). Title of report in sentence case (Report No.
    xxx, if any). Publisher (if different from author).
    https://doi.org/xxx or URL
```

**Preprint (arXiv, bioRxiv, medRxiv, etc.):**
```
Author, A. A. (Year). Title of preprint in sentence case. Repository Name.
    https://doi.org/xxx or URL
```
Note explicitly that the work is a preprint and has not undergone peer review, either in the reference (repository name makes this clear) or in the surrounding text where it is first discussed — relevant when a preprint and its later peer-reviewed version are both cited or when only the preprint exists.

**Website / webpage (no journal, no formal publisher):**
```
Author, A. A., or Organization Name. (Year, Month Day). Title of page in
    sentence case. Site Name. https://url
```

**Systematic review / guideline statement (e.g. PRISMA 2020 itself):**
```
Page, M. J., McKenzie, J. E., Bossuyt, P. M., Boutron, I., Hoffmann, T. C.,
    Mulrow, C. D., Shamseer, L., Tetzlaff, J. M., Akl, E. A., Brennan, S.
    E., Chou, R., Glanville, J., Grimshaw, J. M., Hróbjartsson, A., Lalu,
    M. M., Li, T., Loder, E. W., Mayo-Wilson, E., McDonald, S., ...
    Moher, D. (2021). The PRISMA 2020 statement: An updated guideline for
    reporting systematic reviews. BMJ, 372, Article n71.
    https://doi.org/10.1136/bmj.n71
```
Always verify the current, correct citation for the PRISMA 2020 statement (and any other methodological source cited, e.g. RoB2, GRADE, PRISMA extensions) via WebSearch before inserting it — do not retype the example above from memory without confirming it still matches the published record.

**Dataset:**
```
Author, A. A., or Organization Name. (Year). Title of dataset (Version
    number if any) [Data set]. Publisher/Repository.
    https://doi.org/xxx or URL
```

**Software or statistical package (e.g. citing statsmodels or R):**
```
Author, A. A., or Organization Name. (Year). Name of software (Version
    number) [Computer software]. Publisher/Repository. https://url
```

## 4. Tables and figures (APA style)

- Numbered sequentially and independently: Table 1, Table 2... / Figure 1, Figure 2...
- **Table title** goes directly above the table, italicised, on the line below the "Table N" label (not italicised).
- **Figure caption** goes directly below the figure, same two-line pattern: "Figure N" (not italicised) then the caption (italicised, first word capitalised, sentence case for the rest).
- Notes explaining abbreviations, significance markers, or data sources go below the table/figure in a smaller font, introduced with "Note. ".
- Every table and figure must be referred to by number at least once in the body text (e.g. "as shown in Table 1" / "Figure 2 presents...").
- In this framework, the PRISMA flow diagram is always Figure 1, and the forest plot (when quantitative synthesis applies) is always Figure 2, per the manuscript structure in `SKILL.md`.

## 5. Verification discipline (non-negotiable)

- Every reference inserted into the manuscript — whether supplied by the reviewer or drafted while citing a methodological source (PRISMA 2020, RoB2, GRADE, a statistical method) — must be checked for real existence via WebSearch/WebFetch before it is written into `references.md`. Never fabricate an author, year, title, volume, or DOI.
- A reference pulled from `records.jsonl`/`extraction_table.json` (i.e. studies the pipeline actually retrieved from OpenAlex/Crossref/PubMed/ etc.) already carries a verified DOI or source URL from the connector that found it — re-verify only if the metadata looks incomplete or inconsistent (e.g. mismatched year vs. volume), not as a blanket re-check of every already-sourced record.
- If a reference cannot be verified, flag it explicitly to the reviewer rather than silently dropping it or guessing at the missing fields.
