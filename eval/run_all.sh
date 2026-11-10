#!/usr/bin/env bash
# One command for a complete evaluation run of the Saathi bot: ask it the golden questions and conversations, grade
# every answer (rule checks and the Bedrock judge), run the second grading pass and build every report file.
#
#   ./run_all.sh RUN [filters] [--no-scenarios] [--no-cost|--shared]
#     filters (passed to collect.py): --ids Q-001,MT-12   --priority P0 P1   --category Tax   --limit 20
#   e.g. ./run_all.sh day1                                   the whole golden workbook (questions and conversations)
#        ./run_all.sh day1-p0 --priority P0 --no-scenarios   priority questions only
#        ./run_all.sh check1 --ids Q-001,Q-258,MT-12 --no-cost
#        BUDGET=200 ./run_all.sh day1 --shared               stakeholder files; grading cost goes to grading_cost.xlsx
#
# Steps: 1 ask the bot (answers already collected for RUN are kept, failed bot calls are asked once more);
#        2 grade every answer (run_eval.py), then re-grade once any check whose judge call failed;
#        3 second pass on the answers that fell short (facts_split.py; run twice so a failed judge call is retried);
#        4 report files (build_reports.sh: report.xlsx, findings_by_test_case.xlsx, the two HTML pages).
# Needs eval/.env (AWS access for the Bedrock judge), the golden workbook (config.WORKBOOK) and LibreOffice.
set -euo pipefail
RUN=${1:?usage: ./run_all.sh RUN [--ids ...|--priority ...|--category ...|--limit N] [--no-scenarios] [--no-cost|--shared]}
shift
cd "$(dirname "$0")"
PY=${PY:-../.venv/bin/python}
FILTERS=(); SCENARIOS=1; MODE=()
for arg in "$@"; do
  case "$arg" in
    --no-scenarios)      SCENARIOS=0 ;;
    --no-cost|--shared)  MODE=("$arg") ;;
    *)                   FILTERS+=("$arg") ;;
  esac
done
step() { echo; echo "== $(date '+%H:%M:%S') $*"; }

step "1/4 Asking the bot: questions"
$PY -u collect.py --run "$RUN" "${FILTERS[@]}"
$PY -u collect.py --run "$RUN" --retry-errors "${FILTERS[@]}"
if [ "$SCENARIOS" = 1 ]; then
  step "1/4 Asking the bot: multi-turn conversations"
  $PY -u collect.py --run "$RUN" --scenarios "${FILTERS[@]}"
  $PY -u collect.py --run "$RUN" --scenarios --retry-errors "${FILTERS[@]}"
fi

step "2/4 Grading every answer (rule checks and the Bedrock judge)"
$PY run_eval.py --run "$RUN"
$PY run_eval.py --run "$RUN" --retry-errors

step "3/4 Second grading pass on the answers that fell short"
$PY facts_split.py --run "$RUN"
$PY facts_split.py --run "$RUN" | sed -n 1p   # judges again only what a failed judge call left out

step "4/4 Report files"
./build_reports.sh "$RUN" "${MODE[@]}"
echo
echo "Done. Reports in eval/runs/$RUN: report.xlsx, findings_by_test_case.xlsx, saathi-detailed-report.html, saathi-findings.html"
