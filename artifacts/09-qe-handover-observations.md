# 9. QE hand-over: state, gaps, risks, next steps

Written 4 Nov 2026. Update the "Run log" and "Open items" sections as work proceeds.

## State of the repository

- Branch `main`, two commits (28 Oct 2026), remote `github.com/Akhilesh-Chauhan/India.Gov.In-Saathi`. Working tree
  clean except `India.gov.in-architecture.html` (untracked diagram added 4 Nov) and this `artifacts/` folder.
- Golden set final and signed off (see document 4). Harness complete (documents 5 and 6).
- No evaluation run folders are in the repository; the October runs (`umang-20261016`, `umang-20261016-pilot`,
  `umang-20261019`, `umang-20261019-regrade-*`) and the feature-probe run live only on the original machine.
- Local environment rebuilt on 4 Nov 2026 (document 7 lists what was verified).
- `citizen-guide-indexed-data/` (576 MB, 32,377 files) was added to the workspace on 3 Nov 2026. It is untracked and
  **not in `.gitignore`**; a plain `git add .` would try to commit it. Decide whether to ignore it or store it elsewhere.

## Run log

| Date | Run | Bot build | Scope | Headline | Where |
|---|---|---|---|---|---|
| 16 Oct 2026 | umang-20261016 (+ -pilot) | UAT, 16 Oct | all questions and conversations, judged | Release criteria not met: unanswered questions the biggest gap, outdated facts (Tatkaal passport fee Rs 2,000 vs 2,500; Aadhaar biometric fee Rs 100 vs 125; Ni-kshay Poshan Rs 500 vs 1,000), missing next steps | not in repo |
| 19 Oct 2026 | umang-20261019 (re-check of 16 Oct) | UAT, 19 Oct | all re-asked; changed answers re-graded; checklist grading | Answers unstable day to day; new defects: internal planning notes leaked to users ("Output language is English per target_language..."), one answer began mid-sentence | not in repo |
| 27-28 Oct 2026 | golden-20261027 | n/a | golden check of all 526 test cases | 2,732 facts tied to official pages; 283 answers rewritten; owner approved all | `eval/runs/golden-20261027/` |
| 5 Nov 2026 | indexed-v2-test-20261105 | UAT, 5 Nov | 10 queries from the v2 workbook (6 rewritten, 3 grounded, 1 behaviour-only), judged with in.anthropic.claude-opus-5 | Pipeline works end to end (29 judge calls, ~USD 1.98, 0 errors). Correctness failed 10/10, mostly genuine: no official next step or link at the end, wrong form set for family pension (Q-101), success story instead of NCH channels (Q-203), Hinglish answered in English (Q-006), fake 'PM Free Laptop Yojana' treated as a State scheme (Q-354), stale instalment count plus a blog citation (Q-422). Suggested links are unrelated sites in alphabetical registry order. Harness gaps to decide before the full run: free-text clarify fields, judge not shown citation-card details, live fetch vs indexed text | `eval/runs/indexed-v2-test-20261105/` |
| 5 Nov 2026 | indexed-v2-recheck-20261105 | same 9 answers + Q-354 re-asked | the 10 test queries re-graded after the three harness fixes (State clarify / State in query, source cards to judges, content from index or API) | Figures-on-cited-pages false failures 3 -> 0; Q-323 citations now pass on the myScheme record; judges now cite the cards; Correctness still 10/10 FAIL, now for the bot's own reasons. Q-354 with 'main Bihar se hoon' denies the Central scheme but invents a Bihar laptop scheme. Live test: the bot accepts {'key': 'state', 'answer': 'Bihar'}. A UMANG gap (service text only in the citation snippet) was fixed and re-checked on Q-369. Self-test 8/9 as before (moved UIDAI URL) | `eval/runs/indexed-v2-recheck-20261105/`, `-recheck-q369/` |
| 5 Nov 2026 | indexed-v2-full-20261105 | UAT, 5 Nov | v2 workbook: 347 queries + 13 conversations (38 turns), judged | Collection: 268 answered, 59 no_answer, 20 'blocked' (the bot's canned guardrail replies for politics, medical/legal advice, emergencies, out-of-role requests); median latency about 9 s. 10 queries stopped at 'which State?' and 2 timed out: per the owner's rule a State was written into those 10 queries (query_edits.json; Uttar Pradesh / Madhya Pradesh for the fake-scheme tests Q-355 / Q-392 because the bot's data has no such State scheme there) and all 12 were re-asked. Judged: every gate missed; accuracy P0 3.5%, P1/P2 9.0%; facts right (ignoring guardrail-only failures) P0 13.3%, P1/P2 23.5%; top causes no official next step (259), required fact missing (206), outdated facts picked from the index (53 rows); conversations 0/13; latency p50 8.0 s / p95 14.2 s; cost USD 73.76. Details in document 13 | `eval/runs/indexed-v2-full-20261105/` |

(Headlines for the October runs come from the narrative hard-coded in `findings_page.py` and `recheck.py`; the numbers
themselves are in the run folders on the original machine.)

## Known gaps and risks

### Golden set

1. **Date-sensitive facts age quickly.** PM-KISAN instalments, DA/DR, NSP and exam deadlines, quarterly small-savings
   rates, MSP, EPF rate, weather bulletins. Re-check before every run (Workflow A); 38 answers in
   `golden_verified.json` were flagged `recheck` and the Read Me lists RE-VERIFY rows.
2. **Three kept answers have figures no fact covers** (`golden_check.py status`): Q-067 (31), Q-092 (12, 26),
   Q-380 (30). Q-380's 30-minute session rule comes from the concept note, which has no public page; the other two
   should be looked at once.
3. **28 manual facts in 18 test cases** (myAadhaar screens behind login/HTTP 500, sites that were down) were approved
   by the owner without machine evidence. Re-try them when those sites are reachable.
4. **Snapshots are not in git** (730 MB). Without them, the evidence hashes cannot be re-verified locally; ask the
   owner for the archive before disputing any quote.
5. **Behaviour-only goldens** (24) and discovery questions with "Acceptable examples" give the judge latitude; expect
   grader disagreement to concentrate there.
6. **State rows** accept two outcomes (a cited answer from a crawled State portal, or a G12 "named not refused"
   reply) because concept note 6.2 excludes State content while State portals are in fact ingested.
7. **Q-318 is Marathi** (not a launch language): it tests the out-of-language behaviour, not Marathi support.

### Harness

8. **`selftest.py` depends on live official URLs.** On 4 Nov 2026 the UIDAI fee PDF at
   `uidai.gov.in/images/Aadhaar_Enrolment__and__Update__-__English.pdf` returned HTTP 503, so the "invented figure"
   check came back NA and the self-test printed FAILED although the harness logic is fine. The current fee sheet is at
   `backend.uidai.gov.in/get/files/media/document/2026-09/Aadhaar_Enrolment__and__Update__-__English.pdf`. Fix: update
   `UIDAI_FEES` in `selftest.py` (and consider serving the planted pages from the fake server so the self-test is
   fully offline).
9. **Judge-vs-human agreement (9.3.4) has not been measured.** The findings page itself says so. Until a spot-check
   reaches 90%, human grading is the release criterion. The tooling exists (`findings_sheet.py --spot-check`,
   `checklist.py agreement`).
10. **Checklist grading is a separate human/agent step**, not automated in `run_eval.py`; statuses in the shared
    reports depend on graders following `checklist_grader.md` consistently (the `checklist_next_step.py` tool exists
    because the "next step" item was read differently across batches).
11. **Cost is estimated at Anthropic list prices** (`judge.LIST_PRICES`) unless `JUDGE_PRICE_IN/OUT` are set. Bedrock
    bills differently. A full judged run with Opus was estimated at USD 100-150; the October budget was USD 200.
12. **Freshness runs only for rows whose Golden-fact status contains "Verified" or "Partly"** (485 of 509 after the
    apply). Response flow runs for 145 rows; Source recall for 48. Rows with Source availability "Bot registry" (7)
    or "n/a" (18) are not required to show a source.
13. **Matching by query text** makes the harness robust to ID shifts but assumes query texts are unique in the
    workbook (they are today).
14. **Figures rule is lexical.** It skips years and user-typed numbers and compares digits only; a figure written in
    words on the page ("two thousand") would be a false FAIL, and a wrong figure that happens to appear elsewhere on a
    long cited page would be a false PASS. The judge's Citation support is the semantic complement.
15. **JavaScript-only pages return NA** for figure and citation checks ("check manually"). The golden check renders
    with Chrome, but `pages.get_page` used by the evaluation does not; a Playwright fallback there would reduce NAs.
16. **Hard-coded narrative in `findings_page.py`** (example IDs Q-022, Q-339, Q-006, Q-358, Q-088; stale-value regexes
    for Q-022/Q-002/Q-238; "what to fix first" text) was written for the October runs. The script warns when an example
    no longer fits its group, but the prose must be reviewed for each new run.
17. **Guardrails that need developer help** cannot be judged from outside: G04 (both dates in the API), G06
    (correction queue), G10 (masking in logs), G13 (MCC mode switch), G15 (planted injection page).

### Bedrock access (checked 4 Nov 2026)

22. **Only the `in.*` India inference profiles are usable with the current credentials.** `test_judge.py` succeeded
    with `in.anthropic.claude-opus-5` and `in.anthropic.claude-sonnet-5`; every `global.anthropic.*` profile (Opus 5.5,
    Opus 5, Sonnet 5.5, Haiku 5.5) returned HTTP 403 "explicit deny in a service control policy". `eval/.env` now sets
    `JUDGE_MODEL=in.anthropic.claude-opus-5` and `JUDGE_FALLBACK_MODEL=in.anthropic.claude-sonnet-5`. Consequences:
    the next run is graded by Claude Opus 5, not the Opus 5.5 used in October (comparability note for reports);
    list price is USD 5 / 25 per million tokens instead of 4 / 20, so expect roughly 25% higher grading cost for the
    same token volume; `judge.py` already handles `in.*` profiles rejecting `output_config.format` by embedding the
    JSON schema in the prompt. The report scripts label the judge from `JUDGE_MODEL` (`recheck.judge_name()`), so
    they will read "Claude Opus 5" automatically; the hard-coded "Claude Opus 5.5" strings in `findings_page.py`
    (pass-rule text) and `split_cost.py` (price comment) need a manual edit.

### What the index export shows (4 Nov 2026, document 10)

23. **Over a third of the golden set cannot be grounded in the bot's index.** 187 of 526 test cases (59 of them P0) have
    none of their verified source pages in the 3 Nov 2026 export; only 75 have every verified fact present in indexed
    text. Expect "could not find" or ungrounded answers on those regardless of model quality; they are content and
    crawl gaps, not retrieval failures.
24. **Specific content gaps with direct golden impact:** the UIDAI fee table (Rs 75 demographic / Rs 125 biometric,
    "If done separately") and the MBU fee-waiver OM appear nowhere in the export; the English UIDAI pages the golden
    check quoted exist only as older copies under `/hi/` URLs. PIB has 13 press releases indexed against 179 golden PIB
    URL mentions (MSP, DA, EPF rate). myScheme has 10 scheme pages. backend.uidai.gov.in, static.pib.gov.in,
    ir.indianrailways.gov.in and myaadhaar.uidai.gov.in are not crawled at all.
25. **Freshness cards cannot be filled from the index for most pages:** `lastUpdated` exists on 15% of pages and on
    none of the pmkisan, myscheme, pib, nfsa, nsiindia, cybercrime, rtionline, pmay-urban or esic pages.
26. **Index age vs golden check:** pages were crawled 6-30 Oct 2026; the golden check read live pages on 27-28 Oct.
    Values that changed in October (for example the 1 Oct 2026 UIDAI waiver extension) are current in the golden and
    absent or stale in the index.
27. **31,125 chunks (11%) are not tracked in the crawl state** (no `embeddingStatus`); 13 URLs are indexed twice; the
    same PDF is indexed under two URL spellings. Ask the developers what these mean for retrieval.
28. The index has grown since the 14 Oct CSV and 16 Oct registry (726 sites with pages, 1,015 configured; 109 sites not
    in the registry snapshot). `eval/bot_sources.json` should be refreshed (`validate_features.py` does this) before the
    next run so Source genuineness does not flag new official sites as "not in registry".

### The index-grounded dataset (4 Nov 2026, document 11)

29. **Only 139 of 509 queries and 1 of 17 scenarios are fully grounded in what the bot can read** (the index export
    plus the myScheme search and UMANG all-services APIs) or test behaviour only. Grading every verified fact's evidence
    quote gives: 116 test cases fully grounded, 24 behaviour only, 2 blocked by a manual fact, 220 partially grounded,
    164 not grounded. 1,527 of 2,689 quoted facts are in neither source; 1,022 of those are on pages the crawler did not
    take from sites it did crawl. The filtered workbook is `golden_test_cases_indexed_20261104.xlsx`.
30. **The kept set is skewed:** 28 of its 115 grounded queries are the developer-seed rows, 24 are behaviour tests and
    23 are UMANG/myScheme hand-off rows; identity documents keep 4 of 46 rows, banking 2 of 34, housing 1 of 14. 19 of
    the 48 DB/API rows stay out because the myScheme search API carries only summary fields (no eligibility detail,
    documents, amounts or last-updated date) and the UMANG API has no home-page counts or self-description.
30a. **The API facts were graded by hand** (69 of 73, `artifacts/data/api_manual_verdicts.json`), because the golden
    quotes came from the web pages and the API records word things differently. Four verdicts deserve a second reader:
    Q-379, Q-402, Q-376, Q-377 (document 11, review notes). The API keys the owner shared are in `eval/.env` only.
31. **683 of the 726 indexed sites have no query in the new dataset** (43 used; 123 appear in any golden evidence
    URL at all). The index is far broader than the golden set, and the golden set is far deeper than the index on
    the sites that matter to citizens (UIDAI, PIB, Income Tax, India Post).
32. **80 partially grounded cases are one missing fact away** from being fully grounded. Trimming those expected
    answers would roughly double the dataset but changes signed-off goldens. 22 expected answers list "acceptable
    examples (any one of these)"; the grading honours that rule, which is what lets 9 list questions stay in.

### The rewritten cases (5 Nov 2026, document 12)

33. **All 220 partially grounded cases were rewritten so every claim is grounded** (208 queries, 12 scenarios, 1,358
    facts with verbatim quotes; 771 of the 1,277 query facts are new). Most "missing" facts were on other indexed pages,
    so only 10 questions changed. The v2 workbook `golden_test_cases_indexed_v2_20261105.xlsx` has 347 queries and 13
    scenarios over 108 index sites. The rewrites are the QE's work: the owner must sign off before results on them
    count as golden results.
34. **The index keeps stale values the bot can repeat** (Haryana pension Rs 1,800 of 2017, NFSA Rs 3/2/1, FASTag pass
    Rs 3,000, older EPF para 68K, EDLI 2021 values). The rewrites state them as "the indexed page gives ..." and the
    Behaviour requires the caveat, so these cases test whether the bot presents old text as current.

### The 10-query test run on the v2 workbook (5 Nov 2026)

35. **Suggested links are unrelated to the question.** On 8 of 9 answers the bot's suggested links were sites such as
    112.gov.in, 8cpc.gov.in and aaccc.gov.in (FASTag and consumer-refund answers) or agmarknet, depwd, eshram: they look
    like the first entries of the source registry in alphabetical order, not links chosen for the question. The judge
    then finds no fitting "official next step" (G07).
36. **An unofficial blog is in the bot's index.** `citizen-guide-indexed-data/mylpg-in/` holds 15 WordPress pages
    ("Scheme Archives - MYLPG", "PM Kisan 24th Installment Date 2026 Important New Update") filed under the name
    "MyLPG (PAHAL DBT subsidy)". Q-422 cited one for the PM-Kisan instalment date; the rule check passed it because the
    domain is in the bot's registry. Raise with the developers.
37. **Harness gaps found** (decide before the full run): (a) `saathi.resolve_clarify` only taps chip options, so a
    free-text clarify field such as "State" stays unanswered (Q-354); (b) the judges see the cited URLs but not the
    citation cards' site name, fetch time and last-updated date, so "no source card" failures in Response flow are partly
    an artefact (same as in October); (c) Figures on cited pages and Citation support read the live page, which can
    differ from the indexed text (Q-165's WhatsApp number is on the indexed agriwelfare page; myScheme pages are
    JavaScript-only, so Q-323's Rs 3,000 shows as unsupported); (d) 112.gov.in timed out from this machine.
38. **Cost:** about USD 0.20 per query at list price, four fifths of it the Citation support check. A full v2 run (347
    queries, 13 scenarios) should cost roughly USD 70 to 80.

### Documentation drift

18. `eval/README.md` is partly stale: it names `../golden_test_cases_phase1.xlsx` as the golden source (config now
    defaults to the final workbook), "120 demo questions", "11 multi-turn scenarios" and "445 rows" (now 169 P0, 17
    scenarios, 509 rows), `cd golden-tests/eval` (old folder name) and judge default `anthropic.claude-opus-5-5`
    (config uses `global.anthropic.claude-opus-5-5`). The top-level `README.md` is current.
19. `GATES.md` records absolute paths from the original machine (`/home/user/NeGD/India.gov.in/golden-tests/eval`).
20. The architecture HTML mentions `scripts/own_scraper.py` and `mvp-llms-full-output/` which are not in this repo.

### Security

21. `eval/.env` holds live AWS keys and the UAT web login. It is gitignored; keep it that way and rotate the keys if
    the file is ever shared. `.env.example` now lists the web-login keys as commented placeholders.

## Suggested next steps (in order)

1. Fix the self-test URL (item 8) and re-run `eval/selftest.py` until it passes, so the environment check is trustworthy.
2. Bedrock access confirmed on 4 Nov 2026 (item 22). Still to do: set `JUDGE_PRICE_IN/OUT` to the account's Bedrock rate card.
3. Re-check the date-sensitive expected answers (Workflow A) and apply to a new final workbook.
4. Smoke-collect 20-25 P0 questions against the current bot build; run `summarize_run.py` and `validate_features.py`
   to see whether the October defects (planning-note leaks, mid-sentence starts, unanswered rate) persist.
5. Full collection, judged grading within budget, facts split, unanswered split, checklist grading, reports.
6. Run the reviewer spot-check and measure judge-vs-human agreement (item 9).
7. Refresh `eval/README.md` (item 18) and the findings-page narrative (item 16) for the new run.
8. Consider: Playwright fallback in `pages.get_page` (item 15); a fully offline self-test (item 8); a unit test for
   `metrics.py` rules using the planted cases from `selftest.py` without network.
9. Share the index-gap findings (items 23-26, `artifacts/data/`) with the developers before the next run, so the run
   measures the bot rather than re-discovering known content gaps; re-run `artifacts/scripts/` on the next export.
10. Decide with the owner and developers on the index-grounded dataset (items 29-32): whether a myScheme scheme-detail
    endpoint exists (it would re-ground the remaining DB/API rows), whether to trim the 80 one-fact-away cases, a second
    reader for the four flagged API verdicts, and whether the next run uses `golden_test_cases_indexed_20261104.xlsx`
    (`GOLDEN_WORKBOOK=`) or the full set with the grounding column as a filter.

## Open items

- [ ] selftest.py UIDAI URL updated
- [x] Bedrock access confirmed on this machine (4 Nov 2026, `in.anthropic.claude-opus-5`; `global.*` profiles denied by SCP)
- [ ] New AWS access key in `eval/.env`. On 5 Nov 2026 at 16:48 IST the key rejected every call ("security token
      invalid" on STS and on Bedrock, for both `in.*` judge profiles), although its last judge call succeeded at
      13:54 the same day and `.env` had not changed since 4 Nov. The key was probably deactivated or rotated on the
      AWS side. No grading is possible until it is replaced.
- [ ] `JUDGE_PRICE_IN/OUT` set to the real Bedrock rate card
- [ ] Hard-coded "Claude Opus 5.5" strings in findings_page.py / split_cost.py updated for the new judge
- [ ] Date-sensitive goldens re-checked (new golden run)
- [ ] Next evaluation run collected and graded
- [ ] Judge-vs-human agreement measured
- [ ] eval/README.md refreshed
- [ ] Decision on `citizen-guide-indexed-data/` in git (ignore or move)
- [ ] Index-gap findings shared with the developers; answers to document 10's open questions recorded
- [x] Index-grounded dataset built (4 Nov 2026): `golden_test_cases_indexed_20261104.xlsx`, document 11
- [x] UMANG/myScheme API snapshots taken and API facts hand-reviewed (4 Nov 2026)
- [ ] Owner decision on the remaining DB/API rows (scheme-detail endpoint?), the 80 one-fact-away cases and the four flagged API verdicts
- [x] 220 partially grounded cases rewritten and verified; v2 workbook built (5 Nov 2026)
- [x] Owner sign-off on the 220 rewrites (5 Nov 2026; `artifacts/data/rewrites/signoff.json`); Q-323 corrected after the test run
- [x] Not-grounded queries and 4 scenarios: owner decided to keep them out of scope for now (5 Nov 2026)
- [x] 10-query test run and re-check after the harness fixes (5 Nov 2026)
- [x] Full evaluation run on the v2 workbook: `indexed-v2-full-20261105` (5 Nov 2026, document 13)
- [x] Ground truth corrected for fixed guardrail replies (6 Nov 2026; owner ruling on Q-351/Q-359; document 13 update)
- [x] Partial-credit scoring for Source genuineness, Source recall, Correctness & behaviour, Response flow and
      Conversation flow (pass 0.80, partial from 0.50; 6 Nov 2026, documents 6 and 13); rule-based checks and
      conversations re-scored from saved data
- [x] Re-graded Correctness & behaviour and Response flow with the claim and step prompts (9 Nov 2026, new AWS key;
      judge `global.anthropic.claude-opus-5-5` by QE choice, not mentioned in the reports; 457 calls, USD 17.42).
      Statuses now PASS 44, PARTIAL PASS 102, FAIL 201 questions (+13 conversations fail); the 8 hand-set grades were
      confirmed by the judge. Fixed guardrail replies made NA on Response flow (owner ruling of 6 Nov; Q-258). Document 13
- [x] Composite score per test case decides its status (QE, weight set "Facts + freshness safe": correctness 52,
      freshness 21, citations 8, response flow 6, figures 5, source links 5, source recall 3; personal data a gate;
      9 Nov 2026, weights in `eval/composite_weights.json`). 5 Nov run, questions: PASS 86, PARTIAL PASS 123, FAIL 138
      (earlier rule 44 / 102 / 201). Q-463 now passes with no source link (correctness outweighs it); decide whether a
      linkless answer may pass. Documents 6 and 13
- [x] Chatbot score across all test cases: the average composite of all test cases, each counting once, with its 95%
      range, median and segments (QE, 9 Nov 2026). 5 Nov run: 0.54 (0.51-0.57) from 360 test cases. Documents 6 and 13
- [x] Evaluation, scoring and reporting folded into the framework so it runs without help (9 Nov 2026): `eval/run_all.sh`
      (collect -> grade -> second pass -> reports, with retries), `eval/recalc.py` (no recalc script borrowed from outside
      the repository), the v2 workbook as the default, the findings page's default wording taken from the run's data.
      Verified with a live 8-case run (USD 1.32) and an identical rebuild of the 5 Nov reports; temporary files of the
      sessions removed. Document 7, "Verification performed on 9 Nov 2026"
- [ ] Set a release target for the chatbot score once the owner decides (reported without one for now; for example
      "average 0.80 or more with the lower 95% limit at least 0.77", in the style of the concept note's gates)
- [x] Source recall, Response flow and Conversation flow made release gates (pass 0.80, partial from 0.50, below 0.50
      fails the test case; QE, 6 Nov 2026); omission named in "Fail if" scores 0 (confirmed)
- [x] Official = in the ground-truth evidence, indexed data or APIs (mylpg.in stays official); a look-alike or
      unofficial link does not fail a test case on its own (QE, 6 Nov 2026)
- [x] Source recall credited in full when the facts are right from other official pages it cited (QE, 6 Nov 2026;
      nine answers on the 5 Nov run)
- [ ] `eval/selftest.py`: update the moved UIDAI fee-sheet URL (the only failing check, 8 of 9 pass)
- [ ] Findings 1-4 of document 13 shared with the developers
- [ ] Shareable reports built for the v2 run (findings page text updated)
- [ ] Judge-vs-human spot-check and review of the 53 golden-review candidates
- [ ] `golden_test_cases_indexed_20261104.xlsx`, `golden_test_cases_indexed_v2_20261105.xlsx` and `artifacts/` committed (all untracked)
