# 10. The indexed-data export (`citizen-guide-indexed-data/`)

Added to the workspace on 3 Nov 2026 and studied on 4 Nov 2026. This folder is a text export of the bot's live search
index: what Saathi can actually retrieve from. It is the first time the evaluation side has had the index itself rather
than inferring it from the ingested-sites CSV, the 16 Oct registry and the bot's "Reading N sources" lists.

## What it is

From its `README.md` ("Citizen Guide AI: indexed data export"):

| Item | Value |
|---|---|
| Exported | 2026-11-03T09:19:42Z |
| Index | `chunks-live` (OpenSearch) |
| Websites with indexed pages | 726 (one folder each, named by `sourceId`, e.g. `uidai-gov-in`) |
| Pages | 31,650 (one `.md` file each) |
| Chunks | 283,560 (the README notes the index reported the same number) |
| Websites in the bot's `config/sources.yaml` | 1,015, of which 289 have no indexed pages yet (listed at the end of the README) |
| Size on disk | 576 MB, 32,377 files, all markdown; untracked in git and **not gitignored** (see document 9) |

Embedding vectors are left out; everything else is "exactly as stored in the index, in page order".

## File formats

**`<sourceId>/_site.md`**: site summary (sourceId, domains, jurisdiction, ministry, pages indexed, chunks indexed) and a
table of every page (title, URL, type, chunks, file name).

**`<sourceId>/<slug>--<hash8>.md`**: one indexed page. File name = URL path slug + 8-hex hash (a `-2` suffix marks a
second file for the same URL; 13 URLs have two files).

```
# <page title>

- **Website:** <site name> (`<sourceId>`)
- **url:** https://...
- **docType:** html | pdf
- **language:** en | hi | "hi | en" | "en | hi"
- **jurisdiction:** national | IN-MH | "IN-MH | national" ...
- **ministry:** <code>              (5,669 pages)
- **topics:** government-services, welfare-schemes, ...
- **crawledAt:** 2026-10-13T06:33:04.978Z
- **status:** active
- **pageId:** <32 hex>
- **chunks:** N   - **tokens:** T   - **words:** W
- optional: lastUpdated, dateSource, contentClass, docKind, effectiveFrom, validUntil, issuedOn, note

---

## Chunk 1 of N

chunkId: `<32 hex>` · language: `en` · tokenCount: `391` · contentHash: `<sha256>` · embeddingStatus: `done`

<chunk text, plain>

---
## Chunk 2 of N ...
```

Metadata as found across all 31,650 pages:

| Field | Coverage and values |
|---|---|
| docType | html 24,354; pdf 7,296 |
| language (page) | en 27,989; hi 2,781; "hi \| en" 484; "en \| hi" 396. Chunk-level: en 214,952; hi 37,483 |
| jurisdiction | national 31,417; the rest State codes (IN-MP 32, IN-MH 22, IN-DL 14, IN-RJ 13, ...) sometimes combined with national |
| status | active 31,650 (only active pages were exported) |
| topics | 22 distinct; government-services 25,981 (the default), welfare-schemes 2,145, identity-documents 1,494, disability-welfare 802, law-enforcement 767, agriculture 638, women-child-welfare 497, taxation 476, food-security 408, ration-card 408, employment 396, transport 301, pension 250, education 126, ... |
| ministry | present on 5,669 pages; 21 codes (sje, mea, mha, agri, wcd, finmin, dfpd, mole, railways, uidai, meity, doj, dot, morth, ...) |
| crawledAt | 6 Oct to 3 Nov 2026; 31,512 pages in October, 138 in November |
| lastUpdated | only **4,796 pages (15%)**: 4,598 html, 198 pdf. Years: 2026 3,867; 2025 350; 2024 136; 2023 183; older 260 |
| dateSource | 4,519 pages: none 3,548, http 453, label 323, pdf-info 153, meta 33, jsonld 3 |
| contentClass | 4,519 pages: service 3,931, notice 388, scheme 154, act 46 |
| docKind | 886 pages: order-circular 186, scheme-page 142, news 107, tender-recruitment 89, notification 68, press-release 67, service-page 64, form 60 |
| effectiveFrom / validUntil / issuedOn | 135 / 107 / 45 pages |
| note | 2,113 pages: "N chunk(s) not in the crawl state's chunk list; shown last, in index order" |
| embeddingStatus | `done` on 252,435 chunk lines; the field is **absent on 31,125 chunks**, which are the ones "not in the crawl state's chunk list" (indexed chunks the crawler no longer tracks; ask the developers whether they are searchable and whether they are stale leftovers) |
| chunk size | tokenCount min 2, p10 207, median 425, p90 445, max 450 (chunks are cut at about 450 tokens); mean 379 |

Totals: 107.4 million tokens, 65.1 million words.

## How it relates to the other inputs

| Comparison | Result |
|---|---|
| `eval/bot_sources.json` (registry, 16 Oct 2026, 794 sourceIds) | 617 of the 726 folders are registry sourceIds; 109 folders are sources added after 16 Oct; 177 registry sources have no folder (no indexed pages) |
| `ingested-websites.csv` (14 Oct 2026, 199 domains) | 198 have a folder (`kvs.gov.in` has none). Chunk counts have grown since the CSV: 175,603 chunks for those sites now vs 131,012 then (nfsa 24,145 vs 20,475; agriwelfare 11,777 vs 6,124; wcd 10,811 vs 8,044) |
| `index_seed.json` (developer seed, 16 Oct) | all 39 seed chunk URLs are present as pages |
| UMANG and myScheme | `web.umang.gov.in` has no folder (consistent with "served from DB/API"); `myscheme.gov.in` has only 14 pages (about, FAQs, search, 10 scheme pages) and 141 chunks, so scheme discovery cannot come from this index |

Known duplication inside the export: the same document under two URL spellings is indexed twice with different
pageIds (for example `pmkisan.gov.in/Documents/FAQPMKISAN.pdf` and `.PDF`, each 8 chunks), and `tutorial.gst.gov.in`
pages appear under both `gst-gov-in` and `tutorial-gst-gov-in`.

## What it means for the golden set (analysis of 4 Nov 2026)

Method: every URL in "Golden sources (verified URLs)" and "Index chunk URL" of the final workbook, and every quoted fact in
`eval/runs/golden-20261027/out/*.json`, was looked up in the export. URL match tiers: exact (scheme, www, case,
%-encoding, trailing slash ignored); English-equivalent variant (`/en/` prefix or `index.html` differences); another
language copy only (`/hi/` etc.); page not indexed although the site is; site not indexed. For indexed pages the quote
was searched in the concatenated chunk text after the same normalisation the golden check uses (letters, digits and
vowel signs only). Per-test-case results: `artifacts/data/golden_vs_index_coverage.csv`; per-site summary:
`artifacts/data/index_sites_for_golden_set.csv`.

**Golden pages (per question, 509):**

| Tier | Questions |
|---|---|
| At least one golden URL indexed at the exact URL | 306 |
| Only an English URL variant indexed (`/en/` prefix, case) | 38 |
| No golden URL indexed | 141 (P0 44, P1 50, P2 47) |
| No golden URL on the row (behaviour-only) | 24 |

**Verified facts (2,732):**

| Tier | Facts |
|---|---|
| Page indexed (exact URL) | 1,085, of which the quote is found in the chunk text for 929 and missing for 156 |
| Only another language copy of the page indexed | 130 (quotes mostly missing there) |
| Site indexed, but the page is not | 1,176 |
| Site not indexed at all | 298 |
| No quote (unsupported or manual facts) | 43 |

**Per test case (509 questions + 17 conversations): can the index ground the verified facts?**

| Grade | Cases | Of which P0 |
|---|---|---|
| All quoted facts found in the index | 75 | 19 |
| Some quoted facts found | 197 | 65 |
| Page indexed but the quotes are not in its chunks | 33 | 9 |
| Only another language copy of the page indexed | 7 | 6 |
| Golden pages not indexed | 187 | 59 |
| No quoted facts (behaviour-only) | 27 | 11 |

Read this as an upper bound on what the bot can answer correctly from the index: for 187 test cases (36%), none of the
pages behind the expected answer are in the index, so a correct, cited answer is impossible without a live fetch or
DB/API data. Only 75 test cases have every verified fact present in indexed text.

**Where the gaps are (sites the golden set depends on):**

| Expected site | Golden rows | Pages / chunks indexed | Rows with a golden page indexed | Note |
|---|---|---|---|---|
| uidai.gov.in | 29 | 164 / 537 | 28 (mostly via `/hi/` URLs) | The English pages the golden check quoted (`/en/aadhaar-seva-kendra` fee table, `/en/aadhaar-online-services`, `/en/enrolment-and-update`) are not indexed; the `/hi/...` URLs hold English text but older copies (crawled 8 Oct; `lastUpdated` 2 Jul / 16 Sep 2026). **The UIDAI fee table (Rs 75 / Rs 125, "If done separately") appears nowhere in the export**, nor does the MBU fee-waiver extension OM. The Aadhaar fee questions cannot be answered correctly from this index. |
| pib.gov.in | 23 | 49 / 441 | 2 | Only 13 press releases (PRID pages) indexed; 179 golden PIB URL mentions are missing. PIB is the golden source for MSP, DA, EPF rate, Labour Codes and similar freshness facts. |
| myscheme.gov.in | 25 | 14 / 141 | 7 | 10 scheme pages only; discovery must come from the DB/API |
| web.umang.gov.in | 23 | none | 0 | DB/API by design; hand-off rows cannot be grounded in the index |
| epfo.gov.in | 28 | 218 / 3,018 | 20 | 8 rows' pages missing |
| pmkisan.gov.in | 28 | 48 / 472 | 22 | Includes the 2019 FAQ with the 2-hectare limit ([IDX-STALE] rows) |
| nfsa.gov.in | 18 | 408 / 24,145 | 12 | Mostly evaluation-report PDFs; 344 of 408 pages are PDFs |
| incometax.gov.in | 29 | 467 / 6,457 | 24 | |
| scholarships.gov.in, nsiindia.gov.in, sarathi.parivahan.gov.in, mea.gov.in, ihmcl.co.in, esic.gov.in, nsap.dord.gov.in | 70 | | all rows covered | |
| indianrailways.gov.in | 13 | 246 / 1,851 | 7 | |
| Other hosts behind missing golden URLs | | | | dea.gov.in (30 mentions), indiapost.gov.in (25), egazette.gov.in (16), static.pib.gov.in (12, no folder), doe.gov.in (11), ir.indianrailways.gov.in (11, no folder), backend.uidai.gov.in (10, no folder), myaadhaar.uidai.gov.in (7, no folder), newsonair.gov.in (6) |

Expected source domains with no folder at all: web.umang.gov.in (23 rows), pmjay.gov.in (Q-231, P0), natboard.edu.in
(Q-240), kvs.gov.in (Q-301), digilocker.gov.in (Q-360).

**Freshness cards (G04):** only 15% of indexed pages carry a `lastUpdated` date, and for several golden-critical sites it is
0 pages (pmkisan, myscheme, pib, nfsa, nsiindia, cybercrime, rtionline, pmay-urban, esic). The "document date" the
source card is supposed to show cannot come from the index for those sites; `crawledAt` (fetch date) is always present.

**Index age:** the pages behind the golden set were crawled between 6 and 30 Oct 2026, while the golden check read the
live pages on 27-28 Oct. A fact that changed in October may be current in the golden and stale in the index; the
`[IDX-STALE]` rows in `queries_g.py` were built for exactly this case.

## How to use the export in QE work

- **Explain unanswered questions**: `unanswered_split.py` groups "not answered" cases by the pages the bot said it read.
  With the export, a case can be classified before any run: page in index (retrieval or generation problem) versus page
  not in index (content gap). `artifacts/data/golden_vs_index_coverage.csv` already gives this per test case.
- **Predict Source recall and Freshness outcomes** for the 48 index-grounded rows and the `[IDX-STALE]` traps.
- **Check a fact quickly**: `grep -rl "<words>" citizen-guide-indexed-data/<sourceId>/` shows whether a value exists in the
  index at all (as done above for the UIDAI fee table).
- **Brief the developers**: the per-site CSV lists, for each site the golden set depends on, pages, chunks, crawl window,
  pages with `lastUpdated` and PDF share; the missing-host list above is a crawl backlog (PIB press releases, DEA and DoE
  orders, India Post savings pages, e-Gazette PDFs, backend.uidai.gov.in documents, myaadhaar).
- **Re-run the analysis** after a new export: the scripts used on 4 Nov are kept in
  `artifacts/scripts/` (`scan_index.py`, `golden_vs_index.py`, `coverage_v2.py`); they need the project `.venv` and the
  final workbook.

## Open questions for the developers

1. Are the 31,125 chunks "not in the crawl state's chunk list" searchable, and are they leftovers from earlier crawls
   (possible stale duplicates of current pages)?
2. Why are the English UIDAI pages (`/en/...`) absent while `/hi/...` URLs serve English content? Is the crawler
   following language links, and does it de-duplicate by content hash across URLs?
3. Is PIB crawled by press-release ID at all (13 PRID pages indexed vs 179 golden PIB URLs)?
4. Are `backend.uidai.gov.in`, `static.pib.gov.in`, `ir.indianrailways.gov.in`, `myaadhaar.uidai.gov.in` reachable to
   the crawler? They hold the documents behind many golden facts.
5. Is `lastUpdated` expected to be filled for more pages (15% today), and is the source card showing `crawledAt` when
   it is missing?
