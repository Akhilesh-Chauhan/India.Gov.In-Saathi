"""Re-check a judged run: ask every question again, re-grade only the answers whose content changed, and merge.

Folders (under eval/runs), for a baseline run BASE and a new run NEW:
  NEW-P0, NEW-P1, ...   new answers, collected in parallel shards:  collect.py --run NEW-P0 --priority P0
  NEW-conv              new conversations:                           collect.py --run NEW-conv --scenarios
  NEW/recheck/          working files: pairs.json, plan.json, compare/batch_NN.txt (+ reviewers' out_NN.json)
  NEW-regrade-a, -b...  changed answers, graded with run_eval.py and facts_split.py like any run
  NEW                   the merged run: unchanged answers keep BASE's answer and grades, changed ones get the new ones

Steps:
  python recheck.py prepare --base BASE --new NEW   pair new with old answers; queue side-by-side comparisons
  python recheck.py retry --new NEW                 set aside bot errors and print the collect.py commands to re-ask them
  python recheck.py plan --new NEW                  combine automatic decisions with reviewers' decisions
  python recheck.py stage --base BASE --new NEW --wave a [--no-conversations]
                                                    write NEW-regrade-a with the changed answers not yet staged
  python recheck.py build --base BASE --new NEW     merge into NEW and write report.xlsx (then run build_reports.sh)

Decisions: identical answers, and a "could not find" reply (kind=no_answer) on both days, are the same. A change of
answer kind is a change. Answers given on both days are compared side by side by reviewers following
recheck_compare.md (their out_NN.json files go next to the batches); unreviewed ones count as changed.
Multi-turn conversations are re-graded whenever any reply differs.
"""
import argparse
import json
import re
import textwrap
from collections import Counter
from datetime import datetime
from pathlib import Path

import config

BATCH_SIZE = 75
COMMANDS_DELAY = 2


def jl(p):
    p = Path(p)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def write_jl(path, recs):
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")


def norm(t):
    return re.sub(r"\s+", " ", str(t or "")).strip()


def wrap(t, width=300):
    out = []
    for para in str(t or "").splitlines() or [""]:
        out += textwrap.wrap(para, width, break_long_words=True, break_on_hyphens=False) or [""]
    return "\n".join(out)


def run_date(name, long=False):
    """'umang-20261016' -> '16 Oct' (or '16 Oct 2026'); the run name itself when it has no date."""
    m = re.search(r"(\d{8})$", name)
    if not m:
        return name
    d = datetime.strptime(m.group(1), "%Y%m%d")
    return f"{d.day} {d:%b}" + (f" {d.year}" if long else "")


def shard_dirs(new):
    """Question shards: every NEW-* folder holding responses.jsonl, except re-grade folders."""
    return sorted(d for d in config.RUNS_DIR.glob(f"{new}-*")
                  if (d / "responses.jsonl").exists() and "-regrade-" not in d.name and not d.name.endswith("-pilot"))


def judge_name():
    """'global.anthropic.claude-opus-5-5' -> 'Claude Opus 5.5' for labels."""
    m = re.search(r"claude-([a-z]+)-(\d+)(?:-(\d+))?", config.JUDGE_MODEL)
    return f"Claude {m.group(1).title()} {m.group(2)}" + (f".{m.group(3)}" if m.group(3) else "") if m else config.JUDGE_MODEL


def failed_turn(conv):
    return any(t.get("error") or not (t.get("answer") or "").strip() for t in conv["turns"])


def usd(us):
    from judge import price_for
    pin, pout = price_for(config.JUDGE_MODEL)
    return round(sum(u["input_tokens"] for u in us) / 1e6 * pin + sum(u["output_tokens"] for u in us) / 1e6 * pout, 2)


# --------------------------------------------------------------------------------------------------- prepare
def prepare(base, new):
    OLD, NEW = config.RUNS_DIR / base, config.RUNS_DIR / new
    work = NEW / "recheck"
    (work / "compare").mkdir(parents=True, exist_ok=True)
    b_up, n_up = run_date(base).upper(), run_date(new).upper()
    collected = {}
    for d in shard_dirs(new):
        for r in jl(d / "responses.jsonl"):
            collected[r["id"]] = r
    write_jl(NEW / "collected.jsonl", [collected[i] for i in sorted(collected)])
    old = {r["id"]: r for r in jl(OLD / "responses.jsonl")}

    pairs, cmp = {}, []
    for i in sorted(old):
        o, n = old[i], collected.get(i)
        if n is None:
            pairs[i] = {"decision": "missing"}
            continue
        assert o["query"] == n["query"], f"{i}: the question text differs between the runs"
        if n.get("error"):
            pairs[i] = {"decision": "error", "error": n["error"]}
            continue
        ok, nk = o.get("kind"), n.get("kind")
        if norm(o["answer"]) == norm(n["answer"]) and o["sources"] == n["sources"]:
            d = "same"
        elif ok == "no_answer" and nk == "no_answer":  # a different list of suggested websites on a decline is no change
            d = "same"
        elif ok != nk:
            d = "changed"
        else:
            d = "compare"
            cmp.append(i)
        pairs[i] = {"decision": d, "old_kind": ok, "new_kind": nk}

    oc = {c["id"]: c for c in jl(OLD / "conversations.jsonl")}
    nc = {c["id"]: c for c in jl(config.RUNS_DIR / f"{new}-conv" / "conversations.jsonl")}
    for cid in sorted(oc):
        if cid not in nc:
            pairs[cid] = {"decision": "missing"}
        elif failed_turn(nc[cid]):
            pairs[cid] = {"decision": "error"}  # re-collect before grading
        else:
            same = [norm(t["answer"]) for t in oc[cid]["turns"]] == [norm(t["answer"]) for t in nc[cid]["turns"]]
            pairs[cid] = {"decision": "same" if same else "changed"}
    (work / "pairs.json").write_text(json.dumps(pairs, indent=1), encoding="utf-8")

    outdir = work / "compare"
    queued = {line[4:].split()[0] for f in outdir.glob("batch_*.txt")
              for line in f.read_text(encoding="utf-8").splitlines() if line.startswith("=== ")}
    items = [i for i in cmp if i not in queued]  # incremental: earlier batches stay as they are
    first = len(list(outdir.glob("batch_*.txt")))
    for b in range(0, len(items), BATCH_SIZE):
        lines = []
        for i in items[b:b + BATCH_SIZE]:
            o, n = old[i], collected[i]
            lines += [f"=== {i}", f"QUESTION: {wrap(o['query'])}",
                      f"{b_up} ANSWER (kind={o.get('kind')}; sources: {', '.join(o['sources']) or 'none'}):\n{wrap(o['answer'])}",
                      f"{n_up} ANSWER (kind={n.get('kind')}; sources: {', '.join(n['sources']) or 'none'}):\n{wrap(n['answer'])}", ""]
        body = "\n".join(lines)
        (outdir / f"batch_{first + b // BATCH_SIZE + 1:02d}.txt").write_text(
            f"TOTAL LINES: {body.count(chr(10)) + 2}\n" + body, encoding="utf-8")
    print("questions:", dict(Counter(p["decision"] for k, p in pairs.items() if k.startswith("Q-"))))
    print("conversations:", dict(Counter(p["decision"] for k, p in pairs.items() if k.startswith("MT-"))))
    print("answer kind changes:", dict(Counter((p["old_kind"], p["new_kind"]) for k, p in pairs.items()
                                               if k.startswith("Q-") and p["decision"] == "changed")))
    print(f"{len(items)} answers queued for side-by-side review in {outdir} (instructions: recheck_compare.md)")


# --------------------------------------------------------------------------------------------------- retry
def _split_errors(path, is_bad, keep):
    good, bad = [], []
    for x in Path(path).read_text(encoding="utf-8").splitlines():
        if x.strip():
            (bad if is_bad(json.loads(x)) else good).append(x)
    if bad:
        with Path(keep).open("a", encoding="utf-8") as f:
            f.write("\n".join(bad) + "\n")
        Path(path).write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")
    return [json.loads(x)["id"] for x in bad]


def retry(new):
    cmds = []
    for d in shard_dirs(new):
        ids = _split_errors(d / "responses.jsonl", lambda r: bool(r.get("error")), d / "errors_first_attempt.jsonl")
        print(f"{d.name}: re-ask {ids}")
        if ids:
            cmds.append(f"../.venv/bin/python -u collect.py --run {d.name} --ids {','.join(ids)} --delay {COMMANDS_DELAY}")
    conv = config.RUNS_DIR / f"{new}-conv"
    if (conv / "conversations.jsonl").exists():
        ids = _split_errors(conv / "conversations.jsonl", failed_turn, conv / "errors_first_attempt.jsonl")
        print(f"{conv.name}: re-ask {ids}")
        if ids:
            cmds.append(f"../.venv/bin/python -u collect.py --run {conv.name} --scenarios --delay {COMMANDS_DELAY}")
    print("\n".join(cmds) if cmds else "nothing to re-ask")


# --------------------------------------------------------------------------------------------------- plan
def plan(new, base_date, new_date):
    work = config.RUNS_DIR / new / "recheck"
    pairs = json.loads((work / "pairs.json").read_text())
    reviewed = {d["id"]: d for f in sorted((work / "compare").glob("out_*.json")) for d in json.loads(f.read_text(encoding="utf-8"))}
    decisions, notes, unreviewed = {}, {}, []
    for i, p in pairs.items():
        d = p["decision"]
        if d == "compare":
            if i in reviewed:
                d = reviewed[i]["decision"]
                notes[i] = reviewed[i].get("what_changed", "")
            else:
                d = "changed"
                notes[i] = "answer regenerated with different wording or details; re-graded"
                unreviewed.append(i)
        elif d == "changed" and i.startswith("MT-"):
            notes[i] = f"conversation replies differ from {base_date}; re-graded"
        elif d == "changed":
            notes[i] = f"answer type changed from '{p['old_kind']}' to '{p['new_kind']}'"
        elif d in ("error", "missing"):
            notes[i] = f"bot returned an error on {new_date}; {base_date} answer kept"
            d = "same"
        decisions[i] = d
    out = {"decisions": decisions, "notes": notes,
           "regrade_questions": sorted(i for i, d in decisions.items() if d == "changed" and i.startswith("Q-")),
           "regrade_conversations": sorted(i for i, d in decisions.items() if d == "changed" and i.startswith("MT-")),
           "pending": sorted(unreviewed)}
    (work / "plan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("questions:", dict(Counter(d for i, d in decisions.items() if i.startswith("Q-"))),
          "| conversations:", dict(Counter(d for i, d in decisions.items() if i.startswith("MT-"))),
          "| re-graded without side-by-side review:", len(unreviewed))


# --------------------------------------------------------------------------------------------------- stage
def regrade_dirs(new):
    return sorted(config.RUNS_DIR.glob(f"{new}-regrade-*"))


def stage(base, new, wave, conversations=True):
    OLD, NEW = config.RUNS_DIR / base, config.RUNS_DIR / new
    p = json.loads((NEW / "recheck" / "plan.json").read_text())
    collected = {r["id"]: r for r in jl(NEW / "collected.jsonl")}
    done = {r["id"] for d in regrade_dirs(new) for name in ("responses.jsonl", "conversations.jsonl") for r in jl(d / name)}
    reg = config.RUNS_DIR / f"{new}-regrade-{wave}"
    reg.mkdir(exist_ok=False)
    qs = [i for i in p["regrade_questions"] if i not in done]
    write_jl(reg / "responses.jsonl", [collected[i] for i in qs])
    convs = [c for c in jl(config.RUNS_DIR / f"{new}-conv" / "conversations.jsonl")
             if c["id"] in p["regrade_conversations"] and c["id"] not in done] if conversations else []
    write_jl(reg / "conversations.jsonl", convs)
    from judge import price_for
    pin, pout = price_for(config.JUDGE_MODEL)
    est = Counter()
    for u in jl(OLD / "tokens.jsonl"):
        est[u["row"]] += u["input_tokens"] / 1e6 * pin + u["output_tokens"] / 1e6 * pout
    guess = sum(est[i] for i in qs + [c["id"] for c in convs])
    print(f"staged {len(qs)} questions and {len(convs)} conversations in {reg.name}; cost estimate from the same "
          f"questions in {base}: ~USD {guess:.0f}. Next: run_eval.py --run {reg.name}, then facts_split.py --run {reg.name}")


# --------------------------------------------------------------------------------------------------- build
def build(base, new):
    from run_eval import write_report
    from workbook import load_rows
    OLD, NEW = config.RUNS_DIR / base, config.RUNS_DIR / new
    b_short, n_short = run_date(base), run_date(new)
    p = json.loads((NEW / "recheck" / "plan.json").read_text())
    rows = load_rows()
    by_query = {r["Query (type exactly)"]: r["Test ID"] for r in rows.values()}
    old_resp = {by_query[r["query"]]: r for r in jl(OLD / "responses.jsonl")}
    collected = {r["id"]: r for r in jl(NEW / "collected.jsonl")}
    regs = regrade_dirs(new)
    reg_resp = {by_query[r["query"]]: r for d in regs for r in jl(d / "responses.jsonl")}
    old_res = {r["id"]: r for r in jl(OLD / "results.jsonl")}
    reg_res = {r["id"]: r for d in regs for r in jl(d / "results.jsonl")}
    regrade_q, regrade_c = set(p["regrade_questions"]), set(p["regrade_conversations"])
    missing = (regrade_q | regrade_c) - set(reg_res)
    assert not missing, f"not graded yet in any {new}-regrade-* folder: {sorted(missing)[:10]}"
    by_old = f"Bedrock judge ({judge_name()}), on the {b_short} answer"
    by_new = f"Bedrock judge ({judge_name()}), on the {n_short} answer"

    responses, results = [], {}
    for i in sorted(old_resp):
        note = p["notes"].get(i, "")
        if i in regrade_q:
            rec = dict(reg_resp[i], id=i, recheck={"decision": "changed", "answer_from": n_short, "note": note})
            results[i] = reg_res[i]["metrics"]
        else:
            rec = dict(old_resp[i], id=i, recheck={"decision": "same", "answer_from": b_short, "note": note})
            n = collected.get(i)
            if n and not n.get("error"):  # response time describes the bot as it is now, so it comes from the re-check
                rec["latency_baseline"], rec["latency_s"], rec["first_token_s"] = rec.get("latency_s"), n.get("latency_s"), n.get("first_token_s")
                rec["recheck"]["latency_from"] = n_short
            results[i] = old_res[i]["metrics"]
        responses.append(rec)

    old_convs = {c["id"]: c for c in jl(OLD / "conversations.jsonl")}
    reg_convs = {c["id"]: c for d in regs for c in jl(d / "conversations.jsonl")}
    convs, conv_results = [], {}
    for cid in sorted(old_convs):
        changed = cid in regrade_c
        src = reg_convs[cid] if changed else old_convs[cid]
        convs.append(dict(src, recheck={"decision": "changed" if changed else "same", "answer_from": n_short if changed else b_short,
                                        "note": p["notes"].get(cid, "")}))
        o = (reg_res if changed else old_res)[cid]["conversation"]
        conv_results[cid] = ("Conversation flow", o["verdict"], o["reason"], o["guardrails"])

    regraded = regrade_q | regrade_c
    write_jl(NEW / "responses.jsonl", responses)
    write_jl(NEW / "conversations.jsonl", convs)
    write_jl(NEW / "results.jsonl",
             [{"id": i, "metrics": m, "graded_by": by_new if i in regrade_q else by_old} for i, m in results.items()] +
             [{"id": c, "conversation": {"verdict": v, "reason": r, "guardrails": g}, "graded_by": by_new if c in regrade_c else by_old}
              for c, (_, v, r, g) in conv_results.items()])
    write_jl(NEW / "facts_split.jsonl", sorted([s for s in jl(OLD / "facts_split.jsonl") if s["id"] not in regraded]
                                               + [s for d in regs for s in jl(d / "facts_split.jsonl")], key=lambda s: s["id"]))
    reg_tokens = [u for d in regs for u in jl(d / "tokens.jsonl")]
    reg_facts_tokens = [u for d in regs for u in jl(d / "facts_split_tokens.jsonl")]
    usage = [u for u in jl(OLD / "tokens.jsonl") if u["row"] not in regraded] + reg_tokens  # behind the grades in this report
    write_jl(NEW / "tokens.jsonl", usage)
    write_jl(NEW / "facts_split_tokens.jsonl", [u for u in jl(OLD / "facts_split_tokens.jsonl") if u["row"] not in regraded] + reg_facts_tokens)
    pilot = config.RUNS_DIR / f"{base}-pilot"
    pq, pc = len(jl(pilot / "responses.jsonl")), len(jl(pilot / "conversations.jsonl"))
    spend = [[f"Pilot ({pq} questions, {pc} conversations)", len(jl(pilot / "tokens.jsonl")), usd(jl(pilot / "tokens.jsonl"))],
             [f"Judged run on the {b_short} answers", len(jl(OLD / "tokens.jsonl")), usd(jl(OLD / "tokens.jsonl"))],
             [f"Facts vs guardrails pass on the {b_short} answers", len(jl(OLD / "facts_split_tokens.jsonl")), usd(jl(OLD / "facts_split_tokens.jsonl"))],
             [f"Re-grade of answers that changed on {n_short}", len(reg_tokens), usd(reg_tokens)],
             ["Facts vs guardrails pass on the changed answers", len(reg_facts_tokens), usd(reg_facts_tokens)]]
    (NEW / "regrade.json").write_text(json.dumps({
        "baseline_run": base, "baseline_collected": run_date(base, True), "rechecked": run_date(new, True),
        "grader": f"the same Bedrock judge ({judge_name()})",
        "questions_regraded": sorted(regrade_q), "conversations_regraded": sorted(regrade_c),
        "decisions": p["decisions"], "notes": p["notes"], "spend": [s for s in spend if s[1]]}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(NEW / "report.xlsx", responses, rows, results, conv_results, convs, usage, config.JUDGE_MODEL)
    print(f"built {new}: {len(responses)} questions ({len(regrade_q)} re-graded), {len(convs)} conversations "
          f"({len(regrade_c)} re-graded). Next: ./build_reports.sh {new}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["prepare", "retry", "plan", "stage", "build"])
    ap.add_argument("--base", help="baseline run, e.g. umang-20261016")
    ap.add_argument("--new", required=True, help="new run, e.g. umang-20261019")
    ap.add_argument("--wave", help="stage: re-grade folder suffix (a, b, ...)")
    ap.add_argument("--no-conversations", action="store_true", help="stage: leave conversations for a later wave")
    a = ap.parse_args()
    if a.step in ("prepare", "stage", "build", "plan") and not a.base:
        ap.error(f"{a.step} needs --base")
    if a.step == "prepare":
        prepare(a.base, a.new)
    elif a.step == "retry":
        retry(a.new)
    elif a.step == "plan":
        plan(a.new, run_date(a.base), run_date(a.new))
    elif a.step == "stage":
        if not a.wave:
            ap.error("stage needs --wave")
        stage(a.base, a.new, a.wave, conversations=not a.no_conversations)
    else:
        build(a.base, a.new)


if __name__ == "__main__":
    main()
