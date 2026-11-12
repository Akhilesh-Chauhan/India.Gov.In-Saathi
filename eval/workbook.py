"""Reads golden rows and conversation scenarios from the golden workbook (config.WORKBOOK, read when called, so a
script such as golden_check.py can switch workbooks)."""
from collections import OrderedDict

from openpyxl import load_workbook

import config


def _sheet_dicts(ws):
    rows = ws.iter_rows(values_only=True)
    head = [str(h) if h is not None else "" for h in next(rows)]
    return [dict(zip(head, r)) for r in rows if any(v is not None for v in r)]


def load_rows(path=None):
    """Test Queries rows keyed by Test ID."""
    wb = load_workbook(path or config.WORKBOOK, read_only=True, data_only=True)
    return OrderedDict((r["Test ID"], r) for r in _sheet_dicts(wb["Test Queries"]) if r.get("Test ID"))


EVIDENCE = "Evidence: official page, exact words, copy date"


def load_evidence(path=None):
    """{test case: evidence for the expected answer} from the workbook's 'Final golden' sheet (official page, exact words,
    copy date); {} for workbooks without that sheet."""
    wb = load_workbook(path or config.WORKBOOK, read_only=True, data_only=True)
    if "Final golden" not in wb.sheetnames:
        return {}
    return {r["Test case"]: r.get(EVIDENCE) or "" for r in _sheet_dicts(wb["Final golden"]) if r.get("Test case")}


def load_scenarios(path=None):
    """Conversation Scenarios grouped as {scenario: {"title", "ref", "turns": [(user, expected), ...]}}."""
    wb = load_workbook(path or config.WORKBOOK, read_only=True, data_only=True)
    out = OrderedDict()
    for r in _sheet_dicts(wb["Conversation Scenarios"]):
        s = out.setdefault(r["Scenario"], {"title": r["Title"], "ref": r["Golden facts in"], "lang": r["Language"], "turns": []})
        s["turns"].append((r["User says (type exactly)"], r["Expected bot behaviour at this turn"]))
    return out
