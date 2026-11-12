"""Re-derive a graded run's results.jsonl from its saved layers, without new judge calls, keeping every earlier grade.

  python apply_overrides.py --run RUN

Layers, applied in this order on top of the judge's grades of the full run (results.judge-original.jsonl; copied from
results.jsonl the first time):
  1. results.rejudge.jsonl   later re-grades of some checks (run_eval.py --metrics ... --merge); the newest grade wins
  2. fixed-reply rule        the bot's fixed guardrail replies (answer kind "blocked"): Figures on cited pages and
                             Citation support become NA, Source genuineness NA when no link is shown (owner, 6 Nov 2026);
                             Response flow NA, even over a re-grade (same ruling, applied 9 Nov 2026)
  3. rule re-scoring         Source genuineness and Source recall recomputed with the current rules in metrics.py from
                             the saved answers and cached page fetches (nothing is fetched); Conversation flow given its
                             turn score (turns passed / turns) from the saved reason, which names each failing turn
  4. verdict_overrides.json  grades set by a person: [{"id", "metric", "verdict", "reason", "guardrails"?, "score"?}];
                             skipped for a check that was re-graded later (layer 1), since the re-grade used the
                             corrected golden answer
  5. recall credit           Source recall in full when the answer got the facts right from other official pages it
                             cited (scoring.credit_recall; QE decision 6 Nov 2026; uses facts_split.jsonl for answers
                             graded pass/fail only)
Each changed check keeps the grade it replaced under "original". Run from the command line, it also rebuilds
report.xlsx; then run ./build_reports.sh RUN for the other report files. --fixed-reply-rule and --regrade-genuineness
are accepted for older notes; every layer always applies.
"""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from types import SimpleNamespace

import config
from metrics import FIXED_REPLY, FIXED_REPLY_FLOW, SourceGenuineness, SourceRecall, conversation_score
from scoring import SCORE_PASS, credit_recall


def _jl(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def _cached(u):
    p = config.CACHE_DIR / (hashlib.sha1(u.encode()).hexdigest() + ".json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"status": None, "final": "", "text": "", "error": "not fetched"}


def derive(run_dir, verbose=True):
    from pages import index_domains, ingested_domains
    from workbook import load_evidence, load_rows
    orig = run_dir / "results.judge-original.jsonl"
    if not orig.exists():
        shutil.copy2(run_dir / "results.jsonl", orig)
    records = _jl(orig)  # always start from the judge's grades of the full run
    resp = {r["id"]: r for r in _jl(run_dir / "responses.jsonl")}
    convs = {c["id"]: c for c in _jl(run_dir / "conversations.jsonl")}
    changed = []

    def setv(rec, metric, new, layer):
        """new = {"verdict", "score", "reason", "guardrails", ...}; keeps the replaced grade under "original"."""
        box = rec["metrics"] if metric != "Conversation flow" or "metrics" in rec else None
        old = box.get(metric) if box is not None else rec.get("conversation")
        if old is None and layer != "re-graded":
            return
        keys = ("verdict", "score", "reason")
        if old is not None and all(old.get(k) == new.get(k) for k in keys):
            return
        new = {**new, "guardrails": new.get("guardrails") or [], "layer": layer}
        if old is not None:
            new["original"] = old.get("original") or {k: old.get(k) for k in ("verdict", "score", "reason", "guardrails")}
        if box is not None:
            box[metric] = new
        else:
            rec["conversation"] = new
        changed.append((rec["id"], metric, (old or {}).get("verdict"), new["verdict"], layer))

    by_id = {(r["id"], "conversation" in r): r for r in records}
    # 1. later re-grades
    rejudged = set()
    for r in _jl(run_dir / "results.rejudge.jsonl"):
        conv = "conversation" in r
        rec = by_id.get((r["id"], conv))
        if rec is None:
            rec = {"id": r["id"], **({"conversation": None} if conv else {"metrics": {}})}
            records.append(rec)
            by_id[(r["id"], conv)] = rec
        items = [("Conversation flow", r["conversation"])] if conv else list(r["metrics"].items())
        for metric, new in items:
            setv(rec, metric, new, "re-graded")
            rejudged.add((r["id"], metric))
    # 2. fixed-reply rule
    for rec in records:
        if "metrics" not in rec or resp.get(rec["id"], {}).get("kind") != "blocked":
            continue
        na = {"verdict": "NA", "score": None, "reason": FIXED_REPLY}
        for metric in ("Figures on cited pages", "Citation support"):
            if (rec["id"], metric) not in rejudged:
                setv(rec, metric, na, "fixed-reply rule")
        if not resp[rec["id"]].get("sources"):
            setv(rec, "Source genuineness", {**na, "reason": FIXED_REPLY + "; no links needed"}, "fixed-reply rule")
        rf = rec["metrics"].get("Response flow")
        if rf and rf.get("verdict") not in ("NA", "ERROR"):  # also over a re-grade: the flow never applies to a fixed reply
            setv(rec, "Response flow", {**na, "reason": FIXED_REPLY_FLOW}, "fixed-reply rule")
    # 3. rule re-scoring from saved data
    rows, ingested, evidence, indexed = load_rows(), ingested_domains(), load_evidence(), index_domains()
    by_query = {r["Query (type exactly)"]: r for r in rows.values()}
    for rec in records:
        if "metrics" not in rec:
            continue
        r = resp.get(rec["id"], {})
        row = by_query.get(r.get("query")) or rows.get(rec["id"])
        md = {"row": row, "sources": r.get("sources") or [], "answer": r.get("answer") or "", "kind": r.get("kind"),
              "pages": {u: _cached(u) for u in r.get("sources") or []}, "evidence": evidence.get(row["Test ID"]),
              "checked_urls": [pg.get("url") for s in r.get("sources_checked") or [] for pg in s.get("pages", [])]}
        case = SimpleNamespace(metadata=md, input=r.get("query"))
        for metric in (SourceGenuineness(ingested, indexed), SourceRecall()):
            if metric.name not in rec["metrics"]:
                continue
            metric.measure(case)
            v = "NA" if metric.score is None else ("P" if metric.success else "F")
            setv(rec, metric.name, {"verdict": v, "score": metric.score, "reason": metric.reason,
                                    "guardrails": list(metric.violated or [])}, "re-scored by rule")
    for rec in records:
        c = rec.get("conversation")
        if not c or c.get("score") is not None or c.get("verdict") not in ("P", "F"):
            continue
        turns = len(convs.get(rec["id"], {}).get("turns") or [])
        score = conversation_score(c["verdict"], c.get("reason"), turns)
        if score is None:
            continue
        reason = c.get("reason") or ""
        if c["verdict"] == "F":
            reason = f"{round(score * turns)} of {turns} turns passed | {reason}"
        setv(rec, "Conversation flow", {"verdict": "P" if score >= SCORE_PASS else "F", "score": score, "reason": reason,
                                        "guardrails": c.get("guardrails") if score < 1 else []}, "turn score from saved reason")
    # 4. grades set by a person
    path = run_dir / "verdict_overrides.json"
    for o in json.loads(path.read_text(encoding="utf-8")) if path.exists() else []:
        if (o["id"], o["metric"]) in rejudged:
            if verbose:
                print(f"  override of {o['id']} {o['metric']} skipped: re-graded since (see results.rejudge.jsonl)")
            continue
        rec = by_id.get((o["id"], o["metric"] == "Conversation flow" and o["id"].startswith("MT-")))
        if rec:
            setv(rec, o["metric"], {"verdict": o["verdict"], "score": o.get("score"), "reason": o["reason"],
                                    "guardrails": o.get("guardrails")}, "set by a person")
    # 5. Source recall credited when the facts came right from other official pages
    split = {r["id"]: r for r in _jl(run_dir / "facts_split.jsonl")}
    for rec in records:
        credited = credit_recall(rec.get("metrics"), split.get(rec["id"]))
        if credited:
            setv(rec, "Source recall", credited, "recall credit")
    (run_dir / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    if verbose:
        print(f"results.jsonl re-derived from {orig.name}: {len(changed)} grades differ from the judge's original")
        for (layer, metric, a, b), n in sorted(Counter((c[4], c[1], c[2], c[3]) for c in changed).items()):
            print(f"  {layer:30} {metric:26} {a} -> {b}: {n}")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--fixed-reply-rule", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--regrade-genuineness", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    derive(config.RUNS_DIR / a.run)
    from run_eval import report_only
    report_only(config.RUNS_DIR / a.run)  # report.xlsx follows the re-derived results
    print(f"Next: ./build_reports.sh {a.run} (analysis sheets, findings workbook, HTML pages)")


if __name__ == "__main__":
    main()
