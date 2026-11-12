# 11. The index-grounded evaluation dataset (4 Nov 2026)

## Why it exists

The golden set was authored by reading the government websites directly. On 4 Nov 2026 the developers told the team
that the bot's knowledge base does not hold all of that content: crawling permissions under government rules kept
whole sites out and limited others to a few pages. What the bot actually has is the export in
`citizen-guide-indexed-data/` (document 10) plus, for schemes and services, two UMANG production APIs it calls at
answer time (the owner shared both on 4 Nov 2026): the myScheme search API (`myscheme-prod-api.umangapp.in/search/v7/schemes`,
5,150 scheme records with 13 summary fields each) and the UMANG all-services API (`cache.umang.gov.in/core-dept/1.0/allservices`,
281 department records with description, aliases, links and contacts). Evaluating the bot on a question whose answer
is in none of these measures the content gap, not the bot, so the owner asked for a second dataset: only the test
cases whose expected answer is fully grounded in the export or the API data.

The result is `golden_test_cases_indexed_20261104.xlsx` at the repository root. It is a filtered copy of the signed-off
workbook `golden_test_cases_final_20261028.xlsx`; nothing in a kept row's question, expected answer or evidence was changed.

## How a test case was judged

The golden check (document 4) left, for every test case, the list of facts behind its expected answer with the exact
quote and URL that supports each one (`eval/runs/golden-20261027/out/<ID>.json`). Those quotes are the evidence the
evaluation relies on, so the test is: can each quote be found in the index text?

`artifacts/scripts/ground_in_index.py` does this for all 2,732 facts of the 526 test cases. The two API responses are
snapshotted by `artifacts/scripts/fetch_api_snapshots.py` into `artifacts/data/api_snapshots/20261104/` (keys live only in
`eval/.env` as `MYSCHEME_API_KEY` and `UMANG_API_KEY`) and loaded as two extra "sites", one page per scheme or department,
so a fact that cites myscheme.gov.in or web.umang.gov.in is looked up in them like any other.

1. **Text normalisation.** Quote and page text are NFKC-normalised, lower-cased and reduced to letters, digits and Indic
   marks. Spacing, punctuation, markdown tables and line breaks therefore do not matter; a changed number does.
2. **Page text.** A page's chunks are joined in order. The chunker repeats the tail of one chunk at the head of the next
   (and some chunks are duplicated), so the repeated part is dropped before joining; otherwise a quote that spans two
   chunks would never match.
3. **Where to look, in order:** the page the golden check cited (exact URL, then the same path without `/en/`, then a
   copy of the same path under another language prefix such as `/hi/`); any other page of the same site folder; any
   page of any other site. A hit anywhere counts as grounded, and the place is recorded.
4. **Sentence pieces.** If the whole quote is not found, its sentences (pieces of 30+ normalised characters covering
   at least 70% of the quote) must all be on one page. This catches quotes the checker assembled across line breaks
   or table cells; 30 facts matched this way.
5. **Hand review of API facts.** The golden quotes for UMANG and myScheme came from the public web pages, whose wording
   differs from the API records, so only 4 of the 73 facts that cite those two hosts matched automatically. The other 69
   were read one by one against the API record for that scheme or department: a fact is "found" when the record states
   its main claim (the EPFO record says "Users can check their PF balance, Raise claim ... Check claim status"; the
   NSP record carries the helpdesk e-mail, phone and website; the Ladli Behna record is level State, Madhya Pradesh), and
   stays "missing" when the figure, rate, document list, eligibility condition, count or date the fact asserts is not
   in the record (PMEGP subsidy rates, PM-KISAN's Rs 6,000, PM Vishwakarma's documents, the UMANG home-page service
   counts). 29 found, 40 missing; every verdict with its evidence is in `artifacts/data/api_manual_verdicts.json` and
   in the "Fact grounding" sheet, labelled "API record (reviewed by hand)".
6. **"Acceptable examples (any one of these ...)" rows.** 22 expected answers (scheme-discovery and list questions) say
   that any one correct, cited example satisfies the answer. The grade follows the evaluation: the non-example facts
   must all be found and at least one example must be. The out files mark example facts, so no text matching is needed.
7. **Grade per test case.**

| Grade | Rule | Kept |
|---|---|---|
| fully grounded | every required fact found in the index or the API snapshots, and for "any one example" rows at least one example | yes |
| behaviour only | the expected answer states no fact to find (safety, out-of-scope, abstention, clarify-only rows; `no_facts_reason` in the out file) | yes, flagged |
| grounded except manual | every quoted fact found, but a `manual` fact (checker could not fetch the page) has no quote to test | no |
| partially grounded | some quoted facts found, some not | no |
| not grounded | no quoted fact found | no |

`unsupported` facts (15) are ignored: `golden_check.py apply` removed them from the expected answers.

**Assumptions made, and how to change them.** Behaviour-only cases are included because their expected answers do not
depend on indexed content and dropping them would remove every safety, out-of-scope and abstention test; the grounding
column names them, and `build_indexed_workbook.py --strict` builds the workbook without them. The hand-review verdicts
are data, not code: edit `api_manual_verdicts.json` and re-run to change one. The myScheme search API carries only
summary fields (name, ministry, department, level, category, State, tags, close date, brief description), so facts
about eligibility details, documents, amounts or last-updated dates of a scheme cannot be grounded in it; if the bot
also calls a scheme-detail endpoint, that snapshot can be added as a third "site" the same way.

## Results

### Grades (526 test cases)

| Priority | fully grounded | behaviour only | grounded except manual | partially grounded | not grounded | total |
|---|---|---|---|---|---|---|
| P0 | 38 | 10 | 1 | 65 | 55 | 169 |
| P1 | 39 | 7 | 0 | 80 | 59 | 185 |
| P2 | 38 | 7 | 1 | 63 | 46 | 155 |
| MT | 1 | 0 | 0 | 12 | 4 | 17 |
| **all** | **116** | **24** | **2** | **220** | **164** | **526** |

Kept: **139 of 509 queries** (P0 48, P1 46, P2 45: 115 fully grounded + 24 behaviour-only) and **1 of 17 conversation
scenarios** (MT-05, consumer grievance; 2 turns). Of the 115 fully grounded queries, 19 rest on API records (6 myScheme,
13 UMANG) and 9 are grounded only because one acceptable example is enough (Q-187, Q-282, Q-283, Q-385, Q-387, Q-388,
Q-459, Q-460, Q-461). Before the APIs and the any-one rule were applied the kept set was 116 queries; the APIs added 23,
of which 19 are UMANG or myScheme rows, so 29 of the 48 "DB/API" rows are now in (was 10).

### Facts (2,732)

| Result | Facts |
|---|---|
| found on the cited page (exact URL) | 885 (18 as sentence pieces) |
| found on another-language copy of the cited page (for example `/hi/...` holding the English text) | 64 |
| found on another page of the same site | 93 |
| found on another site (same document indexed under another folder: Form 12 under `dotpension-gov-in` and `cpao-nic-in`, `ir.indianrailways.gov.in` PDFs under `indianrailways-gov-in`, CGST Act under `naa-gov-in`, ...) | 88 |
| found in an API record automatically (quote text in the record) | 4 |
| found in an API record by hand review | 29 |
| **found, total** | **1,163** |
| missing | 1,527 |
| manual fact, no quote to test | 27 |
| unsupported, ignored | 15 |

Where the 1,527 missing facts sit: 1,022 on pages of a site that is indexed but without that page; 239 on sites that
are not indexed at all; 204 on pages or API records that exist but lack the content (the crawler kept a shorter or
older version: 613 characters for the PMFBY home page, 876 for the FASTag booklet PDF, a different table layout for the
Trade Marks fee schedule; or a scheme record whose brief does not carry the detail); 62 on another-language copies
that lack it. By host: pib.gov.in 350, uidai.gov.in 70, egazette.gov.in 59, incometax.gov.in 55, indiapost.gov.in 49,
pmay-urban.gov.in 46, cybercrime.gov.in 35, nsiindia.gov.in 34, dea.gov.in 32, nsap.dord.gov.in 30.

### What the kept set covers (queries kept / in the full set)

| Category | kept / total |
|---|---|
| Index-grounded (developer seed) | 28 / 48 |
| Out of scope, safety & non-ingested sources | 12 / 19 |
| UMANG services (DB/API) | 12 / 18 |
| Provident fund, pension & social security | 11 / 49 |
| myScheme schemes (DB/API) | 11 / 19 |
| Persona variation sets | 11 / 40 |
| Women, children & social welfare | 7 / 23 |
| Education, skills & jobs | 7 / 26 |
| Tax & GST | 6 / 23 |
| Agriculture & farmers | 6 / 38 |
| Food, consumer & grievance | 5 / 38 |
| Discovery, transport & cross-cutting | 5 / 22 |
| Identity & documents | 4 / 46 |
| Guardrail probes | 3 / 16 |
| Health | 3 / 13 |
| Business & entrepreneurship | 3 / 13 |
| Banking, savings & insurance | 2 / 34 |
| State services (ingested State portals) | 2 / 10 |
| Housing, urban & rural development | 1 / 14 |

| Dimension | kept / total |
|---|---|
| English | 85 / 296 |
| Hindi (Devanagari) | 22 / 117 |
| Hinglish | 32 / 95 |
| Marathi | 0 / 1 |
| Scheme / fact detail | 39 / 187 |
| Service procedure | 20 / 99 |
| Current rule or circular | 20 / 86 |
| Service use | 19 / 46 |
| Scheme discovery | 12 / 28 |
| Out of scope | 14 / 21 |
| Personal record | 5 / 15 |
| State-specific | 3 / 13 |
| Insufficient sources | 5 / 7 |
| Adversarial / injection | 2 / 7 |
| Source availability: Crawled | 93 / 434 |
| Source availability: DB/API | 29 / 48 |
| Source availability: Bot registry | 5 / 7 |
| Source availability: n/a or Not available | 12 / 20 |

The kept set leans towards the developer-seed rows (built from indexed chunks, so expected to be grounded), the
behaviour tests and the UMANG/myScheme hand-off rows; the citizen-facing categories that drove the original design
(identity documents, banking, housing, agriculture) are thin. The persona variation groups lose their point when only
some of the four variants survive (VG-09 UMANG passbook and VG-10 senior-citizen schemes are complete; the others are
partial or absent).

### Index sites with a query

The export has **726 sites with indexed pages. 43 of them hold a fact that a kept test case relies on; 683 have no query
in the new dataset.** Both API snapshots are used (UMANG all-services by 13 kept queries, myScheme search by 6). Sites
most used: scholarships-gov-in 14 kept queries, incometax-gov-in 8, epfo-gov-in 6, pmkisan-gov-in 6, uidai-gov-in 6,
passportindia-gov-in 5, nfsa-gov-in 5, then eci, myscheme, socialjustice and wcd with 3 each. Two related counts for context: if the behaviour-only rows are credited to their expected source domain,
seven more sites get a query (amrut-mohua, cbic-gst, indianvisaonline, labour, pensionersportal, pib, sci), so 50 used
and 676 without; and across the whole golden set (all 526 cases) only 123 of the 726 sites appear in any evidence URL
at all. The full per-site table is the "Index sites" sheet and `artifacts/data/index_sites_query_coverage.csv`.

## The new workbook

`golden_test_cases_indexed_20261104.xlsx`, built by `artifacts/scripts/build_indexed_workbook.py` from the signed-off
workbook and `artifacts/data/index_grounding.json`, then recalculated with LibreOffice (670 formulas, 0 errors).

| Sheet | What changed |
|---|---|
| Final golden | dropped rows removed (140 left); new column L "Index grounding (export 3 Nov 2026)"; footer note extended |
| Index grounding (new) | one row per original test case (526): grade, kept yes/no, fact counts by where found (golden page, same site, other site, pieces, API, hand-reviewed), acceptable-example counts, index folders used, the facts NOT in the index or API with their golden URL and page status, manual facts, reason for behaviour-only |
| Fact grounding (new) | one row per fact (2,732): status, example flag, fact, golden URL, quote, result, where found, match type, index file or API record, URL, page language, crawl or snapshot date, whether the golden page is indexed, checker note or hand-review evidence |
| Index sites (new) | the two API snapshots (records, kept queries) then the 726 sites: sourceId, name, domains, pages, chunks, kept queries |
| Read Me | five lines at the top explaining the subset, the API snapshots, the hand review, the any-one rule, counts, and how to run with it |
| Test Queries | 139 rows (was 509); all 40 columns unchanged plus column AO "Index grounding (export 3 Nov 2026)"; the Overall formula, the Y/N and P/F/NA validations and the filter re-pointed at the shorter range |
| Conversation Scenarios | MT-05 only (2 turns); grounding column added; validation re-pointed |
| Personas, Coverage, Guardrails, Summary | COUNTIF ranges re-pointed from row 510 to row 140; Coverage shares now divide by 139 |
| Source Check, Personas, Guardrails text | unchanged |

The harness reads the workbook by header name (`eval/workbook.py`), so the added column is harmless. Verified:
`load_rows()` returns 139 rows with 41 columns and `load_scenarios()` one scenario with two turns.

```bash
cd eval
export GOLDEN_WORKBOOK=/home/user/Documents/India.Gov.In-Saathi/golden_test_cases_indexed_20261104.xlsx
../.venv/bin/python collect.py --run indexed-<date>            # 139 questions
../.venv/bin/python collect.py --run indexed-<date> --scenarios
../.venv/bin/python run_eval.py --run indexed-<date>
```

## Review notes on the matching

- **Cross-site hits in kept cases** were checked by hand: Q-101 (Form 12 content in the DoT pension and CPAO copies),
  Q-472 and Q-474 (Railways citizen charter and GST FAQ PDFs filed under `indianrailways-gov-in`) are the same documents.
  Q-405 is weaker: its fact is the myScheme PM Vishwakarma URL, and the matched quote is scheme text found on
  pmvishwakarma.gov.in; the row is a DB/API "link opens" test, so it stays, flagged in the grounding column.
- **Other-language copies:** Q-009, Q-018 and Q-462 are grounded only through `/hi/...` copies of UIDAI pages that
  carry the English text. The bot can retrieve them; the citation it shows will be the Hindi URL.
- **False negatives are few.** Among the 240 missing facts whose page is indexed, an approximate text test (85% of
  20-character windows present) would turn only two more cases fully grounded (Q-469, Q-507: a PDF table laid out
  differently). The criterion was kept strict.
- **API review calls worth a second pair of eyes:** Q-379 (passport cannot be applied for inside UMANG) is grounded on
  the Passport Seva record listing information services only, not on a sentence saying so; Q-402 (count of Central
  women's schemes) is grounded on the search API's facet counts (Women and Child = 483 in the snapshot, with the level
  filter for the Central-only figure); Q-376 and Q-377 rest on service aliases, with the finer details (9 financial
  years, the input fields) absent from the record. All are flagged in the verdict file.
- **One fact away:** 80 partially grounded cases are blocked by exactly one missing fact (listed in the "Index
  grounding" sheet). Trimming those expected answers to their grounded facts would roughly double the dataset, but it
  changes signed-off goldens and needs the owner.

## Open points for the owner and developers

1. UMANG and myScheme rows: 19 of the 48 DB/API rows remain out because their facts (scheme eligibility details,
   documents, amounts, the PMMVY record's last-updated date, the UMANG home-page counts, UMANG's own description) are not
   in the two APIs. If the bot also calls a myScheme scheme-detail endpoint, share it and those rows can be re-graded.
2. The 80 one-fact-away cases: trim or wait for the next crawl.
3. PIB: 350 missing facts rest on press releases; if PIB cannot be crawled, the freshness tests built on PIB (MSP, DA,
   EPF rate) need another official source or must be dropped from the bot's scope statement.
4. Re-run the three scripts on every new export; the numbers in this document are for the export of 3 Nov 2026 and
   the API snapshots of 4 Nov 2026. The myScheme record for Stand-Up India carries schemeCloseDate 2025-03-31, which the
   golden set (Q-390) does not reflect; worth a check with the owner.

## Reproduce

```bash
.venv/bin/python -I artifacts/scripts/fetch_api_snapshots.py /home/user/Documents/India.Gov.In-Saathi   # keys from eval/.env; ~1 min
.venv/bin/python artifacts/scripts/ground_in_index.py /home/user/Documents/India.Gov.In-Saathi          # ~1 min, 8 cores
.venv/bin/python artifacts/scripts/build_indexed_workbook.py /home/user/Documents/India.Gov.In-Saathi    # add --strict to drop behaviour-only rows
# optional: LibreOffice recalculation as eval/build_reports.sh does (copy the file out of the repo first)
```

Outputs: `artifacts/data/api_snapshots/<date>/` (the API records), `artifacts/data/index_grounding.json` (everything),
`index_grounding_by_case.csv`, `index_grounding_by_fact.csv`, `index_sites_query_coverage.csv`, and the workbook at the
repository root. `artifacts/data/api_manual_verdicts.json` holds the hand-review verdicts and is read by the grounding script.
