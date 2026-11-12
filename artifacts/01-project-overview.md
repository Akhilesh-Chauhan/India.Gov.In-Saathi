# 1. Project overview

## What is being tested

**Saathi** is the AI citizen-information assistant of UMANG / India.gov.in, described in the team's concept note
"One Government, One Conversation" as an *AI-enabled Unified Citizen Information Service*. A citizen asks a question
in English, Hindi or Hinglish; the bot answers from official government web pages it has crawled (about 200 sites,
later a registry of 794 sources) plus UMANG and myScheme service data, shows source cards with citations, asks at
most two clarifying "chip" questions when needed, and ends with an official next step (a UMANG deep link, portal,
form or helpline).

The bot under test is reached through its UAT API:

- API: `https://apigw-uat.umangapp.in/citizen-guidance-be/v1` (protocol `cg-ask/1`, captured from the web app on 16 Oct 2026)
- Web app: `https://web.umang.gov.in/citizenbot/`
- `POST /ask` streams server-sent events: `ready`, `status`, `source`, `citation`, `answer.delta`, `answer.done`, `end`
- Reply kinds: `answer`, `clarify` (chips), `no_answer` ("could not find an official answer")
- `GET /sources` returns the bot's own source registry (794 items on 16 Oct 2026, saved as `eval/bot_sources.json`)

## What this repository is

The **quality framework** for Saathi, owned by the evaluation team (repository `Akhilesh-Chauhan/India.Gov.In-Saathi`
on GitHub, two commits on 28 Oct 2026). It has two halves:

1. **Golden test set**: 509 questions and 17 multi-turn conversations with expected answers, personas, priority,
   language and the guardrails each one exercises. Authored in Python modules, built into an Excel workbook, and then
   every key fact of every expected answer was checked against an official page and signed off.
2. **Evaluation harness** (`eval/`): asks the bot every question, grades each answer with rule-based checks and a
   Claude judge on Amazon Bedrock, applies the concept note's release criteria, and builds the review workbooks and
   HTML reports for the team and stakeholders.

The repository was originally the `golden-tests/` folder of a larger working tree
(`/home/user/NeGD/India.gov.in/golden-tests/eval` appears in `eval/runs/golden-20261027/GATES.md`). That larger tree
also held a "Documents Given" folder with the team's inputs, which are **not** in this repository.

## Inputs the project was built from ("Documents Given", not in the repository)

| Input | Date | Used for |
|---|---|---|
| Concept note "One Government, One Conversation" | - | Scope rules (sections 3.2, 3.3, 6.1-6.3), retrieval and citation rules (7.4-7.8), release criteria (9.2), evaluation method (9.3-9.6). Section numbers are quoted throughout the code. |
| Deck `UMANG-Saathi-14-Oct-2026.pptx`, slide 10 | 14 Oct 2026 | The five-step response flow rubric for procedure and service questions |
| Guardrails table (`Guardrails.png`) | 15 Oct 2026 | The 16 guardrails G01-G16 in `guardrails.py` |
| Ingested-websites CSV (team export) | 14 Oct 2026 | `ingested-websites.csv`: 199 crawled sites (195 `indexed`, 4 with no status); the trust boundary for "crawled" sources |
| Developer QA seed `qa-golden-set-seed-top10-sources.md` | 16 Oct 2026 | Parsed by `parse_seed.py` into `index_seed.json` (10 sources, 39 indexed chunks) for the index-grounded questions |
| Developer statements | 14 Oct 2026 | UMANG and myScheme are not crawled; the bot reads them from internal DB/API |
| Bot source registry (`GET /v1/sources`) | 16 Oct 2026 | `eval/bot_sources.json`, 794 sources; a registry entry means the bot may use the site, not that its content is indexed |

## Timeline (reconstructed from code comments, data and commit history)

| Date (2026) | Event |
|---|---|
| 13-15 Oct | Query bank written (`queries_a.py` to `queries_f.py`, variants, conversations); golden values verified on official pages, markers `[V]`, `[S]`, `[R]`, `[RECHECK]`; `golden_verified.json` produced (112 answers, 15 Oct pass) |
| 14 Oct | Ingested-websites CSV received; deck slide 10 defines the response flow |
| 15 Oct | Guardrails table received; `guardrails.py` and `queries_f.py` (16 guardrail probes) added |
| 16 Oct | Developer seed file received; `queries_g.py` (48 index-grounded questions) added; Saathi API captured; bot registry saved; baseline evaluation run `umang-20261016` with a pilot (`umang-20261016-pilot`, 25 questions, 2 conversations) |
| 19 Oct | Budget of USD 200 approved for judged grading; re-check run `umang-20261019`; checklist grading of answers; its fact items later seeded the golden check |
| 27-28 Oct | Golden check run `golden-20261027`: every fact of all 526 test cases tied to an official page (2,732 facts); second-reader audit (4 packs); owner approved all 838 sign-off rows on 28 Oct; `apply --out` wrote `golden_test_cases_final_20261028.xlsx` |
| 28 Oct | Repository published (two commits) |
| 4 Nov | This knowledge base written; environment re-created and self-tests run (see document 9) |

## Who is involved

- **Owner** of the golden set: approves or rejects every changed, conflicting, unsupported and manual fact in
  `golden_signoff.xlsx` (approved all on 28 Oct 2026).
- **Checkers / graders / reviewers**: the batch-file instructions (`golden_check.md`, `golden_audit.md`,
  `checklist_grader.md`, `recheck_compare.md`) are written for people or Claude Code agents working from text batches
  and writing JSON files that the code validates. The findings page states that the checklist grading pass was done
  by Claude Opus 5.5.
- **Developers** of Saathi (NeGD team): supply the ingested list, registry, seed file, and are needed for guardrails
  that cannot be tested from outside (G04 dates in API, G06 correction queue, G10 masking in logs, G13 election mode,
  G15 planted injection page).
- **Stakeholders**: receive `saathi-findings.html`, `saathi-detailed-report.html` and `findings_by_test_case.xlsx`
  built with `build_reports.sh --shared` (no internal cost data).

## Where it stands (4 Nov 2026)

- Golden set: **final and signed off**. 485 of 509 questions carry "Verified on official page (28 Oct 2026); exact words
  on a saved copy"; 24 are behaviour-only (declines, out of scope, adversarial). All 526 test cases pass
  `golden_check.py status` ("ALL 526 TEST CASES CHECKED, EVERY QUOTE FOUND ON AN OFFICIAL PAGE").
- Evaluation harness: complete and exercised on the 16 and 19 Oct bot builds; those run folders are not in the
  repository (gitignored; only the golden evidence run is shared).
- Release criteria: the earlier runs did not meet them (the findings page narrative in `findings_page.py` describes
  unanswered questions as the biggest gap, outdated facts, missing next steps). The judge-vs-human agreement check
  required by concept note 9.3.4 has not been done; human grading remains the release criterion.
- The next evaluation needs: re-check of date-sensitive expected answers, a fresh collection against the current bot
  build, judged grading (budgeted), checklist grading, reports. See document 7 for the commands.
