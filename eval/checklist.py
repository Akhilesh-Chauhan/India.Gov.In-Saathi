"""Checklist grading: how much of each golden answer the bot's answer covers, and the PASS / PARTIAL PASS / FAIL status.

Each question gets a checklist built from its golden answer: the key facts a correct answer must give, plus the
required behaviours (the golden's own instructions, replying in the user's language, ending with an official link or
next step). A grader marks every item met / missing / wrong, following checklist_grader.md.

  python checklist.py export --run day1 [--batches 8]   readable batches in runs/<run>/checklist/batch_NN.txt
  python checklist.py validate --run day1                checks the graders' out_NN.json files
  python checklist.py score --run day1                   writes runs/<run>/checklist.jsonl with scores and status
  python checklist.py agreement --run day1               reviewer agreement in runs/<run>/spot_check.xlsx
                                                         (made by findings_sheet.py --spot-check; concept note 9.3.4)

Status (per question):
  FAIL          any item marked wrong (a wrong or outdated fact, or something the golden forbids), or the Freshness,
                Source genuineness or Personal data check failed - whatever the percentages
  PASS          at least 85% of the checklist met
  PARTIAL PASS  at least 60% of the key facts present and correct (questions with no facts to give, such as
                declines, use their behaviour items instead)
  FAIL          otherwise
Multi-turn conversations use the share of turns that passed the Conversation flow check for both percentages.
"""
import argparse
import json
import random
import re
import textwrap
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

import config
from run_eval import _read_jsonl
from workbook import load_rows

PASS_AT, PARTIAL_AT = 0.85, 0.60
SAFETY_CHECKS = ["Freshness", "Source genuineness", "Personal data not echoed"]  # a FAIL here makes the answer FAIL
STATUSES = ("met", "missing", "wrong")


def wrap(t, width=300):
    out = []
    for para in str(t or "").splitlines() or [""]:
        out += textwrap.wrap(para, width, break_long_words=True, break_on_hyphens=False) or [""]
    return "\n".join(out)


def status_for(checklist_share, facts_share, wrong):
    if wrong:
        return "FAIL"
    if checklist_share is not None and checklist_share >= PASS_AT:
        return "PASS"
    if facts_share is not None and facts_share >= PARTIAL_AT:
        return "PARTIAL PASS"
    return "FAIL"


def _questions(run_dir):
    rows = load_rows()
    by_query = {r["Query (type exactly)"]: r["Test ID"] for r in rows.values()}
    responses = {by_query.get(r["query"], r["id"]): r for r in _read_jsonl(run_dir / "responses.jsonl")}
    return rows, responses


def export(run, batches):
    run_dir = config.RUNS_DIR / run
    out = run_dir / "checklist"
    out.mkdir(exist_ok=True)
    rows, responses = _questions(run_dir)
    ids = sorted(responses)
    size = -(-len(ids) // batches)
    for b in range(batches):
        lines = []
        for i in ids[b * size:(b + 1) * size]:
            r, rec = rows[i], responses[i]
            lines += [f"=== {i} | {r['Language']} | {r['Question type (concept note)']} | bot reply kind: {rec.get('kind')}",
                      f"QUESTION:\n{wrap(rec['query'])}",
                      f"GOLDEN ANSWER:\n{wrap(r.get('Expected behaviour / golden answer'))}",
                      f"BOT ANSWER:\n{wrap(rec.get('answer') or '(no answer)')}",
                      f"BOT CITED SOURCES: {', '.join(rec.get('sources') or []) or 'none'}", ""]
        if lines:
            body = "\n".join(lines)
            (out / f"batch_{b + 1:02d}.txt").write_text(f"TOTAL LINES: {body.count(chr(10)) + 2}\n{body}", encoding="utf-8")
            print(f"batch_{b + 1:02d}: {sum(1 for x in lines if x.startswith('=== '))} questions, {len(body):,} characters")


def _load_outputs(run_dir):
    graded, problems = {}, []
    for f in sorted((run_dir / "checklist").glob("out_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{f.name}: not valid JSON ({e})")
            continue
        for d in data:
            i, items = d.get("id"), d.get("items")
            if not isinstance(items, list) or not items:
                problems.append(f"{f.name} {i}: no items")
                continue
            bad = [x for x in items if x.get("type") not in ("fact", "behaviour") or x.get("status") not in STATUSES or not x.get("item")]
            if bad:
                problems.append(f"{f.name} {i}: {len(bad)} malformed item(s), e.g. {bad[0]}")
                continue
            graded[i] = d
    return graded, problems


def validate(run):
    run_dir = config.RUNS_DIR / run
    graded, problems = _load_outputs(run_dir)
    expected = {line[4:].split()[0] for f in (run_dir / "checklist").glob("batch_*.txt")
                for line in f.read_text(encoding="utf-8").splitlines() if line.startswith("=== ")}
    missing = sorted(expected - set(graded))
    no_lang = sorted(i for i, d in graded.items() if not any("language" in x["item"].lower() for x in d["items"]))
    print(f"{len(graded)} of {len(expected)} questions graded; {len(problems)} problems; missing: {missing[:20]}")
    for p in problems[:30]:
        print("  ", p)
    if no_lang:
        print(f"  note: {len(no_lang)} checklists have no language item, e.g. {no_lang[:8]}")


def score(run):
    run_dir = config.RUNS_DIR / run
    graded, problems = _load_outputs(run_dir)
    if problems:
        raise SystemExit(f"fix the grader outputs first ({len(problems)} problems): python checklist.py validate --run {run}")
    results = _read_jsonl(run_dir / "results.jsonl")
    res = {r["id"]: r["metrics"] for r in results if "metrics" in r}
    out = []
    for i in sorted(res):
        d = graded.get(i)
        if d is None:
            raise SystemExit(f"{i} has no checklist yet")
        items = d["items"]
        c = Counter((x["type"], x["status"]) for x in items)
        facts = [x for x in items if x["type"] == "fact"]
        basis = facts or [x for x in items if x["type"] == "behaviour"]  # declines: behaviours stand in for facts
        met_all = sum(x["status"] == "met" for x in items)
        met_basis = sum(x["status"] == "met" for x in basis)
        safety = [k for k in SAFETY_CHECKS if res[i].get(k, {}).get("verdict") == "F"]
        wrong_items = [x["item"] for x in items if x["status"] == "wrong"]
        cs, fs = met_all / len(items), (met_basis / len(basis) if basis else None)
        out.append({"id": i, "items": items, "checklist_met": met_all, "checklist_total": len(items), "checklist_share": cs,
                    "facts_met": met_basis, "facts_total": len(basis), "facts_share": fs, "facts_basis": "facts" if facts else "behaviours",
                    "wrong_items": wrong_items, "failed_safety_checks": safety, "counts": {f"{t}:{s}": n for (t, s), n in c.items()},
                    "status": status_for(cs, fs, bool(wrong_items or safety)), "note": d.get("note", "")})
    convs = {c["id"]: c for c in _read_jsonl(run_dir / "conversations.jsonl")}
    for r in results:
        if "conversation" not in r:
            continue
        v, turns = r["conversation"], len(convs.get(r["id"], {}).get("turns", [])) or 1
        failed = 0 if v["verdict"] == "P" else len(re.findall(r"Turn \d+:", v["reason"])) or turns
        share = (turns - failed) / turns
        out.append({"id": r["id"], "items": [], "checklist_met": turns - failed, "checklist_total": turns, "checklist_share": share,
                    "facts_met": turns - failed, "facts_total": turns, "facts_share": share, "facts_basis": "turns",
                    "wrong_items": [], "failed_safety_checks": [], "counts": {}, "status": status_for(share, share, False), "note": ""})
    (run_dir / "checklist.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")
    q = [x for x in out if x["id"].startswith("Q-")]
    print("questions:", dict(Counter(x["status"] for x in q)), "| conversations:", dict(Counter(x["status"] for x in out if x["id"].startswith("MT-"))))
    print(f"wrote {run_dir / 'checklist.jsonl'}")


def spot_check_ids(run_dir, per_cell=2, seed=1):
    """Stratified sample for the reviewer spot-check: per_cell questions for each grading batch and status."""
    status = {c["id"]: c["status"] for c in _read_jsonl(run_dir / "checklist.jsonl")}
    rng, ids = random.Random(seed), set()
    for f in sorted((run_dir / "checklist").glob("out_*.json")):
        batch = sorted(d["id"] for d in json.loads(f.read_text(encoding="utf-8")))
        for s in ("PASS", "PARTIAL PASS", "FAIL"):
            pool = [i for i in batch if status.get(i) == s]
            ids.update(rng.sample(pool, min(per_cell, len(pool))))
    return ids


def agreement(run, file):
    """Share of spot-checked statuses the reviewer agreed with; Unsure and blank rows are left out (target 90%)."""
    run_dir = config.RUNS_DIR / run
    rows = list(load_workbook(run_dir / file, read_only=True)["Findings"].iter_rows(values_only=True))
    h = next(n for n, r in enumerate(rows) if r and r[0] == "Test case")
    k, c = rows[h].index("Reviewer: agree with status?"), rows[h].index("Reviewer comments")
    status = {x["id"]: x["status"] for x in _read_jsonl(run_dir / "checklist.jsonl")}
    marks = [(r[0], status.get(r[0]), r[k], r[c]) for r in rows[h + 1:] if r[0]]
    n = Counter(m for _, _, m, _ in marks)
    print(f"{len(marks)} rows: {n['Agree']} agree, {n['Disagree']} disagree, {n['Unsure']} unsure, "
          f"{len(marks) - n['Agree'] - n['Disagree'] - n['Unsure']} not marked")
    for s in ("PASS", "PARTIAL PASS", "FAIL"):
        a, d = (sum(st == s and m == v for _, st, m, _ in marks) for v in ("Agree", "Disagree"))
        if a + d:
            print(f"  {s}: {a} of {a + d} agreed ({a / (a + d):.0%})")
    if n["Agree"] + n["Disagree"]:
        share = n["Agree"] / (n["Agree"] + n["Disagree"])
        print(f"agreement {share:.1%} of {n['Agree'] + n['Disagree']} decided rows: "
              f"{'meets' if share >= 0.9 else 'below'} the 90% target")
    for i, s, m, note in marks:
        if m in ("Disagree", "Unsure"):
            print(f"  {i} ({s}) {m}: {note or 'no comment'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["export", "validate", "score", "agreement"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--batches", type=int, default=8)
    ap.add_argument("--file", default="spot_check.xlsx", help="agreement: the reviewed workbook in the run folder")
    a = ap.parse_args()
    {"export": lambda: export(a.run, a.batches), "validate": lambda: validate(a.run), "score": lambda: score(a.run),
     "agreement": lambda: agreement(a.run, a.file)}[a.step]()


if __name__ == "__main__":
    main()
