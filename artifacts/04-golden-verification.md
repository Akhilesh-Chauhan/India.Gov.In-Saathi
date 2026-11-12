# 4. Golden verification: tying every expected answer to an official page

## Why it exists

The bot is graded against the expected answers, so an expected answer that is wrong or stale would wrongly fail the
bot. The golden check (`eval/golden_check.py`, instructions in `eval/golden_check.md`) makes every key fact of every
expected answer traceable to an official page, the exact words on that page and a dated copy of the page kept by the
code. Changes go to the owner before anything is written into the workbook. Run `golden-20261027` did this for all
526 test cases on 27-28 Oct 2026.

## Steps and commands (all from `eval/`)

| Step | Command | What happens |
|---|---|---|
| Export | `golden_check.py export --run R [--size 20] [--seed-run umang-20261019]` | Writes `runs/R/batches/wave_NN/batch_NN.txt` for test cases without an `out/<ID>.json`, sorted by expected site so one checker handles one site's pages. Each item shows the question, expected answer now, status, verification notes, sources found earlier, the indexed page, and (from the seed run's `checklist.jsonl`) the fact items graders used on 19 Oct as a starting point. |
| Read a page | `golden_check.py page --run R URL [--find word] [--limit N] [--render]` | Fetches the page through the same code the check uses, keeps the copy, prints the text (or the text around `--find` hits). `--render` opens it in headless Chrome and OCRs a PDF. Checkers copy quotes from this output. |
| Write | checker writes `runs/R/out/<ID>.json` | See the file format below. |
| Check | `golden_check.py check --run R [--ids Q-004]` | For every fact needing a quote: the URL must be official, the quote at least 15 letters/digits, the page is fetched (or its copy reused), and the quote must be on the page text word for word after normalisation. Falls back to a rendered copy and then OCR. Writes `runs/R/evidence/<ID>.json` with problems (empty when OK). |
| Status | `golden_check.py status --run R` | Progress, open problems, facts by status, quotes by site class, page copies kept, and "kept expected answers with figures no listed fact covers". Ends with `ALL N TEST CASES CHECKED, EVERY QUOTE FOUND ON AN OFFICIAL PAGE` when done. |
| Audit | `golden_check.py audit --run R [--parts 4] [--sample 60]` | Second-reader packs (`golden_audit.md`): every test case with a non-confirmed fact, every discovery question, plus a random sample of confirmed-only cases. Lists "CONFIRMED ELSEWHERE?" hints for unsupported/manual facts. Reviewers edit the out files and log changes in `audit/part_N_result.json`. |
| Sign-off | `golden_check.py signoff --run R` | `runs/R/golden_signoff.xlsx` for the owner: sheets "Changed or removed" (changed, conflict, unsupported, manual facts; decide every row), "Facts added" (blank counts as Approve), "New expected answers" (before/after with evidence), "How to use". |
| Apply | `golden_check.py apply --run R [--out FILE] [--provisional]` | Refuses unless every test case is checked clean and every owner row is decided (unless `--provisional`). Rewrites expected answers, fills Golden sources (verified URLs), Golden-fact status, Verification notes, Owner sign-off; rewrites conversation turn texts; adds the "Final golden" sheet. Without `--out` it edits the golden workbook in place and keeps a `.before-<run>.xlsx` backup. |
| Self-test | `golden_check.py selftest --run x` | Offline: quote matching across spacing, punctuation, scripts and doubled-letter PDF text; rejects short quotes, wrong words and non-official sites. Prints `GOLDEN CHECK SELFTEST PASSED`. |

Every step skips finished test cases, so the work can stop and resume.

## The checker's file: `runs/<run>/out/<ID>.json`

```json
{
 "id": "Q-004",
 "checked_on": "2026-10-27",
 "facts": [
  {"fact": "Otherwise a biometric update costs Rs 125", "status": "confirmed",
   "url": "https://uidai.gov.in/en/aadhaar-seva-kendra", "quote": "(iii) If done otherwise: ₹125*"},
  {"fact": "...", "status": "changed", "was": "the old expected value", "url": "...", "quote": "..."},
  {"fact": "...", "status": "conflict", "was": "...", "url": "...", "quote": "...",
   "also": [{"url": "<the other official page>", "quote": "<its exact words>"}], "note": "what you searched"},
  {"fact": "...", "status": "unsupported", "note": "where you looked"},
  {"fact": "...", "status": "manual", "url": "...", "note": "why the code cannot read it"},
  {"fact": "...", "status": "added", "example": true, "url": "...", "quote": "..."}
 ],
 "behaviour": "required when any fact is changed/added/conflict/unsupported",
 "fail_if": "optional",
 "turns": ["conversations only: new text for every turn"],
 "no_facts_reason": "only when facts is empty",
 "summary": "one line"
}
```

| Status | Meaning | Needs quote | Rewrites answer | Owner decides |
|---|---|---|---|---|
| `confirmed` | Expected answer states it and the page says the same | yes | no | no |
| `changed` | Page now says something different; `fact` is current, `was` the old value | yes | yes | yes |
| `added` | Expected answer had no fixed value; this fact comes from the page | yes | yes | yes (blank = Approve) |
| `conflict` | Two official pages disagree and no newer notice settles it; both quoted | yes (both) | yes | yes |
| `unsupported` | No official page states it after a real search; removed from the answer | no | yes | yes |
| `manual` | On an official page but only as an image, scanned PDF the code could not OCR, or behind a login | no | no | yes |

Rules from `golden_check.md` that explain the data you will see: one checkable claim per fact; 2 to 6 facts for
answers with values (every claim must be covered); 2 to 4 facts for behaviour-only answers; list/discovery questions
mark scheme picks as `"example": true`; derived values quote the rule and say "derived" in the note; facts come from
official pages only (`*.gov.in`, `*.nic.in`, rbi.org.in, nsdl.co.in, utiitsl.com, licindia.in, protean-tinfopvt.com,
or a crawled site or its subdomain), never news sites or ClearTax.

## The code's evidence: `runs/<run>/evidence/<ID>.json`

Per fact: `n`, `status`, `url`, `final` (after redirects), `http`, `fetched_at` (IST), `sha256` of the saved copy,
`copy` (file name in `snapshots/`), `rendered` (headless Chrome used), `ocr`, `site` (crawled, subdomain-of-crawled,
official-not-crawled, DB/API), `quote_found`, `also` (for conflicts). Plus `problems` (list) and `out_sha256`: the
SHA-256 of the out file the evidence was made from. The second commit (28 Oct) introduced this fingerprint so the
evidence stays valid after a git clone, which does not preserve file times.

Quote matching (`squash` / `on_page`): NFKC-normalise, lower-case, keep only letters, digits and combining marks;
the quote must be a substring of the page text, or of the page text with doubled letters collapsed (PDFs whose bold
text comes out as "TThhee"). Minimum 15 letters/digits.

Page copies (`snapshot()`): plain fetch with `urllib` (PDF text via `pdftotext` in layout and raw modes); if the text is
under 800 characters or `--render` is asked, headless Chrome (`/usr/bin/google-chrome` or `CHROME_PATH`, else
Playwright's Chromium) renders it; a PDF with no text layer (or on request) is OCR'd with `pdftoppm` + `tesseract`
(first 25 pages, English). Firewall/error pages matched by the `BLOCKED` regex are never kept. Copies live in
`runs/<run>/snapshots/<sha1-20>.{html,pdf,txt,rendered.html,rendered.txt,ocr.txt,json}`.

## What the golden-20261027 run found

| Measure | Value |
|---|---|
| Test cases | 526 (509 questions + 17 conversations), 27 export batches of 20 |
| Facts | 2,732: confirmed 1,894, added 755, changed 30, manual 28, unsupported 15, conflict 10 |
| Expected answers rewritten | 283 (269 questions, 14 conversations); 243 kept as they were |
| Quotes found by site class | crawled 2,321; subdomain-of-crawled 194; DB/API 89; official-not-crawled 85 |
| Facts needing the browser | 248 rendered; 52 read by OCR |
| Test cases with manual facts | 18 (MT-01, Q-006, Q-008, Q-010, Q-029, Q-030, Q-054, Q-060, Q-154, Q-155, Q-174, Q-179, Q-208, Q-276, Q-298, Q-310, Q-395, Q-402), mostly myAadhaar screens behind a login or sites that were down |
| Owner decisions | 83 "Changed or removed" rows and 755 "Facts added" rows, all Approve ("Owner approved all changes in the Claude Code session, 28 Oct 2026") |
| Result | `golden_test_cases_final_20261028.xlsx` written with `apply --out`; `golden_test_cases_phase1.xlsx` byte-identical to before |
| Golden-fact status in the final workbook | 485 "Verified on official page (28 Oct 2026); exact words on a saved copy"; 24 "Behaviour only, no facts to check (28 Oct 2026): ..." |
| Owner sign-off column | 49 "approved", 460 "not needed" |
| Open notes from `status` | 3 kept answers have figures no fact covers: Q-067 (31), Q-092 (12, 26), Q-380 (30: the 30-minute session rule comes from the concept note, which has no public page) |

Examples of what changed: UIDAI extended the free first mandatory biometric update for ages 7-15 to 30.09.2027
(Q-002); the Head-of-Family address update time is "normally up to 60 days" per UIDAI's Citizen's Charter, not 30
days (MT-01, Q-006); the DEA Office Memorandum of 30.09.2026 keeping small-savings rates unchanged was a scanned PDF
read by OCR (Q-121).

## Completion gates (`runs/golden-20261027/GATES.md`)

G1 self-test passes; G2 status reports every test case checked with every quote found; G3 no evaluation run was
started on the unchecked goldens; G4 owner decided every changed/conflict/unsupported/manual fact; G5 apply wrote a
new final workbook leaving phase1 unchanged. All five are ticked with evidence hashes.

## Re-checking before the next evaluation run

Official pages change (fees, instalments, deadlines). The intended routine: `export` a new wave for the test cases
whose facts are date-sensitive (or all), re-check, `signoff`, `apply --out <new workbook>`, then run the evaluation
with `GOLDEN_WORKBOOK=<new workbook>`. Known date-sensitive items: PM-KISAN instalments, DA/DR, exam and NSP deadlines,
small-savings rates each quarter, weather bulletins, MSP each season, EPF rate each year. `golden_verified.json` flags
38 answers with `recheck: true`, and the Read Me sheet lists RE-VERIFY rows.

Because `snapshots/` is not in the repository, a fresh clone has "page copies kept: 0"; `check` re-fetches pages as
needed, while `status` still reports the committed evidence as current through the `out_sha256` fingerprint.
