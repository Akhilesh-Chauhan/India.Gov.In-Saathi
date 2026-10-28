"""One-sheet findings workbook for team and stakeholder review: one row per test case and conversation.

Columns: test case, query, expected response, expected source, the bot's answer and cited URLs, status, result group
and reasons, then context (priority, category, language, profile), every check's verdict, and two reviewer columns.
Reads results.jsonl (run_eval.py) plus, when present, facts_split.jsonl and unanswered_split.jsonl.

Example: python findings_sheet.py --run day1   # writes runs/day1/findings_by_test_case.xlsx
         python findings_sheet.py --run day1 --no-recheck --spot-check   # runs/day1/spot_check.xlsx for reviewers
"""
import argparse
import json
import re
from collections import Counter

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import config
from run_eval import _read_jsonl
from checklist import PARTIAL_AT, PASS_AT, SAFETY_CHECKS, spot_check_ids
from workbook import load_rows, load_scenarios

CHECKS = ["Correctness & behaviour", "Citation support", "Freshness", "Figures on cited pages", "Source genuineness",
          "Source recall", "Response flow", "Personal data not echoed", "Conversation flow"]
# PARTIAL PASS needs correct facts and genuine sources: a FAIL on any of these makes the row FAIL (an outdated value means
# the facts are not correct; repeating personal data is a privacy breach). Failing only other checks can still be PARTIAL PASS.
CRITICAL = ["Source genuineness", "Freshness", "Personal data not echoed"]
WORD = {"P": "PASS", "F": "FAIL", "NA": "NA", "ERROR": "ERROR"}
GROUP = {"wrong": "Wrong or outdated facts", "not answered": "Not answered", "incomplete": "Required fact missing"}
WHY_UNANSWERED = {"Read the expected site, no answer": "Reached the right website ({site}), missed the page with the answer",
                  "Expected site not retrieved": "Never searched the right website ({site}), although it is crawled",
                  "Needs service data (DB/API)": "Needs live UMANG / myScheme service data ({site})",
                  "No expected source": "No source defined for this question"}

# (header, width, column group) - groups: core review, context, check detail, reviewer input
COLUMNS = [("Test case", 10, "core"), ("Query", 42, "core"), ("Expected response (golden answer)", 55, "core"),
           ("Expected source site", 18, "core"), ("Expected source URLs (verified)", 34, "core"),
           ("Bot response", 62, "core"), ("Bot cited URLs", 40, "core"), ("Status", 10, "core"),
           ("Result group", 20, "core"), ("Reason", 55, "core"), ("Grader's detailed reason", 55, "core"),
           ("Guardrails broken", 13, "core"), ("Priority", 8, "context"), ("Category", 18, "context"),
           ("Language", 13, "context"), ("Question type", 18, "context"), ("User profile", 22, "context"),
           ("Facts vs golden answer", 13, "context"), ("Required behaviour met", 11, "context"),
           ("Why unanswered", 34, "context")] + [(c, 12, "check") for c in CHECKS] + [
           ("Other failed checks: reasons", 55, "check"), ("Response time (s)", 9, "check"),
           ("Reviewer: agree with status?", 14, "review"), ("Reviewer comments", 40, "review")]
# Added before the reviewer columns when the run was re-checked against an earlier run (regrade.json)
RECHECK_COLUMNS = [("Re-check", 34, "recheck"), ("Status in earlier run", 12, "recheck"), ("Graded by", 26, "recheck")]
# Added after Status when the run has checklist grades (checklist.py score -> checklist.jsonl)
CHECKLIST_COLUMNS = [("Checklist met", 10, "core"), ("Key facts present", 10, "core"), ("Wrong items", 8, "core"),
                     ("Checklist", 60, "core")]
FILLS = {"core": "1F3864", "context": "2E5597", "check": "44546A", "review": "FFF2CC", "recheck": "7F6000"}
HEADER_ROW = 6
ARIAL = Font(name="Arial", size=10)
WRAP = Alignment(wrap_text=True, vertical="top")


def clean(text, limit=32000):
    text = ILLEGAL_CHARACTERS_RE.sub("", str(text or ""))
    return text if len(text) <= limit else text[:limit] + " ... [truncated]"


def load_checklist(run_dir):
    path = run_dir / "checklist.jsonl"
    return {c["id"]: c for c in _read_jsonl(path)} if path.exists() else None


def checklist_values(c):
    """[Checklist met, Key facts present, Wrong items, Checklist] for one test case."""
    if not c:
        return [None, None, None, "not graded"]
    if c["facts_basis"] == "turns":
        text = f"{c['checklist_met']} of {c['checklist_total']} turns passed the conversation check"
    else:
        basis = "key facts" if c["facts_basis"] == "facts" else "required behaviours (no facts to give)"
        text = f"{c['checklist_met']} of {c['checklist_total']} checklist items met; {c['facts_met']} of {c['facts_total']} {basis}"
        if c["failed_safety_checks"]:
            text += "; failed: " + ", ".join(c["failed_safety_checks"]).lower()
        text += "\n" + "\n".join(f"{x['status'].upper()} ({x['type']}): {x['item']}" for x in c["items"])
        if c.get("note"):
            text += f"\nNote: {c['note']}"
    return [c["checklist_share"], c["facts_share"], len(c["wrong_items"]), text]


def recheck_values(rec, graded_by, earlier):
    """[Re-check, Status in earlier run, Graded by] for a re-checked run."""
    rc = rec.get("recheck") or {}
    if rc.get("decision") == "changed":
        text = "Changed, re-graded" + (f": {rc['note']}" if rc.get("note") else "")
    elif rc:
        text = f"Same content: {rc.get('answer_from', 'earlier')} answer and grades kept" + (f" ({rc['note']})" if rc.get("note") else "")
    else:
        text = ""
    return [text, earlier or "", graded_by or rc.get("graded_by", "")]


def earlier_statuses(run_dir):
    """Test case -> Status from the baseline run's findings workbook (needs regrade.json)."""
    meta = run_dir / "regrade.json"
    if not meta.exists():
        return None
    base = config.RUNS_DIR / json.loads(meta.read_text(encoding="utf-8"))["baseline_run"] / "findings_by_test_case.xlsx"
    if not base.exists():
        return {}
    ws = load_workbook(base, data_only=True)["Findings"]
    head = [c.value for c in ws[HEADER_ROW]]
    k = head.index("Status")
    return {r[0]: r[k] for r in ws.iter_rows(min_row=HEADER_ROW + 1, values_only=True) if r[0]}


def question_rows(run_dir, rows, earlier=None, chk=None):
    results = [r for r in _read_jsonl(run_dir / "results.jsonl")]
    res = {r["id"]: r["metrics"] for r in results if "metrics" in r}
    graded_by = {r["id"]: r.get("graded_by") for r in results}
    by_query = {r["Query (type exactly)"]: r["Test ID"] for r in rows.values()}
    responses = {by_query.get(r["query"], r["id"]): r for r in _read_jsonl(run_dir / "responses.jsonl")}
    split = {r["id"]: r for r in _read_jsonl(run_dir / "facts_split.jsonl")}
    unans = {r["id"]: r for r in _read_jsonl(run_dir / "unanswered_split.jsonl")}
    out = []
    for i in sorted(res):
        row, m, rec, s = rows[i], res[i], responses.get(i, {}), split.get(i)
        cb = m.get("Correctness & behaviour", {})
        failed_other = [(c, m[c]["reason"]) for c in CHECKS[1:] if m.get(c, {}).get("verdict") == "F"]
        if cb.get("verdict") == "F":
            group = (GROUP.get(s["facts"]) or ("Required behaviour not met" if not s["behaviour_met"] else "Guardrails only")
                     if s else "Failed (not split yet)")
            reason = s["reason"] if s else cb.get("reason", "")
        elif failed_other:
            group = "Other check failed"
            reason = "Facts and guardrails OK, but " + failed_other[0][0].lower() + " failed: " + failed_other[0][1]
        elif cb.get("verdict") == "P":
            group, reason = "Pass", "All checks passed or were not applicable."
        else:
            group, reason = "Not graded", cb.get("reason", "")
        facts_ok = cb.get("verdict") == "P" or (s and (s["facts"] == "correct" or (s["facts"] == "not applicable" and s["behaviour_met"])))
        critical = [(c, m[c]["reason"]) for c in CRITICAL if m.get(c, {}).get("verdict") == "F"]
        if facts_ok and critical:  # explain why a facts-right answer is still a FAIL
            reason = f"Facts right, but {critical[0][0].lower()} failed: {critical[0][1]} | {reason}"
        u = unans.get(i)
        why = WHY_UNANSWERED.get(u["group"], u["group"]).format(site=u["expected"]) if u else ""
        golden_urls = "\n".join(x for x in (row.get("Golden sources (verified URLs)"), row.get("Index chunk URL")) if x)
        profile = ", ".join(str(x) for x in (row.get("Profile"), row.get("Knowledge level")) if x)
        values = [i, row.get("Query (type exactly)"), row.get("Expected behaviour / golden answer"),
                  row.get("Expected source domain"), golden_urls, rec.get("answer") or "(no answer)",
                  "\n".join(rec.get("sources") or []), None, group, reason, cb.get("reason", ""),
                  ", ".join(sorted({g for v in m.values() for g in v.get("guardrails", [])})),
                  row.get("Priority"), row.get("Category"), row.get("Language"),
                  row.get("Question type (concept note)"), profile,
                  s["facts"] if s else ("correct" if cb.get("verdict") == "P" else ""),
                  ("Y" if s["behaviour_met"] else "N") if s else ("Y" if cb.get("verdict") == "P" else ""), why]
        if chk is not None:
            values[8:8] = checklist_values(chk.get(i))
        values += [WORD.get(m.get(c, {}).get("verdict"), "NA") if c != "Conversation flow" else "" for c in CHECKS]
        values += ["\n".join(f"{c}: {r}" for c, r in failed_other), rec.get("latency_s")]
        if earlier is not None:
            values += recheck_values(rec, graded_by.get(i), earlier.get(i))
        out.append(values + [None, None])
    return out


def conversation_rows(run_dir, earlier=None, chk=None):
    scen = load_scenarios()
    results = _read_jsonl(run_dir / "results.jsonl")
    verdicts = {r["id"]: r["conversation"] for r in results if "conversation" in r}
    graded_by = {r["id"]: r.get("graded_by") for r in results}
    out = []
    for c in _read_jsonl(run_dir / "conversations.jsonl"):
        v, sc = verdicts.get(c["id"]), scen.get(c["id"], {})
        turns = sc.get("turns") or []
        query = "\n".join(f"Turn {n}: {t['user']}" for n, t in enumerate(c["turns"], 1))
        expected = "\n".join(f"Turn {n}: {t[1]}" for n, t in enumerate(turns, 1))
        answer = "\n\n".join(f"Turn {n}: {t['answer'] or '(no answer)'}" for n, t in enumerate(c["turns"], 1))
        urls = "\n".join(dict.fromkeys(u for t in c["turns"] for u in t.get("sources") or []))
        verdict = WORD.get(v["verdict"], "NA") if v else "NA"
        values = [c["id"], query, expected, "", "", answer, urls, None,
                  "Pass" if verdict == "PASS" else "Conversation turn failed", v["reason"] if v else "", "",
                  ", ".join(v["guardrails"]) if v else "", "", "Multi-turn: " + str(sc.get("title", "")),
                  sc.get("lang", ""), "Multi-turn conversation", "", "", "", ""]
        if chk is not None:
            values[8:8] = checklist_values(chk.get(c["id"]))
        values += ["" for _ in CHECKS[:-1]] + [verdict, "", None]
        if earlier is not None:
            values += recheck_values(c, graded_by.get(c["id"]), earlier.get(c["id"]))
        out.append(values + [None, None])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", help="output file (default runs/<run>/findings_by_test_case.xlsx)")
    ap.add_argument("--no-recheck", action="store_true", help="present a re-checked run as a single run (no re-check columns)")
    ap.add_argument("--spot-check", action="store_true",
                    help="only 2 questions per grading batch and status, to runs/<run>/spot_check.xlsx (concept note 9.3.4)")
    a = ap.parse_args()
    run_dir = config.RUNS_DIR / a.run
    earlier = None if a.no_recheck else earlier_statuses(run_dir)
    chk = load_checklist(run_dir)
    data = question_rows(run_dir, load_rows(), earlier, chk) + conversation_rows(run_dir, earlier, chk)
    if a.spot_check:
        keep = spot_check_ids(run_dir)
        data = [v for v in data if v[0] in keep]
    columns = (COLUMNS[:8] + (CHECKLIST_COLUMNS if chk is not None else []) + COLUMNS[8:-2]
               + (RECHECK_COLUMNS if earlier is not None else []) + COLUMNS[-2:])
    meta = json.loads((run_dir / "regrade.json").read_text(encoding="utf-8")) if earlier is not None else {}

    wb = Workbook()
    ws = wb.active
    ws.title = "Findings"
    col = {h: get_column_letter(n) for n, (h, _, _) in enumerate(columns, 1)}
    first, last = HEADER_ROW + 1, HEADER_ROW + len(data)
    status = f"${col['Status']}${first}:${col['Status']}${last}"
    checks = f"{col[CHECKS[0]]}{{r}}:{col[CHECKS[-1]]}{{r}}"

    ws["A1"] = f"Saathi golden-test evaluation: findings by test case (run {a.run})"
    ws["A1"].font = Font(name="Arial", size=14, bold=True)
    ws["A2"] = ("Graded by rule-based checks and a model grader (Claude Opus 5.5 on Amazon Bedrock) against golden answers "
                "verified on official sites. Preliminary until reviewers confirm the grading (concept note 9.3.4).")
    if meta:
        ws["A2"] = (f"Every question was asked again on {meta['rechecked']}. Answers whose content changed were re-graded with the "
                    f"same rubric by {meta['grader']}; the rest keep their earlier answer and grades (Bedrock judge). "
                    "Response times are from the re-check. See the Re-check columns.")
    summary = [("Test cases", f"=COUNTA({status})"), ("PASS", f'=COUNTIF({status},"PASS")'),
               ("PARTIAL PASS", f'=COUNTIF({status},"PARTIAL PASS")'), ("FAIL", f'=COUNTIF({status},"FAIL")'),
               ("Pass rate", '=IF(B3=0,"",D3/B3)'), ("Pass + partial", '=IF(B3=0,"",(D3+F3)/B3)')]
    if meta:
        rc = f"${col['Re-check']}${first}:${col['Re-check']}${last}"
        summary.append(("Changed since earlier run", f'=COUNTIF({rc},"Changed*")'))
    for k, (label, formula) in enumerate(summary):
        ws.cell(3, 2 * k + 1, label).font = Font(name="Arial", size=10, bold=True)
        ws.cell(3, 2 * k + 2, formula).font = ARIAL
    ws["J3"].number_format = ws["L3"].number_format = "0.0%"
    ws["A4"] = ("Status: PASS = every check passed or did not apply. PARTIAL PASS = the facts are correct (or the required "
                "decline/redirect was done) and the source links are genuine (official, crawled and working), but something else "
                "fell short, such as a claim the cited page does not support, the official next step, helpline, expected response "
                "flow, expected source page or the user's language. FAIL = wrong or outdated facts, no answer, a required fact "
                "missing, a non-official or broken link, or personal data repeated. Result group and Reason say why; "
                "'Other failed checks' lists everything else that fell short.")
    if chk is not None:
        ws["A4"] = ("Status: each answer is checked against a checklist built from its golden answer: the key facts plus the "
                    "required behaviours (the golden's instructions, the user's language, an official link or next step). "
                    f"PASS = at least {PASS_AT:.0%} of the checklist met. PARTIAL PASS = at least {PARTIAL_AT:.0%} of the key facts "
                    "present and correct (declines and redirects use their required behaviours). FAIL = below that, or any wrong "
                    "or outdated fact, a non-official or broken link, or personal data repeated. Conversations: share of turns "
                    "passed. The Checklist column lists every item; Result group and Reason give the grader's view.")
    ws["A5"] = ("Yellow columns are for reviewers: choose Agree, Disagree or Unsure, and explain any disagreement, "
                "e.g. \"Disagree - the Rs 2,500 fee is in the 2026 notice\".")
    if a.spot_check:
        ws["A5"] = ("Spot-check sample: 2 questions per grading batch and status. For each row choose Agree if the Status and "
                    "its reasons (Checklist, Result group, Reason) are right, Disagree if not, and say what is wrong in the comments.")
    for c in ("A2", "A4", "A5"):
        ws[c].font = Font(name="Arial", size=10, italic=True)

    for n, (h, width, grp) in enumerate(columns, 1):
        cell = ws.cell(HEADER_ROW, n, h)
        cell.font = Font(name="Arial", size=10, bold=True, color="000000" if grp == "review" else "FFFFFF")
        cell.fill = PatternFill("solid", fgColor=FILLS[grp])
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(n)].width = width
    ws.row_dimensions[HEADER_ROW].height = 42

    review_fill = PatternFill("solid", fgColor="FFF2CC")
    for r, values in enumerate(data, first):
        for n, v in enumerate(values, 1):
            cell = ws.cell(r, n, clean(v) if isinstance(v, str) else v)
            cell.font, cell.alignment = ARIAL, WRAP
        span = checks.format(r=r)
        if chk is not None:  # checklist rule: percentages, with wrong facts and safety checks always failing
            wrong, cm, kf = (f"{col[h]}{r}" for h in ("Wrong items", "Checklist met", "Key facts present"))
            safety = ",".join(f'{col[c]}{r}="FAIL"' for c in SAFETY_CHECKS)
            ws[f"{col['Status']}{r}"] = (f'=IF(OR({wrong}>0,{safety}),"FAIL",IF({cm}>={PASS_AT},"PASS",'
                                         f'IF({kf}>={PARTIAL_AT},"PARTIAL PASS","FAIL")))')
            ws[cm].number_format = ws[kf].number_format = "0%"
        else:
            facts, met = f"{col['Facts vs golden answer']}{r}", f"{col['Required behaviour met']}{r}"
            critical = ",".join(f'{col[c]}{r}="FAIL"' for c in CRITICAL)
            ws[f"{col['Status']}{r}"] = (
                f'=IF(COUNTIF({span},"ERROR")>0,"ERROR",IF(COUNTIF({span},"FAIL")=0,IF(COUNTIF({span},"PASS")>0,"PASS","NA"),'
                f'IF(AND(OR({facts}="correct",AND({facts}="not applicable",{met}="Y")),NOT(OR({critical}))),"PARTIAL PASS","FAIL")))')
        for h in ("Reviewer: agree with status?", "Reviewer comments"):
            ws[f"{col[h]}{r}"].fill = review_fill
        ws.row_dimensions[r].height = 96

    ws.freeze_panes = f"B{first}"
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(columns))}{last}"
    dv = DataValidation(type="list", formula1='"Agree,Disagree,Unsure"', allow_blank=True)
    dv.add(f"{col['Reviewer: agree with status?']}{first}:{col['Reviewer: agree with status?']}{last}")
    ws.add_data_validation(dv)
    green, red, amber, grey = (PatternFill("solid", fgColor=c) for c in ("C6EFCE", "FFC7CE", "FFEB9C", "D9D9D9"))
    verdict_cols = f"{col['Status']}{first}:{col['Status']}{last} {col[CHECKS[0]]}{first}:{col[CHECKS[-1]]}{last}"
    if meta:
        verdict_cols += f" {col['Status in earlier run']}{first}:{col['Status in earlier run']}{last}"
    for value, fill, ink in (("PASS", green, "006100"), ("PARTIAL PASS", amber, "9C5700"), ("FAIL", red, "9C0006"),
                             ("ERROR", grey, "3F3F3F")):
        ws.conditional_formatting.add(verdict_cols, CellIsRule(operator="equal", formula=[f'"{value}"'], fill=fill,
                                                               font=Font(name="Arial", color=ink, bold=True)))
    out = a.out or run_dir / ("spot_check.xlsx" if a.spot_check else "findings_by_test_case.xlsx")
    wb.save(out)
    groups = Counter(v[8] for v in data)
    print(f"{len(data)} rows -> {out}\n" + "\n".join(f"  {g}: {n}" for g, n in groups.most_common()))


if __name__ == "__main__":
    main()
