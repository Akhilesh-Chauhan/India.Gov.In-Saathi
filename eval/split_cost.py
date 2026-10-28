"""Keep grading tokens and cost out of the shared report: move them into runs/<run>/grading_cost.xlsx.

Removes the 'Token usage' and 'Tokens by question' sheets from report.xlsx and writes grading_cost.xlsx with
  Spend summary       every Bedrock run behind this report (pilot, judged runs, facts splits) against the approved budget
  Token usage         judge calls and tokens per check, for the grades in the report
  Tokens by question  the same per test case
Run recalc on both files afterwards (formulas are written without cached values).

Example: python split_cost.py --run day1 --budget 200
"""
import argparse
import json

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

import config
from run_eval import _read_jsonl, write_token_sheets

BOLD = Font(name="Arial", bold=True, color="FFFFFF")
HEAD = PatternFill("solid", fgColor="1F3864")
FONT, INPUT = Font(name="Arial", size=10), Font(name="Arial", size=10, color="0000FF")


def spend_parts(run_dir):
    """[(label, usage records)] for every Bedrock run that produced or preceded the grades in this run."""
    meta = json.loads((run_dir / "regrade.json").read_text(encoding="utf-8")) if (run_dir / "regrade.json").exists() else {}
    if not meta:
        parts = [("Pilot", _read_jsonl(config.RUNS_DIR / f"{run_dir.name}-pilot" / "tokens.jsonl")),
                 ("Judged run", _read_jsonl(run_dir / "tokens.jsonl")),
                 ("Facts vs guardrails pass", _read_jsonl(run_dir / "facts_split_tokens.jsonl"))]
    else:
        base = config.RUNS_DIR / meta["baseline_run"]
        regs = sorted(config.RUNS_DIR.glob(f"{run_dir.name}-regrade-*"))
        parts = [("Pilot (25 questions, 2 conversations)", _read_jsonl(config.RUNS_DIR / f"{base.name}-pilot" / "tokens.jsonl")),
                 (f"Judged run on the {meta.get('baseline_collected', 'first')} answers", _read_jsonl(base / "tokens.jsonl")),
                 (f"Facts vs guardrails pass on the {meta.get('baseline_collected', 'first')} answers", _read_jsonl(base / "facts_split_tokens.jsonl")),
                 (f"Re-check {meta['rechecked']}: re-grade of the answers that changed", [u for d in regs for u in _read_jsonl(d / "tokens.jsonl")]),
                 (f"Re-check {meta['rechecked']}: facts vs guardrails pass on them", [u for d in regs for u in _read_jsonl(d / "facts_split_tokens.jsonl")])]
    return [(label, us) for label, us in parts if us]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--budget", type=float, help="approved budget in USD (shown against the spend)")
    a = ap.parse_args()
    run_dir = config.RUNS_DIR / a.run

    rep_path = run_dir / "report.xlsx"
    rep = load_workbook(rep_path)
    removed = [n for n in ("Token usage", "Tokens by question") if n in rep.sheetnames]
    for n in removed:
        del rep[n]
    rep.save(rep_path)

    from judge import price_for
    pin, pout = price_for(config.JUDGE_MODEL)
    wb = Workbook()
    s = wb.active
    s.title = "Spend summary"
    s["A1"], s["A1"].font = f"Grading cost: Saathi golden-test evaluation (run {a.run})", Font(name="Arial", size=14, bold=True)
    s["A2"], s["B2"] = "Price USD / million input tokens", pin
    s["A3"], s["B3"] = "Price USD / million output tokens", pout
    s["B2"].comment = s["B3"].comment = Comment("Anthropic list price for Claude Opus 5.5, used for the Bedrock global "
                                                "inference profile; edit to the account's Bedrock rate card.", "evaluation")
    for c in ("A2", "A3"):
        s[c].font = FONT
    s["B2"].font = s["B3"].font = INPUT
    head = ["Part", "Judge calls", "Input tokens", "Output tokens", "Cost (USD)"]
    for col, h in enumerate(head, 1):
        cell = s.cell(5, col, h)
        cell.font, cell.fill = BOLD, HEAD
    widths = {"A": 62, "B": 13, "C": 15, "D": 15, "E": 13}
    for k, w in widths.items():
        s.column_dimensions[k].width = w
    r = 6
    for label, us in spend_parts(run_dir):
        s.cell(r, 1, label)
        s.cell(r, 2, len(us))
        s.cell(r, 3, sum(u["input_tokens"] for u in us))
        s.cell(r, 4, sum(u["output_tokens"] for u in us))
        s.cell(r, 5, f"=C{r}/1000000*$B$2+D{r}/1000000*$B$3")
        r += 1
    first, last = 6, r - 1
    s.cell(r, 1, "Total Bedrock spend")
    for col in "BCDE":
        s[f"{col}{r}"] = f"=SUM({col}{first}:{col}{last})"
    total_row = r
    if a.budget is not None:
        s.cell(r + 2, 1, "Approved budget (USD)")
        s.cell(r + 2, 5, a.budget).font = INPUT
        s.cell(r + 2, 5).comment = Comment("Budget approval received 19 Oct 2026 for the judged evaluation.", "evaluation")
        s.cell(r + 3, 1, "Remaining (USD)")
        s.cell(r + 3, 5, f"=E{r + 2}-E{total_row}")
    for row in s.iter_rows(min_row=6, max_row=s.max_row):
        for cell in row:
            if cell.font != INPUT:
                cell.font = Font(name="Arial", size=10, bold=cell.row == total_row)
            if cell.column >= 2:
                cell.number_format = "#,##0.00" if cell.column == 5 else "#,##0"
    s.cell(s.max_row + 2, 1, "Cost = tokens x price above. Bedrock bills its own rate card, so treat this as an estimate.").font = Font(name="Arial", size=9, italic=True)
    for cell in s["A"]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    write_token_sheets(wb, _read_jsonl(run_dir / "tokens.jsonl"), config.JUDGE_MODEL)
    note = wb["Token usage"]["A4"]
    note.value = (note.value or "") + " These sheets count the judge calls behind the grades in report.xlsx."
    out = run_dir / "grading_cost.xlsx"
    wb.save(out)
    print(f"removed {removed} from {rep_path.name}; wrote {out}")


if __name__ == "__main__":
    main()
