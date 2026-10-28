"""Detailed HTML version of report.xlsx: every sheet as a tab, with search, filters and per-question detail.

Reads runs/<run>/report.xlsx (recalculated, so formula values are cached) and findings_by_test_case.xlsx
(findings_sheet.py: full answers, golden answers, PASS / PARTIAL PASS / FAIL status). Writes one self-contained file.

Example: python report_html.py --run day1   # writes runs/day1/saathi-detailed-report.html
         --no-cost     leave out the Tokens & cost tab (cost kept in a separate file, see split_cost.py)
         --no-recheck  present a re-checked run as a single run (ignore regrade.json)
Optional runs/<run>/run_notes.json: {"latency": "..."} adds a note under the response-time checks.
"""
import argparse
import json
import re

from openpyxl import load_workbook

import config
from run_eval import _read_jsonl

CHECKS = ["Correctness & behaviour", "Citation support", "Freshness", "Figures on cited pages", "Source genuineness",
          "Source recall", "Response flow", "Personal data not echoed"]
SHORT = {"Correctness & behaviour": "Correct", "Citation support": "Citation", "Freshness": "Fresh",
         "Figures on cited pages": "Figures", "Source genuineness": "Links", "Source recall": "Recall",
         "Response flow": "Flow", "Personal data not echoed": "PII"}


def sheet_rows(ws, r0, r1, c0=1, c1=None):
    c1 = c1 or ws.max_column
    return [[ws.cell(r, c).value for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]


def table(ws, header_row=1, last_row=None, c1=None):
    head = [v for v in sheet_rows(ws, header_row, header_row, 1, c1)[0]]
    rows = [r for r in sheet_rows(ws, header_row + 1, last_row or ws.max_row, 1, len(head)) if any(v is not None for v in r)]
    return {"head": head, "rows": rows}


def collect(run_dir, recheck=True, cost_tab=True):
    rep = load_workbook(run_dir / "report.xlsx", data_only=True)
    fnd = load_workbook(run_dir / "findings_by_test_case.xlsx", data_only=True)["Findings"]
    fhead = [c.value for c in fnd[6]]
    findings = {r[0]: dict(zip(fhead, r)) for r in sheet_rows(fnd, 7, fnd.max_row, 1, len(fhead))}
    meta = json.loads((run_dir / "regrade.json").read_text(encoding="utf-8")) if recheck and (run_dir / "regrade.json").exists() else {}
    notes = json.loads((run_dir / "run_notes.json").read_text(encoding="utf-8")) if (run_dir / "run_notes.json").exists() else {}
    if rep["Results"]["A2"].value and rep["Gates"]["D2"].value is None and rep["Gates"]["B2"].value is None:
        raise SystemExit("report.xlsx has no calculated values - run recalc first")

    res = table(rep["Results"])
    results = []
    for r in res["rows"]:
        d = dict(zip(res["head"], r))
        f = findings.get(d["Test ID"], {})
        results.append({
            "id": d["Test ID"], "priority": d["Priority"], "language": d["Language"], "category": d["Category"],
            "knowledge": d["Knowledge level"], "gender": d["Gender"], "age": d["Age group"], "persona": d["Persona code"],
            "qtype": d["Question type (concept note)"], "abstain": d["Abstention row"], "query": d["Query"],
            "answer": f.get("Bot response") or d["Bot answer"], "sources": d["Sources shown"] or "",
            "latency": d["Latency (s)"], "golden": f.get("Expected response (golden answer)") or "",
            "site": f.get("Expected source site") or "", "golden_urls": f.get("Expected source URLs (verified)") or "",
            "status": f.get("Status") or "", "group": f.get("Result group") or "", "reason": f.get("Reason") or "",
            "why_unanswered": f.get("Why unanswered") or "", "profile": f.get("User profile") or "",
            "facts": f.get("Facts vs golden answer") or "", "behaviour": f.get("Required behaviour met") or "",
            "checklist_met": f.get("Checklist met"), "facts_present": f.get("Key facts present"), "checklist": f.get("Checklist") or "",
            "checks": {c: [d.get(c), d.get(c + " - reason")] for c in CHECKS},
            "citation_combined": d["Citation (combined)"], "accuracy": d["Accuracy"],
            "unsupported": d["Unsupported content"], "overall": d["Overall"],
            "gr_violated": d["Guardrails violated"] or "", "gr_exercised": d["Guardrails exercised (golden)"] or "",
            "human": {k.replace("Human: ", ""): d[k] for k in res["head"] if k and k.startswith("Human: ")},
            "recheck": ("Changed, re-graded" if str(f.get("Re-check") or "").startswith("Changed") else "Same content") if meta else "",
            "recheck_note": f.get("Re-check") or "", "earlier": f.get("Status in earlier run") or "", "graded_by": f.get("Graded by") or "",
        })

    convs = [{"id": i, "title": f["Category"], "lang": f["Language"], "turns": f["Query"], "expected": f["Expected response (golden answer)"],
              "transcript": f["Bot response"], "urls": f["Bot cited URLs"] or "", "status": f["Status"], "reason": f["Reason"],
              "guardrails": f["Guardrails broken"] or ""} for i, f in findings.items() if str(i).startswith("MT-")]

    gates = rep["Gates"]
    fvg = rep["Facts vs guardrails"]
    uns = rep["Unanswered split"]
    with_cost = cost_tab and "Token usage" in rep.sheetnames
    tok = rep["Token usage"] if with_cost else None
    extra = []
    for name in ("facts_split_tokens.jsonl",):
        extra += _read_jsonl(run_dir / name)
    pilot = _read_jsonl(run_dir.parent / f"{meta.get('baseline_run', run_dir.name)}-pilot" / "tokens.jsonl")
    pin, pout = (tok["B2"].value or 0, tok["B3"].value or 0) if tok else (0, 0)

    def cost(us):
        return sum(u["input_tokens"] for u in us) / 1e6 * pin + sum(u["output_tokens"] for u in us) / 1e6 * pout

    statuses = {}
    for f in findings.values():
        statuses[f["Status"]] = statuses.get(f["Status"], 0) + 1
    return {
        "run": run_dir.name,
        "results": results,
        "conversations": convs,
        "status_counts": statuses,
        "checklist_rule": "Checklist met" in fhead,
        "gates": {"rows": sheet_rows(gates, 2, 8, 1, 7), "lang": sheet_rows(gates, 10, 12, 1, 7),
                  "latency": sheet_rows(gates, 14, 15, 1, 7), "note": gates["A17"].value},
        "fvg": {"title": fvg["A1"].value, "note": fvg["A2"].value, "classes": table(fvg, 4, 12, 9),
                "accuracy": table(fvg, 14, 17, 5), "acc_note": fvg["A18"].value, "causes": table(fvg, 20, fvg.max_row, 5)},
        "unanswered": {"title": uns["A1"].value, "note": uns["A2"].value, "summary": table(uns, 4, 9, 8),
                       "note2": uns["A10"].value, "page_note": [uns["A11"].value, uns["F11"].value],
                       "detail": table(uns, 14, uns.max_row, 15)},
        "guardrails": table(rep["Guardrails"]),
        "segments": table(rep["Segments"]),
        "judge_human": table(rep["Judge vs Human"]),
        "tokens": {"model": tok["B1"].value, "price_in": pin, "price_out": pout, "note": tok["A4"].value,
                   "table": table(tok, 6, tok.max_row, 7),
                   "extra": [e for e in [["Pilot run (25 questions, 2 conversations)", len(pilot), cost(pilot)],
                                         ["Facts vs guardrails pass", len(extra), cost(extra)]] if e[1]],
                   "spend": meta.get("spend")} if with_cost else None,
        "latency_note": notes.get("latency"),
        "recheck": {"date": meta["rechecked"], "grader": meta["grader"], "baseline": meta["baseline_run"],
                    "questions": len(meta["questions_regraded"]), "conversations": len(meta["conversations_regraded"])} if meta else None,
        "tokens_by_question": table(rep["Tokens by question"]) if with_cost else None,
        "facts_detail": table(rep["Facts split detail"]),
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Saathi Evaluation Detailed Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hind:wght@400;500;600&family=Martel:wght@700;800&display=swap">
<style>
  /* Layout: wide working document; sticky tab bar, one tab per report.xlsx sheet, tables that filter and expand */
  :root {
    --bg: #f3f5f9; --surface: #ffffff; --ink: #131a27; --ink-2: #485266; --muted: #6f7889; --line: #dce1ea;
    --accent: #1f3a8a; --accent-soft: #e4e9f5; --row-hover: #f6f8fc; --bar: #2a78d6; --bar-track: #e4e9f5;
    --good: #0ca30c; --good-ink: #006300; --good-soft: #e3f4e3; --warn: #fab219; --warn-ink: #7a5200; --warn-soft: #fdf1d6;
    --bad: #d03b3b; --bad-ink: #b02a2a; --bad-soft: #fbe4e4;
    --display: "Martel", Georgia, "Times New Roman", serif;
    --body: "Hind", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0d1118; --surface: #151a22; --ink: #edf0f5; --ink-2: #b7bfcd; --muted: #8b94a4; --line: #2a3140;
      --accent: #9db4f5; --accent-soft: #1c2640; --row-hover: #1a202a; --bar: #3987e5; --bar-track: #1c2640;
      --good-ink: #3fc43f; --good-soft: #13281a; --warn-ink: #f3c14d; --warn-soft: #2d2512; --bad-ink: #f07a7a; --bad-soft: #2e1618;
      color-scheme: dark;
    }
  }
  :root[data-theme="dark"] {
    --bg: #0d1118; --surface: #151a22; --ink: #edf0f5; --ink-2: #b7bfcd; --muted: #8b94a4; --line: #2a3140;
    --accent: #9db4f5; --accent-soft: #1c2640; --row-hover: #1a202a; --bar: #3987e5; --bar-track: #1c2640;
    --good-ink: #3fc43f; --good-soft: #13281a; --warn-ink: #f3c14d; --warn-soft: #2d2512; --bad-ink: #f07a7a; --bad-soft: #2e1618;
    color-scheme: dark;
  }
  body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.55; -webkit-text-size-adjust: 100%; }
  [hidden] { display: none !important; }
  .wrap { max-width: 1320px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
  header.top { padding-block: 34px 18px; display: grid; gap: 8px; }
  .eyebrow { font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
  h1 { font-family: var(--display); font-weight: 800; font-size: clamp(28px, 5vw, 40px); line-height: 1.15; margin: 0; text-wrap: balance; }
  h2 { font-family: var(--display); font-weight: 700; font-size: clamp(20px, 3.5vw, 25px); line-height: 1.3; margin: 0; text-wrap: balance; }
  h3 { font-size: 16px; font-weight: 600; margin: 0; }
  p { margin: 0; max-width: 80ch; }
  .lede { color: var(--ink-2); font-size: 16px; }
  nav.tabs { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: var(--bg); border-bottom: 1px solid var(--line); }
  body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--bg); }
  .tabbar { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: thin; padding-block: 6px; }
  .tabbar button { font: inherit; font-size: 14px; font-weight: 500; color: var(--ink-2); background: transparent; border: 0; border-radius: 6px;
    padding: 7px 12px; cursor: pointer; white-space: nowrap; }
  .tabbar button:hover { background: var(--accent-soft); color: var(--ink); }
  .tabbar button[aria-selected="true"] { background: var(--accent); color: var(--surface); }
  .tabbar button:focus-visible, button:focus-visible, select:focus-visible, input:focus-visible, tr.q:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  main { padding-block: 26px 70px; }
  .panel { display: grid; gap: 22px; }
  .card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 20px; display: grid; gap: 14px; min-width: 0; }
  .muted { color: var(--muted); }
  .note { font-size: 13.5px; color: var(--muted); max-width: 100ch; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
  .tile { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: grid; gap: 2px; }
  .tile .lab { font-size: 12.5px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
  .tile .val { font-size: 30px; font-weight: 600; line-height: 1.2; }
  .tile .sub { font-size: 13.5px; color: var(--ink-2); }
  .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
  .table-wrap.tall { max-height: 72vh; overflow: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  thead th { position: sticky; top: 0; background: var(--surface); z-index: 1; font-size: 12px; letter-spacing: .04em; text-transform: uppercase;
    color: var(--muted); font-weight: 600; white-space: nowrap; }
  thead th.sortable { cursor: pointer; }
  thead th.sortable:hover { color: var(--ink); }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  tbody tr:last-child td { border-bottom: 0; }
  tr.total td { font-weight: 600; }
  .clamp { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .wide { min-width: 280px; }
  .chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 600; padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
  .chip::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .chip.pass { background: var(--good-soft); color: var(--good-ink); }
  .chip.partial { background: var(--warn-soft); color: var(--warn-ink); }
  .chip.fail { background: var(--bad-soft); color: var(--bad-ink); }
  .chip.na { background: transparent; color: var(--muted); padding-left: 0; }
  .chip.na::before { display: none; }
  .v { display: inline-block; min-width: 22px; text-align: center; font-size: 12px; font-weight: 700; border-radius: 4px; padding: 0 4px; }
  .v.P { background: var(--good-soft); color: var(--good-ink); }
  .v.F { background: var(--bad-soft); color: var(--bad-ink); }
  .v.NA { color: var(--muted); font-weight: 400; }
  .filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
  .filters label { display: grid; gap: 3px; font-size: 12.5px; color: var(--muted); font-weight: 600; }
  .filters input, .filters select { font: inherit; font-size: 14px; color: var(--ink); background: var(--surface); border: 1px solid var(--line);
    border-radius: 6px; padding: 6px 9px; min-width: 0; }
  .filters input[type="search"] { width: min(320px, 80vw); }
  .count { font-size: 14px; color: var(--ink-2); margin-left: auto; }
  tr.q { cursor: pointer; }
  tr.q:hover td { background: var(--row-hover); }
  tr.q.open td { background: var(--accent-soft); }
  tr.detail > td { background: var(--bg); padding: 16px; }
  .detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
  .block { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; display: grid; gap: 6px; min-width: 0; align-content: start; }
  .detail-inner { position: sticky; left: 0; }
  .block h4 { margin: 0; font-size: 12.5px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
  .pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; }
  .links a { display: block; overflow-wrap: anywhere; color: var(--accent); font-size: 13.5px; }
  .kv { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; font-size: 13.5px; }
  .kv dt { color: var(--muted); }
  .kv dd { margin: 0; min-width: 0; }
  .checks td { font-size: 13.5px; }
  .bar { display: flex; align-items: center; gap: 8px; min-width: 150px; }
  .bar .track { flex: 1; height: 10px; background: var(--bar-track); border-radius: 0 3px 3px 0; position: relative; min-width: 60px; }
  .bar .fill { position: absolute; inset: 0 auto 0 0; background: var(--bar); border-radius: 0 3px 3px 0; }
  .bar .t { font-variant-numeric: tabular-nums; font-size: 13px; min-width: 46px; text-align: right; }
  .conv { display: grid; gap: 10px; }
  details summary { cursor: pointer; color: var(--accent); font-weight: 600; font-size: 14px; }
  .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
  @media (max-width: 640px) { .card { padding: 14px; } .count { margin-left: 0; } }
  @media print { nav.tabs { display: none; } .panel[hidden] { display: grid !important; } .table-wrap.tall { max-height: none; } }
</style>
</head>
<body>
<header class="top wrap">
  <div class="eyebrow">India.gov.in · Saathi golden-test evaluation</div>
  <h1>Saathi evaluation: detailed report</h1>
  <p class="lede">Every sheet of the evaluation workbook in one page: the release checks, all __N__ questions with their answers and grading, the analysis behind the findings__COST_LEDE__.</p>
</header>
<nav class="tabs"><div class="wrap tabbar" role="tablist" id="tabbar"></div></nav>
<main class="wrap" id="main"></main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("data").textContent);
  var CHECKS = __CHECKS__, SHORT = __SHORT__;

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "cls") e.className = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c != null) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  function txt(v) { return v == null ? "" : String(v); }
  function pct(v, d) { return v == null || v === "" ? "–" : (v * 100).toFixed(d == null ? 1 : d) + "%"; }
  function num(v) { return v == null || v === "" ? "–" : (typeof v === "number" ? v.toLocaleString("en-IN") : v); }
  //<cost>
  function usd(v) { return v == null || v === "" ? "–" : "USD " + Number(v).toFixed(2); }
  //</cost>
  function chip(status) {
    var s = txt(status), c = s === "PASS" ? "pass" : s === "PARTIAL PASS" ? "partial" : (s === "FAIL" || s === "NO") ? "fail" : s === "YES" ? "pass" : "na";
    var label = s === "YES" ? "Met" : s === "NO" ? "Not met" : (s || "–");
    return el("span", {cls: "chip " + c, text: label});
  }
  function v(x) { var s = txt(x) || "NA"; return el("span", {cls: "v " + (s === "P" || s === "F" ? s : "NA"), text: s === "NA" ? "–" : s, title: s}); }
  function clean(s) { return txt(s).replace(/\*\*/g, ""); }
  function links(s) {
    var box = el("div", {cls: "links"});
    txt(s).split(/\s+/).forEach(function (u) {
      if (/^https?:\/\//.test(u)) box.appendChild(el("a", {href: u, target: "_blank", rel: "noopener", text: u}));
    });
    if (!box.childNodes.length) box.appendChild(el("span", {cls: "muted", text: "None"}));
    return box;
  }
  function block(title, body) { return el("div", {cls: "block"}, [el("h4", {text: title}), body]); }
  function pre(s) { return el("div", {cls: "pre", text: clean(s) || "–"}); }
  function bar(frac) {
    var b = el("div", {cls: "bar"}), t = el("div", {cls: "track"}), f = el("div", {cls: "fill"});
    f.style.width = Math.max(0, Math.min(1, frac || 0)) * 100 + "%";
    t.appendChild(f); b.appendChild(t); b.appendChild(el("span", {cls: "t", text: pct(frac)})); return b;
  }

  /* generic table: cols = [{key, label, num, fmt(row)->node|string, wide, clamp, filter}] */
  function dataTable(rows, cols, opts) {
    opts = opts || {};
    var wrap = el("div", {cls: "panel"}), state = {q: "", f: {}, sort: null, dir: 1};
    var bar = el("div", {cls: "filters"}), countEl = el("span", {cls: "count"});
    if (opts.search !== false) {
      var s = el("input", {type: "search", placeholder: "Search this table", "aria-label": "Search this table"});
      s.addEventListener("input", function () { state.q = s.value.toLowerCase(); draw(); });
      bar.appendChild(el("label", {}, ["Search", s]));
    }
    cols.forEach(function (c) {
      if (!c.filter) return;
      var vals = {}; rows.forEach(function (r) { vals[txt(r[c.key])] = 1; });
      var sel = el("select", {"aria-label": c.label}, [el("option", {value: "", text: "All"})]);
      Object.keys(vals).sort().forEach(function (k) { sel.appendChild(el("option", {value: k, text: k || "(blank)"})); });
      sel.addEventListener("change", function () { state.f[c.key] = sel.value; draw(); });
      bar.appendChild(el("label", {}, [c.label, sel]));
    });
    bar.appendChild(countEl);
    if (opts.search !== false || cols.some(function (c) { return c.filter; })) wrap.appendChild(bar);
    var tw = el("div", {cls: "table-wrap" + (rows.length > 25 ? " tall" : "")}), t = el("table"), th = el("thead"), tb = el("tbody"), hr = el("tr");
    cols.forEach(function (c, i) {
      var h = el("th", {cls: (c.num ? "num " : "") + "sortable", text: c.label, scope: "col", title: "Sort"});
      h.addEventListener("click", function () { state.dir = state.sort === i ? -state.dir : 1; state.sort = i; draw(); });
      hr.appendChild(h);
    });
    th.appendChild(hr); t.appendChild(th); t.appendChild(tb); tw.appendChild(t); wrap.appendChild(tw);
    function draw() {
      var list = rows.filter(function (r) {
        for (var k in state.f) if (state.f[k] && txt(r[k]) !== state.f[k]) return false;
        if (!state.q) return true;
        return cols.some(function (c) { return txt(r[c.key]).toLowerCase().indexOf(state.q) >= 0; });
      });
      if (state.sort != null) {
        var c = cols[state.sort];
        list = list.slice().sort(function (a, b) {
          var x = a[c.key], y = b[c.key];
          if (typeof x === "number" || typeof y === "number") return ((x == null ? -Infinity : x) - (y == null ? -Infinity : y)) * state.dir;
          return txt(x).localeCompare(txt(y), undefined, {numeric: true}) * state.dir;
        });
      }
      tb.textContent = "";
      list.forEach(function (r) {
        var tr = el("tr", {cls: r._total ? "total" : ""});
        cols.forEach(function (c) {
          var val = c.fmt ? c.fmt(r) : txt(r[c.key]);
          var td = el("td", {cls: (c.num ? "num " : "") + (c.wide ? "wide" : "")});
          if (c.clamp && typeof val === "string") td.appendChild(el("div", {cls: "clamp", text: val, title: val}));
          else td.appendChild(typeof val === "string" ? document.createTextNode(val) : val);
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      countEl.textContent = "Showing " + list.length + " of " + rows.length;
    }
    draw();
    return wrap;
  }
  function objs(t) { return t.rows.map(function (r) { var o = {}; t.head.forEach(function (h, i) { o[h] = r[i]; }); return o; }); }

  /* ---------------------------------------------------------------- tabs */
  var tabs = [], main = document.getElementById("main"), tabbar = document.getElementById("tabbar");
  function tab(id, label, build) { tabs.push({id: id, label: label, build: build, panel: null}); }
  function show(id) {
    tabs.forEach(function (t) {
      var on = t.id === id;
      if (on && !t.panel) { t.panel = el("section", {cls: "panel", id: "panel-" + t.id, role: "tabpanel"}); t.build(t.panel); main.appendChild(t.panel); }
      if (t.panel) t.panel.hidden = !on;
      t.btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    try { history.replaceState(null, "", "#" + id); } catch (e) {}
  }

  tab("overview", "Overview", function (p) {
    var sc = D.status_counts, total = 0; for (var k in sc) total += sc[k];
    var correct = D.results.filter(function (r) { return r.checks["Correctness & behaviour"][0] === "P"; }).length;
    var tiles = el("div", {cls: "tiles"}, [
      el("div", {cls: "tile"}, [el("span", {cls: "lab", text: "Pass"}), el("span", {cls: "val", text: num(sc["PASS"] || 0)}), el("span", {cls: "sub", text: (D.checklist_rule ? "at least 85% of the checklist met, of " : "every check passed, of ") + total + " test cases"})]),
      el("div", {cls: "tile"}, [el("span", {cls: "lab", text: "Partial pass"}), el("span", {cls: "val", text: num(sc["PARTIAL PASS"] || 0)}), el("span", {cls: "sub", text: D.checklist_rule ? "at least 60% of the key facts, nothing wrong" : "facts correct and links genuine, fell short elsewhere"})]),
      el("div", {cls: "tile"}, [el("span", {cls: "lab", text: "Fail"}), el("span", {cls: "val", text: num(sc["FAIL"] || 0)}), el("span", {cls: "sub", text: D.checklist_rule ? "below that, or a wrong fact or bad link" : "wrong, missing or no facts, or bad links"})]),
      el("div", {cls: "tile"}, [el("span", {cls: "lab", text: "Correct and within guardrails"}), el("span", {cls: "val", text: correct + " of " + D.results.length}), el("span", {cls: "sub", text: "Correctness & behaviour check"})])
    ]);
    p.appendChild(el("h2", {text: "Release checks (concept note 9.2)"}));
    //<recheck>
    if (D.recheck) p.appendChild(el("p", {cls: "lede", text: "Re-checked on " + D.recheck.date + ": every question was asked again. " +
      D.recheck.questions + " answers and " + D.recheck.conversations + " conversations had changed in substance and were re-graded with the same rubric (" +
      D.recheck.grader + "). The other answers were unchanged, mostly the same \"could not find\" reply on both days, so they keep their earlier answer and grades. Response times are from the re-check, when the bot was also returning temporary \"upstream unavailable\" errors and was slower than on 16 Oct even for questions asked one at a time; most questions were asked in four parallel streams, which may add some delay."}));
    //</recheck>
    p.appendChild(tiles);
    var rows = D.gates.rows.map(function (r) { return {gate: r[0], pass: r[1], fail: r[2], obs: r[3], lcl: r[4], crit: r[5], met: r[6]}; });
    p.appendChild(dataTable(rows, [
      {key: "gate", label: "Check", wide: true}, {key: "pass", label: "Pass", num: true}, {key: "fail", label: "Fail", num: true},
      {key: "obs", label: "Observed", num: true, fmt: function (r) { return pct(r.obs); }},
      {key: "lcl", label: "Wilson 95% lower limit", num: true, fmt: function (r) { return pct(r.lcl); }},
      {key: "crit", label: "Criterion", wide: true}, {key: "met", label: "Met?", fmt: function (r) { return r.met ? chip(r.met) : el("span", {cls: "muted", text: "Reported"}); }}
    ], {search: false}));
    var extra = D.gates.lang.concat(D.gates.latency).filter(function (r) { return r[0]; }).map(function (r) {
      return {m: r[0], v: r[3], crit: r[5], met: r[6]};
    });
    p.appendChild(dataTable(extra, [
      {key: "m", label: "Measure", wide: true},
      {key: "v", label: "Value", num: true, fmt: function (r) { return /Accuracy/.test(r.m) ? pct(r.v) : (r.v == null ? "–" : (/gap/.test(r.m) ? r.v.toFixed(1) + " points" : r.v.toFixed(2) + " s")); }},
      {key: "crit", label: "Criterion"}, {key: "met", label: "Met?", fmt: function (r) { return r.met ? chip(r.met) : el("span", {cls: "muted", text: "–"}); }}
    ], {search: false}));
    if (D.latency_note) p.appendChild(el("p", {cls: "note", text: D.latency_note}));
    p.appendChild(el("p", {cls: "note", text: D.gates.note}));
    p.appendChild(el("p", {cls: "note", text: D.checklist_rule ? "Status: each answer is checked against a checklist built from its golden answer: the key facts plus the required behaviours (the golden's instructions, the user's language, an official link or next step). PASS = at least 85% of the checklist met. PARTIAL PASS = at least 60% of the key facts present and correct (declines and redirects use their required behaviours). FAIL = below that, or any wrong or outdated fact, a non-official or broken link, or personal data repeated. Conversations use the share of turns passed. The workbook's Overall column (PASS/FAIL) is the stricter every-check view." : "Status: PASS = every check passed or did not apply. PARTIAL PASS = facts correct (or the required decline/redirect done) and source links genuine, but something else fell short, such as a claim the cited page does not support, the official next step, helpline, response flow or the user's language. FAIL = anything else, including wrong or outdated facts, no answer, a missing required fact or a non-official or broken link. The workbook's Overall column (PASS/FAIL) counts partial passes as FAIL."}));
  });

  tab("results", "Results by question", function (p) {
    p.appendChild(el("h2", {text: "Results for all " + D.results.length + " questions"}));
    p.appendChild(el("p", {cls: "note", text: "Click a row to see the question, the golden answer, Saathi's full answer, the sources it cited and every check with its reason. Check columns: P = pass, F = fail, – = not applicable."}));
    var state = {q: "", f: {}, failed: ""}, filters = el("div", {cls: "filters"}), countEl = el("span", {cls: "count"});
    var s = el("input", {type: "search", placeholder: "Search question, answer or reasons", "aria-label": "Search results"});
    s.addEventListener("input", function () { state.q = s.value.toLowerCase(); draw(); });
    filters.appendChild(el("label", {}, ["Search", s]));
    var fdefs = [["status", "Status"], ["priority", "Priority"], ["language", "Language"], ["category", "Category"], ["group", "Result group"], ["qtype", "Question type"]];
    //<recheck>
    if (D.recheck) fdefs.unshift(["recheck", "Re-check"]);
    //</recheck>
    fdefs.forEach(function (f) {
      var vals = {}; D.results.forEach(function (r) { vals[txt(r[f[0]])] = 1; });
      var sel = el("select", {"aria-label": f[1]}, [el("option", {value: "", text: "All"})]);
      Object.keys(vals).sort().forEach(function (k) { sel.appendChild(el("option", {value: k, text: k})); });
      sel.addEventListener("change", function () { state.f[f[0]] = sel.value; draw(); });
      filters.appendChild(el("label", {}, [f[1], sel]));
    });
    var cf = el("select", {"aria-label": "Failed check"}, [el("option", {value: "", text: "Any"})]);
    CHECKS.forEach(function (c) { cf.appendChild(el("option", {value: c, text: c})); });
    cf.addEventListener("change", function () { state.failed = cf.value; draw(); });
    filters.appendChild(el("label", {}, ["Failed check", cf]));
    filters.appendChild(countEl);
    p.appendChild(filters);
    var tw = el("div", {cls: "table-wrap tall"}), t = el("table"), th = el("thead"), tb = el("tbody"), hr = el("tr");
    var heads = ["ID", "Pri", "Language", "Category", "Question", "Status"].concat(D.checklist_rule ? ["Checklist"] : []).concat(["Result group"]);
    var base = heads.length;
    heads.concat(CHECKS.map(function (c) { return SHORT[c]; })).concat(["Time (s)"]).forEach(function (h, i) {
      hr.appendChild(el("th", {text: h, scope: "col", cls: i >= base ? "num" : "", title: i >= base && i < base + CHECKS.length ? CHECKS[i - base] : ""}));
    });
    th.appendChild(hr); t.appendChild(th); t.appendChild(tb); tw.appendChild(t); p.appendChild(tw);
    function detail(r) {
      var checks = el("table", {cls: "checks"}, [el("thead", {}, [el("tr", {}, [el("th", {text: "Check"}), el("th", {text: "Verdict"}), el("th", {text: "Reason"})])])]);
      var cb = el("tbody");
      CHECKS.forEach(function (c) { cb.appendChild(el("tr", {}, [el("td", {text: c}), el("td", {}, [v(r.checks[c][0])]), el("td", {cls: "wide", text: txt(r.checks[c][1])})])); });
      checks.appendChild(cb);
      var kv = el("dl", {cls: "kv"});
      var kvRows = [["Status", r.status], ["Overall (workbook)", r.overall], ["Accuracy", r.accuracy], ["Citation (combined)", r.citation_combined],
       ["Unsupported content", r.unsupported], ["Facts vs golden answer", r.facts], ["Required behaviour met", r.behaviour],
       ["Guardrails violated", r.gr_violated || "none"], ["Guardrails exercised (golden)", r.gr_exercised],
       ["Question type", r.qtype], ["Abstention row", r.abstain], ["Profile", r.profile], ["Knowledge level", r.knowledge],
       ["Gender", r.gender], ["Age group", r.age], ["Persona", r.persona], ["Response time", r.latency == null ? "–" : r.latency + " s"]];
      //<recheck>
      if (D.recheck) kvRows = kvRows.concat([["Re-check", r.recheck_note], ["Status in earlier run", r.earlier], ["Graded by", r.graded_by]]);
      //</recheck>
      kvRows.forEach(function (x) {
        kv.appendChild(el("dt", {text: x[0]})); kv.appendChild(el("dd", {text: txt(x[1]) || "–"}));
      });
      var human = el("dl", {cls: "kv"});
      Object.keys(r.human).forEach(function (k) { human.appendChild(el("dt", {text: k})); human.appendChild(el("dd", {text: txt(r.human[k]) || "not graded"})); });
      var grid = el("div", {cls: "detail-grid"}, [
        block("Question", pre(r.query)),
        block("Expected answer (golden)", pre(r.golden)),
        block("Saathi's answer", pre(r.answer)),
        block("Sources Saathi cited", links(r.sources)),
        block("Expected source", el("div", {}, [el("div", {text: r.site || "–"}), pre(r.golden_urls)])),
        block("Result: " + (r.group || "–"), el("div", {}, [pre(r.reason)].concat(r.why_unanswered ? [el("p", {cls: "note", text: "Why unanswered: " + r.why_unanswered})] : []))),
        block("Grading summary", kv),
        block("Human grades", human)
      ]);
      if (D.checklist_rule) grid.insertBefore(block("Checklist: " + pct(r.checklist_met, 0) + " met, key facts " + pct(r.facts_present, 0), pre(r.checklist)), grid.children[6]);
      return el("div", {cls: "panel"}, [grid, block("Every check", el("div", {cls: "table-wrap"}, [checks]))]);
    }
    function draw() {
      var list = D.results.filter(function (r) {
        for (var k in state.f) if (state.f[k] && txt(r[k]) !== state.f[k]) return false;
        if (state.failed && r.checks[state.failed][0] !== "F") return false;
        if (!state.q) return true;
        var hay = [r.id, r.query, r.answer, r.golden, r.reason, r.group].concat(CHECKS.map(function (c) { return r.checks[c][1]; })).join(" ").toLowerCase();
        return hay.indexOf(state.q) >= 0;
      });
      tb.textContent = "";
      list.forEach(function (r) {
        var tr = el("tr", {cls: "q", tabindex: "0", "aria-expanded": "false"}, [
          el("td", {text: r.id}), el("td", {text: r.priority}), el("td", {text: r.language}), el("td", {text: r.category}),
          el("td", {cls: "wide"}, [el("div", {cls: "clamp", text: r.query})]), el("td", {}, [chip(r.status)]), D.checklist_rule ? el("td", {cls: "num", text: pct(r.checklist_met, 0)}) : null, el("td", {text: r.group})
        ].concat(CHECKS.map(function (c) { return el("td", {cls: "num"}, [v(r.checks[c][0])]); })).concat([el("td", {cls: "num", text: r.latency == null ? "–" : Number(r.latency).toFixed(1)})]));
        var dr = null;
        function toggle() {
          if (dr) { dr.remove(); dr = null; tr.classList.remove("open"); tr.setAttribute("aria-expanded", "false"); return; }
          var inner = detail(r);
          inner.classList.add("detail-inner");
          inner.style.width = Math.max(280, tw.clientWidth - 34) + "px";  /* stays in view while the wide table scrolls sideways */
          dr = el("tr", {cls: "detail"}, [el("td", {colspan: String(base + 1 + CHECKS.length)}, [inner])]);
          tr.after(dr); tr.classList.add("open"); tr.setAttribute("aria-expanded", "true");
        }
        tr.addEventListener("click", toggle);
        tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
        tb.appendChild(tr);
      });
      countEl.textContent = "Showing " + list.length + " of " + D.results.length;
    }
    draw();
  });

  tab("facts", "Facts vs guardrails", function (p) {
    var F = D.fvg;
    p.appendChild(el("h2", {text: F.title}));
    p.appendChild(el("p", {cls: "note", text: F.note}));
    var cls = objs(F.classes);
    cls.forEach(function (r) { if (/^Total/.test(r["Failure class"])) r._total = true; });
    var segs = F.classes.head.slice(1, -1);
    p.appendChild(dataTable(cls, [{key: "Failure class", label: "Failure class", wide: true}].concat(segs.map(function (s) {
      return {key: s, label: s, num: true, fmt: function (r) { var x = r[s]; return /^Facts right/.test(r["Failure class"]) ? pct(x) : num(x); }};
    })).concat([{key: "% of all", label: "% of all", num: true, fmt: function (r) { return r["% of all"] == null ? "" : pct(r["% of all"]); }}]), {search: false}));
    p.appendChild(el("h3", {text: "Accuracy against the targets"}));
    var acc = objs(F.accuracy);
    p.appendChild(dataTable(acc, F.accuracy.head.map(function (h, i) {
      return i === 0 ? {key: h, label: h, wide: true} : {key: h, label: h, num: true, fmt: function (r) { return i < 3 ? bar(r[h]) : pct(r[h], 0); }};
    }), {search: false}));
    p.appendChild(el("p", {cls: "note", text: F.acc_note}));
    p.appendChild(el("h3", {text: "Causes of failure"}));
    var causes = objs(F.causes);
    p.appendChild(dataTable(causes, F.causes.head.map(function (h, i) { return i === 0 ? {key: h, label: h, wide: true} : {key: h, label: h, num: true}; }), {search: false}));
  });

  tab("unanswered", "Unanswered split", function (p) {
    var U = D.unanswered;
    p.appendChild(el("h2", {text: U.title}));
    p.appendChild(el("p", {cls: "note", text: U.note}));
    var sm = objs(U.summary);
    p.appendChild(dataTable(sm, U.summary.head.map(function (h, i) { return i === 0 ? {key: h, label: h, wide: true} : {key: h, label: h, num: true}; }), {search: false}));
    p.appendChild(el("p", {cls: "note", text: U.note2 + " " + U.page_note[0] + " " + U.page_note[1] + "."}));
    p.appendChild(el("h3", {text: "Each unanswered question"}));
    var det = objs(U.detail);
    p.appendChild(dataTable(det, U.detail.head.map(function (h) {
      var c = {key: h, label: h};
      if (/^(Pages|Key figures|Found)/.test(h)) c.num = true;
      if (/^(Priority|Language|Group|Golden page read|Figures found|Bot reply kind|Category)$/.test(h)) c.filter = true;
      if (h === "Sites the bot read") { c.wide = true; c.clamp = true; }
      return c;
    })));
  });

  tab("guardrails", "Guardrails", function (p) {
    p.appendChild(el("h2", {text: "Violations by guardrail"}));
    p.appendChild(el("p", {cls: "note", text: "Rows tested = questions whose golden answer exercises the guardrail. Rows violating = questions where any check recorded a breach of it."}));
    var g = objs(D.guardrails), max = Math.max.apply(null, g.map(function (r) { return r["Rows violating"] || 0; }).concat([1]));
    p.appendChild(dataTable(g, [
      {key: "ID", label: "ID"}, {key: "Guardrail", label: "Guardrail", wide: true},
      {key: "Rows tested", label: "Rows tested", num: true}, {key: "Rows violating", label: "Rows violating", num: true},
      {key: "_bar", label: "Share of the most violated", fmt: function (r) { return bar((r["Rows violating"] || 0) / max); }},
      {key: "Conversations violating", label: "Conversations violating", num: true}
    ], {search: false}));
  });

  tab("segments", "Segments", function (p) {
    p.appendChild(el("h2", {text: "Accuracy by segment"}));
    p.appendChild(el("p", {cls: "note", text: "Accuracy = Correctness & behaviour pass and no fail on figures, citation or freshness (concept note 9.3.3)."}));
    var s = objs(D.segments);
    p.appendChild(dataTable(s, [
      {key: "Dimension", label: "Dimension", filter: true}, {key: "Value", label: "Value", wide: true},
      {key: "Accuracy pass", label: "Pass", num: true}, {key: "Accuracy fail", label: "Fail", num: true},
      {key: "Rate", label: "Rate", fmt: function (r) { return r.Rate === "" || r.Rate == null ? "–" : bar(r.Rate); }}
    ]));
  });

  tab("judge", "Judge vs human", function (p) {
    p.appendChild(el("h2", {text: "Model grader against human graders"}));
    p.appendChild(el("p", {cls: "note", text: "Concept note 9.3.4: the model grader may be relied on for regression only if it agrees with human graders on at least 90% of a sample. Agreement fills in once testers enter P/F grades in the Human columns of the workbook's Results sheet."}));
    var j = objs(D.judge_human);
    p.appendChild(dataTable(j, [
      {key: "Dimension", label: "Dimension"}, {key: "Rows graded by both", label: "Rows graded by both", num: true},
      {key: "Agree", label: "Agree", num: true}, {key: "Agreement", label: "Agreement", num: true, fmt: function (r) { return r.Agreement === "" || r.Agreement == null ? "No human grades yet" : pct(r.Agreement); }},
      {key: "Criterion", label: "Criterion", wide: true}
    ], {search: false}));
  });

  tab("conversations", "Conversations", function (p) {
    p.appendChild(el("h2", {text: D.conversations.length + " multi-turn conversations"}));
    p.appendChild(el("p", {cls: "note", text: "Each conversation is graded turn by turn against the expected behaviour and the guardrails; it passes only if every turn passes."}));
    D.conversations.forEach(function (c) {
      var card = el("article", {cls: "card"}, [
        el("div", {cls: "filters"}, [el("h3", {text: c.id + " · " + txt(c.title).replace(/^Multi-turn: /, "")}), el("span", {cls: "count"}, [chip(c.status)])]),
        el("p", {cls: "note", text: "Language: " + txt(c.lang) + (c.guardrails ? " · Guardrails violated: " + c.guardrails : "")}),
        block("Why", pre(c.reason)),
        el("div", {cls: "two"}, [block("User turns", pre(c.turns)), block("Expected behaviour per turn", pre(c.expected))]),
        el("details", {}, [el("summary", {text: "Show Saathi's replies and sources"}), el("div", {cls: "two"}, [block("Saathi's replies", pre(c.transcript)), block("Sources cited", links(c.urls))])])
      ]);
      p.appendChild(card);
    });
  });

  //<cost>
  if (D.tokens) tab("tokens", "Tokens & cost", function (p) {
    var T = D.tokens;
    p.appendChild(el("h2", {text: "Grading tokens and cost"}));
    p.appendChild(el("p", {cls: "note", text: "Judge model: " + T.model + " · USD " + T.price_in + " per million input tokens, USD " + T.price_out + " per million output tokens. " + T.note}));
    var rows = objs(T.table);
    rows.forEach(function (r) { if (r.Check === "TOTAL") r._total = true; });
    p.appendChild(dataTable(rows, T.table.head.map(function (h, i) {
      return i === 0 ? {key: h, label: h} : {key: h, label: h, num: true, fmt: function (r) { return /cost/.test(h) ? usd(r[h]) : num(r[h]); }};
    }), {search: false}));
    var total = rows.filter(function (r) { return r._total; })[0], extra;
    if (T.spend) {  /* re-checked run: every Bedrock run so far, including grades later replaced by the re-check */
      extra = T.spend.map(function (e) { return {part: e[0], calls: e[1], cost: e[2]}; });
      extra.push({part: "Total Bedrock spend to date", calls: extra.reduce(function (a, e) { return a + (e.calls || 0); }, 0),
                  cost: extra.reduce(function (a, e) { return a + (e.cost || 0); }, 0), _total: true});
      p.appendChild(el("p", {cls: "note", text: "The table above counts the judge calls behind the grades in this report. The table below is every Bedrock run so far, including the 16 Oct grades that the re-check replaced."}));
    } else {
      extra = T.extra.map(function (e) { return {part: e[0], calls: e[1], cost: e[2]}; });
      var all = (total ? Number(total["Est. cost (USD)"]) : 0) + extra.reduce(function (a, e) { return a + e.cost; }, 0);
      extra.unshift({part: "Full judged run (this table)", calls: total ? total.Calls : null, cost: total ? total["Est. cost (USD)"] : null});
      extra.push({part: "Total grading cost", calls: extra.reduce(function (a, e) { return a + (e.calls || 0); }, 0), cost: all, _total: true});
    }
    p.appendChild(el("h3", {text: "All grading spend"}));
    p.appendChild(dataTable(extra, [{key: "part", label: "Part", wide: true}, {key: "calls", label: "Judge calls", num: true, fmt: function (r) { return num(r.calls); }},
      {key: "cost", label: "Cost", num: true, fmt: function (r) { return r.cost == null && !r._total ? "No Bedrock cost" : usd(r.cost); }}], {search: false}));
    p.appendChild(el("h3", {text: "Tokens by question"}));
    var q = objs(D.tokens_by_question);
    p.appendChild(dataTable(q, D.tokens_by_question.head.map(function (h, i) {
      return i === 0 ? {key: h, label: h} : {key: h, label: h, num: true, fmt: function (r) { return /cost/.test(h) ? usd(r[h]) : num(r[h]); }};
    })));
  });
  //</cost>

  tab("factsdetail", "Facts split detail", function (p) {
    p.appendChild(el("h2", {text: "Facts split, one row per question"}));
    p.appendChild(el("p", {cls: "note", text: "Second grading pass on each failed answer: are the facts right (vs the golden answer), and was the required behaviour met? Failure class takes the first that applies: wrong facts, not answered, fact missing, behaviour, guardrails."}));
    var d = objs(D.facts_detail);
    p.appendChild(dataTable(d, D.facts_detail.head.map(function (h) {
      var c = {key: h, label: h};
      if (/^(Priority|Language|Category|Correctness & behaviour|Facts vs golden|Behaviour met|Failure class|Abstention row)$/.test(h)) c.filter = true;
      if (/reason|Causes/.test(h)) { c.wide = true; c.clamp = true; }
      return c;
    })));
  });

  tabs.forEach(function (t) {
    t.btn = el("button", {type: "button", role: "tab", "aria-controls": "panel-" + t.id, text: t.label});
    t.btn.addEventListener("click", function () { show(t.id); window.scrollTo({top: 0}); });
    tabbar.appendChild(t.btn);
  });
  var start = (location.hash || "").slice(1);
  show(tabs.some(function (t) { return t.id === start; }) ? start : "overview");
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--no-cost", action="store_true", help="leave out the Tokens & cost tab")
    ap.add_argument("--no-recheck", action="store_true", help="present a re-checked run as a single run")
    a = ap.parse_args()
    run_dir = config.RUNS_DIR / a.run
    data = collect(run_dir, recheck=not a.no_recheck, cost_tab=not a.no_cost)
    if not data["recheck"]:
        for r in data["results"]:
            for k in ("recheck", "recheck_note", "earlier", "graded_by"):
                r.pop(k, None)
    data = {k: v for k, v in data.items() if v is not None}
    payload = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = (PAGE.replace("__DATA__", payload).replace("__N__", str(len(data["results"])))
            .replace("__CHECKS__", json.dumps(CHECKS)).replace("__SHORT__", json.dumps(SHORT))
            .replace("__COST_LEDE__", ", conversations, and grading cost" if "tokens" in data else " and the conversations"))
    for block, keep in (("recheck", "recheck" in data), ("cost", "tokens" in data)):  # leave unused features out of the file
        if not keep:
            html = re.sub(rf"[ \t]*//<{block}>\n.*?[ \t]*//</{block}>\n", "", html, flags=re.S)
    html = re.sub(r"[ \t]*//</?(recheck|cost)>\n", "", html)
    out = run_dir / "saathi-detailed-report.html"
    out.write_text(html, encoding="utf-8")
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB): {len(data['results'])} questions, {len(data['conversations'])} conversations")


if __name__ == "__main__":
    main()
