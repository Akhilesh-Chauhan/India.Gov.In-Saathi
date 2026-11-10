# 7. Setup and runbook

## Environment

| Need | Why | State on this machine (4 Nov 2026) |
|---|---|---|
| Python 3.12 + `.venv` with `requirements.txt` (anthropic 1.14.0, boto3 1.43.114, deepeval 4.2.9, openpyxl 3.1.5, playwright 1.64.0) | everything | `.venv` created, all imports OK |
| Google Chrome (or `playwright install chromium`, or `CHROME_PATH`) | rendering JavaScript pages in the golden check | Chrome 156 at /usr/bin/google-chrome |
| `poppler-utils` (pdftotext, pdftoppm), `tesseract-ocr` | PDF text and OCR of scanned PDFs | pdftotext 24.02, tesseract 5.3.4 |
| LibreOffice (`soffice` on PATH) | recalculating the report workbooks: `eval/recalc.py`, part of the repository since 9 Nov 2026 (before, `build_reports.sh` borrowed a recalc script from outside the repository) | LibreOffice 24.2 |
| AWS credentials with Bedrock access in ap-south-1 | the judge | in `eval/.env` (gitignored). The first key stopped working on 5 Nov; the key saved on 9 Nov 2026 reaches both the `global.*` and the `in.*` profiles |
| Network access to the Saathi UAT API and to official government sites | collection, page checks | official pages reachable (self-test fetched them); UAT API not probed on 4 Nov |

Setup from a clean clone (repository root):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium          # only if Google Chrome is not installed
sudo apt install poppler-utils tesseract-ocr
cp eval/.env.example eval/.env                 # fill in AWS keys; never commit eval/.env
.venv/bin/python eval/test_scoring.py          # offline checks of the scoring rules: SCORING TESTS PASSED
.venv/bin/python eval/selftest.py              # must print SELFTEST PASSED
cd eval && ../.venv/bin/python golden_check.py selftest --run x   # GOLDEN CHECK SELFTEST PASSED
../.venv/bin/python test_judge.py              # one short Bedrock call: confirms model access and price
```

## Secrets and files that stay local

- `eval/.env`: AWS keys (or `AWS_PROFILE`), judge settings, and the Saathi UAT web login (`SAATHI_WEB_USER`,
  `SAATHI_WEB_PASS`, added 4 Nov 2026; used by people checking answers in the browser at
  web.umang.gov.in/citizenbot, not read by any script). Gitignored.
  Also the UMANG production API keys the owner shared on 4 Nov 2026 (`MYSCHEME_API_KEY`, `UMANG_API_KEY`), read only by
  `artifacts/scripts/fetch_api_snapshots.py`; never copy them into `artifacts/` or a commit.
- `eval/bot_curl.txt`: only for the generic curl adapter (`BOT_ADAPTER=curl`). Gitignored. Not needed for the Saathi
  adapter, which calls the UAT API directly.
- `eval/page_cache/`, `eval/runs/*` except `golden-20261027`, `.venv/`, `.deepeval/`: gitignored.
- `eval/runs/golden-20261027/snapshots/` (730 MB of page copies): kept by the owner, not in git.
- Not in git since 10 Nov 2026 (`.gitignore`): `citizen-guide-indexed-data/` (the bot's index export, about 32,000 files,
  576 MB; the evaluation needs it, so get it from the developers), the working material of building the v2 test set
  (`artifacts/data/` except the latest API snapshot, `artifacts/scripts/` except `fetch_api_snapshots.py`), the 4 Nov API
  snapshot and the HTML report copies in `artifacts/`.

## Settings (`eval/.env`, read by `config.py`)

| Key | Default | Notes |
|---|---|---|
| `GOLDEN_WORKBOOK` | `golden_test_cases_indexed_v2_20261105.xlsx` (since 9 Nov 2026; before, `golden_test_cases_final_20261028.xlsx`) | The v2 set: 347 questions + 13 conversations, owner sign-off 5 Nov 2026 (documents 11, 12). Not set in `.env`. `selftest.py` always uses the October workbook (its fake bot answers October questions), and a `golden_check.py` run uses the workbook in its `runs/<run>/workbook.txt` |
| `INGESTED_CSV` | `ingested-websites.csv` | Team export of crawled sites |
| `BOT_ADAPTER` | `saathi` | or `curl` |
| `SAATHI_API` | `https://apigw-uat.umangapp.in/citizen-guidance-be/v1` | read by `saathi.py` |
| `BOT_TIMEOUT` | 60 (config) / 90 (saathi.py) | seconds |
| `BOT_ANSWER_PATH`, `BOT_SOURCES_PATH`, `BOT_INSECURE_TLS` | empty | curl adapter only |
| `AWS_REGION` | `ap-south-1` | |
| `JUDGE_MODEL` | `global.anthropic.claude-opus-5-5` | Bedrock inference profile; `.env` sets the same since 9 Nov 2026 (the earlier key could use only the `in.*` profiles, so the 5 Nov run was graded with `in.anthropic.claude-opus-5`). |
| `JUDGE_EFFORT` | `high` | main cost lever after the model |
| `JUDGE_FALLBACK_MODEL` | `global.anthropic.claude-opus-5` | empty disables the refusal fallback. On this machine: `in.anthropic.claude-sonnet-5`. |
| `JUDGE_PRICE_IN`, `JUDGE_PRICE_OUT` | unset (list prices used) | set to the account's Bedrock rate card |
| `PAGE_CHAR_LIMIT` | 150000 | characters of each cited page sent to the judge |
| `PAGE_CACHE_HOURS` | 12 | reuse window for fetched official pages (a cached fetch error is retried, not reused) |
| `INDEX_EXPORT_DIR` | `citizen-guide-indexed-data` | index export the content checks read (document 5, "What the content checks read") |
| `API_SNAPSHOT_DIR` | latest `artifacts/data/api_snapshots/<date>` | myScheme / UMANG API snapshot the content checks read; refresh with `artifacts/scripts/fetch_api_snapshots.py` before a run |
| `CONTENT_FROM_INDEX` | 1 | 0 = old behaviour, content checks read live pages only |

## Workflow A: re-check the expected answers before a run

```bash
cd eval
../.venv/bin/python golden_check.py export --run golden-YYYYMMDD --size 20      # new wave of batches
#   checkers follow golden_check.md: page -> write out/<ID>.json -> check --ids <ID> until OK
../.venv/bin/python golden_check.py status --run golden-YYYYMMDD
../.venv/bin/python golden_check.py audit --run golden-YYYYMMDD --parts 4        # second reading (golden_audit.md)
../.venv/bin/python golden_check.py signoff --run golden-YYYYMMDD                # owner decides in golden_signoff.xlsx
../.venv/bin/python golden_check.py apply --run golden-YYYYMMDD --out ../golden_test_cases_final_YYYYMMDD.xlsx
```

To reuse the 27 Oct evidence as a starting point, copy `runs/golden-20261027/out/` into the new run and re-run
`check` so pages are fetched afresh (the new evidence will show the new fetch dates). Prioritise the date-sensitive
test cases listed in document 4.

## Workflow B: evaluation run

One command does it all (since 9 Nov 2026; `eval/README.md` has the details):

```bash
cd eval
RUN=umang-$(date +%Y%m%d)
./run_all.sh $RUN --ids Q-001,Q-258,MT-06 --no-cost   # smoke: a few test cases first (about USD 2)
./run_all.sh $RUN --no-cost                           # everything; answers already collected for $RUN are kept
./monitor_run.sh $RUN 15                              # second terminal: live view of collection and grading
```

`run_all.sh` asks the bot (then once more for failed bot calls), grades with `run_eval.py` (then re-grades once any check
whose judge call failed: `--retry-errors`), runs `facts_split.py` (twice, so a failed judge call is retried) and
`build_reports.sh`. No setting has to be exported: the golden workbook, judge and API defaults come from `config.py`
and `.env`. The same steps by hand:

```bash
../.venv/bin/python collect.py --run $RUN --priority P0 --limit 25           # smoke: a few answers first
../.venv/bin/python summarize_run.py --run $RUN                              # free descriptive stats
for p in P0 P1 P2; do ../.venv/bin/python collect.py --run $RUN-$p --priority $p & done   # parallel shards (optional)
../.venv/bin/python collect.py --run $RUN-conv --scenarios; wait
#   or a single folder: collect.py --run $RUN ; collect.py --run $RUN --scenarios ; each again with --retry-errors
../.venv/bin/python run_eval.py --run $RUN --no-judge                        # free rule checks
../.venv/bin/python run_eval.py --run $RUN                                   # judged (paid); progress.py --run $RUN --watch 15
../.venv/bin/python run_eval.py --run $RUN --retry-errors                    # re-grade checks that came back ERROR
../.venv/bin/python facts_split.py --run $RUN                                # second pass on correctness failures
./build_reports.sh $RUN --no-cost                                            # or BUDGET=200 ... --shared
```

If shards were used, `recheck.py prepare/plan/stage/build` is the tool that merges them (treat the first collection as
BASE on a later day).

`eval/monitor_run.sh [run] [seconds]` (added 5 Nov 2026) shows answers collected against the total, answer kinds, unanswered
'which State?' replies, latency, speed and ETA (from the answers' own timestamps, so it can be restarted at any time) and
the last log lines; once `run_eval.py` starts it shows `progress.py` too, and it exits when grading is done. `--once`
prints a single snapshot.

Cost control: start with `--priority P0` or `--limit`; watch `progress.py` (it projects the total from the share of
citation and correctness checks done); set `JUDGE_PRICE_IN/OUT` so the sheets show the real rate; the Citation support
check is the expensive one.

## Workflow C: re-check an existing judged run on a later day

See document 5 section 5 (`recheck.py`). Baseline `umang-20261016` and re-check `umang-20261019` were the October
examples; neither folder is in the repository.

## Workflow D: share results

`BUDGET=200 ./build_reports.sh RUN --shared` (or `--no-cost` to keep the cost sheets in report.xlsx) then send `runs/RUN/saathi-findings.html`,
`runs/RUN/saathi-detailed-report.html` and `runs/RUN/findings_by_test_case.xlsx`. Cost stays in `grading_cost.xlsx`.
Optional `runs/RUN/run_notes.json` with `{"latency": "..."}` adds a note about response times.

## Workflow E: extend the test set

1. Add rows to the right `queries_*.py` (or a new variant group / scenario). Keep new rows **after** existing ones so
   IDs do not shift (the builder appends GROUPS_G last for the same reason). Domains must be in the CSV or registry.
2. `python3 build_golden_tests.py ingested-websites.csv` rebuilds `golden_test_cases_phase1.xlsx` only. The final
   workbook holds the checked answers, so new rows must then go through the golden check (Workflow A) and be applied
   to a new final workbook; alternatively add the rows to the final workbook by hand and check them.
3. Nothing in the harness needs a code change for new rows; `SourceRecall` applies automatically to rows with an
   Index chunk URL and `ResponseFlow` to PROC/USE rows.

## Verification performed on 4 Nov 2026

| Check | Result |
|---|---|
| `.venv` + `pip install -r requirements.txt` | OK, deepeval 4.2.9 imports |
| `golden_check.py selftest --run x` | GOLDEN CHECK SELFTEST PASSED |
| `golden_check.py status --run golden-20261027` | 526 of 526 checked, every quote found; page copies kept 0 (snapshots absent); 3 kept answers with uncovered figures (Q-067, Q-092, Q-380) |
| `eval/selftest.py` | 8 of 9 checks OK; "invented figure fails" came back NA instead of F because `https://uidai.gov.in/images/Aadhaar_Enrolment__and__Update__-__English.pdf` returned HTTP 503 (the fee sheet now lives at `https://backend.uidai.gov.in/get/files/media/document/2026-09/Aadhaar_Enrolment__and__Update__-__English.pdf`, HTTP 200). The harness logic is intact; the self-test's hard-coded URL needs updating. |
| Tools | Chrome 156, LibreOffice 24.2, pdftotext 24.02, tesseract 5.3.4, recalc.py present |
| Bedrock access (`test_judge.py`) | Confirmed 4 Nov 2026 with `in.anthropic.claude-opus-5` (6.1 s, 538 in / 440 out tokens, about USD 0.014 per call at list price) and `in.anthropic.claude-sonnet-5` (1.6 s, about USD 0.002). Both returned the expected FAIL verdict on the stale-MSP probe. The `global.anthropic.*` profiles (Opus 5.5, Opus 5, Sonnet 5.5, Haiku 5.5) are refused with HTTP 403 by an explicit deny in the AWS organization's service control policy. |
| Saathi UAT API | not probed |

## Verification performed on 9 Nov 2026: the framework runs on its own

After the scoring changes of 6-9 Nov were folded into the scripts (one-command `run_all.sh`, `recalc.py` in the
repository, the v2 workbook as the default, judge-error and bot-error retries, the findings page's wording taken from
the run's own data), nothing has to be set or run by hand:

| Check | Result |
|---|---|
| `test_scoring.py` | 67 of 67 |
| `selftest.py` (always on the October workbook) | 9 of 9 (SELFTEST PASSED) |
| `golden_check.py selftest` and `status --run golden-20261027` | passed; 526 of 526 checked on `golden_test_cases_final_20261028.xlsx` (read from the run's `workbook.txt`) |
| `./build_reports.sh indexed-v2-full-20261105 --no-cost` (5 Nov run, nothing exported) | every workbook value identical to the reports built by hand; detailed page identical; findings page text identical |
| `apply_overrides.py` on a copy of the 5 Nov run | `results.jsonl` identical; `report.xlsx` rebuilt by the script itself |
| `./run_all.sh pipeline-check-20261109 --ids Q-001,Q-258,Q-462,Q-036,Q-078,Q-113,Q-211,MT-06 --no-cost` | live bot and judge, no step by hand: 7 answers and 1 conversation, 20 judge calls (USD 1.26) + 4 second-pass calls (USD 0.06), 0 errors, workbooks recalculated with 0 formula errors, status formula = `scoring.status()` on every row, chatbot score 59% (95% range 34%-83%, 8 test cases). Q-258 came back as the fixed safety reply and was handled by the owner's rule without any override |
| Re-deriving that fresh run with every layer (`apply_overrides.py` on a copy) | 0 grades changed: the fixed-reply rule, link re-scoring, recall credit and conversation turn scores are all part of a normal run |
| `BUDGET=200 ./build_reports.sh pipeline-check-20261109 --shared` | `grading_cost.xlsx` written and recalculated, 0 formula errors |
| Both HTML pages of both runs in headless Chrome, 1300 px and 390 px | no console errors, no sideways scrolling |

The check run is kept in `eval/runs/pipeline-check-20261109/` as an example of a fresh run's reports.
