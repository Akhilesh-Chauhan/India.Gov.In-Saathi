"""Split the questions the bot did not answer into content gaps vs retrieval and answer-generation failures.

Uses facts_split.jsonl (facts = "not answered"), the workbook's expected source domain, and the pages the bot says it
read before replying ("Reading N sources", sources_checked). No judge calls. Groups:
  Read the expected site, no answer     - the bot retrieved pages from the expected (crawled) site and still fell back
  Expected site not retrieved           - the expected site is crawled, but the bot read no page from it
  Needs service data (DB/API)           - the answer lives in UMANG / myScheme service data, not a crawled page
  No expected source                    - the golden names no source site
For the first group it also checks whether the golden answer's key figures (amounts, percentages, quantities) appear
on the pages the bot read, fetching them into the page cache if needed.
Writes runs/<run>/unanswered_split.jsonl and the report.xlsx sheet "Unanswered split".

Example: python unanswered_split.py --run day1
"""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

import config
from facts_split import BOLD, FONT, NOTE, TITLE, WRAP, _head
from metrics import DEVANAGARI_DIGITS, _readable, norm_url
from pages import bare, get_page, host_class, ingested_domains  # bare comes from ../check_sources.py
from run_eval import _read_jsonl
from workbook import load_rows

GROUPS = ["Read the expected site, no answer", "Expected site not retrieved", "Needs service data (DB/API)",
          "No expected source"]
# Key figures in a golden answer, each with the context it must keep on the page (a bare "5" would match anything)
FIGURES = [(re.compile(r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)", re.I), r"(?:₹|rs\.?|inr|rupees?)\s*{n}(?!\d)"),
           (re.compile(r"(\d+(?:\.\d+)?)\s*%"), r"(?<![\d.]){n}\s*(?:%|per\s*cent)"),
           (re.compile(r"(\d+(?:\.\d+)?)\s*(kg|days?|weeks?|months?|lakh|crore|hours?)\b", re.I), r"(?<![\d.]){n}\s*{u}"),
           (re.compile(r"\b(\d{1,3}(?:,\d{2,3})+)\b"), r"(?<![\d.]){n}(?!\d)")]


def golden_figures(golden):
    """(number, unit) pairs from the golden's answer part (before 'Behaviour:' / 'Fail if:', which list stale values)."""
    text = re.split(r"\b(?:Behaviour|Fail if)\s*:", str(golden or ""), maxsplit=1, flags=re.I)[0].translate(DEVANAGARI_DIGITS)
    out = []
    for i, (rx, _) in enumerate(FIGURES):
        for m in rx.finditer(text):
            n = m.group(1).replace(",", "")
            unit = m.group(2).lower().rstrip("s") if rx.groups > 1 else ""
            if (i, n, unit) not in out:
                out.append((i, n, unit))
    return out


def found(fig, corpus):
    i, n, unit = fig
    pattern = FIGURES[i][1].format(n=re.escape(n), u=re.escape(unit) + "s?")
    return re.search(pattern, corpus, re.I) is not None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run_dir = config.RUNS_DIR / a.run
    rows, ingested = load_rows(), ingested_domains()
    by_query = {r["Query (type exactly)"]: r["Test ID"] for r in rows.values()}
    responses = {by_query.get(r["query"], r["id"]): r for r in _read_jsonl(run_dir / "responses.jsonl")}
    split = {r["id"]: r for r in _read_jsonl(run_dir / "facts_split.jsonl")}
    todo = sorted(i for i, s in split.items() if s["facts"] == "not answered")

    urls = sorted({p["url"] for i in todo for s in responses[i].get("sources_checked") or [] for p in s.get("pages", [])})
    print(f"{len(todo)} unanswered questions; reading {len(urls)} pages the bot retrieved (cached for {config.PAGE_CACHE_HOURS:g} h)")
    with ThreadPoolExecutor(8) as pool:
        pages = dict(zip(urls, pool.map(get_page, urls)))

    out = []
    for i in todo:
        row, rec = rows[i], responses[i]
        expected = [bare(d) for d in re.split(r"[,;\s]+", str(row.get("Expected source domain") or "")) if "." in d]
        read = [(bare(s.get("domain") or ""), p["url"]) for s in rec.get("sources_checked") or [] for p in s.get("pages", [])]
        on_site = [u for d, u in read if any(d == e or d.endswith("." + e) or e.endswith("." + d) for e in expected)]
        golden_urls = re.findall(r"https?://[^\s,;)]+", " ".join(str(row.get(k) or "") for k in ("Golden sources (verified URLs)", "Index chunk URL")))
        exact = any(norm_url(u) in {norm_url(g.rstrip(".")) for g in golden_urls} for _, u in read) if golden_urls else None
        classes = {host_class("https://" + e, ingested) for e in expected}
        if not expected:
            group = GROUPS[3]
        elif "DB/API" in classes:
            group = GROUPS[2]
        elif on_site:
            group = GROUPS[0]
        else:
            group = GROUPS[1]
        figs = golden_figures(row.get("Expected behaviour / golden answer"))
        corpus = " ".join(pages[u]["text"] for _, u in read if _readable(pages.get(u))).translate(DEVANAGARI_DIGITS).replace(",", "")
        hits = sum(found(f, corpus) for f in figs)
        out.append({"id": i, "group": group, "expected": ", ".join(expected) or "none",
                    "expected_crawled": "Y" if classes & {"crawled", "subdomain-of-crawled"} else "N",
                    "pages_read": len(read), "expected_site_pages_read": len(on_site),
                    "golden_page_read": "NA" if exact is None else ("Y" if exact else "N"),
                    "key_figures": len(figs), "figures_on_pages_read": hits,
                    "bot_reply": rec.get("kind"), "sites_read": ", ".join(dict.fromkeys(d for d, _ in read))})
    with (run_dir / "unanswered_split.jsonl").open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_sheet(run_dir, rows, out)
    for g in GROUPS:
        print(f"{g:36s} {sum(r['group'] == g for r in out)}")
    print(f"Sheet 'Unanswered split' written to {run_dir / 'report.xlsx'}")


def write_sheet(run_dir, rows, out):
    from run_eval import _clean  # control characters Excel cannot store
    rows, out = _clean(rows), _clean(out)
    path = run_dir / "report.xlsx"
    wb = load_workbook(path)
    if "Unanswered split" in wb.sheetnames:
        del wb["Unanswered split"]
    ws = wb.create_sheet("Unanswered split", index=wb.sheetnames.index("Facts vs guardrails") + 1)
    ws["A1"], ws["A1"].font = "Questions the bot did not answer: content gap or retrieval?", TITLE
    ws["A2"] = ("Rows with Facts vs golden = 'not answered' (Facts split detail). 'Pages read' = the bot's own "
                "'Reading N sources' list. Key figures = amounts, percentages and quantities in the golden answer.")
    ws["A2"].font = NOTE
    first = 14  # detail table header row
    last = first + len(out)

    def rng(col):
        return f"${col}${first + 1}:${col}${last}"

    _head(ws, 4, ["Group", "All", "P0", "P1", "P2", "Golden figures all on pages read", "Some", "None found"],
          [36, 9, 9, 9, 9, 16, 9, 10])
    for r, g in enumerate(GROUPS, 5):
        ws.cell(r, 1, g)
        ws.cell(r, 2, f'=COUNTIF({rng("D")},$A{r})')
        for c, p in ((3, "P0"), (4, "P1"), (5, "P2")):
            ws.cell(r, c, f'=COUNTIFS({rng("D")},$A{r},{rng("B")},"{p}")')
        ws.cell(r, 6, f'=COUNTIFS({rng("D")},$A{r},{rng("J")},">0",{rng("L")},"all")')
        ws.cell(r, 7, f'=COUNTIFS({rng("D")},$A{r},{rng("L")},"some")')
        ws.cell(r, 8, f'=COUNTIFS({rng("D")},$A{r},{rng("L")},"none")')
    ws.cell(9, 1, "Total")
    for c in range(2, 9):
        col = get_column_letter(c)
        ws.cell(9, c, f"=SUM({col}5:{col}8)")
    ws["A10"] = ("Golden-figure columns count only questions whose golden answer has key figures; a figure found on a page "
                 "the bot read means the answer was in front of it.")
    ws["A10"].font = NOTE
    ws["A11"] = "Read the expected site but the exact golden page was not among the pages read:"
    ws["F11"] = f'=COUNTIFS({rng("D")},A5,{rng("I")},"N")'

    cols = ["Test ID", "Priority", "Language", "Group", "Expected site", "Expected site crawled", "Pages read",
            "Pages read from expected site", "Golden page read", "Key figures in golden", "Found on pages read",
            "Figures found", "Bot reply kind", "Category", "Sites the bot read"]
    _head(ws, first, cols)
    for c, w in enumerate([8, 7, 12, 30, 22, 9, 7, 9, 8, 8, 8, 9, 10, 18, 60], 1):
        ws.column_dimensions[get_column_letter(c)].width = max(ws.column_dimensions[get_column_letter(c)].width or 0, w)
    for n, r in enumerate(out, first + 1):
        row = rows[r["id"]]
        vals = [r["id"], row["Priority"], row["Language"], r["group"], r["expected"], r["expected_crawled"], r["pages_read"],
                r["expected_site_pages_read"], r["golden_page_read"], r["key_figures"], r["figures_on_pages_read"], None,
                r["bot_reply"], row["Category"], r["sites_read"]]
        for c, v in enumerate(vals, 1):
            ws.cell(n, c, v)
        ws.cell(n, 12, f'=IF(J{n}=0,"n/a",IF(K{n}=J{n},"all",IF(K{n}>0,"some","none")))')
    for r in ws.iter_rows(min_row=5):
        for cell in r:
            if cell.font != BOLD and cell.row != 10:
                cell.font, cell.alignment = FONT, WRAP
    wb.save(path)


if __name__ == "__main__":
    main()
