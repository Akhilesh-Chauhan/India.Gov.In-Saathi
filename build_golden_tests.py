"""Builds golden_test_cases_phase1.xlsx: ~400 citizen queries over the ingested website list.

Scope: concept note 'One Government, One Conversation' sections 6 (MVP routing) and 9 (evaluation):
freshness, citation accuracy, genuineness of sources. Query data lives in queries_*.py.
Usage: python3 build_golden_tests.py "<ingested-websites CSV>"
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from queries_a import GROUPS_A
from queries_b import GROUPS_B
from queries_c import GROUPS_C
from queries_d import GROUPS_D
from queries_e import GROUPS_E
from queries_f import GROUPS_F
from queries_g import GROUPS_G
from guardrails import GUARDRAILS, tag as guardrail_tags
from queries_variants import VARIANTS
from conversations import FLOW_PROC, FLOW_USE, SCENARIOS

OUT = Path(__file__).with_name("golden_test_cases_phase1.xlsx")
# Developers (14-Oct-2026): UMANG and myScheme are not crawled; the bot reads them from internal DB/API.
# Golden answers verified on official pages (15-Oct-2026 pass), keyed by exact query text; overrides draft text.
GOLDEN_FILE = Path(__file__).with_name("golden_verified.json")
GOLDEN = {g["query"]: g for g in json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))} if GOLDEN_FILE.exists() else {}
VSTATUS = {"VERIFIED": "Verified on official page (15 Oct 2026)",
           "PARTIAL": "Partly verified (15 Oct 2026) - see Verification notes",
           "NOT_ON_OFFICIAL_SOURCE": "Not published on official sources - bot should say so",
           "UNREACHABLE": "Official page unreachable on 15 Oct 2026 - reviewer to check"}
# The bot's own source registry (GET /v1/sources, saved by eval/validate_features.py) and the developer's index seed.
REGISTRY_FILE = Path(__file__).parent / "eval" / "bot_sources.json"
REGISTRY = ({i["domain"].lower().removeprefix("www."): i for i in json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["items"]}
            if REGISTRY_FILE.exists() else {})
INDEX_FILE = Path(__file__).with_name("index_seed.json")
INDEX = ({c["key"]: c for c in json.loads(INDEX_FILE.read_text(encoding="utf-8"))["chunks"]} if INDEX_FILE.exists() else {})
API_SOURCES = {"myscheme.gov.in": "myScheme (internal DB/API)", "web.umang.gov.in": "UMANG (internal DB/API)"}

PERSONAS = {  # code: (profile, gender, age, how they ask)
    "FARM": ("Small farmer", "Male", 58, "Hindi/Hinglish, short, low digital literacy"),
    "HOME": ("Homemaker", "Female", 34, "Hindi, simple, asks for family"),
    "STU": ("College student", "Male", 20, "Hinglish/English, terse, typos"),
    "GRAD": ("Graduate job seeker", "Female", 23, "English, exam/job focused"),
    "ENG": ("Software engineer", "Female", 30, "English, precise, multi-part, edge cases"),
    "TEA": ("Government school teacher", "Female", 45, "Formal, asks on behalf of students"),
    "POL": ("Politician (ward councillor / MLA)", "Male", 52, "Wants numbers, comparisons, credit; tests neutrality"),
    "PEN": ("Retired central govt pensioner", "Male", 71, "Polite, detailed, rumour-prone"),
    "WID": ("Widow, senior citizen", "Female", 67, "Hindi, anxious, zero tech knowledge"),
    "SHOP": ("Small shopkeeper / trader", "Male", 41, "Hinglish, practical, cost focused"),
    "MOM": ("Pregnant working woman", "Female", 28, "English, benefits and leave"),
    "LAB": ("Daily-wage / migrant worker", "Male", 35, "Hinglish with typos, urgent"),
    "EXS": ("Ex-serviceman", "Male", 63, "English, pension and welfare"),
    "PWD": ("Person with visual disability", "Female", 31, "English, accessibility needs"),
    "CA": ("Chartered accountant", "Female", 38, "Section/circular numbers, expects exact citations"),
    "JOUR": ("Journalist / researcher", "Female", 27, "Data, dates, asks for sources"),
    "LAW": ("Lawyer", "Male", 44, "Legal provisions, precise wording"),
    "SCH": ("School student", "Female", 16, "Simple English, first-time user"),
    "FOUN": ("Startup founder", "Male", 33, "Business compliance, expert"),
    "ASHA": ("ASHA / Anganwadi worker", "Female", 42, "Hindi, asks for community"),
    "TG": ("Transgender person", "Transgender", 27, "Rights and documents"),
    "DOC": ("Doctor", "Female", 36, "Professional, regulatory"),
    "NRI": ("Indian working abroad (Gulf)", "Male", 29, "Hinglish, documents from abroad"),
}
QTYPE = {"DISC": "Scheme discovery (6.2)", "DET": "Scheme / fact detail (6.2)", "USE": "Service use (6.2)",
         "PROC": "Service procedure (6.2)", "RULE": "Current rule or circular (6.2)", "PERS": "Personal record (6.2)",
         "STATE": "State-specific (6.2)", "OOS": "Out of scope (3.3, 6.3)", "ABST": "Insufficient sources (7.6.5)",
         "ADV": "Adversarial / injection (7.7)"}
LEVEL = {"L0": "L0 - Zero knowledge", "L1": "L1 - Some knowledge", "L2": "L2 - Expert / informed"}
LANG = {"EN": "English", "HI": "Hindi (Devanagari)", "HG": "Hinglish (romanised Hindi)", "MR": "Marathi"}
STYLE = {"S": "Simple direct", "V": "Vague / incomplete", "T": "Typo / informal", "F": "Formal / long",
         "M": "Multi-part", "C": "Comparative", "W": "Wrong premise / rumour", "E": "Emotional / urgent",
         "D": "Data / statistics", "L": "Technical / legal precise", "P": "Contains personal identifier"}
FOCUS = {"FRESH": "Freshness", "CITE": "Citation accuracy", "SRC": "Source genuineness",
         "ROUTE": "Routing / hand-off", "SAFE": "Safety / scope", "ABST": "Abstention"}
MARKERS = [("[V press]", "Verified via press report - confirm on official page"),
           ("[V via newsonair.gov.in]", "Verified via newsonair.gov.in - confirm on EPFO page"),
           ("[V title]", "PIB release title verified"),
           ("[V]", "Verified on official page (13-15 Oct 2026)"),
           ("[S]", "Stable fact, not re-verified - reviewer confirm"),
           ("[R period]", "Reviewer to fill period from cited page"),
           ("[R]", "Reviewer to fill golden value from cited page"),
           ("[IDX-STALE]", "Indexed chunk is outdated - golden follows the current official position"),
           ("[IDX]", "Grounded in an indexed chunk (developer seed, 16-Oct-2026)")]


def age_group(age):
    return "Under 18" if age < 18 else "18-25" if age <= 25 else "26-40" if age <= 40 else "41-59" if age < 60 else "60+"


def split_markers(text):
    status = []
    for m, label in MARKERS:
        if m in text:
            text = text.replace(m, "")
            status.append(label)
    for tag in ("[RECHECK DEA OM]", "[RECHECK on EPFO]", "[RECHECK]"):
        if tag in text:
            text = text.replace(tag, "")
            status.append("RE-VERIFY ON DEMO DAY")
    tail = text.rfind("[RECHECK:")  # e.g. "[RECHECK: 24th expected Oct 2026]"
    if tail != -1:
        status.append("RE-VERIFY ON DEMO DAY (" + text[tail + 9:text.index("]", tail)].strip() + ")")
        text = text[:tail]
    return text.strip(), "; ".join(status) or "Behaviour check (no fixed value)"


def load_ingested(path):
    with open(path, encoding="utf-8-sig") as f:
        return {r["Domain"].strip().lower().removeprefix("www."): r["Site"] for r in csv.DictReader(f)}


def rows(ingested):
    out = []
    for category, items in GROUPS_A + GROUPS_B + GROUPS_C + GROUPS_D + GROUPS_E + GROUPS_F:
        for r in items:
            out.append((category, "") + r)
    for gid, need, dom, qtype, focus, pri, expected, variants in VARIANTS:
        for persona, lvl, lang, style, query in variants:
            out.append(("Persona variation sets", gid, dom, need, qtype, persona, lvl, lang, style, focus, pri, query, expected))
    # Appended last so earlier Test IDs (and answers already collected for them) never shift.
    for category, items in GROUPS_G:
        for r in items:
            out.append((category, "") + r)
    final = []
    for i, (category, vg, dom, topic, qtype, persona, lvl, lang, style, focus, pri, query, expected) in enumerate(out, 1):
        chunk = INDEX.get(dom) if "#" in dom else None
        if "#" in dom:
            assert chunk, f"unknown index chunk {dom}"
            dom = next(d for d, it in REGISTRY.items() if it["sourceId"] == chunk["sourceId"])
        if dom.startswith("NOT-INGESTED:") and dom.split(":", 1)[1].lower().removeprefix("www.") in REGISTRY:
            dom = dom.split(":", 1)[1]  # the bot's registry lists it after all
        if dom == "-":
            src, site, ing = "None expected", "-", "n/a"
        elif dom.lower().removeprefix("www.") in API_SOURCES:
            src, site, ing = dom, API_SOURCES[dom.lower().removeprefix("www.")], "DB/API"
        elif dom.startswith("NOT-INGESTED:"):
            src, site, ing = dom.split(":", 1)[1], "(official site not available to the bot)", "Not available"
        else:
            key = dom.lower().removeprefix("www.")
            assert key in ingested or key in REGISTRY, f"{dom} is not in the ingested list or the bot registry"
            src, site, ing = (dom, ingested[key], "Crawled") if key in ingested else (dom, REGISTRY[key]["siteName"], "Bot registry")
        profile, gender, age, _ = PERSONAS[persona]
        exp, status = split_markers(expected)
        sources = notes = ""
        g = GOLDEN.get(query)
        if g:
            exp = g["golden"]
            status = VSTATUS[g["status"]] + ("; RE-VERIFY ON DEMO DAY" if g.get("recheck") else "")
            sources = "\n".join(f"{x['url']} - {x.get('supports', '')} [{x.get('host_status', '')}]" for x in g.get("sources", []))
            notes = "\n".join(t for t in (g.get("unverified") and "Unverified: " + g["unverified"], g.get("notes")) if t)
        final.append([f"Q-{i:03d}", category, vg, site, src, ing, topic, QTYPE[qtype], persona, profile, gender, age,
                      age_group(age), LEVEL[lvl], LANG[lang], STYLE[style], query, FOCUS[focus], exp, status, pri]
                     + [None] * 9 + [sources, notes, {"PROC": FLOW_PROC, "USE": FLOW_USE}.get(qtype, ""), None,
                        ", ".join(guardrail_tags(qtype, focus, style, category, ing, query, exp)),
                        chunk["key"] if chunk else None, chunk["url"] if chunk else None,
                        (chunk["text"][:1500] if chunk else None), chunk["lastUpdated"] if chunk else None])
    return final


HEAD = ["Test ID", "Category", "Variant group", "Portal", "Expected source domain", "Source availability", "Topic",
        "Question type (concept note)", "Persona code", "Profile", "Gender", "Age", "Age group", "Knowledge level",
        "Language", "Query style", "Query (type exactly)", "Primary test focus", "Expected behaviour / golden answer",
        "Golden-fact status", "Priority",
        "Actual response (summary / screenshot ref)", "Sources shown (URLs)", "Doc date shown? (Y/N)",
        "Retrieval time shown? (Y/N)", "Freshness (P/F/NA)", "Citation accuracy (P/F/NA)",
        "Source genuine (P/F/NA)", "Overall", "Notes", "Golden sources (verified URLs)", "Verification notes",
        "Expected response flow (deck slide 10)", "Response flow (P/F/NA)", "Guardrails exercised",
        "Index chunk (developer seed)", "Index chunk URL", "Index chunk text", "Index chunk last updated"]
WIDTH = [8, 22, 8, 26, 26, 9, 24, 22, 8, 22, 10, 6, 9, 16, 14, 16, 50, 14, 70, 30, 7, 40, 40, 9, 9, 10, 10, 10, 9, 30, 60, 50, 60, 10, 16, 24, 50, 70, 12]
FONT = Font(name="Arial", size=10)
BOLD = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
FLAG_FILL = PatternFill("solid", fgColor="FCE4D6")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


def header(ws, cols, widths):
    for c, (h, w) in enumerate(zip(cols, widths), 1):
        cell = ws.cell(1, c, h)
        cell.font, cell.fill, cell.alignment, cell.border = BOLD, HEAD_FILL, WRAP, BOX
        ws.column_dimensions[cell.column_letter].width = w
    ws.freeze_panes = "A2"


def body(ws, r, ncols, input_from=None):
    for c in range(1, ncols + 1):
        cell = ws.cell(r, c)
        cell.font, cell.alignment, cell.border = FONT, WRAP, BOX
        if input_from and c >= input_from:
            cell.fill = INPUT_FILL


def build(csv_path):
    ingested = load_ingested(csv_path)
    data = rows(ingested)
    last = len(data) + 1
    wb = Workbook()

    # ---- Read Me ----
    ws = wb.active
    ws.title = "Read Me"
    ws.column_dimensions["A"].width = 130
    readme = [
        ("Phase-1 golden test queries - AI-enabled Unified Citizen Information Service", 12),
        (f"{len(data)} citizen queries built on the crawled website list ({len(ingested)} sites, file dated 14-Oct-2026) plus UMANG and myScheme (internal DB/API). "
         "Based on concept note sections 6 (MVP scope and routing) and 9 (evaluation).", 0),
        ("", 0),
        ("What is tested", 11),
        ("Freshness - the answer gives the CURRENT figure/date and shows the document date. An old value is a FAIL even if it is cited (9.4).", 0),
        ("Citation accuracy - every factual sentence is cited, and the cited page actually contains that figure/date/name (7.6.2, 9.4).", 0),
        ("Source genuineness - every link is official, opens (HTTP 200), is not a look-alike/news/blog/social site, and comes from the crawled list or the UMANG/myScheme DB/API (7.6.2(5), 7.7).", 0),
        ("Routing and scope - section 6.2 question types and 6.3 exclusions behave as specified; safety and abstention rules hold.", 0),
        ("", 0),
        ("How the queries vary", 11),
        ("23 personas (Personas sheet): age 16-71, male/female/transgender, farmer to CA, politician, journalist, teacher, engineer, worker, widow, PwD.", 0),
        ("Knowledge level: L0 zero knowledge, L1 some knowledge, L2 expert. Language: English, Hindi, Hinglish (+1 Marathi out-of-language test).", 0),
        ("Style: simple, vague, typos, formal, multi-part, comparative, wrong premise/rumour, emotional/urgent, data, legal-precise, personal identifiers.", 0),
        ("Variant groups VG-01..VG-08: one need asked 4 ways by different personas. All 4 answers must give the same facts and sources (9.6 consistency).", 0),
        ("Coverage sheet shows the counts by every dimension.", 0),
        ("", 0),
        ("How to run", 11),
        ("1. New session per query. Type the query exactly. Screenshot the answer with its source cards.", 0),
        ("2. Fill the yellow columns. Overall is computed: any F = FAIL.", 0),
        ("3. Paste each cited link into 'Source Check' and run: python3 check_sources.py golden_test_cases_phase1.xlsx \"<ingested CSV>\"", 0),
        ("4. Unsupported content (figure/date/scheme/link not in the cited source) is a release blocker under 9.2 - criterion is 'none observed'.", 0),
        ("5. Run all P0 first (demo set), then P1, then P2.", 0),
        ("", 0),
        ("Golden-fact status (column T)", 11),
        ("'Verified on official page (13-15 Oct 2026)' = golden value checked by us. 'Reviewer to fill' = the query is ready but a reviewer must "
         "write the golden value from the official page before scoring freshness. 'Behaviour check' = scored on behaviour, not a value.", 0),
        ("Rows marked RE-VERIFY ON DEMO DAY can change any day (DA July-2026 instalment, PM-Kisan 24th instalment, NSP deadline, small-savings OM).", 0),
        ("", 0),
        ("Important findings from the ingested list", 11),
        ("UMANG and myScheme are NOT crawled (developers, 14-Oct-2026): the bot reads them from internal DB/API (concept note 7.5.4 "
         "search_schemes / get_scheme / search_services). Source availability = 'DB/API' for these rows. UMANG rows pass only if the deep link opens "
         "the correct service on app and web (9.4 hand-off >= 95%); myScheme rows must show the record's last-updated date, use templated "
         "eligibility wording (7.6.6), and prefer the owning Ministry/portal where myScheme differs (7.6.3 tier 3).", 0),
        ("Hand-off rule (6.1): where a service exists on UMANG, the expected next step is the UMANG deep link; otherwise the official portal.", 0),
        ("The bot's own registry (GET /v1/sources, 794 sources on 16-Oct-2026) also lists Passport Seva, DigiLocker, e-Shram, Sanchar "
         "Saathi, incometaxindia.gov.in, GST Council, IRCTC and voters.eci.gov.in - Source availability 'Bot registry'. A registry entry "
         "means the bot may use the site; it does not prove the content is indexed. Still not available: pmjay.gov.in, NBEMS, UMANG web pages. "
         "Queries on these expect a cited answer from another ingested site or a clean abstention - never a fabricated link.", 0),
        ("State portals ARE ingested (Maharashtra, UP, TN, Karnataka, Haryana, Kerala, Delhi...) although concept note 6.2 says State content is "
         "outside the MVP. State rows accept a cited answer from a crawled State portal, or (G12) naming the responsible State "
         "department with its portal link - a bare 'not covered' fails.", 0),
        ("About 20 ingested official sites are not on .gov.in (e.g. nios.ac.in, mudra.org.in, rbi.org.in, ippbonline.bank.in) - check_sources.py "
         "treats every ingested domain as genuine.", 0),
        ("", 0),
        ("Response flow (deck UMANG-Saathi-14-Oct-2026, slide 10): procedure and service rows carry an 'Expected response flow' "
         "rubric (column AG) scored in column AH; a flow FAIL makes the row FAIL. 'Conversation Scenarios' has multi-turn "
         "scripts that test this behaviour (ask -> up to two clarifying questions only if needed -> route that fits -> what to "
         "bring, steps, exact link, source -> next step and what happens after; edge turns for intermediaries, fake sites, "
         "emergencies and State questions); facts come from the referenced verified rows.", 0),
        ("Guardrails (team table, Documents Given/Guardrails.png): column 'Guardrails exercised' tags each row with the "
         "guardrails it probes; the Guardrails sheet counts coverage and lists what needs developer help (planted injection "
         "page for G15, election-mode switch for G13, log access for G10 masking). G09 allows up to TWO clarifying questions "
         "while concept note 7.5.2 says one - tests follow the newer guardrail; confirm with the team.", 0),
        ("Index-grounded rows (last category): built on the developer's seed file of indexed chunks; columns AJ-AM give the exact "
         "chunk the bot should retrieve and cite, so a miss there is a retrieval failure, not missing data. [IDX-STALE] rows flag "
         "indexed text that is outdated (PM-KISAN 2-hectare limit, NFSA Rs 3/2/1 prices, pre-2026 EPF rules) - the bot must not "
         "present it as current. Re-run parse_seed.py on the developer's 100-website file to extend this group.", 0),
        ("Legend: yellow = tester input; peach Golden-fact status = must re-verify on demo day; white = golden data.", 0),
    ]
    for r, (text, size) in enumerate(readme, 1):
        c = ws.cell(r, 1, text)
        c.font = Font(name="Arial", size=size or 10, bold=bool(size))
        c.alignment = Alignment(wrap_text=True, vertical="top")

    # ---- Personas ----
    ws = wb.create_sheet("Personas")
    header(ws, ["Code", "Profile", "Gender", "Age", "Age group", "How they ask", "Queries"], [8, 32, 12, 6, 10, 50, 9])
    for r, (code, (profile, gender, age, how)) in enumerate(PERSONAS.items(), 2):
        for c, v in enumerate([code, profile, gender, age, age_group(age), how,
                               f"=COUNTIF('Test Queries'!I2:I{last},A{r})"], 1):
            ws.cell(r, c, v)
        body(ws, r, 7)

    # ---- Test Queries ----
    ws = wb.create_sheet("Test Queries")
    header(ws, HEAD, WIDTH)
    yn = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    pf = DataValidation(type="list", formula1='"P,F,NA"', allow_blank=True)
    ws.add_data_validation(yn)
    ws.add_data_validation(pf)
    for r, row in enumerate(data, 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
        ws.cell(r, 29, f'=IF(OR(COUNTIF(Z{r}:AB{r},"F")>0,AH{r}="F"),"FAIL",'
                       f'IF(OR(COUNTIF(Z{r}:AB{r},"P")>0,AH{r}="P"),"PASS",""))')
        body(ws, r, len(HEAD), 22)
        for c in (31, 32, 33, 35, 36, 37, 38, 39):  # golden reference columns, not tester input
            ws.cell(r, c).fill = PatternFill()
        ws.cell(r, 29).fill = PatternFill()
        if "RE-VERIFY" in row[19]:
            ws.cell(r, 20).fill = FLAG_FILL
        for col in ("X", "Y"):
            yn.add(f"{col}{r}")
        for col in ("Z", "AA", "AB", "AH"):
            pf.add(f"{col}{r}")
    ws.auto_filter.ref = f"A1:AM{last}"

    # ---- Coverage ----
    ws = wb.create_sheet("Coverage")
    header(ws, ["Dimension", "Value", "Queries", "Share"], [22, 40, 10, 10])
    dims = [("Category", "B"), ("Portal", "D"), ("Gender", "K"), ("Age group", "M"), ("Knowledge level", "N"),
            ("Language", "O"), ("Query style", "P"), ("Question type", "H"), ("Primary test focus", "R"), ("Priority", "U"),
            ("Source availability", "F")]
    r = 2
    for name, col in dims:
        idx = ord(col) - ord("A")
        for value, _ in sorted(Counter(row[idx] for row in data).items(), key=lambda kv: -kv[1]):
            ws.cell(r, 1, name)
            ws.cell(r, 2, value)
            ws.cell(r, 3, f"=COUNTIF('Test Queries'!{col}2:{col}{last},B{r})")
            ws.cell(r, 4, f"=C{r}/{len(data)}")
            body(ws, r, 4)
            ws.cell(r, 4).number_format = "0.0%"
            r += 1

    # ---- Source Check ----
    ws = wb.create_sheet("Source Check")
    sc = ["Test ID", "Cited URL (paste)", "Claim it supports (exact figure/text)", "Official host? (auto)",
          "HTTP status (auto)", "Final URL after redirects (auto)", "Claim found on page? (auto)",
          "Available to bot? (auto)", "Manual verdict (P/F)", "Notes"]
    header(ws, sc, [8, 50, 30, 14, 12, 50, 16, 12, 12, 40])
    example = ["EXAMPLE", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2316941", "2610", "YES", 200,
               "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2316941&reg=48&lang=2", "YES", "YES", "P",
               "Example row - the checker skips it"]
    for c, v in enumerate(example, 1):
        ws.cell(2, c, v)
    for r in range(2, 603):
        body(ws, r, len(sc), 2)

    # ---- Conversation Scenarios (multi-turn, deck slide 10 flow) ----
    ws = wb.create_sheet("Conversation Scenarios")
    header(ws, ["Scenario", "Title", "Golden facts in", "Persona", "Language", "Turn", "User says (type exactly)",
                "Expected bot behaviour at this turn", "Flow steps (slide 10)", "Bot reply (summary / screenshot)",
                "Turn result (P/F)", "Notes"], [8, 28, 10, 9, 9, 5, 40, 80, 9, 40, 9, 30])
    tf = DataValidation(type="list", formula1='"P,F"', allow_blank=True)
    ws.add_data_validation(tf)
    r = 2
    for sid, title, refs, persona, lang, turns in SCENARIOS:
        ids = []
        for prefix in refs:
            hits = [d[0] for d in data if str(d[16]).startswith(prefix)] if not prefix.startswith("VG-") else [prefix]
            assert len(hits) == 1, f"{sid}: reference {prefix!r} matched {hits}"
            ids += hits
        for t, (says, expect, steps) in enumerate(turns, 1):
            for c, v in enumerate([sid, title, ", ".join(ids) or "behaviour only", persona, LANG[lang], t, says, expect, steps], 1):
                ws.cell(r, c, v)
            body(ws, r, 12, 10)
            tf.add(f"K{r}")
            r += 1

    # ---- Guardrails (team table, 15-Oct-2026) ----
    ws = wb.create_sheet("Guardrails")
    header(ws, ["ID", "Guardrail", "Trigger", "Bot behaviour", "On screen", "Automated check", "Needs developer help",
                "Test rows", "P0 rows", "Scenario turns"], [6, 24, 26, 60, 26, 30, 36, 8, 8, 9])
    for r, g in enumerate(GUARDRAILS, 2):
        for c, v in enumerate(g, 1):
            ws.cell(r, c, v)
        ws.cell(r, 8, f'=COUNTIF(\'Test Queries\'!AI2:AI{last},"*{g[0]}*")')
        ws.cell(r, 9, f'=COUNTIFS(\'Test Queries\'!AI2:AI{last},"*{g[0]}*",\'Test Queries\'!U2:U{last},"P0")')
        ws.cell(r, 10, f'=COUNTIF(\'Conversation Scenarios\'!H2:H200,"*{g[0]}*")')
        body(ws, r, 10)

    # ---- Summary ----
    ws = wb.create_sheet("Summary")
    header(ws, ["Measure", "Pass", "Fail", "Pass rate", "Target (concept note)"], [36, 8, 8, 10, 70])
    q = "'Test Queries'"
    lines = [("Freshness", "Z", "Answer changes when the source changes (9.4)"),
             ("Citation accuracy", "AA", "Every citation supports its sentence (9.4); unsupported content none observed (9.2)"),
             ("Source genuine", "AB", "Official, allow-listed, HTTP 200 (7.6.2(5)); look-alikes never linked (7.7)"),
             ("Response flow (deck slide 10)", "AH", "Procedure / service rows follow the 5-step use-case flow")]
    for i, (name, col, target) in enumerate(lines, 2):
        ws.cell(i, 1, name)
        ws.cell(i, 2, f'=COUNTIF({q}!{col}2:{col}{last},"P")')
        ws.cell(i, 3, f'=COUNTIF({q}!{col}2:{col}{last},"F")')
        ws.cell(i, 4, f'=IF(B{i}+C{i}=0,"",B{i}/(B{i}+C{i}))')
        ws.cell(i, 5, target)
    i = len(lines) + 2
    for name, crit, target in [("Overall - all queries", None, "Priority tasks at least 90% (9.2)"),
                               ("Overall - P0 demo set", "P0", "Target 100% before the demo")]:
        cond = f',{q}!U2:U{last},"{crit}"' if crit else ""
        ws.cell(i, 1, name)
        ws.cell(i, 2, f'=COUNTIFS({q}!AC2:AC{last},"PASS"{cond})')
        ws.cell(i, 3, f'=COUNTIFS({q}!AC2:AC{last},"FAIL"{cond})')
        ws.cell(i, 4, f'=IF(B{i}+C{i}=0,"",B{i}/(B{i}+C{i}))')
        ws.cell(i, 5, target)
        i += 1
    for name, col in [("Language", "O"), ("Knowledge level", "N"), ("Category", "B")]:
        idx = ord(col) - ord("A")
        for value in sorted({row[idx] for row in data}):
            ws.cell(i, 1, f"{name}: {value}")
            ws.cell(i, 2, f'=COUNTIFS({q}!{col}2:{col}{last},"{value}",{q}!AC2:AC{last},"PASS")')
            ws.cell(i, 3, f'=COUNTIFS({q}!{col}2:{col}{last},"{value}",{q}!AC2:AC{last},"FAIL")')
            ws.cell(i, 4, f'=IF(B{i}+C{i}=0,"",B{i}/(B{i}+C{i}))')
            ws.cell(i, 5, "Hindi within 5 points of English (9.2)" if name == "Language" else "")
            i += 1
    for row in ws.iter_rows(min_row=2, max_row=i - 1):
        for cell in row:
            cell.font, cell.alignment, cell.border = FONT, WRAP, BOX
        row[3].number_format = "0.0%"

    wb.save(OUT)
    print(f"wrote {OUT}: {len(data)} queries from {len(ingested)} ingested sites")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
