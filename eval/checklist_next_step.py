"""Re-mark the checklist item 'ends with an official link or next step' with one rule across all grader batches.

Use when graders read that item differently (compare its met rate per batch). Reviewers follow
runs/<run>/checklist/next_step_review.md (copy it from a previous run) and write next_step_out_1.json / _2.json.
  python checklist_next_step.py export --run day1   review files next_step_1.txt / _2.txt (answered replies only)
  python checklist_next_step.py apply --run day1    write the reviewers' marks into out_NN.json; log next_step_changes.json
Then: python checklist.py score --run day1
"""
import argparse
import json
import re
import textwrap

import config

D = C = None  # run folder and its checklist folder, set in main()
ITEM = re.compile(r"official link|next step", re.I)


def wrap(t, width=300):
    out = []
    for para in str(t or "").splitlines() or [""]:
        out += textwrap.wrap(para, width, break_long_words=True, break_on_hyphens=False) or [""]
    return "\n".join(out)


def targets():
    resp = {json.loads(l)["id"]: json.loads(l) for l in (D / "responses.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    out = []
    for f in sorted(C.glob("out_*.json")):
        for d in json.loads(f.read_text(encoding="utf-8")):
            if resp[d["id"]].get("kind") == "no_answer":
                continue  # generic 'could not find' replies were marked by one shared rule already
            for k, x in enumerate(d["items"]):
                if x["type"] == "behaviour" and ITEM.search(x["item"]):
                    out.append((f.name, d["id"], k, x, resp[d["id"]].get("answer") or ""))
    return out


def export():
    t = targets()
    half = -(-len(t) // 2)
    for n, part in enumerate((t[:half], t[half:]), 1):
        lines = []
        for _, i, _, x, ans in part:
            lines += [f"=== {i} | item: {x['item']} | current: {x['status']}", "REPLY:", wrap(ans), ""]
        body = "\n".join(lines)
        (C / f"next_step_{n}.txt").write_text(f"TOTAL LINES: {body.count(chr(10)) + 2}\n{body}", encoding="utf-8")
        print(f"next_step_{n}.txt: {len(part)} items, {len(body):,} characters")


def apply():
    decisions = {}
    for n in (1, 2):
        for d in json.loads((C / f"next_step_out_{n}.json").read_text(encoding="utf-8")):
            decisions[d["id"]] = d
    t = targets()
    missing = [i for _, i, _, _, _ in t if i not in decisions]
    assert not missing, f"no review decision for {missing[:10]}"
    files, log = {}, []
    for fname, i, k, x, _ in t:
        data = files.setdefault(fname, json.loads((C / fname).read_text(encoding="utf-8")))
        entry = next(e for e in data if e["id"] == i)
        new = decisions[i]["status"]
        if entry["items"][k]["status"] != new:
            log.append({"id": i, "batch": fname, "from": entry["items"][k]["status"], "to": new, "why": decisions[i].get("why", "")})
            entry["items"][k]["status"] = new
    for fname, data in files.items():
        (C / fname).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (C / "next_step_changes.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"{len(t)} items reviewed; {len(log)} changed:", dict(Counter((c["batch"], c["from"], c["to"]) for c in log)))


def main():
    global D, C
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["export", "apply"])
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    D = config.RUNS_DIR / a.run
    C = D / "checklist"
    {"export": export, "apply": apply}[a.step]()


if __name__ == "__main__":
    main()
