# 5. Evaluation pipeline

All commands run from `eval/` with the project virtualenv: `../.venv/bin/python <script> ...`.

## 1. Collect: ask the bot (`collect.py`)

```
collect.py --run RUN [--priority P0 P1] [--category Tax] [--ids Q-001,Q-046] [--limit 20] [--delay 1.0]
collect.py --run RUN --scenarios                 # the 17 multi-turn conversations
collect.py --run RUN --import-workbook           # tester-typed answers from the workbook's yellow columns
collect.py --run RUN --no-resolve-clarify        # do not answer the bot's clarifying chips
```

- **Adapter**: `BOT_ADAPTER=saathi` (default) calls `saathi.ask()` directly against the UAT API; `BOT_ADAPTER=curl`
  uses `bot_client.ask()` with the curl command in `eval/bot_curl.txt` (`{{QUERY}}`, `{{SESSION_ID}}` placeholders;
  answer and sources located by `BOT_ANSWER_PATH` / `BOT_SOURCES_PATH` or key heuristics).
- **Language header**: Hindi (Devanagari) rows send `Accept-Language: hi`; English and Hinglish rows send `en`
  ("Hinglish users typically type in the English interface").
- **Clarifying chips**: if the first reply is `kind == "clarify"` and the row is single-turn, the harness taps the
  first option of every chip field and asks again with `clarifications`; the record keeps the first reply as
  `clarify_first` and the picks as `clarify_choice`, so the Response flow judge sees both turns while content metrics
  grade the final answer. Since 5 Nov 2026 a free-text **State** field is answered too, with the State the user named in
  the question (`saathi.state_in`: English, romanised Hindi and Devanagari names, whole-word match). If the question
  names no State, the clarifying question stays the scored answer; by the owner's decision such queries get the State
  written into the query text instead (`artifacts/data/rewrites/query_edits.json`, applied by the workbook builder).
- **Conversations**: one `conversation` dict per scenario carries `conversationId` and `history` across turns
  (curl adapter: one `session_id` UUID).
- **Resume**: IDs already in `responses.jsonl` / `conversations.jsonl` are skipped, so a stopped run continues with
  the same command. Shards (`RUN-P0`, `RUN-P1`, `RUN-conv`) can run in parallel and are merged by `recheck.py`.
- **Record fields** (saathi adapter): answer, kind, grounding, cached, sources (citation URLs then suggested links,
  de-duplicated), citations (n, url, title, siteName, lastUpdated, fetchedAt, trust, snippet), suggested_links,
  sources_checked (the "Reading N sources" list with pages), follow_ups, clarify, answer_language, conversation_id,
  answer_id, request_id, server_timings, latency_s, first_token_s, status, lang_sent, error, raw.

## 2. Grade: `run_eval.py`

```
run_eval.py --run RUN --no-judge        # rules only, free
run_eval.py --run RUN                    # rules + Claude judge on Bedrock (paid)
run_eval.py --run RUN --ids Q-001,Q-002  # subset, e.g. to re-run ERROR rows (replaces results.jsonl; add --merge)
run_eval.py --run RUN --metrics "Correctness & behaviour,Response flow" --merge
                                         # re-judge only these checks and merge them into the saved results (6 Nov 2026)
run_eval.py --run RUN --concurrency 4
progress.py --run RUN --watch 15         # second terminal
test_scoring.py                          # offline checks of the scoring rules (no bot, network or Bedrock)
```

Flow:

1. Read `responses.jsonl` (and `conversations.jsonl`); match each record to a workbook row by exact query text,
   falling back to ID.
2. Fetch every cited URL once (`pages.get_page`, 8 threads, 12-hour disk cache in `eval/page_cache/`). A page is
   "readable" when it fetched without error and has at least 400 characters of text; otherwise it is treated as a
   JavaScript page and the related checks return NA instead of a false FAIL.
3. Build one `LLMTestCase` per answer: `input` = query, `actual_output` = answer or "(no answer)", `expected_output` =
   golden text, `retrieval_context` = readable page texts, `metadata` = row, sources, kind, checked_urls,
   clarify_first/choice, pages.
4. Build the metric set per row: always Source genuineness, Figures on cited pages, Personal data not echoed;
   Source recall when the row has an Index chunk URL; with a judge also Citation support, Correctness & behaviour,
   Response flow, and Freshness when the Golden-fact status contains "Verified" or "Partly".
5. Run all metric measurements concurrently under an asyncio semaphore (`--concurrency`, default 4); each judge call
   is tagged with (row, metric) through a context variable for token accounting. A judge or API exception becomes
   verdict `ERROR` with the exception text, never a crash.
6. Conversations: one `ConversationalTestCase` per scenario (user/assistant turns, sources appended to the assistant
   text) graded by `ConversationFlow` against the expected behaviour per turn.
7. Write `results.jsonl`, `tokens.jsonl`, `report.xlsx` (see document 6 for sheets and formulas); print FAIL counts,
   errors and the judge cost at list price. Each check result is `{"verdict", "score", "reason", "guardrails",
   "detail"?}`: score 0 to 1 (None = NA), verdict P only at the check's pass score (0.80 for partial-credit checks),
   `detail` = the claim, step or turn marks behind a partial score. A full run (no `--ids`, no `--metrics`) also writes
   `results.judge-original.jsonl`, the base layer for `apply_overrides.py`, and renames older layers to
   `*.superseded-<time>`.
8. With `--merge` (6 Nov 2026): the new grades go to `results.rejudge.jsonl` (newest grade per check wins; judge
   ERRORs are never merged), token usage is appended to `tokens.rejudge.jsonl`, `apply_overrides.derive()` re-derives
   `results.jsonl` and `report.xlsx` is rebuilt. When the chosen checks do not read pages (Correctness, Response flow,
   Freshness, Conversation flow) no page is fetched.

### What the content checks read (fix of 5 Nov 2026, `eval/content.py`)

The live fetch of every shown URL (`pages.get_page`) still decides **Source genuineness** (official, opens, no
off-government redirect). The **content** checks (Figures on cited pages, Citation support) now read what the bot had
for that URL: for `myscheme.gov.in/schemes/<slug>` the myScheme search-API record, for UMANG department links the
UMANG all-services record (latest snapshot under `artifacts/data/api_snapshots/`), otherwise the page's copy in the
index export `citizen-guide-indexed-data/` (chunks joined, overlap removed), and only for pages the bot never indexed the
live page. Each page dict carries `content_source`; the Citation support prompt names it for every source. Reason: pages
change after the crawl, myScheme pages are JavaScript-only, and myScheme content reaches the bot from the API, not the
knowledge base. For myScheme and UMANG links the text also includes the snippet the bot showed on its citation card:
the snapshot records are summaries (UMANG all-services describes departments, not services), while the bot reads more
(Q-369: the UMANG 'View Passbook' service text). `CONTENT_FROM_INDEX=0` restores the old live-only behaviour. A cached fetch error is retried on the next
run instead of being served for 12 hours.

### What the judges see of the sources (fix of 5 Nov 2026)

Correctness & behaviour, Response flow and Conversation flow used to see only a list of URLs, so "no source card"
failures were partly an artefact. They now get the citation cards as the user sees them (number, site name, title,
URL, last-updated date, fetch date) and the suggested-link buttons with their titles (`metrics._cards_block`); Citation
support gets the card line above each source's text. Response-flow results from before 5 Nov are therefore not
directly comparable with later ones.

The Results sheet of `report.xlsx` carries "Expected answer (golden)" and "Evidence: official page, exact words, copy date"
(from the workbook's "Final golden" sheet) after "Bot answer" (5 Nov 2026); the detailed HTML report shows both next to
the question and Saathi's answer.

Fixed guardrail replies (answer kind "blocked", 6 Nov 2026): Figures on cited pages and Citation support return NA, and
Source genuineness returns NA when the reply shows no links (`metrics.FIXED_REPLY`, owner ruling).

`apply_overrides.py --run RUN` (rewritten 6 Nov 2026; `derive()` is also called by `run_eval.py --merge`) re-derives a
graded run's `results.jsonl` without judge calls, always starting from the judge's grades of the full run
(`results.judge-original.jsonl`, copied from results.jsonl the first time). Layers, in order: (1) `results.rejudge.jsonl`
re-grades; (2) the fixed-reply rule; (3) rule re-scoring of Source genuineness and Source recall from the saved answers,
evidence and cached page fetches, and Conversation flow's turn score from the saved reason; (4)
`runs/RUN/verdict_overrides.json`, grades set by a person, skipped for a check that was re-graded after it (the re-grade
used the corrected golden answer). Each changed check keeps the grade it replaced under "original" and names its
`layer`. It prints a count of changes per layer, check and verdict move. The old flags `--fixed-reply-rule` and
`--regrade-genuineness` are still accepted; every layer always applies.
Rebuild the v2 workbook with `--out` naming the existing file: the builder's default output name carries today's date.

`run_eval.py --report-only` (5 Nov 2026) rebuilds `report.xlsx` from the saved `results.jsonl` and `tokens.jsonl` without
fetching or judging; report writers strip control characters Excel cannot store (`run_eval._clean`). Note that
`run_eval.py --ids` without `--merge` writes `results.jsonl` with only those IDs (it prints a warning); with `--merge`
the other rows keep their grades.

## 3. The judge (`judge.py`)

- `anthropic.AnthropicBedrock(aws_region="ap-south-1", max_retries=4)` with
  `BetaRefusalFallbackMiddleware([{"model": JUDGE_FALLBACK_MODEL}], betas=[])` when a fallback model is set.
- `beta.messages.create(model=JUDGE_MODEL, max_tokens=16000, output_config={"effort": JUDGE_EFFORT,
  "format": {"type": "json_schema", "schema": ...}})`. If Bedrock rejects `format` (the `in.*` India profiles do), the
  judge switches to embedding the schema in the prompt and parsing the JSON object from the reply.
- Models that reject `effort` (haiku-4-5, sonnet-4-5) get no `output_config.effort`.
- A `stop_reason == "refusal"` raises `RuntimeError("Judge declined to grade: ...")` which the metric reports as ERROR.
- Every call records row, metric, model actually used, input/output/cache-read/cache-write tokens (summed over
  fallback attempts), attempts and seconds; appended to `tokens.live.jsonl` as it happens.
- Prices: `JUDGE_PRICE_IN/OUT` from `.env` if set, else `LIST_PRICES` by model-name substring (Opus 5.5: USD 4 / 20
  per million tokens). Bedrock bills its own rate card, so the sheets call these estimates.
- Test access with `test_judge.py [model_id ...]` (one short graded call per model, prints cost per call).

Cost drivers: the Citation support prompt carries the cited pages' text (up to 150,000 characters per page), typically
10-40k input tokens per answer; `JUDGE_EFFORT` is the second lever. README estimate for a full run of all test cases
with Opus: roughly USD 100-150. The approved budget for the October runs was USD 200 (19 Oct 2026).

## 4. Second passes

### Facts vs guardrails (`facts_split.py`)

For each question that failed Correctness & behaviour, a cheap second judge call (no page text) reads the question,
golden, bot answer and the first grader's reason and returns `facts` (correct / incomplete / wrong / not answered /
not applicable), `behaviour_met`, `causes` (from a fixed list of ten) and a reason. Writes `facts_split.jsonl`
(re-runs skip done IDs), `facts_split_tokens.jsonl`, and the report sheets "Facts vs guardrails" (summary, accuracy
views against the 90% / 85% targets, causes) and "Facts split detail". `--report-only` rebuilds the sheets without
judge calls; `--limit N` for a trial.

### Unanswered split (`unanswered_split.py`)

For questions whose facts verdict is "not answered": compares the expected source domain with the pages the bot said
it read (`sources_checked`) and groups them as *Read the expected site, no answer*, *Expected site not retrieved*,
*Needs service data (DB/API)*, *No expected source*. For the first group it also checks whether the golden's key figures
appear on the pages the bot read (fetched into the page cache). Writes `unanswered_split.jsonl` and the sheet
"Unanswered split". No judge calls.

### Checklist grading (`checklist.py`, `checklist_grader.md`)

```
checklist.py export --run RUN --batches 8      # runs/RUN/checklist/batch_NN.txt
#   graders write out_NN.json (one object per question: items [{type fact|behaviour, item, status met|missing|wrong}], note)
checklist.py validate --run RUN
checklist.py score --run RUN                   # runs/RUN/checklist.jsonl; the reports pick it up
checklist_next_step.py export|apply --run RUN  # re-mark "ends with an official link or next step" with one rule
findings_sheet.py --run RUN --no-recheck --spot-check   # spot_check.xlsx: 2 questions per batch and status
checklist.py agreement --run RUN               # reviewer agreement rate (target 90%, concept note 9.3.4)
```

The grader builds a short checklist from the golden (key facts that answer the question; required behaviours: the
golden's own instructions, "replies in the user's language", "ends with an official link or next step" for
information/service questions, "says what it searched and gives the closest official page or helpline" for could-not-find
replies) and marks each item met / missing / wrong. Scoring rules are in document 6.

## 5. Re-check (`recheck.py`, `recheck_compare.md`)

The bot regenerates every answer, so asking again days later gives different text. The re-check asks everything
again and re-grades only what changed in substance:

```
for p in P0 P1 P2; do collect.py --run NEW-$p --priority $p & done; collect.py --run NEW-conv --scenarios; wait
recheck.py retry --new NEW                   # moves bot errors to errors_first_attempt.jsonl, prints re-ask commands
recheck.py prepare --base BASE --new NEW     # pairs.json: same / changed / compare / error / missing; compare batches
#   reviewers decide compare items (recheck_compare.md) -> recheck/compare/out_NN.json (optional)
recheck.py plan --base BASE --new NEW        # plan.json; unreviewed compare items count as changed
recheck.py stage --base BASE --new NEW --wave a [--no-conversations]   # NEW-regrade-a with the changed answers
run_eval.py --run NEW-regrade-a && facts_split.py --run NEW-regrade-a
recheck.py build --base BASE --new NEW       # merged run NEW with regrade.json; then build_reports.sh NEW
```

Decision rules: identical normalised answer and identical sources = same; `no_answer` on both days = same (a different
list of suggested sites on a decline is no change); a change of answer kind = changed; both answered = side-by-side
review (batches of 75); conversations are re-graded whenever any reply differs; a bot error on the new day keeps the
baseline answer and grades. In the merged run unchanged answers keep the baseline's answer and grades but take the
new latency; `results.jsonl` records `graded_by`; `regrade.json` records decisions, notes and the spend of every
Bedrock run behind the report (pilot, judged run, facts split, re-grade, its facts split).

Run naming matters: `run_date()` reads an 8-digit date suffix (`umang-20261016` -> "16 Oct") for labels; shards are
`NEW-*` folders holding `responses.jsonl` except `-regrade-*` and `-pilot`.

## 6. Reports (`build_reports.sh`)

```
BUDGET=200 ./build_reports.sh RUN --shared    # files for stakeholders (cost moved to grading_cost.xlsx)
./build_reports.sh RUN --no-cost              # the same pages without cost; cost sheets stay in report.xlsx
./build_reports.sh RUN                        # full internal view
```

Sequence: `run_eval.py --report-only` when `results.jsonl` is newer than `report.xlsx` (for example after
`apply_overrides.py`), `facts_split.py --report-only`, `unanswered_split.py`, (shared: `split_cost.py --budget` ->
`grading_cost.xlsx` and token sheets removed from report.xlsx), `recalc.py report.xlsx`, `findings_sheet.py` ->
`findings_by_test_case.xlsx`, `recalc.py` on it, `report_html.py` -> `saathi-detailed-report.html`, `findings_page.py`
-> `saathi-findings.html`. `--shared` and `--no-cost` present a re-checked run as a single run (`--no-recheck`,
`--single-run`) and leave cost off the pages. `eval/recalc.py` (in the repository since 9 Nov 2026; before, the script
borrowed a recalc script from outside the repository) recalculates each workbook with LibreOffice headless, on a copy
outside the run folder (a LibreOffice lock file next to the original can hang it) and with a throwaway profile, and
reports formula errors. The whole run, collection to reports, is one command: `run_all.sh` (document 7, Workflow B).

Report contents:

- **findings_by_test_case.xlsx**: one row per test case and conversation: query, golden, expected site and URLs, bot
  response and URLs, Status, Result group, Reason, grader's detailed reason, guardrails broken, context columns, every
  check's verdict, other failed checks, response time, reviewer columns; re-check columns when `regrade.json` exists;
  checklist columns when `checklist.jsonl` exists. Header on row 6, summary formulas above.
- **saathi-detailed-report.html**: tabs Overview, Results by question, Facts vs guardrails, Unanswered split, Guardrails,
  Segments, Judge vs human, Conversations, Tokens & cost (unless `--no-cost`), Facts split detail; search and filters.
- **saathi-findings.html**: lead finding, where answers landed (failure classes by priority), what each group means with
  real examples (the ones `run_notes.json` names for the run, else one real test case of the run per failure group,
  with its golden answer and the second pass's reason; until 9 Nov 2026 five October cases were hard-coded), distance from release targets, why questions went unanswered, release checks, what to fix first, how this was
  measured, optional re-check section. Also detects reply defects by text (internal planning vocabulary such as
  `NO_ANSWER`, `target_language`, `Output language is`, `NO_CITATION`; an answer starting with "So ").
- **grading_cost.xlsx**: spend summary against the budget, token usage per check and per question.
- **performance.xlsx** (`summarize_run.py`): answer kinds, latency percentiles, first-token time, server timings,
  citations per answer, citations with dates, hosts outside the registry, cached replies, Hindi answered in Hindi,
  index recall; by category, language, priority, knowledge level, question type.

## 7. Feature probes (`validate_features.py`)

Twenty quick probes against the live bot without a judge (F01 cited answer with markers and dates, F02 Hindi
interface, F05 clarifying chips, F06 follow-up context, F08 Aadhaar not echoed, F10 self-harm helplines, F13 Wikipedia
injection, F15 PVC Aadhaar Rs 75, F17 UMANG hand-off, F19 over-long input, F20 cited domains within the registry, and
others marked OBSERVE or REVIEW). Writes `runs/<run>/features.json` and `features.md`, and refreshes `eval/bot_sources.json`.

## 8. Offline self-test (`selftest.py`)

Starts a fake local bot (canned answers for six workbook queries, served over the curl adapter) and a fake judge,
fetches the real official pages those canned answers cite, runs the full metric set and asserts nine verdicts: a
genuine source and figure pass; a user-typed stale figure is NA for the figures rule but FAIL for the freshness judge;
a look-alike link fails; an invented figure fails; a 404 link is only noted (owner decision of 6 Nov 2026); an echoed
OTP fails; no identifier gives NA. Prints `SELFTEST PASSED` or `FAILED`. It always uses the October workbook
(`golden_test_cases_final_20261028.xlsx`), whose questions its canned answers belong to, and depends on live UIDAI, PIB
and Passport Seva pages (the UIDAI fee sheet is intermittently unavailable, which fails one check). The scoring rules
themselves are checked offline by `test_scoring.py`.
