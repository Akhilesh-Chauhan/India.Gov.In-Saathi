# Saathi golden-test evaluation: project knowledge base

Written on 4 Nov 2026 by the incoming quality engineer after a full read of the repository, its data files and its
run evidence, plus a dry run of the offline self-tests. It is the hand-over context for anyone who works on this
project next. Nothing here is copied from a design document; everything was derived from the code and data in
this repository, so where a statement names a file you can open it and confirm.

| # | Document | Read it when you need |
|---|---|---|
| 1 | [01-project-overview.md](01-project-overview.md) | What the project is, who it serves, how it came to be, where it stands today |
| 2 | [02-architecture.md](02-architecture.md) | Components, data flow, file map, run-folder layout, external systems |
| 3 | [03-golden-dataset.md](03-golden-dataset.md) | How the 509 questions and 17 conversations were authored and built into the workbook |
| 4 | [04-golden-verification.md](04-golden-verification.md) | How every expected answer was tied to an official page (golden_check.py), the evidence format, sign-off, apply |
| 5 | [05-evaluation-pipeline.md](05-evaluation-pipeline.md) | Collecting bot answers, grading, re-checking, checklist grading, reports (one command since 9 Nov 2026: `eval/run_all.sh`) |
| 6 | [06-metrics-and-scoring.md](06-metrics-and-scoring.md) | Every metric's exact rule and score (partial credit since 6 Nov 2026), derived columns, gates, the composite score that sets PASS / PARTIAL PASS / FAIL (9 Nov 2026), failure classes |
| 7 | [07-setup-and-runbook.md](07-setup-and-runbook.md) | Environment setup, secrets, commands for each workflow, costs, what was verified on 4 and 9 Nov 2026 |
| 8 | [08-reference.md](08-reference.md) | Guardrails G01-G16, personas, question types, codes, concept-note section map, glossary |
| 9 | [09-qe-handover-observations.md](09-qe-handover-observations.md) | Current state, known gaps, risks, stale documentation, suggested next steps |
| 10 | [10-indexed-data-export.md](10-indexed-data-export.md) | The bot's live-index export (`citizen-guide-indexed-data/`, 3 Nov 2026): format, contents, and how far it can ground the golden set |
| 11 | [11-index-grounded-dataset.md](11-index-grounded-dataset.md) | The filtered dataset `golden_test_cases_indexed_20261104.xlsx`: how each test case was graded against the index export and the two UMANG APIs (myScheme search, all-services), the hand review of API facts, what was kept (139 queries, 1 scenario), site coverage (43 of 726), open points |
| 12 | [12-rewriting-partially-grounded-cases.md](12-rewriting-partially-grounded-cases.md) | The 220 partially grounded cases rewritten so every claim is grounded (208 queries, 12 scenarios, 1,358 quoted facts): briefs, authoring rules, quote and answer checks, the v2 workbook `golden_test_cases_indexed_v2_20261105.xlsx` (347 queries, 13 scenarios, 108 sites), rewrites pending owner sign-off |
| 13 | [13-full-run-v2-20261105.md](13-full-run-v2-20261105.md) | Full evaluation run on the v2 workbook (5 Nov 2026): gates, per-check rates, why answers failed, findings for the developers, cost; 6 Nov updates (ground truth, link rule, partial-credit scores); 9 Nov updates (re-grade with scores, composite score) |
| - | [data/](data/) | Derived tables: per-test-case and per-fact index grounding, per-site query coverage, earlier golden-vs-index coverage; the rewrite batches; the API snapshots the evaluation reads (only the latest snapshot is in git) |
| - | [scripts/](scripts/) | The analysis and build scripts behind documents 10 and 11, for re-running on a new export (only `fetch_api_snapshots.py` is in git) |

## What is in git and what stays local (10 Nov 2026)

Git holds the evaluation framework (`eval/`), the golden workbooks, these documents, the latest API snapshot
(`data/api_snapshots/20261105/`, which the evaluation reads) and `scripts/fetch_api_snapshots.py`. Kept on the QE's
machine and listed in `.gitignore`: the bot's index export `citizen-guide-indexed-data/` (about 32,000 files, 576 MB;
the evaluation needs it, so get it from the developers), the working material of building the v2 test set (the rest of
`data/` and `scripts/`), the superseded 4 Nov API snapshot, the copies of run reports (`*.html` here) and all run
folders except the October golden-check evidence. Paths in these documents still name those local files.

## Thirty-second summary

Saathi is the UMANG / India.gov.in citizen chatbot built by the NeGD team. This repository holds the quality
framework for it: a golden test set of 509 single questions and 17 multi-turn conversations, each with an expected
answer whose every key fact is tied to the exact words on a dated copy of an official government page, and a
DeepEval-based harness that asks the bot every question, grades each answer with rule-based checks plus Claude on
Amazon Bedrock as the judge, and turns the grades into gate checks, review workbooks and stakeholder pages.

The golden set is final (`golden_test_cases_final_20261028.xlsx`, signed off by the owner on 28 Oct 2026). The
evaluation harness has been exercised on earlier bot builds (runs on 16 and 19 Oct 2026, not in the repository) and
is ready to run again. The main open items are listed in document 9.

On 3 Nov 2026 the developers' export of the bot's live search index (31,650 pages, 283,560 chunks from 726 sites) was
added to the workspace; document 10 describes it and measures how much of the golden set it can ground (36% of test
cases have none of their verified source pages in the index).

On 4 Nov 2026 the developers confirmed that crawling permissions kept much of that content out of the bot. The golden
set was therefore filtered fact by fact against the export and against snapshots of the two UMANG APIs the bot also
reads for schemes and services (document 11): `golden_test_cases_indexed_20261104.xlsx` keeps the 139 queries and 1
conversation whose expected answers are fully grounded in the index or the API data, or test behaviour only. Run the
harness on it with `GOLDEN_WORKBOOK=` pointing at that file.

On 5 Nov 2026 the 220 partially grounded cases were rewritten so that every claim rests on quoted index text
(document 12). `golden_test_cases_indexed_v2_20261105.xlsx` holds 347 queries and 13 conversations; the 220 rewrites
are marked "PENDING" in the Owner sign-off column until the owner approves them.

## How to keep this knowledge base current

- When a workflow or rule changes in code, update the matching document here in the same change.
- Record each evaluation run's date, run name, bot build and headline numbers in document 9 (section "Run log").
- Dates in these documents are absolute (for example "28 Oct 2026"), never "last week".
