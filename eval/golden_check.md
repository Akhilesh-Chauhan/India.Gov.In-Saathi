# Checking the expected (golden) answers against official pages

The Saathi chatbot is graded against these expected answers, so every fact in them must be exactly what an official
government page says **today**. Nobody should be able to question one: each fact gets the official page, the exact words
on that page, and a dated copy of the page that the code keeps.

You get a batch file (`runs/<run>/batches/wave_NN/batch_NN.txt`) with test cases. For each test case, in order:

## 1. Read it
The question, the expected answer now, its status, any notes and sources found earlier, and the facts graders used on
19 Oct (a starting point only). Work out the **key facts** a correct answer must give: amounts, fees, dates, deadlines,
eligibility rules, documents, steps, portal or app names, helpline numbers, official URLs. Usually 2 to 6; one checkable
claim per fact. Behaviour ("cite uidai.gov.in", "reply in Hindi", "decline politely") is not a fact.

- **Expected answer has values** (Verified / Partly verified / RE-VERIFY / indexed chunk): list and check **every**
  factual claim in it, including steps, menu paths and conditions. A claim you leave out stays in the expected answer
  unchecked, which is exactly what we must avoid: each one must end up `confirmed`, `changed`, `unsupported` or `manual`.
- **Expected answer has no fixed value** ("Behaviour check", e.g. "Security features as published by RBI, cited"): find
  the official page and add the key facts it states that answer the question (status `added`). Add only the 2 to 4
  facts a correct answer cannot leave out; side details (other services on the same page, extra options) make the
  answer stricter than the question and invite dispute. Prefer a current page of the department over an old press release.
- **List or discovery questions** ("which schemes are there for...", "list schemes for students"): the bot may name any
  correct schemes, so schemes you pick are examples, not requirements. Add `"example": true` to those facts; the
  rebuilt answer then says "Acceptable examples (any one of these, or another correct scheme with its official criteria
  cited)". Facts that every correct answer needs (where to search, who decides eligibility) stay without the flag.
- **Nothing to look up** (out of scope, adversarial, personal record, a decline): no facts, give `no_facts_reason`. But
  a helpline, portal or office the expected answer names is a fact; check it.
- **Conversations (MT-xx):** check the facts in the turn texts (they come from the Q-IDs listed).

## 2. Find the official page
- Start with the expected site; any `*.gov.in`, `*.nic.in` page or rbi.org.in, nsdl.co.in, utiitsl.com, licindia.in,
  protean-tinfopvt.com, or a site the bot crawls also counts. News sites, blogs and portals like ClearTax do not.
- Search with the WebSearch tool (use `allowed_domains`, e.g. `["uidai.gov.in", "pib.gov.in"]`). **Do not use Firecrawl**
  (its credits are nearly used up).
- Prefer, in this order: the latest dated notification, circular, order or gazette of the department that owns the
  service; its FAQ or service page; its official PDF; a PIB release. Check the date: a newer official notice beats an older page.

## 3. Read the page through the code and copy the exact words
```bash
cd eval        # from the repository root
../.venv/bin/python golden_check.py page --run <run> "<url>" --find "<a word near the fact>"
../.venv/bin/python golden_check.py page --run <run> "<url>" --limit 8000      # first 8000 characters
../.venv/bin/python golden_check.py page --run <run> "<url>" --render --find "..."   # pages built by JavaScript
```
This is the exact text the check reads (it keeps a dated copy). A scanned PDF with no text layer is read with OCR from
the saved copy (English only); quote the OCR text as `page` prints it, so a scanned order is not a reason for `manual`. Copy the **quote** from this output, word for word: the
sentence or table row that states the fact, 15 to 300 characters. The quote itself must state the fact (the value,
the rule, the step); a neighbouring sentence on the same page is not evidence, even though the code would accept it. Do not paraphrase, shorten with "...", or join two
places. `--find` matches literally, so search for a word ("fee", "eligible", "helpline"), not a formatted number.
Hindi or other-language pages are fine; quote them as they are.

## 4. Write the file, then check it
Write `runs/<run>/out/<ID>.json` as soon as you finish the test case, then run:
```bash
../.venv/bin/python golden_check.py check --run <run> --ids <ID>
```
Fix every PROBLEM it prints and re-run until it says OK. Then move to the next test case.

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
  {"fact": "...", "status": "manual", "url": "...", "note": "why the code cannot read it"}
 ],
 "behaviour": "only when the expected answer is rewritten (see below)",
 "fail_if": "optional, when rewritten",
 "turns": ["conversations only, when rewritten: the new text for every turn, in order"],
 "no_facts_reason": "only when facts is empty",
 "summary": "one line: what you found or changed"
}
```

| status | when |
|---|---|
| `confirmed` | the expected answer states it and the page says the same |
| `changed` | the page now says something different; `fact` is the current value, `was` the old one |
| `added` | the expected answer had no fixed value; this fact comes from the page |
| `conflict` | two official pages disagree and no newer notice settles it; give both (`also`) |
| `unsupported` | no official page states it after a real search; it will be removed from the expected answer |
| `manual` | it is on an official page but only in an image, a scanned PDF or behind a login; a person checks it |

Write `fact` in plain English, one claim, so a grader can tick it. A value you work out yourself (arithmetic, a date
counted from a rule) is not on the page: quote the rule it comes from and say in `note` that the value is derived.

**Rewritten expected answers.** If any fact is `changed`, `added`, `conflict` or `unsupported`, the code rebuilds the
expected answer as: "Answer (official sources, checked <date>): <your facts>" + "Behaviour: <behaviour>" + "Fail if:
<fail_if>". So `behaviour` must carry over everything the old expected answer asked the bot to do (cite which site,
language, decline, ask a question first, give the helpline...), and `fail_if` should keep the old "Fail if" and add any
stale value the bot must not give (an old fee or date). For a `conflict`, write the behaviour so that either official
value is accepted when the bot cites the page it used. For conversations, also give `turns`: every turn's new text, with
only the facts changed. If every fact is `confirmed` (or `manual`), the expected answer text stays as it is.

## Rules
- Only write files in `runs/<run>/out/` for the test cases in your batch. Do not edit the golden workbook, other test
  cases' files, or any code. Do not run run_eval.py, facts_split.py, recheck.py or anything that calls Bedrock.
- Facts come from the official page, never from memory or a news site.
- Finish one test case completely (file written, check OK) before starting the next, so the work can stop at any point.
- If a check problem cannot be fixed (site down, page blocked), mark that fact `manual` with the reason, or find another
  official page.
- At the end, report: the test cases done, and for each one with `changed`, `conflict`, `unsupported` or `manual` facts,
  one line on what and why.
