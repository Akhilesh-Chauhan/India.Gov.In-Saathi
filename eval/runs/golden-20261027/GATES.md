# Gates: expected (golden) answers checked against official pages

OWNS: golden_check.py, golden_check.md, README.md, runs/golden-20261027/**

Scope: every one of the 509 questions and 17 conversations has its key facts tied to an official page, the exact words on a dated copy of that page, changes signed off by the owner and written into the golden workbook, with the evaluation pipeline not started.

- [x] G1: the quote check accepts real quotes and rejects made-up, short and non-official ones (offline controls)
  CHECK: ../.venv/bin/python golden_check.py selftest --run x
  EXPECT: GOLDEN CHECK SELFTEST PASSED
  EVIDENCE: automatic-evidence=v1; definition-sha256=b66b1c82f28a2c341b7dad6f84c8d1bcaec207d7d39ce06a96624b507968b30d; exit=0; EXPECT=matched; output-sha256=59a08fdad6a0223c37eb661b51b1747b1600303b75f1500bd243e15a288d6cae; output-bytes=29; shell=/bin/sh; cwd=/home/user/NeGD/India.gov.in/golden-tests/eval; path=b3b71b1ad19d/15 entries

- [x] G2: every test case in the golden workbook has a checker file whose every quote was found on an official page
  CHECK: ../.venv/bin/python golden_check.py status --run golden-20261027
  EXPECT: /^ALL \d+ TEST CASES CHECKED, EVERY QUOTE FOUND ON AN OFFICIAL PAGE$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=66e5c032c112e3bd50e421f5827ac5ccc0027445a42c08dee63c283d12a24418; exit=0; EXPECT=matched; output-sha256=4122b957189b57a8f0ecced035b941584180691fc77710f76426db4e8075c3c8; output-bytes=604; shell=/bin/sh; cwd=/home/user/NeGD/India.gov.in/golden-tests/eval; path=b3b71b1ad19d/15 entries

- [x] G3: the evaluation pipeline has not been started (no new umang run folder after 19 Oct)
  CHECK: ../.venv/bin/python -c "import pathlib,sys; d=[p.name for p in pathlib.Path('runs').glob('umang-202610[23]*')]; print(d or 'NO NEW EVAL RUN'); sys.exit(1 if d else 0)"
  EXPECT: NO NEW EVAL RUN
  EVIDENCE: automatic-evidence=v1; definition-sha256=f6ec4513c2885df46a7a4bd3eac264a1353f37d00d13acf5e3f9f7c80078ed3d; exit=0; EXPECT=matched; output-sha256=66c8c9015b0f23be7bfb9dfac1166ee6cf464a81f34c83e64d259cd1272fa8b6; output-bytes=16; shell=/bin/sh; cwd=/home/user/NeGD/India.gov.in/golden-tests/eval; path=b3b71b1ad19d/15 entries

- [x] G4: the owner has approved or rejected every changed, conflicting, unsupported and manual fact in golden_signoff.xlsx
  EVIDENCE: owner approved all changes in the Claude Code session on 28 Oct 2026 ("you have my sign off but still make a new file"); recorded as Approve on all 838 rows of golden_signoff.xlsx (83 changed/conflict/unsupported/manual + 755 added)

- [x] G5: apply has written the approved answers into a new final golden workbook (owner asked for a new file), leaving golden_test_cases_phase1.xlsx unchanged
  EVIDENCE: golden_check.py apply --out ../golden_test_cases_final_20261028.xlsx on 28 Oct 2026; independent read-back: 509 questions + 17 conversations, 283 answers equal the rebuilt text, 243 unchanged, all other columns identical, owner sign-off column 'approved'/'not needed' only; cmp shows golden_test_cases_phase1.xlsx byte-identical to its copy taken before apply
