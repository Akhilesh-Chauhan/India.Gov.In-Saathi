# 12. Rewriting the partially grounded cases so every claim is grounded (started 4 Nov 2026)

## The ask

After document 11, 220 test cases (208 queries, 12 conversation scenarios) were "partially grounded": some of the facts
behind their expected answer are in the bot's index or API data, some are not. The owner asked for these to be
recreated so that they become fully grounded, and explicitly not by trimming alone: the question itself may be rewritten
so that a good answer draws on more of what the index actually holds. Keeping the ID, persona, language, style and the
"Answer / Behaviour / Fail if" shape is preferred but not mandatory.

## How it is done

| Step | Where | What |
|---|---|---|
| 1. Briefs | `artifacts/scripts/make_rewrite_briefs.py` -> `artifacts/data/rewrites/briefs/batch_01..15.md`, `batch_mt.md`, `cases.json` | One brief per case: dimensions, current query and expected answer, Behaviour and Fail-if, every fact marked FOUND (with index page and quote) or MISSING, the index pages that must be read, candidate pages on the same sites ranked by title/URL keyword overlap, and the site folders to grep. 14 cases per batch, grouped by source site. |
| 2. Rules | `artifacts/data/rewrites/AUTHORING_GUIDE.md` | What may be used as evidence (only `citizen-guide-indexed-data/` and `artifacts/data/api_snapshots/20261104/`), what to keep, how to rewrite, quote rules, the output JSON shape. |
| 3. Authoring | general-purpose agents, one per batch | Each reads the guide and its brief, reads the pages, rewrites query and expected answer, attaches a verbatim 40-400 character quote per fact, writes `artifacts/data/rewrites/batches/<batch>.json`, runs the verifier and fixes failures. |
| 4. Verification | `artifacts/scripts/verify_rewrites.py` -> `artifacts/data/rewrites/verification.json` | Mechanical: the named page exists, the quote is on it after normalisation, every number in the fact is in the quote, the fact sentence is in the expected answer, at least two facts. A case passes only when every fact passes. |
| 5. Workbook | `artifacts/scripts/build_indexed_workbook.py --rewrites` -> `golden_test_cases_indexed_v2_<date>.xlsx` | The 140 already-grounded cases plus every rewritten case that passed, with new query, expected answer and index evidence; `Owner sign-off` = "PENDING: rewritten for index grounding"; a "Rewrites for sign-off" sheet shows old and new side by side with the reason. |

The rewritten goldens are the quality engineer's work, not the owner's; they must be signed off before results on them
are reported as golden results.

## Results for the 208 queries (5 Nov 2026)

All 208 partially grounded queries were rewritten and pass both checks. None had to be marked "could not rewrite".

| Measure | Value |
|---|---|
| Queries rewritten and verified | 208 of 208 (P0 65, P1 80, P2 63) |
| Languages | English 117, Hindi (Devanagari) 57, Hinglish 34; every row kept its language |
| Facts in the expected answers | 1,277 (3 to 7 per case; 88 cases have 7) |
| Facts carried over from the original evidence | 506 |
| Facts newly mined from the index | 771 |
| Facts resting on an API record | 10 |
| Index folders used | 94 (incometax 107 facts, pmkisan 88, uidai 86, sarathi.parivahan 58, epfo 55, nfsa 46, ihmcl 42) |
| Query text changed | 10 (Q-076, Q-102, Q-152, Q-165, Q-236, Q-243, Q-313, Q-330, Q-349, Q-469) |
| Behaviour text written or edited | 155 (95 originals had only a one-line expectation, now in the standard shape) |
| Fail-if text written or edited | 120 |

**Why so few queries changed.** In most cases the "missing" facts were not missing from the index at all: the golden
check had quoted a page the crawler did not take (often a PIB release), while the same fact sits on another indexed
page (an operational-guidelines PDF, an FAQ, a Hindi copy, a citizen's charter). The authors found those and kept the
question. Where the index truly lacks the content, the question moved to the angle the index answers:

| Case | Original question | Rewritten question | Why |
|---|---|---|---|
| Q-165 | PM-Kisan helpline number | Where to complain / whom to contact | No PM-Kisan helpline number on any indexed page |
| Q-236 | How much honorarium does an ASHA get | Is it a fixed salary or per activity | No ASHA incentive amounts indexed |
| Q-243 | PMAY-U 2.0 interest subsidy amount | Is the subsidy still available, what changed | PMAY-U 2.0 ISS terms only in an unindexed PDF |
| Q-102 | 8th CPC terms of reference and timeline | When constituted, who heads it, what done so far | ToR only in an unindexed PIB release |
| Q-152 | When the repo rate last changed | Last and next MPC meeting dates | No indexed page says when the rate changed |
| Q-349 | When Haj 2027 applications open | What was the last date, can I still apply | Opening date only on unindexed circulars |
| Q-313 | IEC fee | What is needed before applying | Fee rules only on unindexed DGFT PDFs |
| Q-330 | Does myScheme store my data | What details it asks, does it save the profile | Privacy Policy not indexed |
| Q-469 | PAN deadline, income above exemption limit | PAN deadline, turnover above Rs 5 lakh | That table row lost at a chunk boundary |
| Q-076 | How much PF for a daughter's marriage | Can I, how much, how to apply | Only the older para 68K amount rule is indexed |

## Quality checks

1. **Quote check** (`verify_rewrites.py`): every fact's quote is on its named page or API record, the page URL matches,
   every number in the fact is in the quote, the fact sentence appears in the expected answer. 208 of 208 pass, 0 warnings.
2. **Answer check** (`artifacts/scripts/qa_rewrites.py` -> `artifacts/data/rewrites/qa_report.json`): every sentence in
   the Answer and Acceptable-examples parts is one of the facts (tested with a planted helpline sentence, which it
   catches), every number in those parts is in some quote, query language matches the row, 2 to 7 facts, and no two
   queries in the final set share text (the harness matches answers by query text). 208 of 208 pass. Three pilot cases
   written before the 7-fact cap (Q-067 8, Q-203 12, Q-249 10 facts) were trimmed by hand to 7; the dropped facts are
   named in each case's notes.
3. **Reading check**: the 10 changed questions were read against the originals for persona voice and realism.

## What the owner should look at first

- **Stale values the index still holds.** Where the only indexed value is older than what the golden check found,
  the fact says so ("the indexed page, crawled ..., gives ...") and the Behaviour requires the caveat: Q-323 Haryana
  pension Rs 1,800 (w.e.f. 2017), Q-490 NFSA Rs 3/2/1 prices, Q-034 and Q-410 FASTag annual pass Rs 3,000, Q-075 and
  Q-076 the older para 68K withdrawal rule, Q-082 EDLI 2021 values, Q-056 PAN-Aadhaar late fee, Q-308 MUDRA
  collateral-free limit. These test whether the bot presents old text as current.
- **Re-angled behaviour.** Q-033 (driving-school test exemption rumour: nothing indexed, so the bot must not confirm
  it and must give the learner-licence route), Q-245 (PMAY-G completions: no figure indexed, so the bot must point to
  the dashboard and not invent one), Q-292 (SSC CGL result date: none indexed), Q-153 to Q-155 (24th PM-Kisan
  instalment: not in the index, so the 23rd of 20 Jun 2026 is the latest the bot can show).
- **Fail-if clauses removed** because they would have penalised the bot for repeating its own indexed text, for
  example Q-315 (2020 PMEGP guideline wording) and Q-032 (the Sarathi FAQ itself gives 16 years for gearless 50cc).

## Results for the 12 conversation scenarios

All 12 partially grounded scenarios (MT-01, 02, 04, 06, 07, 08, 09, 12, 13, 14, 15, 17; 36 turns) were rewritten and
pass the quote check: 81 facts, 5 to 7 per scenario. No user turn was changed; every turn keeps its language and the
flow (clarifying question, fitting route, intermediary or fake-site edge, what happens next). The turns' expected
behaviour now quotes only indexed facts: for example the IPPB doorstep life certificate at Rs 70 (MT-13), the CSC
charge of Rs 30 for NSP (MT-12), KRPH 14447 from the 2023 PMFBY guidelines on agriwelfare.gov.in (MT-04), and the
20-day escalation rule from EPFO's FAQ (MT-14). Every number in a turn that no quote carries was checked by hand: they
are the export label, a scheme name (EPF Scheme 1952 / 2026), the guardrail tag G14, or a figure the user states (the
Rs 499 look-alike fee, the Rs 500 cyber-cafe demand, the father's age of 82).

The authoring agent for this batch was cut off by the usage limit after writing the file and before its final review;
the quality engineer finished the review by hand on 5 Nov 2026. Scenario-level notes worth the owner's eye: MT-01 turn 3
now gives the Aadhaar App labels (the myAadhaar portal pages are not indexed); MT-07 relies on cybercrime.gov.in's 1930
sheet headed "For Delhi Only" (the same advice is national on sancharsaathi.gov.in); MT-13 grounds the 80+ October
window on an older DoPPW booklet; MT-14 turn 2 no longer states withdrawal limits because the EPF Scheme 2026 rules are
not indexed; MT-12 turn 1 handles the NSP renewal deadline of 31 Oct 2026 having passed.

## The v2 workbook

`golden_test_cases_indexed_v2_20261105.xlsx` (repository root), built with
`artifacts/scripts/build_indexed_workbook.py --rewrites` and recalculated with LibreOffice (878 formulas, 0 errors).

| Measure | v1 (`golden_test_cases_indexed_20261104.xlsx`) | v2 |
|---|---|---|
| Queries | 139 | **347** of 509 (P0 113, P1 126, P2 108) |
| of which signed-off grounded / behaviour only / rewritten | 115 / 24 / 0 | 115 / 24 / **208** |
| Conversation scenarios | 1 (2 turns) | **13** of 17 (38 turns) |
| Index sites with a query | 43 of 726 | **108 of 726** (618 without) |
| Owner sign-off pending | 0 | 220 |

Coverage of the v2 set (kept / all 509): identity & documents 37/46, provident fund & pension 36/49, developer seed
44/48, tax & GST 20/23, food & grievance 23/38, agriculture 20/38, education 19/26, banking 13/34, housing 9/14; English
202/296, Hindi 79/117, Hinglish 66/95. Dropped: the 160 "not grounded" queries and 2 "grounded except manual" queries,
and scenarios MT-03, MT-10, MT-11, MT-16, none of which was in scope for this rewrite.

What changed in the workbook: the 208 rewritten rows in "Test Queries" carry the new query and expected answer, the
index evidence in "Golden sources (verified URLs)", the status "Rewritten to index-grounded facts", and "Owner
sign-off" = "PENDING: rewritten for index grounding"; the 12 scenarios' turns are replaced in "Conversation Scenarios";
"Final golden" mirrors both; a new "Rewrites for sign-off" sheet lists all 220 with old and new query, old and new
expected answer, fact count, evidence, notes and dimension changes; "Index grounding" marks them "yes (rewritten,
pending sign-off)"; "Index sites" counts the sites the rewrites use. The harness loads it (`load_rows()` 347 rows,
`load_scenarios()` 13 scenarios, 38 turns); every rewritten row's text matches its batch file and all 347 query texts
are unique.

```bash
cd eval
export GOLDEN_WORKBOOK=/home/user/Documents/India.Gov.In-Saathi/golden_test_cases_indexed_v2_20261105.xlsx
../.venv/bin/python collect.py --run indexed-v2-<date>
../.venv/bin/python collect.py --run indexed-v2-<date> --scenarios
../.venv/bin/python run_eval.py --run indexed-v2-<date>
```

Results on the rewritten rows can be filtered with the "Owner sign-off" column until the owner approves them.

## Reproduce

```bash
.venv/bin/python artifacts/scripts/make_rewrite_briefs.py /home/user/Documents/India.Gov.In-Saathi 14   # briefs
# authoring: one agent (or person) per brief, following artifacts/data/rewrites/AUTHORING_GUIDE.md
.venv/bin/python artifacts/scripts/verify_rewrites.py /home/user/Documents/India.Gov.In-Saathi           # all batches
.venv/bin/python artifacts/scripts/qa_rewrites.py /home/user/Documents/India.Gov.In-Saathi
.venv/bin/python artifacts/scripts/build_indexed_workbook.py /home/user/Documents/India.Gov.In-Saathi --rewrites
# then LibreOffice recalculation of a copy outside the repo, as eval/build_reports.sh does
```

Cost note: authoring took 16 agent runs of roughly 220,000 to 420,000 tokens each, and several were cut off by the
5-hour usage limit and resumed. The owner asked on 5 Nov 2026 that any further agents run on Opus at max effort and,
later, that no more agents be used; the scenario review and everything after it were done by hand.

## Owner decisions (5 Nov 2026)

1. **Sign-off given for all 220 rewrites.** Recorded in `artifacts/data/rewrites/signoff.json`, which the builder reads:
   'Owner sign-off' now reads "approved (rewrite, 05 Nov 2026)" in "Test Queries", "Conversation Scenarios" and "Final golden".
2. **Stale values are correct as written.** Where the index still holds an old value (Haryana Rs 1,800 of 2017, NFSA
   Rs 3/2/1, FASTag Rs 3,000, older EPF para 68K, EDLI 2021), the expected answer states it as what the indexed page
   says and the bot must give the caveat. This is the intended test of whether the bot presents old text as current.
3. **Q-033 and Q-245 re-angled expectations accepted.**
4. **The 160 not-grounded queries and MT-03, MT-10, MT-11, MT-16 stay out of scope for now.**

## Correction after sign-off: Q-323 (5 Nov 2026)

The 10-query test run showed the bot answering Rs 3,000 a month for Haryana's Old Age Samman Allowance from its
myScheme record (`api-myscheme-search/oasas.json`). The rewrite had used only the indexed haryana.gov.in page (Rs 1,800
w.e.f. 01-11-2017) and its Fail-if wrongly called Rs 3,000 stale. Under decision 2 the bot's own figure is the right
answer, so Q-323 now expects the myScheme figure with its source and a confirm-with-the-department note, frames
Rs 1,800 as the older indexed rate, and fails only if the 2017 figure is presented as current or an amount is on no
cited source. (The live rate found on 28 Oct 2026, Rs 3,200 w.e.f. 01-11-2025, is in neither source.) A scan of all
220 rewrites for the same pattern, a myScheme record of the same scheme carrying an amount no fact quotes, found no
other case: the Q-249 and Q-250 hits are the old SVANidhi amounts that the newer indexed guidelines supersede.

## Test run on the v2 workbook (5 Nov 2026)

Run `indexed-v2-test-20261105` (eval/runs/): 10 queries chosen across kinds (rewritten Q-006, Q-165, Q-203, Q-323, Q-422,
Q-034; signed-off grounded Q-470, Q-369, Q-101; behaviour-only Q-354), 6 P0 / 3 P1 / 1 P2, 4 English / 3 Hindi / 3
Hinglish. All 10 were answered (4 to 18 s; Q-354 as a clarifying question). Rule checks and the judge ran without
errors; 29 judge calls cost about USD 1.98 at list price. Correctness failed on all 10, mostly for genuine reasons (see
document 9, items 35 to 38): answers end without an official next step, suggested links are unrelated, several answers
retrieve the wrong page. The test also exposed the Q-323 rewrite defect corrected above, and four harness gaps to
decide before the full run.
