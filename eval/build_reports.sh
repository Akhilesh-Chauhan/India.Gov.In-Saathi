#!/usr/bin/env bash
# Rebuild every report file of a judged run (after run_eval.py and facts_split.py, or after recheck.py build):
#   report.xlsx (rebuilt from results.jsonl when the results are newer, e.g. after apply_overrides.py) and its analysis
#   sheets, findings_by_test_case.xlsx, saathi-detailed-report.html, saathi-findings.html
#
#   ./build_reports.sh RUN                       full internal view (re-check and cost included when present)
#   ./build_reports.sh RUN --no-cost             the same files without grading tokens or cost on the pages
#                                                (a re-checked run is shown as one run; cost stays in report.xlsx)
#   BUDGET=200 ./build_reports.sh RUN --shared   files to share: as --no-cost, and grading tokens and cost move out of
#                                                report.xlsx into grading_cost.xlsx (BUDGET in USD is optional)
#
# Workbook formulas are recalculated with LibreOffice by recalc.py (each file as a copy outside the run folder).
set -euo pipefail
RUN=${1:?usage: ./build_reports.sh RUN [--no-cost|--shared]}
MODE=${2:-}
cd "$(dirname "$0")"
PY=${PY:-../.venv/bin/python}
DIR="runs/$RUN"
[ -f "$DIR/results.jsonl" ] || { echo "No graded results in $DIR: run run_eval.py --run $RUN first"; exit 1; }

case "$MODE" in
  "")        SHEET_FLAGS=(); HTML_FLAGS=(); PAGE_FLAGS=() ;;
  --no-cost) SHEET_FLAGS=(--no-recheck); HTML_FLAGS=(--no-recheck --no-cost); PAGE_FLAGS=(--single-run --no-cost) ;;
  --shared)  SHEET_FLAGS=(--no-recheck); HTML_FLAGS=(--no-recheck --no-cost); PAGE_FLAGS=(--single-run --no-cost) ;;
  *)         echo "unknown mode $MODE (use --no-cost or --shared)"; exit 1 ;;
esac

if [ ! -f "$DIR/report.xlsx" ] || [ "$DIR/results.jsonl" -nt "$DIR/report.xlsx" ]; then
  $PY run_eval.py --run "$RUN" --report-only
fi
$PY facts_split.py --run "$RUN" --report-only | tail -1
$PY unanswered_split.py --run "$RUN" | tail -1
if [ "$MODE" = "--shared" ]; then
  $PY split_cost.py --run "$RUN" ${BUDGET:+--budget "$BUDGET"}
  $PY recalc.py "$DIR/grading_cost.xlsx"
fi
$PY recalc.py "$DIR/report.xlsx"
$PY findings_sheet.py --run "$RUN" "${SHEET_FLAGS[@]}" | sed -n 1p
$PY recalc.py "$DIR/findings_by_test_case.xlsx"
$PY report_html.py --run "$RUN" "${HTML_FLAGS[@]}"
$PY findings_page.py --run "$RUN" "${PAGE_FLAGS[@]}"
