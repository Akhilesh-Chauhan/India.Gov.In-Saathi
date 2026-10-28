#!/usr/bin/env bash
# Rebuild the report files of a judged run (after run_eval.py and facts_split.py, or after recheck.py build):
#   report.xlsx analysis sheets, findings_by_test_case.xlsx, saathi-detailed-report.html, saathi-findings.html
#
#   ./build_reports.sh RUN                       full internal view (re-check and cost included when present)
#   BUDGET=200 ./build_reports.sh RUN --shared   files to share: presented as a single run, no tokens or cost;
#                                                grading cost goes to grading_cost.xlsx (BUDGET in USD is optional)
#
# Formulas are recalculated with LibreOffice through RECALC (default: the xlsx skill's recalc.py). Each workbook is
# recalculated as a copy outside the run folder, because a LibreOffice lock file next to the original can hang it.
set -euo pipefail
RUN=${1:?usage: ./build_reports.sh RUN [--shared]}
MODE=${2:-}
cd "$(dirname "$0")"
PY=../.venv/bin/python
RECALC=${RECALC:-$(ls -d "$HOME"/.claude/skills/synced/*/xlsx/scripts/recalc.py 2>/dev/null | head -1)}
[ -f "$RECALC" ] || { echo "Set RECALC to a LibreOffice recalculation script (recalc.py)"; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

recalc() {
  local name; name=$(basename "$1")
  cp "$1" "$TMP/$name"
  echo "$(python3 "$RECALC" "$TMP/$name" 300 | tr -d '\n ') <- $name"
  cp "$TMP/$name" "$1"
}

$PY facts_split.py --run "$RUN" --report-only | tail -1
$PY unanswered_split.py --run "$RUN" | tail -1
if [ "$MODE" = "--shared" ]; then
  $PY split_cost.py --run "$RUN" ${BUDGET:+--budget "$BUDGET"}
  recalc "runs/$RUN/grading_cost.xlsx"
  SHEET_FLAGS=(--no-recheck); HTML_FLAGS=(--no-recheck --no-cost); PAGE_FLAGS=(--single-run --no-cost)
else
  SHEET_FLAGS=(); HTML_FLAGS=(); PAGE_FLAGS=()
fi
recalc "runs/$RUN/report.xlsx"
$PY findings_sheet.py --run "$RUN" "${SHEET_FLAGS[@]}" | head -1
recalc "runs/$RUN/findings_by_test_case.xlsx"
$PY report_html.py --run "$RUN" "${HTML_FLAGS[@]}"
$PY findings_page.py --run "$RUN" "${PAGE_FLAGS[@]}"
