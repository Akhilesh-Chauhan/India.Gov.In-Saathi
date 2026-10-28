"""Descriptive performance summary of a collected run (no grading, no LLM): answer types, latency, citations,
source dates, registry coverage, language match, caching, errors - overall and by category / language / priority.

Run: ../.venv/bin/python summarize_run.py --run umang-20261016   -> runs/<run>/performance.xlsx + console summary
"""
import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config
from pages import bare, ingested_domains
from metrics import norm_url
from workbook import load_rows

DEV = re.compile(r"[ऀ-ॿ]")
KINDS = ("answer", "clarify", "no_answer")


def pct(values, q):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 2)


def stats(recs, rows, registry):
    n = len(recs)
    kinds = Counter((r.get("clarify_first") and "clarify->answer") or r.get("kind") or "error" for r in recs)
    answered = [r for r in recs if r.get("kind") == "answer"]
    cites = [c for r in answered for c in r.get("citations", [])]
    cited_hosts = [bare(urlsplit(c["url"]).hostname or "") for c in cites if c.get("url")]
    hindi = [r for r in recs if str(rows[r["id"]]["Language"]).startswith("Hindi")]
    return {
        "Questions": n,
        "Answered": sum(r.get("kind") == "answer" for r in recs),
        "Asked a clarifying question first": sum(bool(r.get("clarify_first")) or r.get("kind") == "clarify" for r in recs),
        "No answer ('not found')": kinds.get("no_answer", 0),
        "Errors / no reply": sum(bool(r.get("error")) for r in recs),
        "Answer rate": round(sum(r.get("kind") == "answer" for r in recs) / n, 3) if n else None,
        "Latency p50 (s)": pct([r.get("latency_s") for r in recs], 0.5),
        "Latency p95 (s)": pct([r.get("latency_s") for r in recs], 0.95),
        "First token p50 (s)": pct([r.get("first_token_s") for r in recs], 0.5),
        "Server total p50 (ms)": pct([(r.get("server_timings") or {}).get("totalMs") for r in recs], 0.5),
        "Server retrieval p50 (ms)": pct([(r.get("server_timings") or {}).get("retrievalMs") for r in recs], 0.5),
        "Citations per answer (avg)": round(len(cites) / len(answered), 2) if answered else None,
        "Answers with no citation": sum(not r.get("citations") for r in answered),
        "Citations with a 'last updated' date": round(sum(bool(c.get("lastUpdated")) for c in cites) / len(cites), 3) if cites else None,
        "Citations with a fetch time": round(sum(bool(c.get("fetchedAt")) for c in cites) / len(cites), 3) if cites else None,
        "Cited hosts outside bot registry": sorted({h for h in cited_hosts if h not in registry and "umang.gov.in" not in h}),
        "Answers citing UMANG": sum(any("umang.gov.in" in (c.get("url") or "") for c in r.get("citations", [])) for r in answered),
        "Cached replies": sum(bool(r.get("cached")) for r in recs),
        "Hindi questions": len(hindi),
        "Hindi questions answered in Hindi": sum(r.get("answer_language") == "hi" and bool(DEV.search(r.get("answer") or "")) for r in hindi),
        **recall(recs, rows),
    }


def recall(recs, rows):
    """Index-grounded rows only: was the page holding the answer retrieved ('checked') and cited?"""
    idx = [r for r in recs if rows[r["id"]].get("Index chunk URL")]
    if not idx:
        return {}
    want = {r["id"]: norm_url(rows[r["id"]]["Index chunk URL"]) for r in idx}
    cited = sum(want[r["id"]] in {norm_url(u) for u in r.get("sources", [])} for r in idx)
    got = sum(want[r["id"]] in {norm_url(pg.get("url")) for s in r.get("sources_checked") or [] for pg in s.get("pages", [])}
              or want[r["id"]] in {norm_url(u) for u in r.get("sources", [])} for r in idx)
    return {"Index-grounded questions": len(idx), "Expected page retrieved": got, "Expected page cited": cited,
            "Recall (retrieved)": round(got / len(idx), 3), "Recall (cited)": round(cited / len(idx), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run_dir = config.RUNS_DIR / a.run
    recs = [json.loads(x) for x in (run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rows, registry = load_rows(), ingested_domains()
    by_query = {r["Query (type exactly)"]: r["Test ID"] for r in rows.values()}
    for r in recs:
        r["id"] = by_query.get(r["query"], r["id"])  # robust to Test ID shifts
    recs = [r for r in recs if r["id"] in rows]
    overall = stats(recs, rows, registry)

    wb = Workbook()
    ws = wb.active
    ws.title = "Overall"
    head = Font(name="Arial", bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="1F3864")
    for c, h in enumerate(["Measure", "Value"], 1):
        ws.cell(1, c, h).font, ws.cell(1, c).fill = head, fill
    for r, (k, v) in enumerate(overall.items(), 2):
        ws.cell(r, 1, k)
        ws.cell(r, 2, ", ".join(v) if isinstance(v, list) else v)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 40, 60

    for dim in ("Category", "Language", "Priority", "Knowledge level", "Question type (concept note)"):
        groups = defaultdict(list)
        for r in recs:
            groups[str(rows[r["id"]][dim])].append(r)
        sh = wb.create_sheet(dim[:28])
        cols = ["Value", "Questions", "Answered", "Clarified first", "No answer", "Errors", "Answer rate", "Latency p50 (s)", "Latency p95 (s)"]
        for c, h in enumerate(cols, 1):
            sh.cell(1, c, h).font, sh.cell(1, c).fill = head, fill
            sh.column_dimensions[get_column_letter(c)].width = 34 if c == 1 else 13
        for i, (value, rs) in enumerate(sorted(groups.items()), 2):
            s = stats(rs, rows, registry)
            for c, v in enumerate([value, s["Questions"], s["Answered"], s["Asked a clarifying question first"],
                                   s["No answer ('not found')"], s["Errors / no reply"], s["Answer rate"],
                                   s["Latency p50 (s)"], s["Latency p95 (s)"]], 1):
                sh.cell(i, c, v)

    det = wb.create_sheet("Responses")
    cols = ["Test ID", "Category", "Priority", "Language", "Query", "Kind", "Clarifying question (first reply)", "Chip chosen",
            "Answer", "Cited URLs", "Cited 'last updated'", "Suggested links", "Follow-ups", "Answer language",
            "Latency (s)", "First token (s)", "Server total (ms)", "Cached", "Error"]
    for c, h in enumerate(cols, 1):
        det.cell(1, c, h).font, det.cell(1, c).fill = head, fill
        det.column_dimensions[get_column_letter(c)].width = {5: 40, 7: 40, 9: 70, 10: 50}.get(c, 14)
    for i, r in enumerate(recs, 2):
        row = rows[r["id"]]
        cf = r.get("clarify_first") or {}
        clar = cf.get("clarify") or r.get("clarify") or {}
        vals = [r["id"], row["Category"], row["Priority"], row["Language"], r["query"], r.get("kind"),
                (clar.get("lead", "") + " " + " | ".join(f"{f.get('question')} {f.get('options')}" for f in clar.get("fields", []))).strip(),
                json.dumps(r.get("clarify_choice"), ensure_ascii=False) if r.get("clarify_choice") else "",
                (r.get("answer") or "")[:4000], "\n".join(c.get("url") or "" for c in r.get("citations", [])),
                "\n".join(str(c.get("lastUpdated") or "-") for c in r.get("citations", [])),
                "\n".join(s.get("url", "") for s in r.get("suggested_links") or []), "\n".join(r.get("follow_ups") or []),
                r.get("answer_language"), r.get("latency_s"), r.get("first_token_s"),
                (r.get("server_timings") or {}).get("totalMs"), r.get("cached"), r.get("error")]
        for c, v in enumerate(vals, 1):
            det.cell(i, c, v)
    for sh in wb.worksheets:
        for row in sh.iter_rows(min_row=2):
            for cell in row:
                cell.font, cell.alignment = Font(name="Arial", size=10), Alignment(wrap_text=True, vertical="top")
        sh.freeze_panes = "B2"
    wb.save(run_dir / "performance.xlsx")
    for k, v in overall.items():
        print(f"{k}: {v}")
    print("Saved:", run_dir / "performance.xlsx")


if __name__ == "__main__":
    main()
