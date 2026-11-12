# 3. The golden dataset: how it was created

## Design intent

The set was written to test the concept note's release criteria, not to be a random sample of traffic:

- **Freshness** (9.4): the answer gives the current figure or date, not a stale one even if cited.
- **Citation accuracy** (7.6.2, 9.4): every factual sentence is cited and the cited page contains it.
- **Source genuineness** (7.6.2(5), 7.7): every link is official, opens, is not a look-alike, and comes from the
  crawled list or UMANG/myScheme data.
- **Routing and scope** (6.2, 6.3, 3.3): question types behave as specified; safety and abstention rules hold.
- **Response flow** (deck slide 10) and the **16 guardrails**.

So each row carries a *primary test focus*, a *question type*, a *persona* and *language*, and the expected answer
often includes an explicit "Fail if" list of stale values or forbidden behaviours.

## Authoring format

Every single-turn row in `queries_a.py` .. `queries_g.py` is one tuple:

```
(domain, topic, qtype, persona, level, lang, style, focus, priority, query, expected)
```

| Field | Values |
|---|---|
| `domain` | Expected source site. Special forms: `-` (no source expected), `NOT-INGESTED:<domain>` (official site not available to the bot; the builder downgrades this to a plain domain if the bot registry lists it), `<sourceId>#<Letter>` (an indexed chunk key from `index_seed.json`, group G only), `myscheme.gov.in` / `web.umang.gov.in` (DB/API sources). Any other domain must be in `ingested-websites.csv` or `eval/bot_sources.json` (asserted at build). |
| `qtype` | `DISC` scheme discovery, `DET` scheme/fact detail, `USE` service use, `PROC` service procedure, `RULE` current rule or circular, `PERS` personal record, `STATE` state-specific, `OOS` out of scope, `ABST` insufficient sources, `ADV` adversarial/injection |
| `persona` | One of 23 codes (FARM, HOME, STU, GRAD, ENG, TEA, POL, PEN, WID, SHOP, MOM, LAB, EXS, PWD, CA, JOUR, LAW, SCH, FOUN, ASHA, TG, DOC, NRI); see document 8 |
| `level` | `L0` zero knowledge, `L1` some knowledge, `L2` expert |
| `lang` | `EN`, `HI` (Devanagari), `HG` (Hinglish), `MR` (Marathi, one row) |
| `style` | `S` simple, `V` vague, `T` typo/informal, `F` formal, `M` multi-part, `C` comparative, `W` wrong premise/rumour, `E` emotional/urgent, `D` data, `L` legal-precise, `P` contains personal identifier |
| `focus` | `FRESH`, `CITE`, `SRC`, `ROUTE`, `SAFE`, `ABST` |
| `priority` | `P0` demo set, `P1`, `P2` |
| `query` | Typed exactly as a citizen would (typos and all) |
| `expected` | Expected behaviour / golden answer, with verification markers (below) |

Markers inside `expected` are stripped by the builder and turned into the "Golden-fact status" column:

| Marker | Meaning |
|---|---|
| `[V]` | Verified on official page (13-15 Oct 2026) |
| `[V press]`, `[V via newsonair.gov.in]`, `[V title]` | Verified through a press report / newsonair / PIB title; confirm on the official page |
| `[S]` | Stable fact, not re-verified; reviewer to confirm |
| `[R]`, `[R period]` | Reviewer to fill the golden value (or the period) from the cited page |
| `[IDX]` | Grounded in an indexed chunk from the developer seed |
| `[IDX-STALE]` | The indexed chunk is outdated; the golden follows the current official position and the bot must not present the old text as current (PM-KISAN 2-hectare limit, NFSA Rs 3/2/1 prices, pre-2026 EPF rules) |
| `[RECHECK]`, `[RECHECK: note]`, `[RECHECK DEA OM]`, `[RECHECK on EPFO]` | Re-verify on demo day (values that change any day) |
| none | "Behaviour check (no fixed value)" |

Variant groups (`queries_variants.py`):

```
(group_id, need, domain, qtype, focus, priority, expected, [(persona, level, lang, style, query), ...])
```

VG-01 PM-Kisan benefit, VG-02 ITR audit due date, VG-03 SCSS rate, VG-04 wheat MSP, VG-05 DA, VG-06 Aadhaar mobile fee,
VG-07 NSP renewal deadline, VG-08 EPF rate, VG-09 EPF passbook via UMANG, VG-10 senior-citizen scheme discovery. Each
group has four variants; all four must give the same facts and sources.

Conversations (`conversations.py`):

```
(scenario, title, based_on, persona, lang, [(user_turn, expected_behaviour, flow_steps), ...])
```

`based_on` lists query-text prefixes of rows whose verified golden answers hold the facts (or a VG id); the builder
resolves them to Test IDs and asserts each prefix matches exactly one row. `flow_steps` names the slide-10 steps
the turn exercises ("1-2", "3", "4-5", ...). The 17 scenarios cover: Aadhaar address change (MT-01), Aadhaar mobile
update with an intermediary (MT-02), Sukanya Samriddhi (MT-03), crop loss under PMFBY (MT-04), consumer complaint
(MT-05), RTI (MT-06), UPI fraud emergency (MT-07), UDID card (MT-08), Udyam registration with a paid look-alike
(MT-09), EPF passbook direct UMANG service (MT-10), theft on a train (MT-11), NSP renewal with cyber-cafe fee and
fake site (MT-12), life certificate for an 82-year-old (MT-13), PF withdrawal with an agent (MT-14), MUDRA loan for a
shop (MT-15), Bihar caste certificate "named not refused" (MT-16), emergency in the middle of a pension question (MT-17).

## Build order and Test IDs

`build_golden_tests.py rows()` concatenates, in this order: GROUPS_A, B, C, D, E, F; then the variant sets (category
"Persona variation sets"); then GROUPS_G **last** ("appended last so earlier Test IDs, and answers already collected
for them, never shift"). IDs are `Q-{position:03d}`. Totals: A 69 + B 83 + C 76 + D 140 + E 37 + F 16 + variants 40 + G 48 = **509**.

For each row the builder:

1. Resolves the domain: `#` keys to the registry domain of the chunk's sourceId; `NOT-INGESTED:` to the plain domain
   if the registry lists it; sets Portal (site name from the CSV or registry) and Source availability
   (`Crawled`, `Bot registry`, `DB/API`, `Not available`, `n/a`).
2. Expands persona to Profile, Gender, Age, Age group.
3. Splits markers into the expected text and the status string.
4. If `golden_verified.json` has an entry for the exact query text, replaces the expected text with its `golden`,
   sets status from its `status` (VERIFIED / PARTIAL / NOT_ON_OFFICIAL_SOURCE / UNREACHABLE, plus RE-VERIFY if
   `recheck`), fills "Golden sources (verified URLs)" and "Verification notes".
5. Attaches the response-flow rubric: `FLOW_PROC` for PROC rows, `FLOW_USE` for USE rows (145 rows in total).
6. Tags guardrails with `guardrails.tag(qtype, focus, style, category, availability, query, expected)`.
7. For index-grounded rows, copies the chunk key, URL, first 1,500 chars of text and lastUpdated.

## Workbook produced (`golden_test_cases_phase1.xlsx`)

| Sheet | Content |
|---|---|
| Read Me | Scope, what is tested, how queries vary, how to run manually, status legend, findings about the ingested list (UMANG/myScheme not crawled; State portals are ingested although 6.2 says State content is out of MVP; about 20 ingested sites are not on .gov.in), response flow, guardrails, index-grounded rows |
| Personas | 23 personas with COUNTIF of rows |
| Test Queries | One row per question, 39 columns (40 in the final workbook). Yellow columns V..AD are tester input (Actual response, Sources shown, Doc date shown, Retrieval time shown, Freshness/Citation/Source genuine P/F/NA, Overall formula, Notes); white columns are golden data. Data validation lists for Y/N and P/F/NA. |
| Coverage | Counts by Category, Portal, Gender, Age group, Knowledge level, Language, Query style, Question type, Focus, Priority, Source availability |
| Source Check | Paste cited URLs; `check_sources.py` fills the automatic columns |
| Conversation Scenarios | One row per turn: Scenario, Title, Golden facts in, Persona, Language, Turn, User says, Expected bot behaviour, Flow steps, Bot reply, Turn result, Notes |
| Guardrails | The 16 guardrails with counts of rows, P0 rows and scenario turns that exercise each |
| Summary | Pass/fail formulas per measure, overall, by language / knowledge level / category, with concept-note targets |

Test Queries columns (final workbook): Test ID, Category, Variant group, Portal, Expected source domain, Source
availability, Topic, Question type (concept note), Persona code, Profile, Gender, Age, Age group, Knowledge level,
Language, Query style, Query (type exactly), Primary test focus, Expected behaviour / golden answer, Golden-fact
status, Priority, Actual response (summary / screenshot ref), Sources shown (URLs), Doc date shown? (Y/N), Retrieval
time shown? (Y/N), Freshness (P/F/NA), Citation accuracy (P/F/NA), Source genuine (P/F/NA), Overall, Notes, Golden
sources (verified URLs), Verification notes, Expected response flow (deck slide 10), Response flow (P/F/NA),
Guardrails exercised, Index chunk (developer seed), Index chunk URL, Index chunk text, Index chunk last updated,
Owner sign-off.

The harness reads only three things from the workbook: Test Queries rows (`load_rows`), Conversation Scenarios
(`load_scenarios`), and, for grading, the columns Expected behaviour / golden answer, Golden-fact status, Question
type, Source availability, Language, Profile, Knowledge level, Expected response flow, Index chunk URL, Guardrails
exercised and the human P/F columns (for Judge vs Human).

## Composition of the final set (509 questions)

| Dimension | Breakdown |
|---|---|
| Priority | P0 169, P1 185, P2 155 |
| Language | English 296, Hindi 117, Hinglish 95, Marathi 1 (Q-318, an out-of-language test) |
| Question type | Scheme/fact detail 187, Service procedure 99, Current rule or circular 86, Service use 46, Scheme discovery 28, Out of scope 21, Personal record 15, State-specific 13, Adversarial 7, Insufficient sources 7 |
| Primary focus | Citation accuracy 239, Freshness 138, Routing/hand-off 63, Source genuineness 31, Safety/scope 31, Abstention 7 |
| Source availability | Crawled 434, DB/API 48, n/a 18, Bot registry 7, Not available 2 |
| Knowledge level | L1 242, L0 187, L2 80 |
| Query style | Simple 279, Emotional/urgent 39, Typo 38, Legal-precise 37, Data 36, Wrong premise 28, Multi-part 15, Vague 12, Comparative 12, Formal 7, Personal identifier 6 |
| Categories (19) | Provident fund/pension/social security 49, Index-grounded 48, Identity & documents 46, Persona variation sets 40, Agriculture 38, Food/consumer/grievance 38, Banking/savings/insurance 34, Education/skills/jobs 26, Tax & GST 23, Women/children/social welfare 23, Discovery/transport 22, Out of scope/safety/non-ingested 19, myScheme 19, UMANG 18, Guardrail probes 16, Housing/urban/rural 14, Health 13, Business 13, State services 10 |
| Rows with a response-flow rubric | 145 (99 PROC + 46 USE) |
| Index-grounded rows (Source recall check applies) | 48 |
| Variant-set rows | 40 |
| Top personas | FARM 47, LAB 47, STU 42, ENG 41, PEN 39 |

## Golden answer shape after the golden check

Two forms exist in the final workbook:

1. **Kept text** (243 test cases: every fact was `confirmed` or `manual`): the original expected text, for example
   Q-001 "Channels listed by UIDAI: Aadhaar Enrolment Centre, postman (IPPB doorstep) or the Aadhaar app; ... Fee: Rs 75
   when done as a separate demographic update; ... Cite uidai.gov.in."
2. **Rebuilt text** (283 test cases: 269 questions and 14 conversations with a `changed`, `added`, `conflict` or
   `unsupported` fact), generated by `golden_check.new_golden()`:

   ```
   Answer (official sources, checked 28 Oct 2026): <one sentence per live fact>
   Acceptable examples (any one of these, or another correct scheme with its official criteria cited): <example facts>   (list questions only)
   Behaviour: <everything the old text asked the bot to do: cite which site, language, decline, helpline...>
   Fail if: <old Fail if plus any stale value the bot must not give>
   ```

Graders rely on the "Fail if" part for stale values and forbidden behaviour, and `unanswered_split.golden_figures()`
deliberately reads only the text before "Behaviour:" / "Fail if:" so stale values are not mistaken for key figures.

## Companion data

- `golden_verified.json` records (112): `id`, `query`, `golden`, `status`, `sources[{url, supports, host_status}]`,
  `unverified`, `notes`, `recheck`. `host_status` uses the same classes as `pages.host_class` (crawled,
  subdomain-of-crawled, ...). These were the 15 Oct 2026 verification pass that fed the draft workbook; the 27-28 Oct
  golden check superseded them.
- `index_seed.json`: sources uidai-gov-in, incometax-gov-in, indianrailways-gov-in, pmkisan-gov-in, epfo-gov-in,
  nfsa-gov-in, passportindia-gov-in, eci-gov-in, sarathi-parivahan-gov-in, scholarships-gov-in. To extend group G,
  re-run `parse_seed.py` on the developer's larger seed file and add rows to `queries_g.py`.
- `eval/bot_sources.json`: registry snapshot; refreshed by `validate_features.py`. Used by the builder for Portal
  names and "Bot registry" availability and by `pages.ingested_domains()` for the source-genuineness trust list.
