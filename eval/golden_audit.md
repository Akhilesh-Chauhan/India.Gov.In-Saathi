# Second reading of the checked expected answers

The code has proved that every quote is on a saved copy of an official page. It cannot prove that the quote says what
the fact claims, or that checkers in different batches agree. You are the second reader. Your pack is
`runs/<run>/audit/part_N.txt`; each test case shows the expected answer before, every fact with its status, quote,
page and note, and (for rewritten answers) the behaviour and fail-if. Work from
the `eval` folder and follow `golden_check.md` for the file format and tools.

For every test case in your pack, check:

1. **The quote states the fact.** The value, rule, step or name in the fact must be in the quote itself, not only on
   the same page. If not: find the sentence that does state it (`golden_check.py page --run <run> URL --find ...`)
   and replace the quote, or reword the fact to exactly what the quote supports, or mark it `unsupported`.
2. **Nothing over-claims.** A fact must not add a qualifier, number or date the quote lacks. Derived values must say
   "derived" in the note.
3. **Unsupported and manual facts get one more try.** Where the pack shows `CONFIRMED ELSEWHERE?`, read that quote: if
   it states the same fact, use it (status `confirmed`, or `changed` if the value differs from the old answer). Retry
   manual facts: scanned PDFs are now read by OCR, and sites that were down (IMD, AICTE, Sarathi, EPFO) may be back.
4. **List and discovery questions.** Schemes picked as examples carry `"example": true`; facts every correct answer
   needs do not. Remove negative facts ("X does not apply") that a grader cannot tick; put them in fail-if instead.
5. **Not stricter than the question.** For answers that had no fixed value, keep the 2 to 4 facts a correct answer
   cannot leave out (more only when the question asks for steps). Drop side details.
6. **Behaviour and fail-if carry over.** For a rewritten answer, `behaviour` keeps everything the old expected answer
   asked the bot to do (cite which site, language, decline, helpline), and `fail_if` keeps the old "Fail if".
7. **Consistency.** The same fact (a fee, a rate, a date, a helpline) must have the same value in every test case of
   your pack. Note any clash with another pack in your reply.

Edit only the `runs/<run>/out/<ID>.json` files of the test cases in your pack. After every edit run
`golden_check.py check --run <run> --ids <ID>` until it prints OK. Never edit code, the golden workbook or another
pack's test cases, and never run anything that calls Bedrock.

Write `runs/<run>/audit/part_N_result.json`: a list of `{"id", "fact": n, "issue", "action"}` for every change, and
reply with counts (facts read, quotes replaced, facts reworded, now unsupported, manual resolved, example flags added,
facts trimmed) plus any cross-pack clash.
