#!/usr/bin/env bash
# Live view of an evaluation run in the terminal.
#   Collection: answers collected vs expected, answer kinds, unanswered State questions, speed, ETA, last log lines.
#   Grading:    once run_eval.py has started, the harness's own progress view (progress.py) with spend and ETA.
# Usage:  eval/monitor_run.sh [run name] [refresh seconds] [--once]
#   e.g.  eval/monitor_run.sh indexed-v2-full-20261105 15
# Stop with Ctrl+C. It only reads files; it never touches the run.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
RUN=${1:-indexed-v2-full-20261105}
EVERY=${2:-15}
ONCE=${3:-}
PY=${PY:-$HERE/../.venv/bin/python}
DIR=$HERE/runs/$RUN
export GOLDEN_WORKBOOK=${GOLDEN_WORKBOOK:-$HERE/../golden_test_cases_indexed_v2_20261105.xlsx}
[ -d "$DIR" ] || { echo "No run folder: $DIR"; exit 1; }

# Expected totals, read once from the workbook the run uses.
read -r EXP_Q EXP_S < <(cd "$HERE" && "$PY" -c \
  "from workbook import load_rows, load_scenarios; print(len(load_rows()), len(load_scenarios()))" 2>/dev/null || echo "? ?")

collection_stats() {
  "$PY" - "$DIR" "$EXP_Q" "$EXP_S" <<'PYEOF'
import json, sys, statistics
from collections import Counter
from datetime import datetime
d, exp_q, exp_s = sys.argv[1], sys.argv[2], sys.argv[3]
def rows(name):
    try:
        return [json.loads(l) for l in open(f"{d}/{name}", encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        return []
rs, cs = rows("responses.jsonl"), rows("conversations.jsonl")
n = len(rs)
kinds = Counter(r.get("kind") or ("error" if r.get("error") else "none") for r in rs)
errors = sum(1 for r in rs if r.get("error"))
state_q = [r["id"] for r in rs if r.get("kind") == "clarify"
           and any("state" in str(f.get("type", "")) + str(f.get("key", "")) for f in (r.get("clarify") or {}).get("fields") or [])]
lat = [r["latency_s"] for r in rs if isinstance(r.get("latency_s"), (int, float))]
def bar(done, total, width=40):
    try:
        f = min(1.0, done / int(total))
    except (ValueError, ZeroDivisionError):
        return ""
    return "[" + "#" * int(f * width) + "-" * (width - int(f * width)) + f"] {100 * f:5.1f}%"
print(f"Queries        {n:4d} / {exp_q:<4} {bar(n, exp_q)}")
turns = sum(len(c.get('turns', [])) for c in cs)
print(f"Conversations  {len(cs):4d} / {exp_s:<4} {bar(len(cs), exp_s)}   ({turns} turns)")
if n:
    print("Answer kinds   " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()) + (f"   | errors {errors}" if errors else ""))
    if lat:
        print(f"Latency        median {statistics.median(lat):.1f} s, p95 {sorted(lat)[int(0.95 * (len(lat) - 1))]:.1f} s, max {max(lat):.1f} s")
    ts = sorted(datetime.fromisoformat(r["collected_at"].replace("Z", "+00:00")) for r in rs if r.get("collected_at"))
    if len(ts) >= 2:
        span = (ts[-1] - ts[0]).total_seconds()
        rate = (len(ts) - 1) / span if span > 0 else 0
        left = int(exp_q) - n if exp_q.isdigit() else 0
        eta = f"{left / rate / 60:.0f} min left" if rate and left > 0 else ("done" if left <= 0 else "?")
        print(f"Speed          {rate * 60:.1f} answers/min   ETA {eta}   (last answer {ts[-1].astimezone():%H:%M:%S})")
    if state_q:
        print(f"State asked    {len(state_q)} unanswered 'which State?' replies: {', '.join(state_q[:12])}{' ...' if len(state_q) > 12 else ''}")
    print(f"Last IDs       {', '.join(r['id'] for r in rs[-6:])}")
PYEOF
}

while true; do
  [ -z "$ONCE" ] && clear
  echo "Run: $RUN   ($(date '+%d %b %Y %H:%M:%S'))   refresh every ${EVERY}s, Ctrl+C to stop"
  echo "Workbook: $(basename "$GOLDEN_WORKBOOK")"
  echo
  # count only processes whose program is python (shell wrappers also carry the command line)
  count_py() { pgrep -af "$1 --run $RUN( |\$)" 2>/dev/null | awk '$2 ~ /python[0-9.]*$/' | wc -l; }
  collectors=$(count_py collect.py)
  graders=$(count_py run_eval.py)
  echo "Processes      collect.py: ${collectors:-0} running   run_eval.py: ${graders:-0} running"
  echo
  echo "== Collection =="
  collection_stats
  for log in "$DIR"/collect_queries.log "$DIR"/collect_scenarios.log; do
    [ -f "$log" ] && { echo "-- $(basename "$log"):"; tail -n 3 "$log" | cut -c1-150; }
  done
  if [ -f "$DIR/progress.jsonl" ]; then
    echo
    echo "== Grading (progress.py) =="
    (cd "$HERE" && "$PY" progress.py --run "$RUN" 2>&1 | tail -n 40)
    if tail -n 1 "$DIR/progress.jsonl" 2>/dev/null | grep -q '"stage": *"done"'; then
      echo
      echo "Grading finished. Report: $DIR/report.xlsx"
      break
    fi
  fi
  [ -n "$ONCE" ] && break
  sleep "$EVERY"
done
