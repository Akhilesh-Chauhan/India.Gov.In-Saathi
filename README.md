# Saathi golden-test evaluation

Evaluation framework for Saathi, the UMANG / India.gov.in citizen chatbot, built on
[DeepEval](https://github.com/confident-ai/deepeval). It asks the bot a fixed set of citizen questions and grades every
answer against expected answers taken from official government pages, using rule-based checks plus Claude on Amazon
Bedrock as the grader.

| Part | What it is | Where |
|---|---|---|
| Golden test set | 509 questions + 17 multi-turn conversations, with expected answers, priority, language, persona and guardrails | `golden_test_cases_final_20261028.xlsx` (sheet "Final golden" to read; "Test Queries" and "Conversation Scenarios" are what the code reads) |
| Evidence for the expected answers | Every key fact tied to an official page and the exact words on it, checked by code on a dated copy of the page (28 Oct 2026), then signed off | `eval/runs/golden-20261027/` (`out/` facts, `evidence/` checks, `golden_signoff.xlsx`) |
| Expected-answer check | Re-checks the expected answers against official pages before a run (no Bedrock cost) | `eval/golden_check.py`, `eval/golden_check.md` |
| Evaluation pipeline | Collects the bot's answers, grades them, scores PASS / PARTIAL PASS / FAIL, builds the reports | `eval/` (see `eval/README.md`) |

## Setup

```bash
git clone https://github.com/Akhilesh-Chauhan/India.Gov.In-Saathi.git && cd India.Gov.In-Saathi
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium        # only if Google Chrome is not installed (or set CHROME_PATH)
sudo apt install poppler-utils tesseract-ocr  # pdftotext and OCR for official PDFs
cp eval/.env.example eval/.env               # then fill in the AWS (Bedrock) credentials; never commit eval/.env
.venv/bin/python eval/selftest.py            # offline check with a fake bot and grader: must print SELFTEST PASSED
.venv/bin/python eval/golden_check.py selftest --run x
```
LibreOffice is needed only to recalculate the Excel reports (`eval/build_reports.sh`, set `RECALC` to a recalc script).

## Typical use

1. **Re-check the expected answers** shortly before a run, since official pages change (fees, dates, instalments).
   See "Checking the expected answers against official pages" in `eval/README.md`. Changes go to the owner in
   `golden_signoff.xlsx`; `golden_check.py apply --out <new workbook>` writes the result.
2. **Run the evaluation**: collect the bot's answers, grade them on Bedrock, score, build the reports. See
   "Running" and "Report files" in `eval/README.md`. Pass `GOLDEN_WORKBOOK=<file>` to use a workbook other than
   the final one.
3. **Share the results**: `BUDGET=200 ./eval/build_reports.sh <run> --shared` writes the findings page, the detailed
   report and the review workbook without internal cost data.

Grading on Bedrock is paid per call (roughly USD 100 to 150 for a full run of all test cases with Claude Opus);
the expected-answer check and the reports cost nothing on Bedrock.

## Not in this repository

- `eval/.env` (AWS keys) and `eval/bot_curl.txt` (the bot request, which may hold tokens): each user creates their own.
- The dated copies of the official pages behind the evidence (`eval/runs/golden-20261027/snapshots/`, about 730 MB),
  and the cached pages in `eval/page_cache/`; ask the owner for the archive if you need to inspect a copy.
- Earlier evaluation runs and their internal cost files.

## Known limits

- Some expected answers depend on the date (PM-KISAN instalments, DA/DR, exam deadlines, weather bulletins): re-check
  them before each run.
- A few facts could only be checked by a person (image-only pages, sites behind a login); they are marked `manual` in
  the evidence and listed in `golden_signoff.xlsx`.
- Q-380's 30-minute session rule comes from the project concept note, which has no public page.
