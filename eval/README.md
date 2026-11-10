# Saathi evaluation harness (DeepEval + Claude judge on Amazon Bedrock)

Scores the Saathi citizen-guidance bot (UMANG / India.gov.in) on the concept note's release criteria (section 9):
correctness and required behaviour, freshness, citation support and source genuineness, plus source recall, the deck's
response flow (slide 10) and multi-turn conversations. Every check gives a score from 0 to 1; each test case gets a
weighted composite score that sets its PASS / PARTIAL PASS / FAIL, and the chatbot gets one overall score.

Golden data: `../golden_test_cases_indexed_v2_20261105.xlsx` (347 questions + 13 conversations, every expected answer
grounded in the bot's index export or API data; owner sign-off 5 Nov 2026). Set `GOLDEN_WORKBOOK` to use another one.
Background, decisions and run write-ups: `../artifacts/` (start with its README).

## One-time setup
```bash
# from the repository root
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp eval/.env.example eval/.env      # then fill in the AWS keys (Bedrock access for the judge); never commit eval/.env
sudo apt install libreoffice-calc   # recalculates the report workbooks (recalc.py); `soffice` must be on PATH
.venv/bin/python eval/test_scoring.py   # offline checks of the scoring rules: must end "SCORING TESTS PASSED"
.venv/bin/python eval/selftest.py       # fake bot + fake judge, real pages: must end "SELFTEST PASSED"
.venv/bin/python eval/test_judge.py     # one short call per judge model: checks the AWS key and model access
```
The bot's index export is not in git (about 32,000 files): get it from the developers and place it at
`../citizen-guide-indexed-data/` (or set `INDEX_EXPORT_DIR`). The content checks, source recall and the "available to
the bot" rule read it; without it they fall back to live pages and give different results.
The judge model is `JUDGE_MODEL` in `.env` (Bedrock inference profile, region `AWS_REGION`, default ap-south-1), with
`JUDGE_FALLBACK_MODEL` if it declines. The bot is called through its public UAT API (`saathi.py`; no credentials).

## Running an evaluation: one command
```bash
cd eval
./run_all.sh day1                                   # every question and conversation of the golden workbook
./run_all.sh day1-p0 --priority P0 --no-scenarios   # priority questions only
./run_all.sh check1 --ids Q-001,Q-258,MT-06         # a few test cases (MT-.. = conversations)
BUDGET=200 ./run_all.sh day1 --shared               # files to share: grading cost moved to grading_cost.xlsx
../.venv/bin/python progress.py --run day1 --watch 15   # second terminal: live progress, spend so far, ETA
```
`run_all.sh` runs the four steps below, each resumable, and retries once whatever failed for a passing reason (a bot
call, a judge call). Output in `runs/<run>/`: `report.xlsx`, `findings_by_test_case.xlsx`, `saathi-detailed-report.html`
and `saathi-findings.html`. Its last line prints the pass / partial counts and the chatbot score.

| Step | Command | What it does |
|---|---|---|
| 1 Ask the bot | `collect.py --run R [--ids/--priority/--category/--limit]`, `collect.py --run R --scenarios`, then each with `--retry-errors` | Answers with sources, citations, latency and the raw response in `responses.jsonl` / `conversations.jsonl`; a rerun skips what is collected; `--retry-errors` asks again what the bot failed to answer (the failed attempt goes to `errors_first_attempt.jsonl`) |
| 2 Grade | `run_eval.py --run R`, then `run_eval.py --run R --retry-errors` | Rule checks and the judge; `results.jsonl` (+ `results.judge-original.jsonl`), `tokens.jsonl`, `report.xlsx`; `--retry-errors` re-grades only checks whose judge call failed |
| 3 Second pass | `facts_split.py --run R` (twice) | For every answer that fell short on correctness: facts wrong / missing / not answered vs behaviour or guardrail only (`facts_split.jsonl`); the second call retries failed judge calls |
| 4 Reports | `./build_reports.sh R [--no-cost\|--shared]` | Analysis sheets, findings workbook, both HTML pages; workbooks recalculated with LibreOffice (`recalc.py`) |

`run_eval.py --no-judge` runs the free rule checks only (no findings page: it needs the judge's correctness grades).
Answers typed into the workbook by testers can be scored too: `collect.py --run manual1 --import-workbook`.

## Report files (`build_reports.sh`)
```bash
./build_reports.sh day1              # internal view: grading tokens and cost included
./build_reports.sh day1 --no-cost    # the same files without cost on the pages (cost stays in report.xlsx)
BUDGET=200 ./build_reports.sh day1 --shared   # for stakeholders: cost moved out to grading_cost.xlsx (split_cost.py)
```
It rebuilds `report.xlsx` first when `results.jsonl` is newer, then writes the analysis sheets (`facts_split.py
--report-only`, `unanswered_split.py`), `findings_by_test_case.xlsx` (`findings_sheet.py`: one row per test case with
status, composite score and reviewer columns), `saathi-detailed-report.html` (`report_html.py`: every sheet as a tab)
and `saathi-findings.html` (`findings_page.py`: the short findings page; scores shown as percentages). Workbook formulas
are recalculated by `recalc.py` (LibreOffice headless, on a copy outside the run folder, reports any formula error).
`runs/<run>/run_notes.json` is optional: hand-written narrative and worked examples for the findings page; without it
the page uses its default wording and picks one real test case of the run per failure group.

## Scoring (details: `scoring.py`, `../artifacts/06-metrics-and-scoring.md`)
| Check | Score | How |
|---|---|---|
| Correctness & behaviour | claims met / claims | Judge: one claim per key fact of the golden answer and per required behaviour; a wrong claim counts as not met; a triggered "Fail if" (including a named omission) or a safety breach scores 0; fixed guardrail replies judged by what the guardrail needs |
| Freshness | 1 / 0 | Judge vs the verified golden: current value, no stale value from its "Fail if" |
| Citation support | 1 / 0 | Judge: each factual sentence supported by the page it cites (the bot's indexed copy or API record when available) |
| Figures on cited pages | 1 / 0 | Rules: every Rs amount, % and large number appears on a cited page |
| Source genuineness | correct links / unique links | Rules: official and available to the bot (crawled list, registry, APIs, index export); a link that does not open is only noted |
| Source recall | expected pages cited or retrieved / expected pages | Rules, index-seed questions; credited in full when the facts are right from other official pages the bot cited |
| Response flow | rubric steps met / steps that apply | Judge, questions with a flow rubric; not applicable to the bot's fixed guardrail replies |
| Personal data not echoed | 1 / 0 | Rules: an identifier the user typed is never repeated |
| Conversation flow | turns passed / turns | Judge, every turn of the multi-turn scenarios |

A partial-credit check passes at 0.80, is partial from 0.50 and fails below. **Composite score** of a test case: the
weighted average of the checks that apply (`composite_weights.json`: correctness 52, freshness 21, citations 8,
response flow 6, figures 5, source links 5, source recall 3; repeating personal data sets it to 0; a conversation's
composite is its share of turns passed). **Status**: PASS at 0.80 or more, PARTIAL PASS from 0.50, FAIL below.
**Chatbot score**: the average composite of all test cases with its 95% range (`scoring.bot_score`), shown with the
median, the status counts and the scores by segment. The Gates sheet keeps the concept note's release gates (Wilson
95% lower limits) and the QE's per-check gates; every failed check records the guardrail IDs it breaks.

## Changing grades after a run
```bash
../.venv/bin/python run_eval.py --run day1 --metrics "Correctness & behaviour,Response flow" --merge   # re-judge some checks
../.venv/bin/python run_eval.py --run day1 --ids Q-001,MT-06 --merge                                  # or some test cases
../.venv/bin/python apply_overrides.py --run day1     # re-derive results.jsonl from its layers (also rebuilds report.xlsx)
./build_reports.sh day1 --no-cost
```
`results.jsonl` is always re-derived from `results.judge-original.jsonl` plus layers: later re-grades
(`results.rejudge.jsonl`), the fixed-reply rule, rule re-scoring from cached pages, grades set by a person
(`verdict_overrides.json`: `[{"id", "metric", "verdict", "reason"}]`, skipped once that check is re-graded) and the
recall credit. Each changed grade keeps the one it replaced under "original".

## Re-checking a run
The bot generates every answer afresh, so asking again a few days later gives different answers. `recheck.py` asks
everything again and re-grades only the answers whose content changed:
```bash
for p in P0 P1 P2; do ../.venv/bin/python collect.py --run day2-$p --priority $p & done   # new answers, in parallel
../.venv/bin/python collect.py --run day2-conv --scenarios; wait                            # new conversations
../.venv/bin/python recheck.py retry --new day2              # set aside bot errors; prints the collect.py commands to re-ask
../.venv/bin/python recheck.py prepare --base day1 --new day2 # same / changed / compare; batches in runs/day2/recheck/compare
#   reviewers decide each compare item following recheck_compare.md (out_NN.json next to batch_NN.txt; optional)
../.venv/bin/python recheck.py plan --base day1 --new day2    # unreviewed compare items count as changed
../.venv/bin/python recheck.py stage --base day1 --new day2 --wave a
../.venv/bin/python run_eval.py --run day2-regrade-a && ../.venv/bin/python facts_split.py --run day2-regrade-a
../.venv/bin/python recheck.py build --base day1 --new day2   # merged run in runs/day2, with regrade.json
BUDGET=200 ./build_reports.sh day2 --shared
```
Unchanged answers keep the baseline's answer and grades; response times come from the re-check.

## Checklist status (older runs)
The October runs used a checklist rule instead (`checklist.py`, graders following `checklist_grader.md`; PASS = 85% of
the checklist, PARTIAL PASS = 60% of the key facts). When `runs/<run>/checklist.jsonl` exists the reports use it.
Reviewer spot-check (concept note 9.3.4, target 90% agreement): `findings_sheet.py --run day1 --no-recheck --spot-check`
writes `spot_check.xlsx` (2 questions per grading batch and status) and `checklist.py agreement --run day1` scores it.

## Checking the expected answers against official pages
`golden_check.py` ties every key fact of an expected answer to an official page, the exact words on it and a dated copy
(checkers follow `golden_check.md`); `export`, `check`, `status`, `signoff`, `apply` (see the script's help). A check
run remembers the workbook it checked in `runs/<run>/workbook.txt` (the October run `golden-20261027` checked
`golden_test_cases_final_20261028.xlsx`). The v2 set was grounded in the bot's index export instead (`../artifacts/`
documents 11 and 12).

## Notes
- Judge cost: the citation check sends the cited pages' text. A full run of the v2 workbook took 932 judge calls, about
  USD 67 at list price, and its second pass about USD 7 (5 Nov 2026); re-grading Correctness and Response flow for
  every answer cost about USD 18 (9 Nov 2026). Try a small run first (`--priority P0`, `--limit`, `--ids`).
- Pages are fetched once and cached for 12 hours in `page_cache/`; the cache also serves the rule re-scoring layer.
- DeepEval telemetry is switched off (`DEEPEVAL_TELEMETRY_OPT_OUT=1`); nothing is uploaded to Confident AI.
- `monitor_run.sh RUN` shows a live view of collection and grading; `summarize_run.py` describes a collected run
  (answer types, latency, citations) without grading.
