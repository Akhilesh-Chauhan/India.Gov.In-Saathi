"""Live progress of a run_eval.py run, from runs/<run>/progress.jsonl and tokens.live.jsonl.

Examples:
  python progress.py --run day1             # one snapshot
  python progress.py --run day1 --watch 15  # refresh every 15 s until the run finishes (Ctrl+C to stop)
"""
import argparse
import json
import time
from collections import Counter, defaultdict

import config
from judge import price_for

JUDGED = ("Citation support", "Correctness & behaviour", "Response flow", "Freshness", "Conversation flow")
CORE = ("Citation support", "Correctness & behaviour")  # always call the judge, so they pace the cost projection


def _read(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:  # a line being written right now
            pass
    return out


def snapshot(run):
    run_dir = config.RUNS_DIR / run
    events, usage = _read(run_dir / "progress.jsonl"), _read(run_dir / "tokens.live.jsonl")
    if not events:
        return f"No progress for run '{run}' yet (progress.jsonl is written by run_eval.py once it starts).", True
    stages = [e for e in events if "stage" in e]
    planned, done, verdicts = Counter(), Counter(), defaultdict(Counter)
    for e in events:
        planned.update(e.get("planned") or {})
        if "verdict" in e:
            done[e["metric"]] += 1
            verdicts[e["metric"]][e["verdict"]] += 1
    judge_model = next((e.get("judge") for e in stages if "judge" in e), None)
    finished = stages[-1]["stage"] == "done"

    names = [m for m in planned if m in JUDGED] or list(planned)
    total, complete = sum(planned[m] for m in names), sum(done[m] for m in names)
    frac = complete / total if total else 0.0
    started = next((e["t"] for e in stages if e["stage"].startswith("judging")), None)
    now = time.time()
    lines = [f"Run {run} - {time.strftime('%H:%M:%S')}",
             f"Stage: {stages[-1]['stage']}" + (f" (judging since {time.strftime('%H:%M', time.localtime(started))})" if started else "")]
    width = 40
    lines.append(f"[{'#' * int(frac * width)}{'-' * (width - int(frac * width))}] {frac * 100:5.1f}%  "
                 f"{complete:,} / {total:,} judged checks")
    lines.append("")
    lines.append(f"{'Check':26s} {'done':>11s}   {'P':>4s} {'F':>4s} {'NA':>4s} {'ERR':>4s}")
    for m in sorted(planned, key=lambda x: (x not in JUDGED, x)):
        v = verdicts[m]
        lines.append(f"{m:26s} {done[m]:>5,}/{planned[m]:<5,}   {v['P']:>4} {v['F']:>4} {v['NA']:>4} {v['ERROR']:>4}")
    if usage:
        pin, pout = price_for(judge_model or config.JUDGE_MODEL)
        tin, tout = sum(u["input_tokens"] for u in usage), sum(u["output_tokens"] for u in usage)
        spent = tin / 1e6 * pin + tout / 1e6 * pout if pin is not None else None
        core = sum(done[m] for m in CORE) / max(1, sum(planned[m] for m in CORE))
        lines.append("")
        lines.append(f"Judge calls {len(usage):,} | {tin:,} input / {tout:,} output tokens"
                     + (f" | USD {spent:.2f} so far" if spent is not None else " | price unknown"))
        if spent is not None and 0.02 < core < 1 and not finished:
            lines.append(f"Projected total ~USD {spent / core:.0f} (from the share of citation and correctness checks done)")
    errors = sum(v["ERROR"] for v in verdicts.values())
    if errors:
        lines.append(f"Errors so far: {errors} (reasons go into the report; re-run those IDs with --ids)")
    if finished:
        lines.append(f"Finished. Report: {run_dir / 'report.xlsx'}")
    elif started and 0.02 < frac < 1:
        eta = (now - started) / frac * (1 - frac)
        lines.append(f"ETA ~{eta / 60:.0f} min (about {time.strftime('%H:%M', time.localtime(now + eta))})")
    return "\n".join(lines), finished


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--watch", type=int, metavar="SECONDS", help="refresh until the run finishes")
    a = ap.parse_args()
    while True:
        text, finished = snapshot(a.run)
        if a.watch:
            print("\033[2J\033[H", end="")  # clear the terminal
        print(text, flush=True)
        if not a.watch or finished:
            break
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
