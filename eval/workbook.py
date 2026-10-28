"""Reads golden rows and conversation scenarios from the phase-1 workbook."""
from collections import OrderedDict

from openpyxl import load_workbook

import config


def _sheet_dicts(ws):
    rows = ws.iter_rows(values_only=True)
    head = [str(h) if h is not None else "" for h in next(rows)]
    return [dict(zip(head, r)) for r in rows if any(v is not None for v in r)]


def load_rows(path=config.WORKBOOK):
    """Test Queries rows keyed by Test ID."""
    wb = load_workbook(path, read_only=True, data_only=True)
    return OrderedDict((r["Test ID"], r) for r in _sheet_dicts(wb["Test Queries"]) if r.get("Test ID"))


def load_scenarios(path=config.WORKBOOK):
    """Conversation Scenarios grouped as {scenario: {"title", "ref", "turns": [(user, expected), ...]}}."""
    wb = load_workbook(path, read_only=True, data_only=True)
    out = OrderedDict()
    for r in _sheet_dicts(wb["Conversation Scenarios"]):
        s = out.setdefault(r["Scenario"], {"title": r["Title"], "ref": r["Golden facts in"], "lang": r["Language"], "turns": []})
        s["turns"].append((r["User says (type exactly)"], r["Expected bot behaviour at this turn"]))
    return out
