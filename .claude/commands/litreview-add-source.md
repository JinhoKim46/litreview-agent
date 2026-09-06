# /litreview-add-source - Generate a New Literature-Search Connector

You are helping the user add a new bibliographic-database connector to this systematic-review pipeline. Six connectors ship out of the box (OpenAlex, Crossref, Semantic Scholar, PubMed, Europe PMC, arXiv) covering most disciplines with no paid access required. This command scaffolds a seventh (or eighth, ninth...) — typically an institutional-access source (Scopus, Web of Science, CINAHL, EBSCO) or a discipline-specific index the six free sources don't cover — investigating the real API before writing any code, then proving it works against a real response before registering it.

This mirrors the `/add-portal` pattern from the job-search sibling project this pipeline's architecture is descended from — same shape, adapted from TypeScript job-portal scrapers to Python literature-search connectors: interview, investigate, scaffold, mandatory live test, register. Per `CONTRIBUTING.md`, a paid-access-only connector tied to one institution's subscription stays in your fork rather than being merged upstream — this command exists precisely so you can build one for yourself without needing it upstream.

`$ARGUMENTS` may contain `--list`, a source name, or nothing.

Follow these steps **in order. Do not skip steps.**

---

## Step 0: Parse Arguments

- If `$ARGUMENTS` contains `--list`: show installed connectors via `connectors/registry.py`, which discovers every `connectors/*.py` module by glob (excluding `__init__.py`, `_shared.py`, and `registry.py` itself):
  ```bash
  python3 -m connectors.registry --list
  ```
This is the expected surface (`--list` printing each discovered `SOURCE_KEY`, `BASE_URL`, and whether it needs an API key) — if `connectors/registry.py` doesn't yet exist or doesn't yet expose this flag, build/extend it to match before continuing, since Step 5 depends on it too. Print the table and stop.
- If `$ARGUMENTS` contains what looks like a source name (kebab-case, optionally already suffixed `-search`): carry it into Step 1 as a pre-answered question.
- Otherwise: start the interview at Step 1.

---

## Step 1: Interview - Source Basics

Ask the user (skip anything already answered by `$ARGUMENTS`):

1. **API base URL** - the database's programmatic access point (e.g. `https://api.elsevier.com/content/search/scopus`, `https://api.clarivate.com/apis/wos-starter/v1`). If the user only has a web search UI in mind and no API, tell them plainly: this pipeline's connector contract is API-first (JSON/XML over HTTP), and an HTML-scraping fallback is out of scope for a literature database — ask whether they know of an API, and stop here if not.
2. **Source name** - kebab-case, suffixed `-search` (e.g. `scopus-search`, `webofscience-search`, `cinahl-search`). Must not collide with an existing `connectors/<name>.py` or `.agents/skills/<name>-search/` folder — check with `Glob("connectors/*.py")` and `Glob(".agents/skills/*-search")` before accepting the name. The bare source key used inside the module (`SOURCE_KEY`, and the `<name>` in `connectors.<name>`) is the same string with `-search` stripped, e.g. `scopus`.
3. **Does it need an API key or subscription credential?** If yes, ask what the provider calls it (API key, access token, institutional token) — this drives the environment-variable name in Step 3's credential rule.
4. **A realistic test query** - a topic or keyword phrase the user would actually search for in a real review, used for the live test in Step 4.
5. **Discipline / coverage note** - what this source indexes and how it differs from the six shipped connectors (e.g. "Scopus: broader citation-indexed coverage with institutional access, useful when OpenAlex/ Crossref metadata is incomplete for older or non-English venues"). This drives the trigger-phrase description in `SKILL.md`.

---

## Step 2: Investigate the API

Do reconnaissance before writing any code. Use WebFetch/WebSearch on the provider's real, current documentation — never hardcode endpoint shapes or parameter names from memory; APIs change.

1. **Find and fetch the real API docs.** WebFetch the provider's developer documentation page (WebSearch `"<source> API documentation"` first if the user didn't give a docs URL directly). Confirm the base URL from Step 1 against what the docs actually say.
2. **Identify the search endpoint and its parameters:** the query parameter name, any field-restriction syntax (title/abstract-only vs full-text search), and the pagination mechanism — offset/page-based, cursor-based, or an opaque continuation token — plus its documented limits (max results per page, max total offset, e.g. OpenAlex's 10,000-result basic-paging cap that forces cursor pagination beyond one page).
3. **Fetch one real search-results response** for the test query from Step 1.4. If the source is keyless or has a free tier, WebFetch/`curl` an actual request and capture the real JSON/XML. If it strictly requires a paid credential the user doesn't have to hand you, work from the docs' own documented example response instead, and say so plainly to the user — the live-response requirement is not waived, only deferred to Step 4 once the user has supplied a real credential.
4. **Map every field the fixed shape needs** to this source's native field paths: `id`, `title`, `authors` (list of display names), `year`, `venue`, `doi`, `abstract`, `url`, plus the constant `source` key. Note any source-specific bonus fields worth carrying through on top of the fixed shape (the plan's precedent: OpenAlex adds `cited_by_count` and `is_oa`) — allowed, never required.
5. **Identify the true total-match count field** (for `meta.total_available`) and confirm it reflects the *actual* number of matches, not just the current page size — this is load-bearing for the PRISMA Identification box and must never be silently under-reported when `--limit` truncates.
6. **Rate limits and etiquette:** requests-per-second/day limits, any `mailto=`/contact-header "polite pool" convention, and what a 429 response looks like (`Retry-After` header or not) — `_shared.py`'s `http_get_with_backoff` already handles the retry/backoff mechanics generically, so you only need the source-specific status-code mapping.
7. **Check access terms.** Fetch the provider's API terms of use / developer agreement page.
   - If the API requires a paid subscription the user doesn't have, or login credentials beyond a documented API key/token, that's expected for institutional sources (Scopus, WoS) — proceed, but flag in `url-reference.md` and `SKILL.md` that this connector is credential-gated and per-call cost or seat limits may apply.
   - If the terms prohibit automated/programmatic access outright even with a valid credential, **stop**: tell the user plainly and do not scaffold the connector. This pipeline's untrusted-content and reproducibility guarantees (see `SECURITY.md`) assume every connector's access is legitimate under its own provider's terms.
8. **Note quirks that change code:** two-step fetch (PubMed-style search-then-fetch-by-id), XML vs. JSON response format, a "preprint / not-yet-peer-reviewed" flag worth surfacing (arXiv precedent), or a full-text-availability flag (Europe PMC precedent) useful for PRISMA's "reports not retrieved" bookkeeping.

Record everything found — exact endpoint URLs, parameter names, field paths, pagination mechanics, rate limits, quirks — you will write it into `url-reference.md` in Step 3. Do not proceed to scaffolding on assumptions; if a docs page was ambiguous, fetch a second real response to confirm.

---

## Step 3: Scaffold the Connector

**Canonical reference:** read `connectors/openalex.py` and `connectors/_shared.py` in full before generating — `openalex.py` is the worked example of a keyless source with cursor pagination and a `detail` endpoint; skim `connectors/pubmed.py` too if the new source needs a two-step XML fetch. Copy their architecture and their use of `_shared.py`'s helpers, not their source-specific parsing.

Create these three artifacts:

### 3a. `connectors/<name>.py`

Must honor the connector contract exactly (this is what `tools/check_connector_contract.py` verifies in CI):

- **Invocation:** `python3 -m connectors.<name> <search|detail> [flags]`, parsed via `_shared.build_arg_parser(SOURCE_KEY)` — do not hand-roll argparse; the shared scaffold already gives you `--query`, `--query-file`/`--source-key` (reads a pre-built query string out of `search_plan.json` — the actual reproducibility path `/litreview-search` uses), `--limit`, `--page`, `--cursor`, `--since`, `--until`, `--format json|table|plain` (default `json`), `--out <path>`, and `detail <id>`.
- **Fixed JSON output shape**, identical to every other connector:
  ```json
  {"meta": {"source": "...", "query": "...", "retrieved": 100, "total_available": 4213, "truncated": true, "fetched_at": "..."},
   "results": [{"id": "...", "title": "...", "authors": [...], "year": 2023, "venue": "...", "doi": null, "abstract": "...", "url": "...", "source": "..."}]}
  ```
Build it with a small `_meta(query, retrieved, total_available, truncated)` helper (using `_shared.utc_now_iso()` for `fetched_at`) and a `<source>_to_result(raw)` mapper function, mirroring `work_to_result` in `openalex.py`. Emit through `_shared.write_output(payload, args.format, args.out)`, which calls `validate_output_shape` for you — never print raw JSON directly.
- **Missing fields are `None`/`[]`, never a crash and never a dropped key** — every one of the required result keys (`id`, `title`, `authors`, `year`, `venue`, `doi`, `abstract`, `url`, `source`) must always be present, even when the upstream field is absent.
- **Errors go to stderr only**, via `_shared.write_error(message, code)` then `sys.exit(1)` — never write an error to stdout. Codes: `RATE_LIMITED`, `INVALID_QUERY`, `MISSING_CREDENTIALS`, `UPSTREAM_ERROR`. Map the source's real HTTP status codes to these (400/422 → `INVALID_QUERY`, 429 after retries exhausted → `RATE_LIMITED`, other 4xx/5xx → `UPSTREAM_ERROR`), following `openalex.py`'s `_request`/`_fail` pattern.
- **Retry/backoff is already written once** in `_shared.http_get_with_backoff` — call it, don't reimplement exponential backoff + jitter per connector.
- **User-Agent** via `_shared.build_user_agent()`, which honestly names the tool plus a contact email (from `PRISMA_CONTACT_EMAIL`, defaulting to a placeholder) — never a browser-impersonating string.
- **Credentials only via environment variable**, per the rule in Step 3's Credential Rule box below.
- **Two-step or XML sources:** if the API returns XML (like PubMed's `esearch`/`efetch`) or requires a two-step search-then-fetch, use the stdlib `xml.etree.ElementTree` (already the pattern in `connectors/ pubmed.py` and `connectors/arxiv.py`) — do not add a new XML-parsing dependency for this.

#### Credential Rule (identical to `add-portal.md`'s rule for portal skills)

A connector that needs an API key or token reads it **only** from an environment variable named `<SOURCE>_API_KEY` (matching the shipped convention: `NCBI_API_KEY`, `S2_API_KEY`) — never hardcode it, never accept it as a CLI flag (flags leak into shell history and process listings), and never write a real credential into `url-reference.md`, a `SKILL.md` example, a test fixture, or any committed file. If the variable is unset, exit `1` with the standard stderr JSON error and code `MISSING_CREDENTIALS`, naming the exact variable to set — never fall through to an unauthenticated request that fails confusingly. `.gitignore` already covers `.env`/`.env.*`; do not commit one. If the source allows degraded keyless access (like OpenAlex's optional `mailto=` polite pool), degrade gracefully instead of requiring the key.

### 3b. `.agents/skills/<name>-search/SKILL.md`

Read `.agents/skills/openalex-search/SKILL.md` first — copy its structure.

- **Frontmatter:** `name: <name>-search`, `version: 1.0.0`, a `description` written for skill triggering (name the discipline/coverage from Step 1.5, plus trigger phrases: "search <source>", "<source> search", "literature search", "systematic review search"), `context: fork`.
- **Body:** what this connector searches and how it differs from the six shipped ones (Step 1.5's coverage note); the `search`/`detail` command reference with flags; 3-5 usage examples using real query syntax for this source (native filter syntax **and** a bare-keyword form, if the source supports both, mirroring `openalex-search/SKILL.md`'s two examples); an Output section restating the fixed `{meta, results}` shape and this source's specific error codes; and, if Step 1.3 found a credential is needed, a **Setup** section naming the exact environment variable to export and any per-call cost or institutional-seat implication — stated where the user reads it before running the skill, not after.

### 3c. `.agents/skills/<name>-search/url-reference.md`

The endpoints, parameters table, pagination mechanics, rate limits, and response-structure notes recorded in Step 2 — this is the file a future maintainer needs when the provider changes its API. Include the exact field paths used in the `<source>_to_result` mapper so a schema change is easy to diagnose against this doc.

### 3d. `tests/test_connector_<name>.py` + fixtures

Read `tests/test_connector_openalex.py` first — copy its structure: patch `connectors._shared.requests.get` (never make a live call in a test), build a `_fake_response()` helper, and cover:
- the `<source>_to_result` mapper against a full record (all fields present) and a sparse one (missing fields map to `None`/`[]`, not a crash);
- `cmd_search` producing output that passes `_shared.validate_output_shape`, with the correct `meta.total_available`/`truncated` from a capped `--limit`;
- pagination (whichever mechanism Step 2 found — cursor-following or offset paging — exercised across at least two simulated pages);
- error mapping: a 429 response → `RATE_LIMITED` on stderr with exit 1; an invalid-query-shaped 4xx → `INVALID_QUERY`; if credentialed, an unset env var → `MISSING_CREDENTIALS` without ever making a request.

The fixture JSON file(s) these tests load (`tests/fixtures/<name>_search.json`, and `tests/fixtures/<name>_detail.json` if `detail` returns a distinct shape) are placeholder-shaped from the docs at this point — **Step 4 replaces them with a real captured response**, so don't over-invest in guessed field values here.

---

## Step 4: Live Test Run (MANDATORY)

Never register a connector that has not returned a real response. Docs and guessed field mappings routinely miss quirks — a differently-cased field, an undocumented null, an encoding issue — that only show up live.

1. **Capture the raw upstream response first** — not the connector's normalized output. Every shipped fixture (`tests/fixtures/ openalex_search_response.json`, `pubmed_esearch.xml`, `arxiv_search.xml`, ...) is the *unmapped* body the API actually returned, because that's what `test_connector_<name>.py` (Step 3d) patches `requests.get` to return before exercising `<source>_to_result`. Get it with a direct fetch of the exact request URL Step 2 identified (WebFetch, or `curl` with the same params/headers your connector sends), saved as `tests/fixtures/<name>_search.json` (or `.xml`). If the source needs an API key, confirm the user has exported it first (`echo $<SOURCE>_API_KEY
   | head -c1` to check non-empty without printing the secret) — never
proceed with a fabricated fixture standing in for a real captured one.
2. **Separately, run the connector itself** to verify the normalized shape, writing to a scratchpad path, not `tests/fixtures/` (`--out` always emits the validated `{meta, results}` JSON and ignores `--format`, so never combine `--out` with `--format table`/`plain` expecting rendered text):
   ```bash
   python3 -m connectors.<name> search --query "<test query>" --limit 5
   ```
Inspect the printed JSON. Verify: titles and abstracts are real text (not HTML-escaped, not truncated mid-sentence, not empty strings), `year` is a plausible integer, `doi`/`url` resolve to something real, `authors` is a non-empty list of display names when the source has authors. If anything is wrong, fix the mapper in `connectors/<name>.py` and re-run from Step 4.1 if the raw fixture itself needs re-capturing, or just this step if only the mapper changed — iterate until clean.
3. **Run `detail` on one real id** taken from the search results just inspected, as readable text:
   ```bash
   python3 -m connectors.<name> detail <id> --format plain
   ```
Verify the description/record is complete and matches the same field mapping, then capture its raw response the same way as Step 4.1 into `tests/fixtures/<name>_detail.json` (or `.xml`) if its shape differs from the search response. If this source has no standalone detail endpoint (some don't), note that in `url-reference.md` and have `cmd_detail` return a clear `INVALID_QUERY`/not-supported error rather than a silent empty result.
4. **Update `tests/test_connector_<name>.py`'s assertions** (from Step 3d) to match the real values now in the captured fixtures — field values, pagination-cursor/token shape, the true `total_available` — then run:
   ```bash
   python3 -m unittest tests.test_connector_<name> -v
   ```
5. **Keep volume low during iteration** - a handful of requests, not a crawl. If the source rate-limits you mid-test, back off and tell the user; do not loop retries aggressively against a live API.

Do not proceed to Step 5 until search, detail (or its documented not-supported error), and the unit tests all pass against real captured data.

---

## Step 5: Register

1. **Confirm auto-discovery.** No core-pipeline file needs editing — run:
   ```bash
   python3 -m connectors.registry --list
   ```
and verify `<name>` (or its `SOURCE_KEY`) now appears, picked up purely by `registry.py`'s glob over `connectors/*.py`. If it does not appear, the module likely has an import-time error — run `python3 -c "import connectors.<name>"` directly to surface it, fix it, and re-check.
2. **If this connector needs an API key**, remind the user now:
   - Export `<SOURCE>_API_KEY` in their shell (or a local, gitignored `.env` the user sources themselves — this repo doesn't auto-load `.env` files) before the first real `/litreview-search` run that includes this source.
   - Never commit the real key anywhere — not in `url-reference.md`, not in a `SKILL.md` example, not in a test fixture.
   - If per-call cost or an institutional seat limit applies (Step 2.7), restate it here so the reminder lands right when it's actionable.
3. **Add the Bash allowlist entry.** `.claude/settings.json` pre-approves Bash commands one entry per connector module (`Bash(python3 -m connectors.<source>:*)`) — this is the one file registration *does* touch, and deliberately: add
   ```json
   "Bash(python3 -m connectors.<name>:*)"
   ```
to its `permissions.allow` list, next to the six shipped entries. If Step 0/Step 5.1 required creating or extending `connectors/registry.py`'s `--list` flag, also confirm `Bash(python3 -m connectors.registry:*)` is present, adding it if not. `SECURITY.md` notes a future `tools/security_guards.py` CI job is meant to catch an allowlist widening that lacks justification — this one is justified (a new connector module needs its own invocation allowed) and should be called out as such in the PR/commit, not left for that check to question.
4. **New runtime dependency?** Only if the source's response format genuinely needs one beyond stdlib + `requests` (rare — XML sources use `xml.etree.ElementTree`, already stdlib). If one was truly necessary, add it to `requirements.txt` and say so explicitly in the summary.
5. **CI coverage is automatic.** The `discover-connectors` CI job globs `connectors/*.py`, so `tools/check_connector_contract.py` and `python3 -m unittest discover` pick up the new connector's test file on every push without editing `.github/workflows/ci.yml`.

---

## Step 6: Confirm

Present a summary:

> **Connector `<name>` generated and verified.**
>
> - Files: `connectors/<name>.py`, `.agents/skills/<name>-search/` (SKILL.md, url-reference.md), `tests/test_connector_<name>.py` + `tests/fixtures/<name>_search.json` - Live test: `search "<test query>"` returned `<N>` real results (`total_available: <T>`); `detail` verified on one real id - Registered: `python3 -m connectors.registry --list` shows `<name>` automatically (discovery needed no pipeline-logic edit); one line was added to `.claude/settings.json`'s Bash allowlist for the new module - Credentials: `<SOURCE>_API_KEY` required, set via environment variable only <or: "none — keyless access">
>
> Try it: `python3 -m connectors.<name> search --query "<test query>" --format table`
>
> This source is now available to `/litreview-search` for any review topic in this fork. If it's an institutional-access connector, per `CONTRIBUTING.md` it stays in your fork rather than being PR'd upstream — only the `/litreview-add-source` generator itself is the mergeable, universal part.

---

## Design Principles

- Investigation before scaffolding: this command never generates a field mapper from guesses about a docs page — Step 2 fetches real documentation and a real response first, and Step 4 proves it against a live query before anything is registered.
- The fixed `{meta, results}` shape keeps every connector interchangeable for `/litreview-search`, `synthesis/`, and any future consumer: same commands, same flags, same output shape, same error convention, same retry/backoff (`_shared.py`, written once).
- `total_available`/`truncated` are load-bearing, not cosmetic — a `--limit`-capped run must never silently under-report the true match count the PRISMA Identification box needs.
- Access rules are surfaced, not silently bypassed: a provider whose terms prohibit automated access outright is declined at Step 2.7, not scaffolded and hoped past.
- Credentials live in the environment, never in the repo: a generated connector reads its key from an environment variable, fails loudly with `MISSING_CREDENTIALS` when it is unset, and never commits one. Per-call cost or seat limits are disclosed before the connector is generated, not discovered afterwards.
- No pipeline-logic edit is needed to add a source: `connectors/registry.py` discovers by glob, so `/litreview-search` and this command's own `--list` both pick up a new connector the moment its file exists and imports cleanly. The one file that *is* touched, deliberately, is `.claude/settings.json`'s Bash allowlist (Step 5.3) — permission scope, not pipeline logic.
